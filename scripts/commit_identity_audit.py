"""Audit forward-only public commit identities without exposing rejected values."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from shutil import which
from typing import Any

BASELINE_COMMIT = "969789f845ee5df38f5e518220e5e72e029803a7"
KNOWN_HISTORY_EXCEPTIONS = {
    # The platform-created v0.5.2 squash commit predates enforced metadata checks.
    "102f8dab03d5f7e079525e25c54afd0670a0972e": frozenset(
        {"author_email_not_private", "prohibited_trailer"}
    ),
}
MAINTAINER_IDENTITY = (
    "Tovellan Maintainers",
    "tovellan@users.noreply.github.com",
)
SERVICE_IDENTITIES = frozenset(
    {
        ("GitHub", "noreply@github.com"),
        (
            "github-actions[bot]",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ),
    }
)
SERVICE_ACCOUNTS = {
    ("GitHub", "noreply@github.com"): ("web-flow", 19864447),
    (
        "github-actions[bot]",
        "41898282+github-actions[bot]@users.noreply.github.com",
    ): ("github-actions[bot]", 41898282),
}
NOREPLY_EMAIL = re.compile(r"^[^@\s]+@users\.noreply\.github\.com$")
PROHIBITED_TRAILER = re.compile(
    r"^[ \t]*(?:co-authored-by|generated-by|signed-off-by)[ \t]*:",
    flags=re.IGNORECASE | re.MULTILINE,
)
WRITE_PERMISSIONS = frozenset({"admin", "maintain", "push", "write"})
ACTIONS_APP_ID = 15368
MAX_PULL_COMMITS = 100


@dataclass(frozen=True)
class CommitIdentity:
    """Identity fields needed for one commit audit."""

    sha: str
    author_name: str
    author_email: str
    committer_name: str
    committer_email: str
    author_login: str | None = None
    committer_login: str | None = None
    author_id: int | None = None
    committer_id: int | None = None
    message: str = ""
    parent_count: int = 1


@dataclass(frozen=True)
class PullRequestAudit:
    """Safe result of auditing the current head of one pull request."""

    head_sha: str
    commit_count: int
    failures: tuple[str, ...]


def _is_private_email(email: str) -> bool:
    return email == "noreply@github.com" or NOREPLY_EMAIL.fullmatch(email) is not None


def _is_maintainer(name: str, email: str) -> bool:
    return (name, email) == MAINTAINER_IDENTITY


def _is_service(name: str, email: str) -> bool:
    return (name, email) in SERVICE_IDENTITIES


def _role_values(
    commit: CommitIdentity,
    role: str,
) -> tuple[str, str, str | None, int | None]:
    if role == "author":
        return commit.author_name, commit.author_email, commit.author_login, commit.author_id
    return (
        commit.committer_name,
        commit.committer_email,
        commit.committer_login,
        commit.committer_id,
    )


def _role_syntax_violations(commit: CommitIdentity, role: str) -> list[tuple[str, str]]:
    name, email, _, _ = _role_values(commit, role)
    prefix = f"{commit.sha}: {role}"
    violations: list[tuple[str, str]] = []
    if not _is_private_email(email):
        violations.append(
            (f"{role}_email_not_private", f"{prefix} email is not privacy-preserving")
        )
    if name.endswith("[bot]") and not _is_service(name, email):
        violations.append(
            (f"{role}_service_not_allowed", f"{prefix} uses an undocumented service identity")
        )
    return violations


def _syntax_violations(commit: CommitIdentity) -> list[tuple[str, str]]:
    violations = [
        *_role_syntax_violations(commit, "author"),
        *_role_syntax_violations(commit, "committer"),
    ]
    if commit.parent_count > 1:
        violations.append(("merge_commit", f"{commit.sha}: merge commits are not allowed"))
    if PROHIBITED_TRAILER.search(commit.message):
        violations.append(
            ("prohibited_trailer", f"{commit.sha}: prohibited authorship trailer found")
        )
    return violations


def audit_commits(commits: tuple[CommitIdentity, ...]) -> list[str]:
    """Audit privacy syntax for locally available Git history."""

    failures: list[str] = []
    for commit in commits:
        violations = _syntax_violations(commit)
        expected = KNOWN_HISTORY_EXCEPTIONS.get(commit.sha)
        if expected is not None:
            if {code for code, _ in violations} != expected:
                failures.append(f"{commit.sha}: recorded history exception changed")
            continue
        failures.extend(message for _, message in violations)
    return failures


def audit_github_associations(
    commits: tuple[CommitIdentity, ...],
    permission_for: Callable[[str], str],
) -> list[str]:
    """Audit identities using GitHub's account association for each raw commit role."""

    failures = audit_commits(commits)
    for commit in commits:
        if commit.sha in KNOWN_HISTORY_EXCEPTIONS:
            continue
        author_identity = (commit.author_name, commit.author_email)
        committer_identity = (commit.committer_name, commit.committer_email)
        if (author_identity == MAINTAINER_IDENTITY) != (committer_identity == MAINTAINER_IDENTITY):
            failures.append(f"{commit.sha}: maintainer identity must own both commit roles")
        for role in ("author", "committer"):
            name, email, login, account_id = _role_values(commit, role)
            if _is_maintainer(name, email):
                continue
            prefix = f"{commit.sha}: {role}"
            service_account = SERVICE_ACCOUNTS.get((name, email))
            if service_account is not None:
                if (login, account_id) != service_account:
                    failures.append(f"{prefix} service account association is invalid")
                continue
            if login is None or account_id is None:
                failures.append(f"{prefix} is not associated with a GitHub account")
                continue
            modern_noreply = re.compile(
                rf"^[0-9]+\+{re.escape(login)}@users\.noreply\.github\.com$",
                flags=re.IGNORECASE,
            )
            legacy_noreply = f"{login}@users.noreply.github.com"
            if name != login or (
                email.casefold() != legacy_noreply.casefold()
                and modern_noreply.fullmatch(email) is None
            ):
                failures.append(f"{prefix} does not match its linked GitHub account")
            if permission_for(login) in WRITE_PERMISSIONS:
                failures.append(
                    f"{prefix} is maintainer-linked but does not use the maintainer identity"
                )
    return failures


def audit_pull_request_roles(
    commits: tuple[CommitIdentity, ...],
    *,
    pull_author_login: str,
    pull_author_id: int,
    pull_author_permission: str,
) -> list[str]:
    """Prevent a pull-request author from claiming another allowed identity."""

    failures: list[str] = []
    pull_service = next(
        (
            identity
            for identity, account in SERVICE_ACCOUNTS.items()
            if account == (pull_author_login, pull_author_id)
        ),
        None,
    )
    for commit in commits:
        if commit.sha in KNOWN_HISTORY_EXCEPTIONS:
            continue
        author = (commit.author_name, commit.author_email)
        committer = (commit.committer_name, commit.committer_email)
        if pull_author_permission in WRITE_PERMISSIONS:
            if author != MAINTAINER_IDENTITY:
                failures.append(
                    f"{commit.sha}: maintainer pull request has a non-maintainer author"
                )
            if committer != MAINTAINER_IDENTITY:
                failures.append(
                    f"{commit.sha}: maintainer pull request has a non-maintainer committer"
                )
            continue
        if pull_service is not None:
            if author != pull_service:
                failures.append(f"{commit.sha}: service pull request has an invalid author")
            if committer not in {pull_service, ("GitHub", "noreply@github.com")}:
                failures.append(f"{commit.sha}: service pull request has an invalid committer")
            continue

        if author in SERVICE_IDENTITIES or author == MAINTAINER_IDENTITY:
            failures.append(f"{commit.sha}: outside pull request claims a reserved author identity")
        elif (commit.author_login, commit.author_id) != (pull_author_login, pull_author_id):
            failures.append(f"{commit.sha}: author differs from the pull-request account")

        allowed_committers = {("GitHub", "noreply@github.com")}
        if committer not in allowed_committers and (
            commit.committer_login,
            commit.committer_id,
        ) != (pull_author_login, pull_author_id):
            failures.append(f"{commit.sha}: committer differs from the pull-request account")
    return failures


def load_git_commits(base: str, head: str) -> tuple[CommitIdentity, ...]:
    """Read identities from a Git range without invoking a shell."""

    git = which("git")
    if git is None:
        raise RuntimeError("git executable not found")
    ancestor = subprocess.run(
        [git, "merge-base", "--is-ancestor", base, head],
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise RuntimeError("commit identity baseline is not an ancestor of the target")
    completed = subprocess.run(
        [
            git,
            "rev-list",
            "--reverse",
            f"{base}..{head}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("commit identity audit could not read the configured Git range")

    commits: list[CommitIdentity] = []
    for sha in completed.stdout.splitlines():
        metadata = subprocess.run(
            [
                git,
                "show",
                "-s",
                "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%P%x00%B",
                sha,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if metadata.returncode != 0:
            raise RuntimeError("commit identity audit could not read commit metadata")
        fields = metadata.stdout.split("\x00", 6)
        if len(fields) != 7:
            raise RuntimeError("commit identity audit received malformed Git metadata")
        commit_sha, author_name, author_email, committer_name, committer_email, parents, message = (
            fields
        )
        commits.append(
            CommitIdentity(
                sha=commit_sha,
                author_name=author_name,
                author_email=author_email,
                committer_name=committer_name,
                committer_email=committer_email,
                message=message,
                parent_count=len(parents.split()),
            )
        )
    return tuple(commits)


def audit_history(head: str = "HEAD") -> tuple[list[str], int]:
    """Audit every reachable commit after the frozen v0.5.1 baseline."""

    commits = load_git_commits(BASELINE_COMMIT, head)
    return audit_commits(commits), len(commits)


def _run_gh(arguments: list[str], *, not_found: Any = None) -> Any:
    gh = which("gh")
    if gh is None:
        raise RuntimeError("GitHub CLI is required for hosted commit identity checks")
    completed = subprocess.run(
        [gh, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and "HTTP 404" in completed.stderr:
        return not_found
    if completed.returncode != 0:
        raise RuntimeError("hosted commit identity check could not read GitHub metadata")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("hosted commit identity check received invalid GitHub metadata") from exc


def _pull_request(repository: str, number: int) -> dict[str, Any]:
    value = _run_gh(["api", f"repos/{repository}/pulls/{number}"])
    if not isinstance(value, dict):
        raise RuntimeError("hosted commit identity check received an invalid pull request")
    return value


def _pull_request_commits(repository: str, number: int) -> tuple[CommitIdentity, ...]:
    values = _run_gh(
        [
            "api",
            f"repos/{repository}/pulls/{number}/commits?per_page=100",
        ]
    )
    if not isinstance(values, list):
        raise RuntimeError("hosted commit identity check received an invalid commit list")

    try:
        return tuple(_repository_commit_identity(value) for value in values)
    except (AttributeError, KeyError, TypeError) as exc:
        raise RuntimeError(
            "hosted commit identity check received malformed commit metadata"
        ) from exc


def _repository_commit_identity(value: Any) -> CommitIdentity:
    """Parse one GitHub repository commit without retaining unrelated metadata."""

    try:
        raw = value["commit"]
        author = raw["author"]
        committer = raw["committer"]
        author_account = value.get("author") or {}
        committer_account = value.get("committer") or {}
        return CommitIdentity(
            sha=value["sha"],
            author_name=author["name"],
            author_email=author["email"],
            committer_name=committer["name"],
            committer_email=committer["email"],
            author_login=author_account.get("login"),
            committer_login=committer_account.get("login"),
            author_id=author_account.get("id"),
            committer_id=committer_account.get("id"),
            message=raw["message"],
            parent_count=len(value["parents"]),
        )
    except (AttributeError, KeyError, TypeError) as exc:
        raise RuntimeError(
            "hosted commit identity check received malformed commit metadata"
        ) from exc


def _repository_commit(repository: str, sha: str) -> CommitIdentity:
    value = _run_gh(["api", f"repos/{repository}/commits/{sha}"])
    if not isinstance(value, dict):
        raise RuntimeError("hosted commit identity check received an invalid commit")
    commit = _repository_commit_identity(value)
    if commit.sha != sha:
        raise RuntimeError("hosted commit identity check received the wrong commit")
    return commit


def _permission_lookup(repository: str) -> Callable[[str], str]:
    cache: dict[str, str] = {}

    def permission_for(login: str) -> str:
        if login in cache:
            return cache[login]
        value = _run_gh(
            ["api", f"repos/{repository}/collaborators/{login}/permission"],
            not_found={"permission": "none"},
        )
        if not isinstance(value, dict) or not isinstance(value.get("permission"), str):
            raise RuntimeError("hosted commit identity check received an invalid permission")
        cache[login] = value["permission"]
        return cache[login]

    return permission_for


def audit_pull_request(repository: str, number: int) -> PullRequestAudit:
    """Audit raw PR commits and verify that the audited head stayed stable."""

    pull = _pull_request(repository, number)
    try:
        head_sha = pull["head"]["sha"]
        pull_author_login = pull["user"]["login"]
        pull_author_id = pull["user"]["id"]
        declared_commits = pull["commits"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            "hosted commit identity check received an invalid pull-request head"
        ) from exc
    if (
        not isinstance(head_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None
        or not isinstance(pull_author_login, str)
        or not isinstance(pull_author_id, int)
        or not isinstance(declared_commits, int)
        or declared_commits < 1
    ):
        raise RuntimeError("hosted commit identity check received invalid pull-request metadata")
    if declared_commits > MAX_PULL_COMMITS:
        raise RuntimeError("pull request exceeds the 100-commit identity audit limit")
    commits = _pull_request_commits(repository, number)
    if len(commits) != declared_commits:
        raise RuntimeError("hosted commit identity check received an incomplete commit list")
    if commits[-1].sha != head_sha:
        raise RuntimeError("hosted commit identity check did not receive the current head")
    permission_for = _permission_lookup(repository)
    failures = audit_github_associations(commits, permission_for)
    failures.extend(
        audit_pull_request_roles(
            commits,
            pull_author_login=pull_author_login,
            pull_author_id=pull_author_id,
            pull_author_permission=permission_for(pull_author_login),
        )
    )
    current_pull = _pull_request(repository, number)
    try:
        current_head = current_pull["head"]["sha"]
        current_declared_commits = current_pull["commits"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("hosted commit identity check could not re-read the head") from exc
    if current_head != head_sha or current_declared_commits != declared_commits:
        failures.append("pull-request head changed during commit identity audit")
    return PullRequestAudit(head_sha, len(commits), tuple(failures))


def audit_repository_commit(repository: str, sha: str) -> tuple[str, ...]:
    """Re-read and semantically audit one immutable repository commit."""

    commit = _repository_commit(repository, sha)
    return tuple(audit_github_associations((commit,), _permission_lookup(repository)))


def audit_hosted_history(
    repository: str,
    head: str = "HEAD",
) -> tuple[list[str], int]:
    """Audit GitHub account associations for every post-baseline history commit."""

    local_commits = load_git_commits(BASELINE_COMMIT, head)
    commits = tuple(_repository_commit(repository, commit.sha) for commit in local_commits)
    if tuple(commit.sha for commit in commits) != tuple(commit.sha for commit in local_commits):
        raise RuntimeError("hosted history identity audit received a different Git range")
    return audit_github_associations(commits, _permission_lookup(repository)), len(commits)


def _publish_check(repository: str, audit: PullRequestAudit) -> None:
    conclusion = "failure" if audit.failures else "success"
    summary = (
        "Commit identity audit found a violation. Inspect the safe job diagnostics."
        if audit.failures
        else f"All {audit.commit_count} pull-request commit identities passed."
    )
    _run_gh(
        [
            "api",
            "--method",
            "POST",
            f"repos/{repository}/check-runs",
            "-f",
            "name=identity",
            "-f",
            f"head_sha={audit.head_sha}",
            "-f",
            "status=completed",
            "-f",
            f"conclusion={conclusion}",
            "-f",
            "output[title]=Public commit identity",
            "-f",
            f"output[summary]={summary}",
        ]
    )


def _check_pull_request(repository: str, number: int) -> tuple[list[str], int]:
    audit = audit_pull_request(repository, number)
    _publish_check(repository, audit)
    return list(audit.failures), audit.commit_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-pull-request", type=int)
    parser.add_argument("--check-hosted-history", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.check_pull_request is not None and args.check_hosted_history:
            raise RuntimeError("choose one hosted commit identity audit mode")
        if args.check_pull_request is not None:
            repository = os.environ.get("GITHUB_REPOSITORY")
            if not repository:
                raise RuntimeError("GITHUB_REPOSITORY is required for hosted identity checks")
            failures, count = _check_pull_request(repository, args.check_pull_request)
        elif args.check_hosted_history:
            repository = os.environ.get("GITHUB_REPOSITORY")
            if not repository:
                raise RuntimeError("GITHUB_REPOSITORY is required for hosted identity checks")
            failures, count = audit_hosted_history(repository)
        else:
            failures, count = audit_history()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"commit identity audit passed for {count} commits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

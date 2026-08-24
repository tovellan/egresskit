"""Fast-forward main to an audited pull-request head through protected checks."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from typing import Any

from scripts.commit_identity_audit import (
    ACTIONS_APP_ID,
    PullRequestAudit,
    _run_gh,
    audit_pull_request,
    audit_repository_commit,
)

DEFAULT_BRANCH = "main"
MAIN_UPDATE_RULESET = "sealed-main-updates"


def validate_pull_request(
    pull: dict[str, Any],
    *,
    main_sha: str,
    expected_head: str,
    audit: PullRequestAudit,
    identity_check_passed: bool,
    conversations_resolved: bool,
) -> list[str]:
    """Return safe reasons why an exact fast-forward must not proceed."""

    failures: list[str] = []
    try:
        state = pull["state"]
        draft = pull["draft"]
        base_ref = pull["base"]["ref"]
        base_sha = pull["base"]["sha"]
        head_sha = pull["head"]["sha"]
    except (KeyError, TypeError):
        return ["pull request metadata is incomplete"]

    if state != "open":
        failures.append("pull request is not open")
    if draft:
        failures.append("pull request is still a draft")
    if base_ref != DEFAULT_BRANCH:
        failures.append("pull request does not target main")
    if base_sha != main_sha:
        failures.append("pull request is not based on the current main commit")
    if head_sha != expected_head:
        failures.append("pull-request head differs from the dispatched commit")
    if audit.head_sha != expected_head:
        failures.append("pull-request head differs from the audited commit")
    if audit.failures:
        failures.append("pull-request commit identity audit failed")
    if not identity_check_passed:
        failures.append("required trusted identity check is not successful")
    if not conversations_resolved:
        failures.append("pull request has unresolved review conversations")
    return failures


def _main_sha(repository: str) -> str:
    value = _run_gh(["api", f"repos/{repository}/git/ref/heads/{DEFAULT_BRANCH}"])
    try:
        sha = value["object"]["sha"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("checked merge could not read the main commit") from exc
    if not isinstance(sha, str):
        raise RuntimeError("checked merge received an invalid main commit")
    return sha


def _identity_check_passed(repository: str, head_sha: str) -> bool:
    value = _run_gh(
        [
            "api",
            f"repos/{repository}/commits/{head_sha}/check-runs?check_name=identity&filter=latest",
        ]
    )
    try:
        runs = value["check_runs"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("checked merge received invalid check metadata") from exc
    return any(
        run.get("name") == "identity"
        and run.get("head_sha") == head_sha
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and (run.get("app") or {}).get("id") == ACTIONS_APP_ID
        for run in runs
    )


def _main_update_ruleset_enforcement(repository: str) -> str:
    values = _run_gh(["api", f"repos/{repository}/rulesets"])
    if not isinstance(values, list):
        raise RuntimeError("checked merge received invalid ruleset metadata")
    matches = [
        value
        for value in values
        if isinstance(value, dict)
        and value.get("name") == MAIN_UPDATE_RULESET
        and value.get("target") == "branch"
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("id"), int):
        raise RuntimeError("checked merge requires the sealed main update ruleset")
    value = _run_gh(["api", f"repos/{repository}/rulesets/{matches[0]['id']}"])
    try:
        enforcement = value["enforcement"]
        bypass_actors = value["bypass_actors"]
        conditions = value["conditions"]["ref_name"]
        rules = value["rules"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("checked merge received invalid ruleset metadata") from exc
    if (
        not isinstance(enforcement, str)
        or enforcement not in {"active", "disabled"}
        or bypass_actors != []
        or conditions != {"exclude": [], "include": ["~DEFAULT_BRANCH"]}
        or not isinstance(rules, list)
        or [rule.get("type") for rule in rules if isinstance(rule, dict)] != ["update"]
        or len(rules) != 1
    ):
        raise RuntimeError("checked merge requires the exact sealed main update ruleset")
    return enforcement


def _require_update_window(repository: str) -> None:
    if _main_update_ruleset_enforcement(repository) != "disabled":
        raise RuntimeError("checked merge requires an explicitly opened update window")


def _wait_for_main_reseal(repository: str) -> None:
    for _ in range(36):
        if _main_update_ruleset_enforcement(repository) == "active":
            return
        time.sleep(5)
    raise RuntimeError("checked merge advanced main but the update ruleset was not resealed")


def _review_conversations_resolved(repository: str, number: int) -> bool:
    try:
        owner, name = repository.split("/", 1)
    except ValueError as exc:
        raise RuntimeError("checked merge received an invalid repository name") from exc
    if not owner or not name or "/" in name:
        raise RuntimeError("checked merge received an invalid repository name")

    query = """
    query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          reviewThreads(first: 100, after: $cursor) {
            nodes { isResolved }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
    """
    cursor: str | None = None
    while True:
        arguments = [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-f",
            f"owner={owner}",
            "-f",
            f"name={name}",
            "-F",
            f"number={number}",
        ]
        if cursor is not None:
            arguments.extend(["-f", f"cursor={cursor}"])
        value = _run_gh(arguments)
        try:
            threads = value["data"]["repository"]["pullRequest"]["reviewThreads"]
            nodes = threads["nodes"]
            page_info = threads["pageInfo"]
            has_next_page = page_info["hasNextPage"]
            next_cursor = page_info["endCursor"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                "checked merge received invalid review-conversation metadata"
            ) from exc
        if not isinstance(nodes, list) or not isinstance(has_next_page, bool):
            raise RuntimeError("checked merge received invalid review-conversation metadata")
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get("isResolved"), bool):
                raise RuntimeError("checked merge received invalid review-conversation metadata")
            if not node["isResolved"]:
                return False
        if not has_next_page:
            return True
        if not isinstance(next_cursor, str) or not next_cursor:
            raise RuntimeError("checked merge received invalid review-conversation metadata")
        cursor = next_cursor


def _preflight(repository: str, number: int, expected_head: str) -> PullRequestAudit:
    pull = _run_gh(["api", f"repos/{repository}/pulls/{number}"])
    if not isinstance(pull, dict):
        raise RuntimeError("checked merge received invalid pull-request metadata")
    audit = audit_pull_request(repository, number)
    failures = validate_pull_request(
        pull,
        main_sha=_main_sha(repository),
        expected_head=expected_head,
        audit=audit,
        identity_check_passed=_identity_check_passed(repository, expected_head),
        conversations_resolved=_review_conversations_resolved(repository, number),
    )
    if failures:
        raise RuntimeError("; ".join(failures))
    return audit


def merge_pull_request(repository: str, number: int, expected_head: str) -> str:
    """Validate and fast-forward main to the exact audited PR head."""

    if os.environ.get("GITHUB_REF") != f"refs/heads/{DEFAULT_BRANCH}":
        raise RuntimeError("checked merge must run from the default branch")
    if number < 1 or re.fullmatch(r"[0-9a-f]{40}", expected_head) is None:
        raise RuntimeError("checked merge received an invalid dispatch target")

    _require_update_window(repository)
    _preflight(repository, number, expected_head)
    # Close over every mutable PR, check, review-thread, and main-ref value again.
    _require_update_window(repository)
    _preflight(repository, number, expected_head)
    _require_update_window(repository)

    _run_gh(
        [
            "api",
            "--method",
            "PATCH",
            f"repos/{repository}/git/refs/heads/{DEFAULT_BRANCH}",
            "-f",
            f"sha={expected_head}",
            "-F",
            "force=false",
        ]
    )
    if _main_sha(repository) != expected_head:
        raise RuntimeError("checked merge could not verify the final main commit")
    if audit_repository_commit(repository, expected_head):
        raise RuntimeError("checked merge could not verify final commit identities")
    _wait_for_main_reseal(repository)
    return expected_head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pull_request", type=int)
    parser.add_argument("expected_head")
    args = parser.parse_args(argv)
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        print("GITHUB_REPOSITORY is required for checked merges", file=sys.stderr)
        return 1
    try:
        sha = merge_pull_request(repository, args.pull_request, args.expected_head)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"checked merge advanced main to {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

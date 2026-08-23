from __future__ import annotations

import pytest

import scripts.commit_identity_audit as commit_identity_audit
from scripts.commit_identity_audit import (
    KNOWN_HISTORY_EXCEPTIONS,
    CommitIdentity,
    audit_commits,
    audit_github_associations,
    audit_history,
    audit_pull_request,
    audit_pull_request_roles,
)


def identity(
    *,
    sha: str = "a" * 40,
    author_name: str = "Tovellan Maintainers",
    author_email: str = "tovellan@users.noreply.github.com",
    committer_name: str = "Tovellan Maintainers",
    committer_email: str = "tovellan@users.noreply.github.com",
    author_login: str | None = "tovellan",
    committer_login: str | None = "tovellan",
    author_id: int | None = None,
    committer_id: int | None = None,
    message: str = "",
    parent_count: int = 1,
) -> CommitIdentity:
    return CommitIdentity(
        sha=sha,
        author_name=author_name,
        author_email=author_email,
        committer_name=committer_name,
        committer_email=committer_email,
        author_login=author_login,
        committer_login=committer_login,
        author_id=author_id,
        committer_id=committer_id,
        message=message,
        parent_count=parent_count,
    )


def test_current_history_passes_forward_only_audit() -> None:
    failures, count = audit_history()
    assert failures == []
    assert count >= 1


def test_exact_maintainer_identity_passes_for_write_linked_account() -> None:
    assert audit_github_associations((identity(),), lambda _: "admin") == []


def test_linked_outside_contributor_keeps_private_identity() -> None:
    contributor = identity(
        author_name="contributor-account",
        author_email="456+contributor-account@users.noreply.github.com",
        committer_name="contributor-account",
        committer_email="456+contributor-account@users.noreply.github.com",
        author_login="contributor-account",
        committer_login="contributor-account",
        author_id=456,
        committer_id=456,
    )
    assert audit_github_associations((contributor,), lambda _: "none") == []


def test_write_linked_personal_noreply_must_use_maintainer_identity() -> None:
    commit = identity(
        author_name="Maintainer Account",
        author_email="123+maintainer-account@users.noreply.github.com",
        author_login="maintainer-account",
        author_id=123,
    )
    failures = audit_github_associations((commit,), lambda _: "write")
    assert any("author is maintainer-linked" in failure for failure in failures)


@pytest.mark.parametrize("permission", ["admin", "maintain", "push", "write"])
def test_every_write_capable_permission_requires_maintainer_identity(permission: str) -> None:
    commit = identity(
        author_name="maintainer-account",
        author_email="123+maintainer-account@users.noreply.github.com",
        author_login="maintainer-account",
        author_id=123,
    )
    failures = audit_github_associations((commit,), lambda _: permission)
    assert any("author is maintainer-linked" in failure for failure in failures)


def test_unlinked_identity_is_rejected() -> None:
    commit = identity(
        author_name="contributor-account",
        author_email="456+contributor-account@users.noreply.github.com",
        author_login=None,
        author_id=None,
    )
    failures = audit_github_associations((commit,), lambda _: "none")
    assert any("author is not associated" in failure for failure in failures)


def test_personal_email_is_rejected_without_echoing_it() -> None:
    failures = audit_commits(
        (
            identity(
                author_name="External Contributor",
                author_email="private-address@example.test",
            ),
        )
    )
    assert failures == [f"{'a' * 40}: author email is not privacy-preserving"]
    assert "private-address" not in failures[0]


def test_only_exact_documented_service_identities_are_allowed() -> None:
    service = identity(
        author_name="github-actions[bot]",
        author_email="41898282+github-actions[bot]@users.noreply.github.com",
        committer_name="github-actions[bot]",
        committer_email="41898282+github-actions[bot]@users.noreply.github.com",
        author_login="github-actions[bot]",
        committer_login="github-actions[bot]",
        author_id=41898282,
        committer_id=41898282,
    )
    assert audit_github_associations((service,), lambda _: "none") == []

    unknown = identity(
        author_name="unknown-service[bot]",
        author_email="999+unknown-service[bot]@users.noreply.github.com",
    )
    failures = audit_commits((unknown,))
    assert any("undocumented service identity" in failure for failure in failures)


def test_recorded_history_exception_is_scoped_to_one_sha() -> None:
    exception = identity(
        sha=next(iter(KNOWN_HISTORY_EXCEPTIONS)),
        author_email="recorded-legacy@example.test",
        committer_name="GitHub",
        committer_email="noreply@github.com",
        message="Co-authored-by: Tovellan Maintainers <tovellan@users.noreply.github.com>",
    )
    assert audit_commits((exception,)) == []
    failures = audit_commits((identity(author_email="new-leak@example.test"),))
    assert failures


def test_pull_request_role_prevents_reserved_identity_spoofing() -> None:
    assert (
        audit_pull_request_roles(
            (identity(),),
            pull_author_login="maintainer-account",
            pull_author_id=123,
            pull_author_permission="admin",
        )
        == []
    )
    failures = audit_pull_request_roles(
        (identity(),),
        pull_author_login="contributor-account",
        pull_author_id=456,
        pull_author_permission="none",
    )
    assert failures == [
        f"{'a' * 40}: outside pull request claims a reserved author identity",
        f"{'a' * 40}: committer differs from the pull-request account",
    ]


def test_maintainer_pull_request_requires_both_exact_commit_roles() -> None:
    mixed = identity(
        committer_name="contributor-account",
        committer_email="456+contributor-account@users.noreply.github.com",
        committer_login="contributor-account",
        committer_id=456,
    )
    failures = audit_github_associations((mixed,), lambda _: "none")
    assert failures == [f"{'a' * 40}: maintainer identity must own both commit roles"]
    failures = audit_pull_request_roles(
        (mixed,),
        pull_author_login="maintainer-account",
        pull_author_id=123,
        pull_author_permission="admin",
    )
    assert failures == [f"{'a' * 40}: maintainer pull request has a non-maintainer committer"]


def test_outside_pull_request_cannot_claim_a_service_or_maintainer_committer() -> None:
    contributor = identity(
        author_name="contributor-account",
        author_email="456+contributor-account@users.noreply.github.com",
        author_login="contributor-account",
        author_id=456,
    )
    for name, email in (
        ("Tovellan Maintainers", "tovellan@users.noreply.github.com"),
        ("GitHub", "noreply@github.com"),
        (
            "github-actions[bot]",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ),
    ):
        commit = CommitIdentity(
            **{
                **contributor.__dict__,
                "committer_name": name,
                "committer_email": email,
            }
        )
        failures = audit_pull_request_roles(
            (commit,),
            pull_author_login="contributor-account",
            pull_author_id=456,
            pull_author_permission="none",
        )
        assert failures == [f"{'a' * 40}: committer differs from the pull-request account"]


def test_web_flow_association_does_not_prove_github_provenance() -> None:
    commit = identity(
        author_name="contributor-account",
        author_email="456+contributor-account@users.noreply.github.com",
        committer_name="GitHub",
        committer_email="noreply@github.com",
        author_login="contributor-account",
        committer_login="web-flow",
        author_id=456,
        committer_id=19864447,
    )
    failures = audit_github_associations((commit,), lambda _: "none")
    assert failures == [f"{'a' * 40}: committer does not match its linked GitHub account"]


def test_outside_pull_request_must_match_its_linked_account() -> None:
    contributor = identity(
        author_name="contributor-account",
        author_email="456+contributor-account@users.noreply.github.com",
        committer_name="contributor-account",
        committer_email="456+contributor-account@users.noreply.github.com",
        author_login="contributor-account",
        committer_login="contributor-account",
        author_id=456,
        committer_id=456,
    )
    assert (
        audit_pull_request_roles(
            (contributor,),
            pull_author_login="contributor-account",
            pull_author_id=456,
            pull_author_permission="none",
        )
        == []
    )
    failures = audit_pull_request_roles(
        (contributor,),
        pull_author_login="different-account",
        pull_author_id=789,
        pull_author_permission="none",
    )
    assert failures == [
        f"{'a' * 40}: author differs from the pull-request account",
        f"{'a' * 40}: committer differs from the pull-request account",
    ]


def test_merge_commits_and_authorship_trailers_are_rejected() -> None:
    failures = audit_commits(
        (
            identity(
                parent_count=2,
                message=(
                    "Synthetic change\n\n"
                    "Signed-off-by: Tovellan Maintainers "
                    "<tovellan@users.noreply.github.com>"
                ),
            ),
        )
    )
    assert failures == [
        f"{'a' * 40}: merge commits are not allowed",
        f"{'a' * 40}: prohibited attribution trailer found",
    ]


def test_indented_authorship_trailer_is_rejected() -> None:
    for trailer in (
        "  Co-authored-by: hidden",
        "Signed-off-by : hidden",
        "Generated-by\t:\thidden",
        "Authored-by: hidden",
        "Co-developed-by: hidden",
        "AI-generated-by: hidden",
        "Generated-with: hidden",
    ):
        failures = audit_commits((identity(message=f"Change\n\n{trailer}"),))
        assert failures == [f"{'a' * 40}: prohibited attribution trailer found"]


def pull_metadata(*, commits: int = 1, head: str = "a" * 40) -> dict[str, object]:
    return {
        "head": {"sha": head},
        "user": {"login": "maintainer-account", "id": 123},
        "commits": commits,
    }


def test_hosted_pull_request_rejects_more_than_100_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        commit_identity_audit,
        "_pull_request",
        lambda *_: pull_metadata(commits=101),
    )
    with pytest.raises(RuntimeError, match="100-commit"):
        audit_pull_request("example/repository", 1)


@pytest.mark.parametrize(
    ("declared", "commits", "message"),
    [
        (2, (identity(),), "incomplete commit list"),
        (1, (identity(sha="b" * 40),), "current head"),
    ],
)
def test_hosted_pull_request_closes_count_and_head(
    monkeypatch: pytest.MonkeyPatch,
    declared: int,
    commits: tuple[CommitIdentity, ...],
    message: str,
) -> None:
    monkeypatch.setattr(
        commit_identity_audit,
        "_pull_request",
        lambda *_: pull_metadata(commits=declared),
    )
    monkeypatch.setattr(commit_identity_audit, "_pull_request_commits", lambda *_: commits)
    with pytest.raises(RuntimeError, match=message):
        audit_pull_request("example/repository", 1)

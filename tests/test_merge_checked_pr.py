from __future__ import annotations

import pytest

import scripts.merge_checked_pr as merge_checked_pr
from scripts.commit_identity_audit import PullRequestAudit
from scripts.merge_checked_pr import merge_pull_request, validate_pull_request


def pull_data() -> dict[str, object]:
    return {
        "state": "open",
        "draft": False,
        "base": {"ref": "main", "sha": "b" * 40},
        "head": {"sha": "h" * 40},
    }


def test_checked_pull_request_is_accepted() -> None:
    failures = validate_pull_request(
        pull_data(),
        main_sha="b" * 40,
        expected_head="h" * 40,
        audit=PullRequestAudit("h" * 40, 1, ()),
        identity_check_passed=True,
        review_approved=True,
        conversations_resolved=True,
    )
    assert failures == []


def test_stale_or_unaudited_pull_request_is_rejected() -> None:
    failures = validate_pull_request(
        pull_data(),
        main_sha="c" * 40,
        expected_head="h" * 40,
        audit=PullRequestAudit("x" * 40, 1, ("identity failure",)),
        identity_check_passed=False,
        review_approved=False,
        conversations_resolved=False,
    )
    assert failures == [
        "pull request is not based on the current main commit",
        "pull-request head differs from the audited commit",
        "pull-request commit identity audit failed",
        "required trusted identity check is not successful",
        "required independent review is not approved",
        "pull request has unresolved review conversations",
    ]


def test_draft_or_wrong_base_is_rejected() -> None:
    pull = pull_data()
    pull["draft"] = True
    pull["base"] = {"ref": "release", "sha": "b" * 40}
    failures = validate_pull_request(
        pull,
        main_sha="b" * 40,
        expected_head="h" * 40,
        audit=PullRequestAudit("h" * 40, 1, ()),
        identity_check_passed=True,
        review_approved=True,
        conversations_resolved=True,
    )
    assert failures == [
        "pull request is still a draft",
        "pull request does not target main",
    ]


def test_dispatched_head_must_match_current_pull_request() -> None:
    failures = validate_pull_request(
        pull_data(),
        main_sha="b" * 40,
        expected_head="x" * 40,
        audit=PullRequestAudit("h" * 40, 1, ()),
        identity_check_passed=True,
        review_approved=True,
        conversations_resolved=True,
    )
    assert failures == [
        "pull-request head differs from the dispatched commit",
        "pull-request head differs from the audited commit",
    ]


def test_merge_rechecks_before_updating_exact_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = "a" * 40
    preflights: list[tuple[str, int, str]] = []
    api_calls: list[list[str]] = []

    def record_api_call(arguments: list[str]) -> object:
        api_calls.append(arguments)
        return {}

    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setattr(
        merge_checked_pr,
        "_preflight",
        lambda repository, number, head: preflights.append((repository, number, head)),
    )
    monkeypatch.setattr(merge_checked_pr, "_main_sha", lambda _: expected)
    monkeypatch.setattr(merge_checked_pr, "_require_update_window", lambda _: None)
    monkeypatch.setattr(merge_checked_pr, "_wait_for_main_reseal", lambda _: None)
    monkeypatch.setattr(merge_checked_pr, "audit_repository_commit", lambda *_: ())
    monkeypatch.setattr(
        merge_checked_pr,
        "_run_gh",
        record_api_call,
    )

    assert merge_pull_request("example/repository", 7, expected) == expected
    assert preflights == [
        ("example/repository", 7, expected),
        ("example/repository", 7, expected),
    ]
    assert any(f"sha={expected}" in argument for argument in api_calls[0])
    assert "force=false" in api_calls[0]


def test_merge_rejects_an_invalid_expected_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    with pytest.raises(RuntimeError, match="invalid dispatch target"):
        merge_pull_request("example/repository", 1, "main")


def test_update_window_requires_exact_disabled_ruleset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        (
            [
                {"id": 11, "name": "immutable-release-tags", "target": "tag"},
                {"id": 22, "name": "sealed-main-updates", "target": "branch"},
            ],
            {
                "enforcement": "disabled",
                "bypass_actors": [],
                "conditions": {"ref_name": {"exclude": [], "include": ["~DEFAULT_BRANCH"]}},
                "rules": [{"type": "update"}],
            },
        )
    )
    monkeypatch.setattr(merge_checked_pr, "_run_gh", lambda _: next(responses))
    merge_checked_pr._require_update_window("example/repository")


def test_active_update_ruleset_keeps_window_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        (
            [{"id": 22, "name": "sealed-main-updates", "target": "branch"}],
            {
                "enforcement": "active",
                "bypass_actors": [],
                "conditions": {"ref_name": {"exclude": [], "include": ["~DEFAULT_BRANCH"]}},
                "rules": [{"type": "update"}],
            },
        )
    )
    monkeypatch.setattr(merge_checked_pr, "_run_gh", lambda _: next(responses))
    with pytest.raises(RuntimeError, match="explicitly opened"):
        merge_checked_pr._require_update_window("example/repository")


@pytest.mark.parametrize(
    ("decision", "approved"),
    [("APPROVED", True), ("REVIEW_REQUIRED", False), (None, False)],
)
def test_review_decision_is_read_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    decision: str | None,
    approved: bool,
) -> None:
    monkeypatch.setattr(
        merge_checked_pr,
        "_run_gh",
        lambda _: {"data": {"repository": {"pullRequest": {"reviewDecision": decision}}}},
    )
    assert merge_checked_pr._review_approved("example/repository", 7) is approved


def test_invalid_review_metadata_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        merge_checked_pr,
        "_run_gh",
        lambda _: {"data": {"repository": {"pullRequest": {"reviewDecision": "UNKNOWN"}}}},
    )
    with pytest.raises(RuntimeError, match="invalid review metadata"):
        merge_checked_pr._review_approved("example/repository", 7)


@pytest.mark.parametrize("repository", ["missing-slash", "/missing-owner", "too/many/parts"])
def test_review_rejects_invalid_repository_name(repository: str) -> None:
    with pytest.raises(RuntimeError, match="invalid repository name"):
        merge_checked_pr._review_approved(repository, 7)

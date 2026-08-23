from __future__ import annotations

import json

from egresskit import (
    Policy,
    PolicyLintCode,
    lint_policy,
    policy_lint_report_json_schema,
)

from .conftest import make_policy, policy_data


def test_clean_policy_passes() -> None:
    report = lint_policy(make_policy())
    assert report.passed
    assert report.diagnostic_count == 0
    assert report.diagnostics == ()


def test_no_rules_reports_unused_declarations_deterministically() -> None:
    policy = make_policy({"rules": []})
    first = lint_policy(policy)
    second = lint_policy(policy)
    assert first == second
    assert not first.passed
    assert [(item.code, item.object_id) for item in first.diagnostics] == [
        (PolicyLintCode.NO_RULES, "test_policy"),
        (PolicyLintCode.UNUSED_PROVIDER, "processor_a"),
        (PolicyLintCode.UNUSED_PROVIDER, "synthetic_processor"),
        (PolicyLintCode.UNUSED_PURPOSE, "summarize"),
    ]


def test_rule_outside_classification_ceiling_is_unreachable() -> None:
    data = policy_data()
    data["rules"] = [
        {
            **data["rules"][0],
            "id": "allow_restricted",
            "classifications": ["restricted"],
            "providers": ["processor_a"],
        }
    ]
    report = lint_policy(Policy.model_validate(data))
    assert [(item.code, item.object_id) for item in report.diagnostics] == [
        (PolicyLintCode.UNREACHABLE_RULE, "allow_restricted"),
        (PolicyLintCode.UNUSED_PROVIDER, "synthetic_processor"),
    ]


def test_rule_outside_purpose_ceiling_is_unreachable() -> None:
    data = policy_data()
    data["purposes"].append({"id": "embed", "description": "Synthetic embedding."})
    data["rules"] = [{**data["rules"][0], "purposes": ["embed"]}]
    report = lint_policy(Policy.model_validate(data))
    assert PolicyLintCode.UNREACHABLE_RULE in {item.code for item in report.diagnostics}


def test_rule_outside_environment_ceiling_is_unreachable() -> None:
    data = policy_data()
    data["rules"] = [{**data["rules"][0], "environments": ["staging"]}]
    report = lint_policy(Policy.model_validate(data))
    assert PolicyLintCode.UNREACHABLE_RULE in {item.code for item in report.diagnostics}


def test_live_rule_for_synthetic_only_provider_is_unreachable() -> None:
    data = policy_data()
    data["rules"] = [
        {
            **data["rules"][0],
            "providers": ["synthetic_processor"],
            "execution_modes": ["live"],
        }
    ]
    report = lint_policy(Policy.model_validate(data))
    assert PolicyLintCode.UNREACHABLE_RULE in {item.code for item in report.diagnostics}


def test_any_reachable_provider_makes_multi_provider_rule_reachable() -> None:
    data = policy_data()
    data["rules"] = [data["rules"][0]]
    report = lint_policy(Policy.model_validate(data))
    assert report.passed


def test_report_is_versioned_and_payload_free() -> None:
    report = lint_policy(make_policy({"rules": []}))
    encoded = json.dumps(report.model_dump(mode="json"))
    assert report.schema_version == "1"
    for forbidden in ("payload", "receipt", "destination", "endpoint"):
        assert forbidden not in encoded


def test_lint_report_schema_is_strict() -> None:
    schema = policy_lint_report_json_schema()
    assert schema["properties"]["schema_version"]["const"] == "1"
    assert schema["additionalProperties"] is False

from __future__ import annotations

import json

from egresskit import (
    DecisionStatus,
    PolicyEvaluator,
    decision_explanation_json_schema,
    explain_decision,
)

from .conftest import make_policy
from .test_policy import intent


def test_explanation_is_deterministic_across_receipts() -> None:
    evaluator = PolicyEvaluator(make_policy())
    first_decision = evaluator.evaluate(intent())
    second_decision = evaluator.evaluate(intent())
    assert first_decision.receipt.receipt_id != second_decision.receipt.receipt_id
    assert explain_decision(first_decision) == explain_decision(second_decision)


def test_explanation_preserves_allow_semantics_and_metadata() -> None:
    explanation = explain_decision(PolicyEvaluator(make_policy()).evaluate(intent(dry_run=True)))
    assert explanation.status is DecisionStatus.ALLOW
    assert explanation.matched_rule_ids == ("allow_internal_test",)
    assert explanation.provider == "processor_a"
    assert explanation.classification.value == "internal"
    assert explanation.purpose == "summarize"
    assert explanation.environment == "test"
    assert explanation.execution_mode.value == "synthetic"
    assert explanation.dry_run


def test_explanation_preserves_deny_reasons() -> None:
    explanation = explain_decision(PolicyEvaluator(make_policy()).evaluate(intent(mode="live")))
    assert explanation.status is DecisionStatus.DENY
    assert [reason.value for reason in explanation.reason_codes] == ["explicit_deny"]
    assert explanation.matched_rule_ids == (
        "allow_internal_test",
        "deny_live_processor_a",
    )


def test_explanation_is_payload_free_and_omits_receipt_evidence() -> None:
    explanation = explain_decision(PolicyEvaluator(make_policy()).evaluate(intent()))
    encoded = json.dumps(explanation.model_dump(mode="json"))
    for forbidden in ("payload", "receipt", "receipt_id", "evaluated_at", "timestamp"):
        assert forbidden not in encoded


def test_explanation_schema_is_versioned_and_strict() -> None:
    schema = decision_explanation_json_schema()
    assert schema["properties"]["schema_version"]["const"] == "1"
    assert schema["additionalProperties"] is False

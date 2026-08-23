"""Deterministic decision explanations without receipt identifiers or timestamps."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from .models import (
    DataClassification,
    Decision,
    DecisionStatus,
    ExecutionMode,
    Identifier,
    ImmutableModel,
    ReasonCode,
)


class DecisionExplanation(ImmutableModel):
    schema_version: Literal["1"] = "1"
    policy_id: Identifier
    policy_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    status: DecisionStatus
    reason_codes: tuple[ReasonCode, ...]
    matched_rule_ids: tuple[Identifier, ...]
    provider: Identifier
    classification: DataClassification
    purpose: Identifier
    environment: Identifier
    execution_mode: ExecutionMode
    dry_run: bool


def explain_decision(decision: Decision) -> DecisionExplanation:
    """Remove nondeterministic receipt evidence while retaining decision semantics."""

    receipt = decision.receipt
    return DecisionExplanation(
        policy_id=receipt.policy_id,
        policy_digest=receipt.policy_digest,
        status=decision.status,
        reason_codes=decision.reason_codes,
        matched_rule_ids=decision.matched_rule_ids,
        provider=receipt.provider,
        classification=receipt.classification,
        purpose=receipt.purpose,
        environment=receipt.environment,
        execution_mode=receipt.execution_mode,
        dry_run=receipt.dry_run,
    )


def decision_explanation_json_schema() -> dict[str, Any]:
    return DecisionExplanation.model_json_schema()

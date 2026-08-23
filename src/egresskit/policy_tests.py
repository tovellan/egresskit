"""Versioned, payload-free declarative policy test cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from .errors import TestSuiteLoadError
from .models import (
    DecisionStatus,
    EgressIntent,
    ExecutionMode,
    Identifier,
    ImmutableModel,
    ReasonCode,
)
from .policy import PolicyEvaluator


class PolicyTestCase(ImmutableModel):
    id: Identifier
    intent: EgressIntent
    expected_status: DecisionStatus
    expected_reason_codes: tuple[ReasonCode, ...] | None = None

    @field_validator("expected_reason_codes")
    @classmethod
    def canonicalize_reasons(
        cls, value: tuple[ReasonCode, ...] | None
    ) -> tuple[ReasonCode, ...] | None:
        if value is None:
            return None
        if len(value) != len(set(value)):
            raise ValueError("expected reason codes must be unique")
        return tuple(sorted(value, key=lambda reason: reason.value))

    @model_validator(mode="after")
    def require_safe_context(self) -> PolicyTestCase:
        if self.intent.context.mode is not ExecutionMode.SYNTHETIC:
            raise ValueError("policy test cases must use synthetic execution mode")
        if not self.intent.context.dry_run:
            raise ValueError("policy test cases must enable dry_run")
        return self


class PolicyTestSuite(ImmutableModel):
    schema_version: Literal["1"]
    suite_id: Identifier
    cases: tuple[PolicyTestCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_ids(self) -> PolicyTestSuite:
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate policy test case id")
        return self


class PolicyTestCaseResult(ImmutableModel):
    id: Identifier
    passed: bool
    expected_status: DecisionStatus
    actual_status: DecisionStatus
    expected_reason_codes: tuple[ReasonCode, ...] | None
    actual_reason_codes: tuple[ReasonCode, ...]


class PolicyTestReport(ImmutableModel):
    schema_version: Literal["1"] = "1"
    suite_id: Identifier
    policy_id: Identifier
    passed: bool
    total: int
    passed_count: int
    failed_count: int
    cases: tuple[PolicyTestCaseResult, ...]


def load_policy_test_suite(path: str | Path) -> PolicyTestSuite:
    suite_path = Path(path)
    try:
        raw = suite_path.read_text(encoding="utf-8")
        value = json.loads(raw) if suite_path.suffix.lower() == ".json" else yaml.safe_load(raw)
        if not isinstance(value, dict):
            raise TestSuiteLoadError("test_suite_root_invalid", "test suite root must be an object")
        return PolicyTestSuite.model_validate(value)
    except TestSuiteLoadError:
        raise
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ValidationError) as exc:
        raise TestSuiteLoadError(
            "test_suite_invalid", "policy test suite could not be loaded", cause=exc
        ) from exc


def run_policy_tests(evaluator: PolicyEvaluator, suite: PolicyTestSuite) -> PolicyTestReport:
    results: list[PolicyTestCaseResult] = []
    for case in suite.cases:
        decision = evaluator.evaluate(case.intent)
        reasons_match = (
            case.expected_reason_codes is None
            or case.expected_reason_codes == decision.reason_codes
        )
        passed = case.expected_status is decision.status and reasons_match
        results.append(
            PolicyTestCaseResult(
                id=case.id,
                passed=passed,
                expected_status=case.expected_status,
                actual_status=decision.status,
                expected_reason_codes=case.expected_reason_codes,
                actual_reason_codes=decision.reason_codes,
            )
        )
    passed_count = sum(result.passed for result in results)
    return PolicyTestReport(
        suite_id=suite.suite_id,
        policy_id=evaluator.policy.policy_id,
        passed=passed_count == len(results),
        total=len(results),
        passed_count=passed_count,
        failed_count=len(results) - passed_count,
        cases=tuple(results),
    )


def policy_test_suite_json_schema() -> dict[str, Any]:
    return PolicyTestSuite.model_json_schema()

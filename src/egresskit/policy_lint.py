"""Deterministic, payload-free policy diagnostics."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import StrictBool

from .models import (
    ExecutionMode,
    Identifier,
    ImmutableModel,
    Policy,
    PolicyRule,
    ProviderCapability,
)


class PolicyLintCode(str, Enum):
    NO_RULES = "no_rules"
    UNUSED_PROVIDER = "unused_provider"
    UNUSED_PURPOSE = "unused_purpose"
    UNREACHABLE_RULE = "unreachable_rule"


class PolicyLintDiagnostic(ImmutableModel):
    code: PolicyLintCode
    object_type: Literal["policy", "provider", "purpose", "rule"]
    object_id: Identifier


class PolicyLintReport(ImmutableModel):
    schema_version: Literal["1"] = "1"
    policy_id: Identifier
    passed: StrictBool
    diagnostic_count: int
    diagnostics: tuple[PolicyLintDiagnostic, ...]


def lint_policy(policy: Policy) -> PolicyLintReport:
    """Return stable diagnostics for declarations that cannot affect evaluation."""

    diagnostics: list[PolicyLintDiagnostic] = []
    if not policy.rules:
        diagnostics.append(
            PolicyLintDiagnostic(
                code=PolicyLintCode.NO_RULES,
                object_type="policy",
                object_id=policy.policy_id,
            )
        )

    referenced_purposes = frozenset(purpose for rule in policy.rules for purpose in rule.purposes)
    referenced_providers = frozenset(
        provider for rule in policy.rules for provider in rule.providers
    )
    diagnostics.extend(
        PolicyLintDiagnostic(
            code=PolicyLintCode.UNUSED_PURPOSE,
            object_type="purpose",
            object_id=purpose.id,
        )
        for purpose in policy.purposes
        if purpose.id not in referenced_purposes
    )
    diagnostics.extend(
        PolicyLintDiagnostic(
            code=PolicyLintCode.UNUSED_PROVIDER,
            object_type="provider",
            object_id=provider.id,
        )
        for provider in policy.providers
        if provider.id not in referenced_providers
    )

    providers = {provider.id: provider for provider in policy.providers}
    diagnostics.extend(
        PolicyLintDiagnostic(
            code=PolicyLintCode.UNREACHABLE_RULE,
            object_type="rule",
            object_id=rule.id,
        )
        for rule in policy.rules
        if not _rule_is_reachable(rule, providers)
    )

    ordered = tuple(
        sorted(
            diagnostics,
            key=lambda item: (item.code.value, item.object_type, item.object_id),
        )
    )
    return PolicyLintReport(
        policy_id=policy.policy_id,
        passed=not ordered,
        diagnostic_count=len(ordered),
        diagnostics=ordered,
    )


def _rule_is_reachable(rule: PolicyRule, providers: dict[str, ProviderCapability]) -> bool:
    for provider_id in rule.providers:
        provider = providers[provider_id]
        if not rule.classifications.intersection(provider.classifications):
            continue
        if not rule.purposes.intersection(provider.purposes):
            continue
        if not rule.environments.intersection(provider.environments):
            continue
        if provider.synthetic_only and ExecutionMode.SYNTHETIC not in rule.execution_modes:
            continue
        return True
    return False


def policy_lint_report_json_schema() -> dict[str, Any]:
    return PolicyLintReport.model_json_schema()

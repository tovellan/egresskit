"""Policy loading and deterministic evaluation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, ValidationError

from ._documents import DocumentParseError, parse_document
from .errors import PolicyLoadError
from .models import (
    Decision,
    DecisionReceipt,
    DecisionStatus,
    EgressIntent,
    Policy,
    PolicyRule,
    ProviderCapability,
    ReasonCode,
    RuleEffect,
)


def load_policy(path: str | Path) -> Policy:
    """Load YAML or JSON without environment interpolation or custom YAML objects."""

    policy_path = Path(path)
    try:
        raw = policy_path.read_text(encoding="utf-8")
        value = parse_document(raw, is_json=policy_path.suffix.lower() == ".json")
        if not isinstance(value, dict):
            raise PolicyLoadError("policy_root_invalid", "policy root must be an object")
        return Policy.model_validate(value)
    except PolicyLoadError:
        raise
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        yaml.YAMLError,
        DocumentParseError,
        ValidationError,
    ) as exc:
        raise PolicyLoadError("policy_invalid", "policy could not be loaded", cause=exc) from exc


def policy_digest(policy: Policy) -> str:
    canonical = json.dumps(_canonicalize(policy), sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        items = [_canonicalize(item) for item in value]
        return sorted(
            items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))
        )
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


class PolicyEvaluator:
    """Evaluate capability limits first, then deny-overrides policy rules."""

    def __init__(self, policy: Policy) -> None:
        self._policy = policy
        self._purposes = frozenset(purpose.id for purpose in policy.purposes)
        self._providers = {provider.id: provider for provider in policy.providers}
        self._digest = policy_digest(policy)

    @property
    def policy(self) -> Policy:
        return self._policy

    def evaluate(self, intent: EgressIntent) -> Decision:
        reasons: set[ReasonCode] = set()
        matched: tuple[PolicyRule, ...] = ()
        provider = self._providers.get(intent.provider)
        if intent.purpose not in self._purposes:
            reasons.add(ReasonCode.UNKNOWN_PURPOSE)
        if provider is None:
            reasons.add(ReasonCode.UNKNOWN_PROVIDER)
        else:
            reasons.update(self._capability_failures(provider, intent))

        if not reasons:
            matched = tuple(rule for rule in self._policy.rules if self._matches(rule, intent))
            denied = tuple(rule for rule in matched if rule.effect is RuleEffect.DENY)
            allowed = tuple(rule for rule in matched if rule.effect is RuleEffect.ALLOW)
            if denied:
                reasons.add(ReasonCode.EXPLICIT_DENY)
            elif not allowed:
                reasons.add(ReasonCode.NO_MATCHING_ALLOW)
            else:
                reasons.add(ReasonCode.ALLOWED_BY_RULE)

        status = (
            DecisionStatus.ALLOW if reasons == {ReasonCode.ALLOWED_BY_RULE} else DecisionStatus.DENY
        )
        reason_codes = tuple(sorted(reasons, key=lambda reason: reason.value))
        matched_ids = tuple(sorted(rule.id for rule in matched))
        receipt = DecisionReceipt(
            receipt_id=str(uuid4()),
            evaluated_at=datetime.now(timezone.utc),
            policy_id=self._policy.policy_id,
            policy_digest=self._digest,
            status=status,
            reason_codes=reason_codes,
            provider=intent.provider,
            classification=intent.classification,
            purpose=intent.purpose,
            environment=intent.context.environment,
            execution_mode=intent.context.mode,
            dry_run=intent.context.dry_run,
            matched_rule_ids=matched_ids,
        )
        return Decision(
            status=status,
            reason_codes=reason_codes,
            matched_rule_ids=matched_ids,
            receipt=receipt,
        )

    @staticmethod
    def _capability_failures(provider: ProviderCapability, intent: EgressIntent) -> set[ReasonCode]:
        failures: set[ReasonCode] = set()
        if intent.classification not in provider.classifications:
            failures.add(ReasonCode.CLASSIFICATION_NOT_SUPPORTED)
        if intent.purpose not in provider.purposes:
            failures.add(ReasonCode.PURPOSE_NOT_SUPPORTED)
        if intent.context.environment not in provider.environments:
            failures.add(ReasonCode.ENVIRONMENT_NOT_SUPPORTED)
        if provider.synthetic_only and intent.context.mode.value != "synthetic":
            failures.add(ReasonCode.SYNTHETIC_ONLY_PROVIDER)
        return failures

    @staticmethod
    def _matches(rule: PolicyRule, intent: EgressIntent) -> bool:
        return (
            intent.classification in rule.classifications
            and intent.purpose in rule.purposes
            and intent.provider in rule.providers
            and intent.context.environment in rule.environments
            and intent.context.mode in rule.execution_modes
        )


def policy_json_schema() -> dict[str, Any]:
    return Policy.model_json_schema()

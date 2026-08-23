"""Typed policy, request, decision, and receipt models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

IDENTIFIER_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN, max_length=128)]


class ImmutableModel(BaseModel):
    """Base for validated public values that must not change after evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DataClassification(str, Enum):
    """Application-assigned sensitivity label."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ExecutionMode(str, Enum):
    """Whether the application is processing synthetic or live data."""

    LIVE = "live"
    SYNTHETIC = "synthetic"


class RuleEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class DecisionStatus(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class ReasonCode(str, Enum):
    ALLOWED_BY_RULE = "allowed_by_rule"
    CLASSIFICATION_NOT_SUPPORTED = "classification_not_supported"
    ENVIRONMENT_NOT_SUPPORTED = "environment_not_supported"
    EXPLICIT_DENY = "explicit_deny"
    NO_MATCHING_ALLOW = "no_matching_allow"
    PURPOSE_NOT_SUPPORTED = "purpose_not_supported"
    SYNTHETIC_ONLY_PROVIDER = "synthetic_only_provider"
    UNKNOWN_PROVIDER = "unknown_provider"
    UNKNOWN_PURPOSE = "unknown_purpose"


class Purpose(ImmutableModel):
    id: Identifier
    description: Annotated[str, Field(min_length=1, max_length=240)]


class ProviderCapability(ImmutableModel):
    id: Identifier
    classifications: frozenset[DataClassification] = Field(min_length=1)
    purposes: frozenset[Identifier] = Field(min_length=1)
    environments: frozenset[Identifier] = Field(min_length=1)
    synthetic_only: StrictBool = False


class PolicyRule(ImmutableModel):
    id: Identifier
    effect: RuleEffect
    classifications: frozenset[DataClassification] = Field(min_length=1)
    purposes: frozenset[Identifier] = Field(min_length=1)
    providers: frozenset[Identifier] = Field(min_length=1)
    environments: frozenset[Identifier] = Field(min_length=1)
    execution_modes: frozenset[ExecutionMode] = Field(min_length=1)


class Policy(ImmutableModel):
    """Policy schema version 1. Unknown fields and versions are rejected."""

    schema_version: Literal["1"]
    policy_id: Identifier
    purposes: tuple[Purpose, ...] = Field(min_length=1)
    providers: tuple[ProviderCapability, ...] = Field(min_length=1)
    rules: tuple[PolicyRule, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> Policy:
        purpose_ids = [purpose.id for purpose in self.purposes]
        provider_ids = [provider.id for provider in self.providers]
        rule_ids = [rule.id for rule in self.rules]
        for label, identifiers in (
            ("purpose", purpose_ids),
            ("provider", provider_ids),
            ("rule", rule_ids),
        ):
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"duplicate {label} id")

        known_purposes = set(purpose_ids)
        known_providers = set(provider_ids)
        for provider in self.providers:
            unknown = set(provider.purposes) - known_purposes
            if unknown:
                raise ValueError(f"provider {provider.id!r} refers to unknown purposes")
        for rule in self.rules:
            if set(rule.purposes) - known_purposes:
                raise ValueError(f"rule {rule.id!r} refers to unknown purposes")
            if set(rule.providers) - known_providers:
                raise ValueError(f"rule {rule.id!r} refers to unknown providers")
        return self


class ExecutionContext(ImmutableModel):
    environment: Identifier
    mode: ExecutionMode = ExecutionMode.LIVE
    dry_run: StrictBool = False


class EgressIntent(ImmutableModel):
    """Payload-free metadata supplied to policy evaluation."""

    schema_version: Literal["1"] = "1"
    classification: DataClassification
    purpose: Identifier
    provider: Identifier
    context: ExecutionContext


class DecisionReceipt(ImmutableModel):
    """Privacy-safe evidence. No payload, endpoint, or arbitrary context is accepted."""

    schema_version: Literal["1"] = "1"
    receipt_id: str
    evaluated_at: datetime
    policy_id: Identifier
    policy_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    status: DecisionStatus
    reason_codes: tuple[ReasonCode, ...]
    provider: Identifier
    classification: DataClassification
    purpose: Identifier
    environment: Identifier
    execution_mode: ExecutionMode
    dry_run: StrictBool
    matched_rule_ids: tuple[Identifier, ...]


class Decision(ImmutableModel):
    schema_version: Literal["1"] = "1"
    status: DecisionStatus
    reason_codes: tuple[ReasonCode, ...]
    matched_rule_ids: tuple[Identifier, ...]
    receipt: DecisionReceipt

    @property
    def allowed(self) -> bool:
        return self.status is DecisionStatus.ALLOW

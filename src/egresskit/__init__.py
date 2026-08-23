"""Public EgressKit API."""

from .errors import EgressKitError, EgressRefused, PolicyLoadError, SerializationFailed
from .models import (
    DataClassification,
    Decision,
    DecisionReceipt,
    DecisionStatus,
    EgressIntent,
    ExecutionContext,
    ExecutionMode,
    Policy,
    PolicyRule,
    ProviderCapability,
    Purpose,
    ReasonCode,
    RuleEffect,
)
from .policy import PolicyEvaluator, load_policy, policy_digest, policy_json_schema
from .transport import DispatchResult, GuardedAsyncTransport, GuardedTransport

__all__ = [
    "DataClassification",
    "Decision",
    "DecisionReceipt",
    "DecisionStatus",
    "DispatchResult",
    "EgressIntent",
    "EgressKitError",
    "EgressRefused",
    "ExecutionContext",
    "ExecutionMode",
    "GuardedAsyncTransport",
    "GuardedTransport",
    "Policy",
    "PolicyEvaluator",
    "PolicyLoadError",
    "PolicyRule",
    "ProviderCapability",
    "Purpose",
    "ReasonCode",
    "RuleEffect",
    "SerializationFailed",
    "load_policy",
    "policy_digest",
    "policy_json_schema",
]

__version__ = "0.1.0"

"""Public EgressKit API."""

from .destination import (
    BoundGuardedAsyncTransport,
    BoundGuardedTransport,
    Destination,
    DestinationBindings,
)
from .errors import (
    DestinationRefused,
    EgressKitError,
    EgressRefused,
    PolicyLoadError,
    SerializationFailed,
    TestSuiteLoadError,
)
from .explanation import (
    DecisionExplanation,
    decision_explanation_json_schema,
    explain_decision,
)
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
from .policy_lint import (
    PolicyLintCode,
    PolicyLintDiagnostic,
    PolicyLintReport,
    lint_policy,
    policy_lint_report_json_schema,
)
from .policy_tests import (
    PolicyTestCase,
    PolicyTestCaseResult,
    PolicyTestReport,
    PolicyTestSuite,
    load_policy_test_suite,
    policy_test_suite_json_schema,
    run_policy_tests,
)
from .transport import DispatchResult, GuardedAsyncTransport, GuardedTransport

__all__ = [
    "BoundGuardedAsyncTransport",
    "BoundGuardedTransport",
    "DataClassification",
    "Decision",
    "DecisionExplanation",
    "DecisionReceipt",
    "DecisionStatus",
    "Destination",
    "DestinationBindings",
    "DestinationRefused",
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
    "PolicyLintCode",
    "PolicyLintDiagnostic",
    "PolicyLintReport",
    "PolicyLoadError",
    "PolicyRule",
    "PolicyTestCase",
    "PolicyTestCaseResult",
    "PolicyTestReport",
    "PolicyTestSuite",
    "ProviderCapability",
    "Purpose",
    "ReasonCode",
    "RuleEffect",
    "SerializationFailed",
    "TestSuiteLoadError",
    "decision_explanation_json_schema",
    "explain_decision",
    "lint_policy",
    "load_policy",
    "load_policy_test_suite",
    "policy_digest",
    "policy_json_schema",
    "policy_lint_report_json_schema",
    "policy_test_suite_json_schema",
    "run_policy_tests",
]

__version__ = "0.5.1"

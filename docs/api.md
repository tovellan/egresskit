# API

The supported public API is exported from `egresskit`. Symbols in other modules are not
covered by compatibility guarantees except `egresskit.testing` helpers.

## Load and evaluate

```python
from egresskit import EgressIntent, ExecutionContext, PolicyEvaluator, load_policy

policy = load_policy("policy.yaml")
evaluator = PolicyEvaluator(policy)
decision = evaluator.evaluate(
    EgressIntent(
        classification="internal",
        purpose="summarize",
        provider="processor_a",
        context=ExecutionContext(environment="production", mode="live"),
    )
)
```

`evaluate` never raises for a well-formed intent. Unknown declarations return a denial.
Policy and model validation errors occur before evaluation.

## Enforce dispatch

`GuardedTransport.dispatch(intent, payload, serializer)` returns `DispatchResult`. A
normal denial raises `EgressRefused`; its `to_dict()` method returns a machine-readable,
payload-free error. Serializer failures raise `SerializationFailed`. Exceptions from the
raw transport pass through unchanged.

Dry-run dispatch always returns after evaluation with `serialized=False`, `sent=False`,
and `response=None`. Inspect `result.decision.allowed` for the hypothetical outcome.

`GuardedAsyncTransport` provides the same contract for async transports and accepts a
sync or async serializer.

For destination enforcement, construct `DestinationBindings` with an exact canonical
HTTPS URL for each provider and use `BoundGuardedTransport` or
`BoundGuardedAsyncTransport`. An allowed request resolves its provider binding before
the serializer runs. An unknown binding raises `DestinationRefused` with the reason
`provider_unbound`. `DestinationBindings.require(provider, destination)` lets an adapter
verify a caller-selected destination and raises the reason `destination_mismatch` when
it differs.

The bound raw transport receives `send(destination: Destination, body: bytes)`. EgressKit
has no HTTP client dependency. See [Destination binding](destinations.md) for the adapter
boundary.

## Declarative policy tests

`load_policy_test_suite()` loads a strict versioned YAML or JSON suite.
`run_policy_tests(evaluator, suite)` returns a deterministic `PolicyTestReport`.
`policy_test_suite_json_schema()` exposes its JSON Schema. Test cases are required to be
synthetic and dry-run, and neither suites nor reports have a payload field. See
[Policy test suites](test-cases.md).

## Policy lint

`lint_policy(policy)` returns a deterministic `PolicyLintReport` with no runtime
evaluation, receipts, timestamps, or payload fields. It reports valid declarations that
cannot affect evaluation: policies with no rules, unreferenced purposes or providers,
and rules that cannot intersect any named provider's capability ceiling. Use
`policy_lint_report_json_schema()` for its versioned output schema. See
[Policy lint](policy-lint.md).

## Decisions and receipts

`Decision` contains status, reason codes, matched rule identifiers, and a receipt.
`DecisionReceipt` has a fixed schema and rejects extra fields. The receipt omits payloads,
payload hashes, endpoints, workload names, arbitrary attributes, and serialized data.

Classification, purpose, environment, and provider identifiers can still reveal system
metadata. Treat receipt storage as security telemetry and apply access controls and
retention limits.

## JSON Schema

Call `policy_json_schema()` or run `egresskit schema --kind policy` for the policy schema.
Call `policy_test_suite_json_schema()` or run `egresskit schema --kind tests` for the
test-suite schema. Both generated schemas currently use schema version 1.

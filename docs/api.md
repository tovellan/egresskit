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

## Decisions and receipts

`Decision` contains status, reason codes, matched rule identifiers, and a receipt.
`DecisionReceipt` has a fixed schema and rejects extra fields. The receipt omits payloads,
payload hashes, endpoints, workload names, arbitrary attributes, and serialized data.

Classification, purpose, environment, and provider identifiers can still reveal system
metadata. Treat receipt storage as security telemetry and apply access controls and
retention limits.

## JSON Schema

Call `policy_json_schema()` or run `egresskit schema`. The generated schema corresponds
to policy schema version 1.

# Architecture

EgressKit separates policy decisions from payload handling.

```text
application metadata -> PolicyEvaluator -> Decision + payload-free receipt
                              |
                              v allow
provider id -> exact DestinationBindings
                              |
                              v resolved
application payload  -> serializer -> bound Transport -> external provider
```

`PolicyEvaluator` receives an `EgressIntent`, which contains only classification,
purpose, provider identifier, environment, execution mode, and dry-run state. It never
receives the application payload.

`BoundGuardedTransport` owns the full order of operations. It evaluates metadata, stops
on denial, resolves the exact provider destination, invokes the caller's serializer,
then invokes the destination transport. The async variant keeps the same order. Dry runs
never serialize or send. Allowed dry runs still require a configured binding.

The raw transport is intentionally a small protocol. Applications can adapt an HTTP,
queue, SDK, or batch client behind it. A caller that accesses an unguarded network client
directly is outside EgressKit's enforcement boundary. The earlier `GuardedTransport`
remains available for compatibility where an application has its own independently
reviewed destination enforcement.

## Determinism

Policy evaluation has no network or environment-variable reads. Rules are set matches.
Deny rules override allow rules, and absence of an explicit allow is a denial. Receipt
identifiers and timestamps differ between evaluations, while status, reasons, matched
rules, and the canonical policy digest are deterministic.

## Package layout

- `models.py` defines immutable validated contracts.
- `policy.py` loads, validates, hashes, and evaluates policies.
- `transport.py` enforces pre-serialization sync and async dispatch.
- `destination.py` validates exact destinations and enforces provider bindings.
- `policy_tests.py` loads and runs versioned payload-free policy test suites.
- `errors.py` exposes machine-readable safe errors.
- `testing.py` provides explicitly synthetic intent and mock transports.
- `cli.py` exposes validation, decision, test, schema, and fixture commands.

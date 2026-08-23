# EgressKit

EgressKit is a Python policy gate for application payloads that may leave a trust
boundary. It decides whether an external provider may receive a declared data
classification for a declared purpose and execution context. Its guarded transports run
that decision before serialization and before any network call.

EgressKit does not discover sensitive data, redact content, or make legal compliance
claims. Applications must classify data correctly and bind provider identifiers to the
actual transport destinations they control.

## Status

Version 0.1.0 is the initial tagged release. The policy schema is versioned as `"1"`.
Unknown versions, fields, providers, purposes, and unmatched requests fail closed.

The Python package is not published to a package index. Install it from an approved
release archive or checked-out repository:

```console
python -m pip install .
```

Python 3.10 through 3.14 are supported.

## Complete synthetic example

Clone the repository, then run:

```console
python -m venv .venv
. .venv/bin/activate
python -m pip install .
egresskit validate examples/synthetic-policy.yaml
egresskit decide examples/synthetic-policy.yaml \
  --classification internal \
  --purpose test_processing \
  --provider mock_processor \
  --environment test \
  --mode synthetic
python examples/guarded_call.py
```

The example uses an in-memory transport and synthetic data. It makes no network call.

Application integration keeps the payload out of policy evaluation:

```python
import json

from egresskit import GuardedTransport, PolicyEvaluator, load_policy
from egresskit.testing import MockTransport, synthetic_intent

transport = MockTransport()
guarded = GuardedTransport(
    PolicyEvaluator(load_policy("examples/synthetic-policy.yaml")),
    transport,
)
result = guarded.dispatch(
    synthetic_intent(),
    {"record_id": "synthetic-001"},
    lambda value: json.dumps(value).encode(),
)
assert result.sent
```

For a refused request, `GuardedTransport` raises `EgressRefused` before the serializer is
called. In dry-run mode it returns the decision without serializing or sending, whether
the decision allows or denies the request.

## Policy semantics

A policy declares purposes, providers, provider capabilities, and rules. Evaluation is
deterministic:

1. The purpose and provider must be declared.
2. The provider must support the classification, purpose, and environment.
3. A synthetic-only provider rejects live execution.
4. Every applicable deny rule overrides allow rules.
5. At least one applicable allow rule is required.

Receipts contain policy and decision metadata only. They cannot contain a payload,
endpoint, or arbitrary application context. See [Policy schema](docs/policy-schema.md),
[API](docs/api.md), and [Threat model](docs/threat-model.md).

## CLI

The CLI emits JSON to support automation:

```console
egresskit validate POLICY
egresskit decide POLICY --classification LABEL --purpose ID \
  --provider ID --environment ID [--mode live|synthetic] [--dry-run]
egresskit schema
egresskit fixture
```

Exit code `0` means the command succeeded or the decision allowed egress. Exit code `2`
means input or policy validation failed. Exit code `3` means the decision denied egress.

## Development

Install [uv](https://docs.astral.sh/uv/) and run:

```console
uv sync --all-groups --locked
make ci
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[support policy](docs/support.md).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

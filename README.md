# EgressKit

EgressKit is a Python policy gate for application payloads that may leave a trust
boundary. It decides whether an external provider may receive a declared data
classification for a declared purpose and execution context. Its guarded transports run
that decision before serialization and before any network call.

EgressKit does not discover sensitive data, redact content, or make legal compliance
claims. Applications must classify data correctly and bind provider identifiers to the
actual transport destinations they control.

## Status

Version 0.5.3 adds enforced, forward-only privacy controls for public commit metadata.
It also rejects duplicate keys in policy and declarative test-suite documents and
includes optional sync and async HTTPX destination transports, deterministic
explanations, policy lint reports, exact provider destination bindings, and declarative
policy test suites. Every serialized contract is versioned. Unknown versions, fields,
providers, purposes, and unmatched requests fail closed.

The Python package is not published to a package index. Install from a release archive,
a checked-out repository, or the public Git repository:

```console
python -m pip install "egresskit @ git+https://github.com/tovellan/egresskit.git@v0.5.3"
```

Install the optional HTTPX adapter with:

```console
python -m pip install "egresskit[httpx] @ git+https://github.com/tovellan/egresskit.git@v0.5.3"
```

Python 3.10 through 3.14 are supported.

## Complete synthetic example

Clone the repository, then run:

```console
python -m venv .venv
. .venv/bin/activate
python -m pip install .
egresskit validate examples/synthetic-policy.yaml
egresskit lint examples/synthetic-policy.yaml
egresskit test examples/synthetic-policy.yaml examples/synthetic-tests.yaml
egresskit decide examples/synthetic-policy.yaml \
  --classification internal \
  --purpose test_processing \
  --provider mock_processor \
  --environment test \
  --mode synthetic
python examples/bound_call.py
```

The example uses an in-memory transport and synthetic data. It makes no network call.

Application integration keeps the payload out of policy evaluation:

```python
import json

from egresskit import (
    BoundGuardedTransport,
    DestinationBindings,
    PolicyEvaluator,
    load_policy,
)
from egresskit.testing import MockDestinationTransport, synthetic_intent

transport = MockDestinationTransport()
guarded = BoundGuardedTransport(
    PolicyEvaluator(load_policy("examples/synthetic-policy.yaml")),
    DestinationBindings({"mock_processor": "https://processor.example.test/v1"}),
    transport,
)
result = guarded.dispatch(
    synthetic_intent(),
    {"record_id": "synthetic-001"},
    lambda value: json.dumps(value).encode(),
)
assert result.sent
```

For a refused request, `BoundGuardedTransport` raises before the serializer is called.
It also refuses an allowed provider that has no exact destination binding. In dry-run
mode it returns the decision without serializing or sending. See
[Destination binding](docs/destinations.md) for DNS, redirect, and adapter guidance.
Applications using HTTPX can use the optional sync or async transports described in
[HTTPX integration](docs/httpx.md).

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
egresskit lint POLICY
egresskit explain POLICY --classification LABEL --purpose ID \
  --provider ID --environment ID [--mode live|synthetic] [--dry-run]
egresskit decide POLICY --classification LABEL --purpose ID \
  --provider ID --environment ID [--mode live|synthetic] [--dry-run]
egresskit schema [--kind policy|tests|lint|explanation]
egresskit test POLICY SUITE
egresskit fixture
```

Exit code `0` means the command succeeded or the decision allowed egress. Exit code `2`
means input or policy validation failed. Exit code `3` means the decision denied egress.
Exit code `4` means at least one declarative policy test failed.
Exit code `5` means policy lint diagnostics were found.

## Development

Install [uv](https://docs.astral.sh/uv/) and run:

```console
uv sync --all-groups --locked
make ci
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[public commit identity boundary](docs/public-history.md),
[protected releases](docs/releases.md), and [support policy](docs/support.md).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

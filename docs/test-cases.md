# Policy test suites

Declarative test suites capture expected decisions without including application
payloads. They are strict YAML or JSON objects with schema version `"1"`.

```yaml
schema_version: "1"
suite_id: synthetic_policy_contract
cases:
  - id: allow_fixture
    intent:
      classification: internal
      purpose: test_processing
      provider: mock_processor
      context:
        environment: test
        mode: synthetic
        dry_run: true
    expected_status: allow
    expected_reason_codes:
      - allowed_by_rule
```

Every case must use synthetic execution mode and enable dry-run. Unknown fields are
rejected, so a `payload` field is invalid at every model boundary. Case identifiers must
be unique. Duplicate JSON object keys and YAML mapping keys are rejected at every
nesting level. Expected reason codes are optional; when present, comparison is exact
after canonical ordering.

Run a suite with:

```console
egresskit test POLICY SUITE
```

The command writes a deterministic JSON report containing case identifiers, expected and
actual status, expected and actual reason codes, and counts. It omits decisions,
receipts, timestamps, destinations, and payload data. Exit code `0` means every case
passed, `2` means input was invalid, and `4` means at least one expectation failed.

Use `egresskit schema --kind tests` to generate the JSON Schema. See
`examples/synthetic-tests.yaml` for an executable suite.

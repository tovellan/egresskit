# Policy lint

Policy validation proves that a file has the version 1 structure and only valid
references. Linting examines a valid policy for declarations that cannot affect an
evaluation.

```console
egresskit lint POLICY
```

The command emits a version 1 JSON report. Exit code `0` means no diagnostics were
found. Exit code `5` means the policy is valid but contains at least one diagnostic.
Invalid policy input still exits with code `2`.

Diagnostics are deterministic and contain only a code, object type, and object
identifier:

- `no_rules` means every request will fail closed because the policy has no rules.
- `unused_purpose` means no rule references the declared purpose.
- `unused_provider` means no rule references the declared provider.
- `unreachable_rule` means no provider named by the rule can intersect its
  classification, purpose, environment, and execution-mode conditions within that
  provider's capability ceiling.

Linting does not evaluate an intent and does not create a decision receipt. Its report
has no payload, destination, timestamp, or arbitrary context field. Treat object
identifiers as operational metadata when storing reports.

Applications can call `lint_policy(policy)` directly or use
`policy_lint_report_json_schema()` to validate report consumers.

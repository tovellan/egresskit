# Policy schema version 1

Policies are YAML or JSON objects with four required sections:

- `schema_version` must be the string `"1"`.
- `policy_id` is a stable identifier.
- `purposes` declares every permitted processing purpose.
- `providers` declares each provider's maximum capabilities.
- `rules` contains explicit allow and deny conditions.

Identifiers start with a lowercase letter and contain lowercase letters, digits, dots,
underscores, or ASCII hyphens. Unknown fields are invalid.

Provider capabilities are ceilings, not grants. A request within the capability ceiling
still needs a matching allow rule. An explicit matching deny rule wins over any matching
allow rule.

The four classifications are `public`, `internal`, `confidential`, and `restricted`.
They are labels, not an ordered hierarchy. A provider must list each accepted label.

Execution mode is `live` or `synthetic`. Set `synthetic_only: true` on providers that
must never receive live application data. This check is independent of rules.

See `examples/synthetic-policy.yaml` for the complete format. Use `egresskit validate`
in CI before deploying a policy.

## Versioning

The schema version covers serialized policy structure and evaluation semantics. An
incompatible schema uses a new value. Version 0.2.x rejects any unsupported value.

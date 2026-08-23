# Threat model

## Security objective

Stop a payload from being serialized or sent through an EgressKit guarded transport
unless its declared metadata is explicitly allowed by a valid local policy.

## Trusted components

- The application assigns accurate classifications, purposes, and execution context.
- Policy files and application code are protected from unauthorized modification.
- The application routes egress through a bound guarded transport.
- The destination transport uses the supplied destination without substitution.
- The Python process and dependency environment are trusted.

## Addressed threats

- Unknown or misspelled providers and purposes fail closed.
- Missing allow rules fail closed.
- Provider capability limits cannot be expanded by an allow rule.
- Deny rules override matching allow rules.
- Refusals occur before serializer side effects.
- Dry runs never serialize or send.
- Decision receipts and EgressKit errors cannot accept protected payload fields.
- Ordinary serialization failures discard serializer exceptions, causal chains, and
  payload data from standard formatted tracebacks.
- Serializer results must be exact built-in bytes, so active subclasses cannot alter a
  body after the serialization boundary.
- Strict schema validation rejects unknown policy fields and unsupported versions.
- Security-sensitive boolean fields reject string and numeric coercion.
- Unknown provider destination bindings fail before serialization.
- Canonical HTTPS destination bindings reject credentials, queries, fragments, encoded
  paths, dot segments, and noncanonical hosts.
- Destination values reject active subclasses that could change a validated URL later.
- Declarative policy test suites require synthetic dry-run intents and reject payload
  fields.

## Out of scope

- Discovering PII, secrets, regulated records, or misclassified data inside a payload.
- Preventing code from bypassing EgressKit and calling a network library directly.
- Operating-system network confinement, service-mesh policy, endpoint attestation, DNS
  resolution security, TLS identity beyond the client defaults, credential controls, or
  destination identity.
- Redirect enforcement inside an HTTP client unless its adapter disables redirects or
  validates every redirect target against the original binding.
- Protecting a compromised process, dependency, policy author, or transport adapter.
- Preventing observability tools from capturing payloads in caller source lines, frame
  locals, raw transport exceptions, or application-managed logs.
- Sanitizing process-control exceptions such as cancellation, `KeyboardInterrupt`, or
  `SystemExit`; guarded transports propagate them unchanged.
- Proving consent, legality, residency, or compliance.
- Encrypting or signing receipts.
- Preventing metadata disclosure from receipt storage.

For higher assurance, combine EgressKit with code review, outbound firewall rules, a
single approved transport adapter, policy-file integrity controls, and receipt-store
access limits.

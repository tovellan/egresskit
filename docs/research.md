# Clean-room research record

Reviewed 2026-08-24. Only public project documentation and repositories were used. The
implementation was designed independently for the narrow egress-authorization problem.
No third-party source code was copied or translated.

## Primary sources reviewed

- [Open Policy Agent documentation](https://www.openpolicyagent.org/docs/) describes a
  general policy decision engine that accepts arbitrary structured input and leaves
  enforcement to the integrating application.
- [Cedar documentation](https://docs.cedarpolicy.com/) describes authorization over
  principal, action, resource, and context with schema-based policy validation.
- [Microsoft Presidio documentation](https://microsoft.github.io/presidio/) describes
  detection and de-identification of sensitive data.
- [Google Sensitive Data Protection documentation](https://cloud.google.com/sensitive-data-protection/docs/inspecting-text)
  describes managed inspection and de-identification APIs.
- [NVIDIA NeMo Guardrails documentation](https://docs.nvidia.com/nemo/guardrails/latest/)
  describes programmable input, retrieval, dialog, execution, and output rails for LLM
  applications.
- [LLM Guard repository](https://github.com/protectai/llm-guard) describes scanners for
  prompt and output risks, including anonymization and sensitive output. The repository
  was archived when reviewed.
- [HTTPX transport documentation](https://www.python-httpx.org/advanced/transports/)
  informed the use of a small transport protocol without coupling the core package to a
  specific HTTP client.
- [Pydantic strict mode documentation](https://docs.pydantic.dev/latest/concepts/strict_mode/)
  informed schema validation tradeoffs.

## Decision

The maintained general authorization projects are broader than this problem. The data
protection systems inspect or transform payloads. The guardrail projects focus on model
content and behavior. EgressKit therefore does not introduce a general policy language or
a scanner. It supplies a local, typed policy and a small enforcement point specifically
for data classification, processing purpose, provider capability, and runtime context.

The differentiating constraint is ordering: policy evaluation sees only metadata, and
the guarded transport does not invoke serialization until the request is allowed. The
receipt schema structurally excludes payloads and payload-derived values.

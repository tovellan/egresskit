# Changelog

This project follows Semantic Versioning for the Python package. Policy format
compatibility is additionally governed by `schema_version`.

## 0.4.0 - 2026-08-24

- Add deterministic, versioned decision explanations without receipt UUIDs or timestamps.
- Add the `egresskit explain` command for stable allow and deny inspection in CI.
- Expose JSON Schemas for lint reports and decision explanations through the CLI.

## 0.3.0 - 2026-08-24

- Add deterministic, versioned, payload-free policy lint reports.
- Report no-rule policies, unused purposes and providers, and unreachable rules.
- Add the `egresskit lint` command with a dedicated CI exit code.
- Correct the synthetic example so every rule can intersect provider capabilities.
- Align contribution guidance with the repository's sole-author commit policy.

## 0.2.1 - 2026-08-24

- Reject resolver-ambiguous legacy hexadecimal IPv4 destination spellings.
- Preserve ordinary DNS names that contain hexadecimal-looking labels.

## 0.2.0 - 2026-08-24

- Add canonical HTTPS destinations and immutable exact provider bindings.
- Add sync and async bound guarded transports that resolve destinations before
  serialization.
- Add safe, machine-readable refusals for unbound providers and destination mismatches.
- Add version 1 payload-free, synthetic-only declarative policy test suites.
- Add deterministic policy test reports, JSON Schema, and the `egresskit test` command.
- Document adapter, DNS, redirect, and network-boundary responsibilities.

## 0.1.0 - 2026-08-24

- Add typed classification, purpose, provider capability, and execution context models.
- Add version 1 strict policy validation and fail-closed deny-overrides evaluation.
- Add payload-free decisions and receipts.
- Add sync and async pre-serialization guarded transports.
- Add dry-run behavior, synthetic fixtures, mock transports, and a JSON CLI.
- Add tests, packaging, security checks, and public project documentation.

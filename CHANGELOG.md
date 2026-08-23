# Changelog

This project follows Semantic Versioning for the Python package. Policy format
compatibility is additionally governed by `schema_version`.

## 0.5.4 - 2026-08-24

- Discard ordinary serializer exception chains so standard errors and tracebacks remain
  payload-free after authorization while process-control exceptions still propagate.
- Reject HTTPX defaults and hooks that can change an exact bound destination.
- Accept every Python awaitable serializer form while rejecting non-byte results.
- Make evaluator policy state read-only so rules, capabilities, and digests cannot drift.
- Reject coercive security booleans, empty URL delimiters, and bracketed non-IPv6 hosts.
- Version top-level intents, decisions, CLI argument errors, and structured errors.
- Publish future releases from complete drafts and verify GitHub-native immutability and
  exact asset digests.
- Require a current independent approval in branch protection and the checked merge
  preflight.

## 0.5.3 - 2026-08-24

- Add a forward-only public commit identity audit anchored at the v0.5.1 baseline.
- Require the exact organization identity for write-linked accounts while preserving
  linked, privacy-safe outside-contributor provenance.
- Add a base-anchored trusted check and a guarded exact-head fast-forward workflow.
- Protect every `v*` tag from updates or deletion and create future releases as
  annotated tags through the checked release workflow.
- Reject merge commits and authorship, signoff, or generator trailers after the baseline.
- Record the sole pre-enforcement metadata exception without rewriting published history.

## 0.5.2 - 2026-08-24

- Reject duplicate keys at every nesting level in JSON and YAML policies.
- Reject repeated YAML merge keys and collisions introduced by mapping merges.
- Apply the same strict parsing contract to declarative policy test suites.
- Reject nonstandard JSON constants and oversized integers as structured load errors.
- Return structured load errors for non-UTF-8 policy and test-suite documents.

## 0.5.1 - 2026-08-24

- Add a safe legacy issue-template fallback so GitHub detects complete community health
  metadata while preserving the structured issue forms.

## 0.5.0 - 2026-08-24

- Add optional sync and async HTTPX destination transports.
- Force redirect following off for every adapter request, including clients configured
  to follow redirects by default.
- Add network-free HTTPX mock integration and redirect tests.

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

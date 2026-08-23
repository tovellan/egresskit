# Dependency and license review

Reviewed for version 0.5.3 on 2026-08-24.

The runtime has two direct dependencies:

- Pydantic 2.x is MIT licensed and provides validated immutable models and JSON Schema.
- PyYAML 6.x is MIT licensed and provides safe YAML parsing through a restricted loader.

Both licenses are compatible with distribution of EgressKit under Apache License 2.0.
Dependencies are installed separately and are not vendored or copied into release
artifacts. No dependency notice requires an EgressKit `NOTICE` file.

HTTPX 0.x is an optional BSD-3-Clause dependency for the `httpx` extra. Its transitive
runtime dependencies are installed separately and are not bundled. The default EgressKit
installation does not install HTTPX.

Development and build dependencies are locked in `uv.lock`. They are not runtime
dependencies and are not bundled. `pip-audit` checks the locked environment during the
quality gate. Dependency updates are proposed weekly through Dependabot.

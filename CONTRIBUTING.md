# Contributing

Small, focused changes are welcome. Open an issue before a policy-semantic or public API
change so compatibility and threat-model effects can be discussed.

## Development setup

```console
git clone https://github.com/tovellan/egresskit.git
cd egresskit
uv sync --all-groups --locked
make ci
```

Add tests for every behavior change. Security-boundary changes should include an
adversarial or property-based test. Documentation examples must remain executable.

By submitting a contribution, contributors confirm that they have the right to submit
the work under this repository's license. Maintainers use the configured organization
identity. Outside contributors use their linked GitHub login and its privacy-preserving
noreply address. Do not use another contributor's identity or add authorship, signoff,
or generator trailers. The required identity check enforces the complete policy in
[Public commit identity boundary](docs/public-history.md).

Do not include personal data, credentials, real customer payloads, or proprietary
policies in tests or reports. Use synthetic fixtures.

Repository text must not contain Unicode en dash or em dash characters. Run `make ci`
before opening a pull request.

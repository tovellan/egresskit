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

Use the repository-configured Git identity as the sole commit author. Do not add
authorship or generator trailers. Contributors must have the right to submit their work
under this repository's license. Do not include personal data, credentials, real
customer payloads, or proprietary policies in tests or reports. Use synthetic fixtures.

Repository text must not contain Unicode en dash or em dash characters. Run `make ci`
before opening a pull request.

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
the work under this repository's license. Public commits and merge commits must use the
generic organization identity `Tovellan Maintainers <noreply@github.com>`. Do not publish
personal names or email addresses in commit metadata, and do not add authorship or
generator-attribution trailers. Do not include personal data, credentials, real customer
payloads, or proprietary policies in tests or reports. Use synthetic fixtures.

Repository text must not contain Unicode en dash or em dash characters. Run `make ci`
before opening a pull request.

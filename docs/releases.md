# Release integrity

Release tags matching `v*` are governed by an active tag ruleset that blocks every
update and deletion without a bypass. A new tag may still be created by a write-capable
actor, including the checked release workflow, but it cannot be moved or deleted after
creation. A creation-only GitHub Actions bypass is not available for this repository,
so the project does not claim that tag creation has a narrower actor boundary than the
documented trusted-write boundary.

The release workflow runs only from `main` and requires the exact package version and
40-character main commit SHA. It verifies both against the checked-out tree, runs the
complete quality gate, builds exact distributions, writes SHA-256 checksums, and then
creates an annotated tag with the maintainer identity. The quality gate includes a clean
wheel installation and executable examples. It re-reads remote `main` before tagging
and verifies the tag type, target, and tagger on a retry. It also verifies that the
remote tag peels to the expected commit before creating the GitHub release.

Repository release immutability is enabled. The workflow creates or safely resumes a
draft, uploads every distribution and checksum, and verifies the exact draft metadata
and GitHub-computed asset digests. It deliberately does not publish the draft because
the workflow token cannot read the repository administration setting that controls
release immutability.

Immediately before publication, the trusted administrator rechecks that the repository
immutable-releases API returns `enabled: true`, and re-verifies remote `main`, the
canonical annotated tag, the draft metadata, all asset names, and all asset digests. The
administrator then publishes the already complete draft. Publication is successful only
when the release API returns `immutable: true` and `gh release verify` validates the
automatically generated release attestation. GitHub then locks the release tag and
assets. The separate tag ruleset remains defense in depth. A workflow retry accepts only
the exact verified draft or the exact immutable, attested release.

The v0.5.3 API record originally reported `immutable: false`. After repository
immutability was enabled, GitHub finalized that release when its public release note was
corrected: the API now reports `immutable: true`, and `gh release verify` validates the
GitHub-generated attestation for its tag and all three assets. This current state
supersedes the earlier snapshot. Its annotated tag and underlying commit remain unsigned,
so the project does not describe the attestation as a maintainer signature.

Every release through v0.5.2 remains a mutable GitHub release object. Its checksum file
is stored beside mutable assets, so matching SHA-256 values are reproducibility evidence
rather than an independent signature. Branch policy does not require signed commits, and
the project does not claim signature-backed provenance for those historical releases.

Tags through v0.5.2 were created as lightweight tags before this boundary. They remain
unchanged, and the immutability ruleset now prevents them from being moved or deleted.
The project does not claim that those historical tags were retroactively annotated.

Branch protection requires the pull-request path but requires zero approving reviews
while the project has one maintainer. Administrators remain subject to the required
checks, linear history, resolved-conversation, and no-force-push controls, and no user,
team, or app has a pull-request bypass allowance. The checked merge still binds the
current pull request, main commit, audited head, trusted identity check, and resolved
review conversations immediately before the fast-forward. A future multi-maintainer
project can restore an independent approval requirement without changing the release
artifact boundary.

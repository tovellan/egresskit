# Protected releases

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

Tags through v0.5.2 were created as lightweight tags before this boundary. They remain
unchanged, and the immutability ruleset now prevents them from being moved or deleted.
The project does not claim that those historical tags were retroactively annotated.

Branch protection intentionally requires no GitHub approval while the project has no
independent maintainer approver. A second administrative credential controlled by the
same owner would not constitute independent review, and requiring one approval would
otherwise deadlock the checked release path. The maintainer still inspects every change
and all required checks must pass. One approval should become mandatory when an
independent maintainer is available.

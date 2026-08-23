# Public commit identity boundary

Public Git history is permanent project metadata. EgressKit applies a forward-only
identity boundary after the frozen v0.5.1 commit
`969789f845ee5df38f5e518220e5e72e029803a7`.

Reachable commits at or before that boundary still contain historical identity fields
and attribution trailers that do not meet the current rule. Closed pull-request metadata
also preserves historical head branch names after live branches are deleted. Removing
that exposure would require an explicitly authorized rewrite of commits, tags, releases,
and hosting metadata. No such rewrite has been authorized or performed, so this control
does not claim zero historical identity exposure.

Maintainer-authored commits use exactly:

```text
Tovellan Maintainers <tovellan@users.noreply.github.com>
```

Outside contributors use the login embedded in their linked modern
`ID+LOGIN@users.noreply.github.com` address as the commit name. The stable numeric ID is
matched to GitHub's account ID, so a later username change does not invalidate history.
Legacy noreply addresses are not accepted because they lack that durable binding.
Outside contributors must not use the maintainer identity. The exact documented service
account is `github-actions[bot]`. GitHub `web-flow`
association alone is not accepted as provenance because its raw identity fields can be
copied into a locally created commit. Attribution, signoff, and generator trailers are
not accepted, including synonymous `-by` and `-with` forms. Merge commits are not
accepted. Automated dependency proposals must be recreated as a conforming maintainer
commit before they can enter `main`.

The service allowlist is exact:

| Commit identity | Linked account | Account ID |
|---|---|---:|
| `github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>` | `github-actions[bot]` | `41898282` |

The boundary has three controls:

1. A base-anchored `pull_request_target` workflow reads raw commit metadata through the
   GitHub API without checking out or executing pull-request code. It resolves each
   author and committer account separately and posts the required `identity` check on
   the exact head commit. Pull requests above 100 commits fail closed and must be split
   so the audit reads the complete commit range in one API response.
2. An active update ruleset with no bypass seals `main` between changes. For an update,
   an administrator opens a bounded window by disabling that exact rule, dispatches the
   checked fast-forward workflow, and immediately reactivates it. The workflow refuses
   a missing, altered, active, or bypassable rule. It re-runs the identity audit, relies
   on strict protected-branch checks, updates with `force: false`, re-reads the final ref
   and raw identities, and waits for the rule to be active again before succeeding.
3. The local repository audit checks privacy syntax for every reachable commit after
   the v0.5.1 baseline. A hosted main-history workflow separately resolves GitHub
   accounts and permissions on every commit after that baseline. Both emit diagnostics
   without echoing rejected names or addresses. The sole historical exception must keep
   its exact expected violation-code set.

Maintainer changes are committed once with the configured identity, tested on a pull
request, and fast-forwarded to `main` only after every required check passes. This keeps
the reviewed commit object intact instead of asking the hosting platform to synthesize
a replacement commit. GitHub does not allow its built-in Actions integration as a
bypass actor for this repository's ruleset, so the bounded update window trusts the
administrator and workflows already present on `main`. A dedicated merger application
would remove that window and defend against a malicious write actor, but it is outside
the keyless project boundary.

Commit `102f8dab03d5f7e079525e25c54afd0670a0972e` was created by the hosting platform
before these controls became active and is the audit's sole recorded exception. The
project does not rewrite published history and does not claim that the exception was
repaired. Any new exception fails the required check.

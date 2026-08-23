# Public commit identity boundary

Public Git history is permanent project metadata. EgressKit applies a forward-only
identity boundary after the frozen v0.5.1 commit
`969789f845ee5df38f5e518220e5e72e029803a7`.

Maintainer-authored commits use exactly:

```text
Tovellan Maintainers <tovellan@users.noreply.github.com>
```

Outside contributors use their linked GitHub login as the commit name and that account's
modern or legacy `@users.noreply.github.com` address. They must not use the maintainer
identity. The exact documented service account is `github-actions[bot]`. GitHub `web-flow`
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
2. An active update ruleset blocks user-driven changes to `main`. The checked
   fast-forward workflow is the only configured integration bypass. It re-runs the
   identity audit, relies on strict protected-branch checks, updates with `force: false`,
   and re-reads both the final ref and raw identities before succeeding.
3. The local repository audit checks privacy syntax for every reachable commit after
   the v0.5.1 baseline. A hosted main-history workflow separately resolves GitHub
   accounts and permissions on every commit after that baseline. Both emit diagnostics
   without echoing rejected names or addresses. The sole historical exception must keep
   its exact expected violation-code set.

Maintainer changes are committed once with the configured identity, tested on a pull
request, and fast-forwarded to `main` only after every required check passes. This keeps
the reviewed commit object intact instead of asking the hosting platform to synthesize
a replacement commit. The built-in automation boundary trusts repository write actors
and the workflows already present on `main`; a dedicated merger application would be
required to defend against a malicious write actor and is outside the keyless project
boundary.

Commit `102f8dab03d5f7e079525e25c54afd0670a0972e` was created by the hosting platform
before these controls became active and is the audit's sole recorded exception. The
project does not rewrite published history and does not claim that the exception was
repaired. Any new exception fails the required check.

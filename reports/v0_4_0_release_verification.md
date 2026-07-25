# AgentGauge v0.4.0 — release, rename, and verification

Closes the full ship sequence: PR #64 merge → PyPI Trusted Publishing setup →
distribution rename (`agentgauge` was taken) → publish → independent
verification against the tagged commit.

## What shipped

- **PyPI**: `agentgauge-harness` 0.4.0, https://pypi.org/project/agentgauge-harness/0.4.0/
- **GitHub Release**: https://github.com/gaurav-gandhi-2411/agentgauge/releases/tag/v0.4.0
- **Tag**: `v0.4.0` → commit `e41f7b5` on `main`
- **Import package / CLI command**: unchanged, still `agentgauge` (only the
  PyPI distribution name changed)
- **Publish mechanism**: GitHub Actions Trusted Publishing (OIDC) — no PyPI
  token ever generated, handled, or stored by this session

## Rename: why, and what was and wasn't touched

PyPI rejected the plain name `agentgauge` as an ultranormalization collision
with an existing project. The pending publisher was re-registered on
pypi.org as `agentgauge-harness`. Only `pyproject.toml`'s `[project].name`
changed (plus the regenerated `uv.lock` name field); `[project.scripts]`
(`agentgauge = "agentgauge.cli:app"`) and
`[tool.hatch.build.targets.wheel]`'s `packages = ["agentgauge"]` were
untouched by design. Every `pip install agentgauge` reference was found and
corrected: the GitHub Action template in `agentgauge/cli.py`'s
`_GITHUB_ACTION_TEMPLATE`, and README.md's Install section — which, on
inspection, had never had an end-user `pip install` line at all (only the
git-clone dev path), so one was added rather than merely renamed, since the
package is now genuinely publishable. `reports/capability_statement.md` and
`docs/` had no install instructions to touch.

## Two real issues found and fixed mid-task, not swept under

1. **GitHub Release silently flipped to draft with a broken URL.** Moving
   the `v0.4.0` tag (`git tag -d` + recreate, required because the original
   tag predated both `release.yml` and the rename) caused the existing
   GitHub Release object — still correctly referencing `tag_name: "v0.4.0"`
   internally — to show `draft: true` and an `https://.../releases/tag/untagged-...`
   URL. `gh release edit` alone did not fix it; a direct
   `gh api --method PATCH .../releases/<id> -f draft=false` did. Verified
   healthy afterward (`isDraft: false`, correct URL).
2. **A false-alarm wheel mismatch, caused by my own local Windows checkout.**
   Comparing the published wheel's file hashes against a *locally rebuilt*
   wheel showed every single file differing — including the static
   `LICENSE` file, which should never vary with source content. Root cause:
   this repo's Windows checkout has `core.autocrlf`-style LF→CRLF
   conversion (visible throughout this whole project's git output as
   "LF will be replaced by CRLF"), while the GitHub Actions Linux runner
   checks out pure LF. The wheel's *content* was never wrong — only the
   comparison method was. Corrected by comparing the published wheel
   against `git show v0.4.0:<path> | sha256sum` (the raw git blob, immune
   to local checkout line-ending conversion) instead of a local rebuild —
   this is the only verification method that actually proves "the publish
   matches the tagged commit," and it's what the independent verifier used.

## Independent verification

A separate verifier agent re-derived every claim from primary sources
(downloaded the actual published wheel via its real PyPI JSON API URL — not
a WebFetch-summarized digest, which was found to garble binary hex during
an earlier attempt in this same task — and compared file-by-file against
git blobs at the tag).

**Result: all 5 items CONFIRMED, no discrepancies.**

1. Tag `v0.4.0` → commit `e41f7b5` → on `main`. Confirmed via
   `git show`/`git rev-list`/`git branch --contains`, independently.
2. Published wheel content vs. tagged-commit git blobs: **24/24 `.py`
   files matched exactly**, plus `LICENSE`. (One transient false mismatch
   during the verifier's own first pass, traced to a shell quoting bug in
   its comparison script, not a real discrepancy — re-verified with a
   Python-based comparator and confirmed clean.)
3. Distribution/import split: `entry_points.txt` confirms
   `agentgauge = agentgauge.cli:app`; wheel's top-level package directory
   is `agentgauge/`, not `agentgauge_harness/`; `METADATA` confirms
   `Name: agentgauge-harness`.
4. Fresh `pip install agentgauge-harness --no-cache` in an independently
   created venv: `agentgauge --version` → `agentgauge 0.4.0`;
   `agentgauge lint examples/call_constraints_server_fixed.py` →
   `No violations found.` Both exit code 0.
5. GitHub Release: `isDraft: false`, correct tag URL, install line reads
   `pip install agentgauge-harness`.

## What this does not cover

No new measurement, no new fixture, no new lint rule — this task was
packaging and distribution only, per its own explicit scope. All product
claims (MDE=0.0537, the BLOCKING causal effect, the argument-degradation
null) are unchanged from `reports/v2_product_readiness.md` and
`reports/capability_statement.md`; this report only concerns whether the
package that ships those claims actually installs and runs as documented,
from the exact commit it claims to be built from.

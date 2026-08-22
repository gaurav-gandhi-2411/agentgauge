# Releasing agentgauge

This repo had no written release process before this document — releases were tag-triggered
(`release.yml`, PyPI Trusted Publishing/OIDC, publishing `agentgauge-harness`) but the actual
steps lived only in whoever ran them last time. Written after running the flow for real (`0.5.3`).

## The flow

1. **Bump the version** in both places — nothing derives one from the other:
   - `pyproject.toml`: `[project].version`
   - `agentgauge/__init__.py`: `__version__`
   - Run `uv sync` afterward so `uv.lock`'s own self-referential version resyncs — this exact
     class of drift has bitten the sibling `tracegauge`/`adk-tracegauge` repos before.
2. **This repo has no `CHANGELOG.md`** — release notes are written directly as the GitHub
   Release body at tag time (see `gh release view v0.5.2` for the existing convention: real
   hand-authored prose sections, not auto-generated "What's Changed" text). Order findings by
   severity, not by discovery order — a real CVE fix leads, a docs correction trails.
3. **Every example config/doc code block presented as copy-pasteable actually reflects the
   shipped code's real defaults, and every runnable example actually runs.** Real incident:
   `configs/provider.openai_compatible.yaml`/`provider.custom_endpoint.yaml` explicitly set
   `cost_ceiling_usd: .inf`, silently contradicting the other three adapters' finite default —
   found in a cross-repo audit, not by anyone re-checking the example files against the code
   they're meant to demonstrate.
4. **Every version pin in the papers and their submission docs is re-checked against the
   version this release is about to publish.** Real incident (BL2): `docs/paper2/main.tex`'s
   reproduction-instructions appendix and `docs/paper2/SUBMISSION.md`'s code-availability
   section both still cited `agentgauge-harness==0.5.2` after `0.5.3` had already shipped --
   found in a cross-repo audit, not by anyone re-checking the papers against the version they
   were published from. Grep both papers' `.tex` files and `docs/paper2/SUBMISSION.md` for
   `agentgauge-harness==` and `agentgauge==` before every tag.
5. **Commit and open a PR.** CI (`verify`/`hygiene`/`pip-audit`) runs against the version-bumped
   code. Merge once green — never self-merge.
6. **Tag the merged commit and push the tag:**
   ```bash
   git checkout main && git pull
   git tag vX.Y.Z <merged-commit-sha>   # the exact commit, not blindly HEAD
   git push origin vX.Y.Z
   ```
7. **`release.yml` takes it from there** — triggered by the `v*` tag push, builds from that
   exact tag ref (never a branch head), `twine check`s the artifact, publishes via
   `pypa/gh-action-pypi-publish@release/v1` using OIDC. Confirm it actually succeeded — read
   the log for the real upload confirmation (a Sigstore `Successfully verified SCT...` line and
   `View at: https://pypi.org/project/agentgauge-harness/X.Y.Z/`), not just a green checkmark.
8. **Post-publish verify from a fresh environment against the real index** — PyPI index
   propagation can lag the workflow's own success by several minutes; a failed install
   immediately after publish is not necessarily a real failure, re-check before concluding one.
   Confirm `agentgauge --version` reports the new version, and re-run whatever specific behavior
   this release changed against the actual published artifact — not the local build.
9. **Do not yank or delete a published version, ever.** PyPI does not allow re-uploading a
   version's metadata; a wrong claim in a published README stays wrong for that version
   permanently. Ship a new version that supersedes it instead.

# Changelog

All notable changes to **agentgauge-harness** (the PyPI distribution; the CLI and import name are
`agentgauge`). Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

**How this file was made.** Until now this repo had no CHANGELOG; release notes lived only in each
GitHub Release body. The entries below were reconstructed on 2026-10-08 from the tags (release dates
are the tag dates, which match the PyPI upload dates), the GitHub Release bodies (`gh release view
vX.Y.Z`) and the commit ranges between tags (`git log vA..vB`). Where a Release body and the commits
disagree the commits are the record. Measured figures are quoted from the Release bodies and are not
re-measured here; their provenance is in `reports/` at each tag.

## [Unreleased]

Nothing under `agentgauge/` or in `pyproject.toml` has changed since 0.5.3
(`git diff --stat v0.5.3 origin/main -- agentgauge pyproject.toml` is empty); the commits since the
tag are documentation, CI and dependency-lockfile updates:

- `uv.lock`: `pyjwt` 2.13.0 -> 2.15.0, which cleared a red `pip-audit` check (#112), and minor/patch
  groups (#92, #113). `pyjwt` is transitive; it is not a direct dependency.
- CI: stale action pins fixed, daily Dependabot cadence for GitHub Actions (#109); a
  manifest-provenance gate (#88).
- Docs and papers: README badges and a bug-report template (#108); brand hero image (#107);
  corrections to the two papers and their submission notes (#98-#101, #103-#106); consistency-check
  scripts for the papers (#100, #102); a version-pin checklist in `RELEASING.md` (#105).

## [0.5.3] - 2026-08-21

- **Security:** `cryptography` bumped to 50.0.0 (PYSEC-2026-3552). 0.5.2 was tagged just before this fix
  landed on `main` (#91).
- **Fixed an unbounded-spend gap:** the `openai_compatible` and `custom_endpoint` adapters defaulted
  `cost_ceiling_usd` to infinity, unlike the other three paid adapters (finite $5.0 default, enforced
  before and after each call). Fixed in code and in the two bundled example configs that set `.inf`
  explicitly (#95).
- **Corrected an overstated README claim** about multi-culprit attribution (#95). The product decision to
  keep `agentgauge attribute` gated `--experimental` is unaffected; it rests on cost.
- Added `RELEASING.md`. Full suite at release: 1049 passed, 93.52% coverage (from the release notes).

## [0.5.2] - 2026-07-30

- **Security:** nine `pip-audit` findings cleared (cryptography, mcp, pydantic-settings,
  python-multipart, starlette, all transitive via `mcp`); `mcp` 1.27.2 -> 1.29.0 (#68).
- **Every direct dependency now has an upper bound** (`>=X,<NEXT_MAJOR`), closing the gap that broke
  0.4.0 and 0.5.0 (#68).
- **A daily PyPI-install canary** (`pypi-canary.yml`) installs the published package in a clean
  environment, runs `--version` and the quickstart, and opens an issue on failure (#70, #71).
- `pip-audit` is a blocking CI check and a required status check (#70).

## [0.5.1] - 2026-07-30

- **Fixed a broken install:** `mcp>=1.3.0` with no ceiling resolved to `mcp` 2.0.0 on a fresh install, which
  renamed `McpError` and crashed `agentgauge` on import. `mcp` is now pinned `<2.0.0` (#67).
  0.4.0 and 0.5.0 are affected; install 0.5.1 or later. Both stay on PyPI unmodified (PyPI versions are
  immutable).
- This is the first release whose notes describe the 0.5.0 features: six model adapters (`ollama`,
  `anthropic`, `openai_compatible`, `bedrock`, `vertex`, `custom_endpoint`) behind one config-driven
  interface (`--provider-config`), 100% replay determinism on all six (20/20 replays each), and per-run
  cost and timing accounting in `diff`/`eval` output.

## [0.5.0] - 2026-07-30 (superseded by 0.5.1; do not install)

- **Added** the model-adapter abstraction (shipped) and failure attribution (`agentgauge attribute`,
  gated `--experimental`, off by default) (#66); a machine-readable metrics manifest (#65).
- **Broken on a fresh install**: see 0.5.1.

## [0.4.0] - 2026-07-25 (first tagged release; broken on a fresh install, see 0.5.1)

- A statistical regression harness for MCP tool-description changes (`agentgauge diff` / `eval`) and a
  deterministic defect linter (`agentgauge lint`), replacing v1's LLM-judged eight-axis quality score
  after a predictive-validity study found that score does not predict task success.
- Headline measurements from the release notes (provenance in `reports/capability_statement.md` and
  `reports/v2_product_readiness.md` at the tag): minimum detectable regression 5.37 percentage points at
  80% power on the 253-task corpus; lint false-alarm rate 4.22% over 521 tools; replay determinism 100%
  (50/50 runs).

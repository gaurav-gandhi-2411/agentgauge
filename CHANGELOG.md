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

Branch `fix/integrity-hygiene` (not yet merged) changes the package, `pyproject.toml` and the README;
the entries below it are the commits already on `main` since 0.5.3 (documentation, CI and
dependency-lockfile updates only).

### Changed on `fix/integrity-hygiene`

- **Per-trial seeds and `--seed` (4c3ba84, 26be3ab).** `run_tasks` passed no seed, so every repeat
  trial used the adapter default (42) and, on a seeded sampler such as Ollama, returned the same
  completion: 650 of 720 (tool set, task) groups in the audited variance corpus had exactly zero
  within-group variance. Each (task, trial) now gets a seed derived from `--seed`, task and trial
  index (new `--seed` on `diff` and `eval`, default 42). Same inputs give the same seed, so cassette
  replay stays byte-identical, and both arms share a seed per (task, trial). Hosted-API adapters
  accept and ignore the seed. **Consequences:** cassettes recorded against the old fixed seed no
  longer match `run_tasks` calls; historical research scripts that call `run_tasks` now draw different
  seeds than the runs behind their committed numbers (committed result files are unchanged). The
  calibration constants derived from the fixed-seed corpus (ICC 0.793, MDE, abstention, null
  false-alarm strata) are under re-measurement, see below.
- **Packaging (5d59521).** sdist is now an allow-list (`agentgauge/`, `pyproject.toml`, `README.md`,
  `LICENSE`, `CHANGELOG.md`): the published 0.5.3 sdist carried 431 files including internal planning
  documents; the new one has 42 members (35 when first measured; the demo files and `py.typed` came later). `tests/` is deliberately not shipped (it imports `evals/`,
  `examples/` and `scripts/`). Added `agentgauge/py.typed` (the `Typing :: Typed` classifier was
  declared without it). The PyPI "Changelog" URL now points at this file. Two mypy errors in
  `fixer.py` fixed with no behaviour change and `scripts/verify.sh` no longer swallows mypy failures;
  coverage gate raised from 60% to 90% (measured 92.6%).
- **First-run experience (1006acb).** New `agentgauge demo` replays a bundled recording (24 tasks,
  `gemma2:9b`, seed 42; provenance in `agentgauge/demo/PROVENANCE.md`) with no GPU, keys or network;
  its honest verdict is `INSUFFICIENT_SENSITIVITY` (joint success 0.667 to 1.000, delta +0.333, 95% CI
  [+0.125, +0.500], n=24 per arm). `demo --extract DIR` copies the demo servers and tasks out for a live
  run. `diff --replay-before/--replay-after` no longer needs positional server paths. A missing or
  unreadable server path is a one-line `Error: server script not found` with exit 2 before any
  subprocess; an unreachable Ollama is a one-line error after a 3 s probe. **`diff`/`eval --mock` are
  now refused with exit 2:** the mock gives one canned reply, so it cannot produce a verdict at any
  task count (it remains a free dry-run of the schema audit). `init --out` creates the directory. The
  scaffolded GitHub workflow is lint-only by default; the live-diff job is opt-in through the
  repository variable `AGENTGAUGE_LIVE_DIFF=true` (its Ollama install steps are not verified on a
  runner). `scan`/`fix`/`ci`/`try` are labelled `(legacy)` and `attribute` is hidden from `--help`.
  Known gaps: `diff` still returns `NO_CHANGE` for a real n=1 run; a tasks file naming a tool absent
  from the server is skipped by the audit rather than blocked; a server script that exists but crashes
  on start still produces the old `McpError` traceback.
- **README rewrite and integrity corrections.** The README now leads with the demo, drops the
  "for the first time" claims and the superseded ADVISORY "larger drop" text, withdraws the
  pre-registered / frozen-protocol framing for experiments whose results predate the protocol
  (`1493791`, 2026-06-22), and replaces the pooled BLOCKING figure with `type_enum_contradiction`-only
  effects and tool-set-clustered CIs (`scripts/type_enum_clustered_ci.py`,
  `evals/fixtures/type_enum_contradiction_clustered.json`). Version narrative moved to
  `docs/history/`. Figures that depend on the fixed-seed variance study are replaced by a generated
  block (`scripts/render_readme_metrics.py`).
- **Re-measured calibration with per-trial seeds** (`scripts/recalibration_collect.py`,
  `scripts/recalibration_analyze.py`; raw rows, results and manifest in
  `evals/fixtures/recalibration_seedfix/`): same 44 tool sets and 5,535 trials as the original
  corpus, gemma2:9b. Zero-variance share 90.3% -> 82.9% (paired -7.4 points, CI -10.7 to -4.5);
  ICC(1) 0.793 -> 0.731 [0.653, 0.809]; MDE(100x1) 0.0848 -> 0.0878 (sensitivity 0.0768-0.1001),
  MDE(253x1) 0.0537 -> 0.0562. **The earlier diagnosis that the fixed seed explained the zero
  variance was mostly wrong**: the identical scores come mostly from a coarse outcome metric, not a
  deterministic model (597 zero-variance groups: 235 identical calls, 362 differing calls with the
  same score). Effective decoding temperature verified above zero
  (`decoding_temperature_check.json`). `--trials` help now quotes these figures and is guarded by a
  test against drift.
- **Audit semantics.** `degenerate_metrics` now pools both arms (its docstring always said "across
  every trial in a corpus"), so a perfect "after" arm next to an imperfect "before" arm passes; a
  live run of the bundled demo pair had been refused for exactly this. If every trial in both arms
  scores 1.0 (0.0), `diff` reports a distinct `CEILING` (`FLOOR`) verdict with no delta and exits 0.
  `diff --replay-*` and `demo` now run the same trial-level audit as a live run. A pooled constant at
  a non-extreme value (a scorer returning one fixed number) still blocks. The `ceiling_floor` warning
  now names the arm and says "effect size may be truncated (no headroom above 1.0)".
- **Constraint-coverage check.** `diff`/`eval` print how many tasks are selection-only / partial /
  full (zero argument constraints / a required parameter or stated value unchecked / neither) and
  label the verdict `(selection-only)` with a warning when more than half are selection-only
  (warn, never block). `agentgauge init` scaffolds a fully-constrained worked example. Class counts
  for every committed corpus: `evals/fixtures/constraint_coverage_corpora.json` (the 253-task
  argument-degradation corpus: 16 / 211 / 26). All 24 bundled demo tasks are constrained to full
  coverage (a `ticket_id` constraint on every task); the demo was re-recorded and the replay files
  came out byte-identical (`agentgauge/demo/PROVENANCE.md`).
- **Superseded numbers.** 27 reports and paper sources that still quote the fixed-seed figures now
  start with a "Historical" banner (`scripts/add_historical_banners.py`); the paper drafts have
  READMEs itemising their known false or unsupported claims.
- **UTF-8 pipe output** (975bdd7): the CLI writes UTF-8 to redirected stdout/stderr, fixing a Windows
  decode crash; a `windows-tests` CI job runs the suite without `PYTHONUTF8`.

### Already on `main` since 0.5.3

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
  0.4.0 and 0.5.0 are affected; install 0.5.1 or later. Both were later **yanked** on PyPI with the
  reason "ImportError with mcp>=2 (uncapped dependency); use 0.5.1 or later" (verified against the PyPI
  JSON API on 2026-10-11): the files are unmodified (PyPI files are immutable) but hidden from the web
  listing and from default `pip` resolution. Git history does not record who yanked them or when.
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

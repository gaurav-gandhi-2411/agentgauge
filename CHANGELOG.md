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

## [0.6.0] - unreleased (date set at tag)

First release with package changes since 0.5.3. It integrates PRs #118-#124 and follow-up
branches (mcp CVE, Ollama num_ctx, google_workspace correction, n=1 diff, server crash). #118-#122 are merged to `main`; #123, #124 and the follow-up branches were
integrated on `release/v0.6.0` for rehearsal and are folded in once merged.

### Behaviour changes (read before upgrading)

- **`diff` with one trial per arm no longer exits 1 and no longer prints a confident verdict.** It
  returns `INSUFFICIENT_SENSITIVITY` (exit 0); JSON `ci_lo`/`ci_hi` are `null`. Previously a
  zero-width bootstrap CI produced `NO_CHANGE` / `IMPROVEMENT` / `REGRESSION` / `CEILING` / `FLOOR`
  (b9df83b: 0.8 vs 0.8 gave `NO_CHANGE`, 1.0 vs 0.0 gave `REGRESSION` with exit 1). Scripts that
  gated on that exit code or verdict at `--trials 1` will see a different result. n>=2 arms whose
  values are all identical still yield a zero-width CI (pre-existing, not addressed).
- **`diff`/`eval --mock` are refused with exit 2** (#123): the mock gives one canned reply and cannot
  produce a verdict. It remains a free dry-run of the schema audit.
- **A stdio server's stderr is replayed, not live.** It is captured in a temp file and written to our
  stderr right after the handshake and again at cleanup (c2b7b87, 449c6ba). Output ordering relative
  to agentgauge's own output differs from the previous inherited stderr, and nothing appears while a
  server is mid-run.
- **A server script that crashes on start exits 2** with a one-line error and the last <= 20 stderr
  lines, instead of exit 1 with an async traceback.
- **Ollama calls can now raise `OllamaTruncationError`** when the prompt would be silently truncated
  (see Fixed). Previously such a run completed against a cut-off tool listing.
- **Per-trial seeds change what repeat trials return** on seeded samplers (#119): cassettes recorded
  against the old fixed seed no longer match, and `diff`/`eval` take a new `--seed` (default 42).
- **`mcp` floor is now `>=1.30.0`** (was `>=1.3.0`).
- **`agentgauge init` scaffolds a lint-only GitHub workflow by default** (#123); the live-diff job runs
  only when the repository variable `AGENTGAUGE_LIVE_DIFF=true` is set.
- **`scan`/`fix`/`ci`/`try` are labelled `(legacy)` and `attribute` is hidden from `--help`** (#123);
  all still run.

### Security

- **Security:** `mcp` floor raised to `>=1.30.0,<2.0.0` in `pyproject.toml` and `uv.lock` 1.29.0 ->
  1.30.0, for CVE-2026-59951 (pip-audit red on `main`). The `<2` cap stays: mcp 2.x is a breaking
  major. `uv.lock`: transitive `certifi` 2026.5.20 -> 2026.10.19 for PYSEC-2026-4320, found by the
  same audit.
- `uv.lock`: `pyjwt` 2.13.0 -> 2.15.0, which cleared a red `pip-audit` check (#112), and minor/patch
  groups (#92, #113). `pyjwt` is transitive; it is not a direct dependency.

### Added

- **`agentgauge demo` and the first-run experience (#123).** See the "First-run experience" entry
  under Changed for the full list; `demo --extract DIR` copies the demo servers and tasks out for a
  live run.
- **Constraint-coverage check (#122)**, **CEILING/FLOOR verdicts (#122)** and **`--seed` on
  `diff`/`eval` (#119)**: see Changed.

### Fixed

- **Ollama silently truncating prompts (`fix/ollama-num-ctx`).** `OllamaProvider` sets
  `options.num_ctx = max(4096, estimated_tokens + 1024)` rounded up to a power of two (6d79532), clamps
  it to the model's own context length read once from `/api/show` (952170b), and raises
  `OllamaTruncationError` when `prompt_eval_count` shows truncation: a full window, or the
  context-shift signature `count ~ num_ctx/2 + 2` measured on Ollama 0.40.3 (6892910). The call is
  rejected up front only when the lower-bound token estimate plus a 256-token reply reserve cannot fit
  the model maximum; otherwise the guard runs after the call at the effective window (88654f1). If
  `/api/show` is unavailable, a warning is logged and the requested `num_ctx` is used. Impact audit
  (read-only, no published number changed): `docs/evidence/ollama_numctx_impact_audit.json`,
  `scripts/ollama_numctx_impact_audit.py` (ef66fb7): 316 estimated prompts over 79 bundled servers, 10
  exceed 4096 tokens: 8 are `fixer_source` upper bounds (the scripts used much smaller per-tool
  source) and the 2 agent-selection prompts are both the 116-tool google_workspace mirror.
- **`diff` at n=1 per arm (`fix/diff-insufficient-sensitivity`, b9df83b)** now returns
  `INSUFFICIENT_SENSITIVITY` instead of a verdict computed from a zero-width CI (see Behaviour changes).
- **Server crash on start (`fix/server-crash-one-line-error`, c2b7b87, 449c6ba, 60ee1be).** A stdio
  server script that exists but dies on import or before the MCP handshake gave a ~140-line async
  traceback ending in `McpError: Connection closed`. It now gives `Error: server failed to start:
  <target> did not complete the MCP handshake`, the last <= 20 lines of the server's stderr (each capped
  at 300 chars), a "run it directly" hint, and exit 2. The child's stderr goes to a temp file, not a
  pipe, so it cannot fill and block the child. The capture file is closed and deleted on every path;
  a closed or detached `sys.stderr` of our own no longer fails a healthy connect (60ee1be). A server
  that stays alive but never answers the handshake is not covered (still hangs, as before).
- **UTF-8 pipe output (#118, 975bdd7):** the CLI writes UTF-8 to redirected stdout/stderr, fixing a
  Windows decode crash; a `windows-tests` CI job runs the suite without `PYTHONUTF8`.

### Changed

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
  Known gap: a tasks file naming a tool absent from the server is skipped by the audit rather
  than blocked. (The two other gaps listed when #123 was written, `diff` returning `NO_CHANGE` for a
  real n=1 run and the `McpError` traceback for a server that crashes on start, are fixed below.)
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

### Docs

- **google_workspace EXP-1 correction (`docs/gw-truncation-correction`, 0524f65, 3621711).** The
  published 0%/0% "catalog-overwhelm" result for `taylorwilsdon-google_workspace_mcp` came from Ollama
  truncating the ~7k-token 116-tool listing at the default 4096-token window. With `num_ctx` sized
  (gemma2:9b, seeds 42+trial) both arms score 65% (13/20), +0pp; the catalog-overwhelm mechanism claim
  for this server is withdrawn (OUT-OF-REGIME stands, for the reason of no recovery). Corrected in
  STATUS.md, `paper.md` and its LaTeX mirror, `evidence_table.md`, with a dated erratum beside the
  pre-registration text; raw `exp1_trial_*` fixtures are untouched. Raw record:
  `docs/evidence/gw_rerun_check.json`.
- **README rewrite and integrity corrections.** The README now leads with the demo, drops the
  "for the first time" claims and the superseded ADVISORY "larger drop" text, withdraws the
  pre-registered / frozen-protocol framing for experiments whose results predate the protocol
  (`1493791`, 2026-06-22), and replaces the pooled BLOCKING figure with `type_enum_contradiction`-only
  effects and tool-set-clustered CIs (`scripts/type_enum_clustered_ci.py`,
  `evals/fixtures/type_enum_contradiction_clustered.json`). Version narrative moved to
  `docs/history/`. Figures that depend on the fixed-seed variance study are replaced by a generated
  block (`scripts/render_readme_metrics.py`).
- **Superseded numbers.** 27 reports and paper sources that still quote the fixed-seed figures now
  start with a "Historical" banner (`scripts/add_historical_banners.py`); the paper drafts have
  READMEs itemising their known false or unsupported claims.
- Docs and papers: README badges and a bug-report template (#108); brand hero image (#107);
  corrections to the two papers and their submission notes (#98-#101, #103-#106); consistency-check
  scripts for the papers (#100, #102); a version-pin checklist in `RELEASING.md` (#105).

### CI

- CI: stale action pins fixed, daily Dependabot cadence for GitHub Actions (#109); a
  manifest-provenance gate (#88).

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

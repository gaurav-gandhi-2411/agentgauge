# Predictive-validity study — session handoff

## CLOSED OUT (2026-07-23) — read this first, do not resume without explicit authorization

**This study is complete. Final verdict: FALSIFIED** under the pre-registered decision rule.
`overall_score` never survives multiple-comparison correction across the 8 fields tested;
`description_quality` survives alone but its correlation with real task success collapses to a
level that would not survive the same correction once description length is controlled for
(partial ρ=0.308, p=0.044 vs. a 0.00625 Bonferroni cutoff), and it never demonstrated the
pre-registered rule's "beats the best naive baseline by a meaningful margin" requirement in the
first place. **No axis or composite score in this study beats a free character-count heuristic by
a margin surviving both correction and length-control.** Full reasoning:
`reports/predictive_validity_study.md`, "FINAL CONCLUSION: FALSIFIED" at the top.

**No further ground-truth collection is planned or authorized.** A Phase-3 expansion attempt was
tried and abandoned after 5 consecutive local-process/Cloud-Run-proxy failures (see
`reports/predictive_validity_study.md`'s Repo State section and the
`local-gcloud-proxy-unreliable` reference memory) — that infra problem, not the underlying research
question, was why it stopped; it is not grounds to resume this study to "get past" the FALSIFIED
result. All GCP resources from this study are torn down; zero billable resources remain.

**What is still open, separately, and does not rescue the falsified thesis:** a small-sample
(n=7-9), suggestive schema-consistency lead (Spearman(Δviolations, Δsuccess) ≈ -0.6, not
statistically significant) — see the report's "Schema-consistency checker" sections. If ever
revisited, the checker's known false-positive bugs need fixing first (see report), and any new
ground-truth collection needs the infra reliability problem solved first, independent of whether
the question is worth re-testing.

A PR from `chore/predictive-validity-study` to `main` is open (not merged) summarizing this
close-out. Everything below this note is the original, pre-close-out handoff — kept for provenance,
not current instructions.

---

**Status as of 2026-07-19. Not committed to git** (one unauthorized commit by an
executor happened early on — `blind_tasks.py`, flagged to the user at the time —
everything else below is untracked, awaiting an explicit commit decision).

## What this is

A predictive-validity study: does AgentGauge's 8-axis tool-description scoring
correlate with real agent task success? Full narrative and methodology in
`reports/predictive_validity_study.md` (covers the original 18-set run — **stale
on numbers**, written before Stage B/Phase 3; update before treating as current).

## Files on disk (all local, all present, verified intact)

### Core pipeline (evals/fixtures/predictive_validity/)
- `manifest.py` — 45 `ToolSetEntry` records (18 original + 22 Stage B expansion +
  5 Phase 3 fixer-generated pairs). `MANIFEST` list, `AGENT_MODEL="gemma2:9b"`,
  `JUDGE_MODEL="llama3.1:8b"`.
- `blind_tasks.py` — anti-tautology tasks for all 45 entries (partially tracked —
  shows as `M` in git status, base version was committed without authorization).
- `constraints.py` — fractional constraint-satisfaction scoring (`Constraint`,
  `constraint_satisfaction()`, `TASK_CONSTRAINTS` dict) for continuous ground truth.
- `results_raw.json` / `.ndjson` — **current, valid dataset: 40 of 45 records
  complete.** Continuous ground truth (5 trials), fixed metric. Missing:
  `rw2_arm_a`, `rw2_arm_guardb` (failed to transient remote overload, need retry),
  and all 5 `*_fixed` Phase 3 entries (ground truth never collected — ran out of
  time before this could happen).
- `results_raw_PHASE2_binary_1trial.json/.ndjson` — archived: the 18-set run with
  the OLD binary success metric, 1 trial. Kept for the old-vs-new comparison in the
  report. Do not treat as current ground truth.
- `results_raw_INVALID_leaked_tasks.json/.ndjson` — archived: the very first
  9-record run, invalidated by the task-generator leak bug. Reference only, never
  usable as data.

### Scripts
- `scripts/predictive_validity_study.py` — the collection script.
  `GROUND_TRUTH_TRIALS=5`, `TRIALS=3`. Resumable (skips any manifest entry with an
  `error: null` record already in `results_raw.ndjson`). Cheapest-first execution
  order. Run directly for local Ollama, or via the GCP launcher below.
- `scripts/predictive_validity_analysis.py` — correlation analysis:
  `build_correlation_table()` (Spearman rho, p, bootstrap 95% CI, effect-size
  label, degenerate-field detection), `find_axis_flagged_cases()`. Run:
  `uv run python scripts/predictive_validity_analysis.py --axis discoverability`
  (swap `--axis` to check others; the axis flag only controls which axis's
  flagged-cases list prints, the correlation table always covers all fields).
- `scripts/run_predictive_validity_via_gcp.py` — monkeypatch launcher, points
  `OllamaProvider.BASE_URL` at `http://localhost:11435` before running the study.
  **Dead until a new remote Ollama endpoint exists** — the GCP service it pointed
  at (`agentgauge-agent`) was torn down this session (see below). Either point it
  at a new proxy port, or just run `predictive_validity_study.py` directly for
  local Ollama.
- `scripts/build_fixed_fixtures.py` / `run_build_fixed_fixtures_via_gcp.py` — the
  Phase 3 fixer-pair builder. Already run successfully for all 5 targets (outputs
  below exist). Only needed again if more fixer pairs are wanted.
- `scripts/agentgauge-agent-service.yaml` — Cloud Run service definition used for
  the (now-deleted) `agentgauge-agent` service. Kept as a template — re-deploy with
  `gcloud run services replace scripts/agentgauge-agent-service.yaml --region=us-central1 --project=expense-tracker-498014`
  if GCP is wanted again. Bucket (`agentgauge-agent-models-expense-tracker`) was
  also deleted, so a fresh deploy needs the bucket recreated and all 3 models
  (`gemma2:9b`, `llama3.1:8b`, `qwen3:8b`) re-pulled (~15 min).

### New example fixtures (Phase 3 fixer outputs)
`examples/grounded_server_fixed.py`, `confusable_server_fixed.py`,
`mediocre_server_fixed.py`, `call_constraints_server_fixed.py`,
`call_constraints_v2_server_fixed.py` — all generated via `agentgauge.fixer.run_fixer`,
tool-name parity verified against their "before" counterparts, wired into
`manifest.py`/`blind_tasks.py`/`constraints.py` already. Ground truth not yet
collected (see above).

### Tests
`tests/test_predictive_validity_analysis.py` — 20 tests (10 original + 10 for the
bootstrap CI feature). Last known-good: `uv run pytest --no-cov -q` → 759 passed.

## What's left to do (in order)

1. **Retry 2 failed entries + collect ground truth for 5 new Phase 3 entries** (7
   tool sets total out of 45). Just re-run `predictive_validity_study.py` — the
   resume logic will skip the 38 already-done and only process these 7. Either
   local Ollama (watch for GPU contention from an unrelated `aetherart` process on
   this machine — confirmed recurring root cause of every local failure this
   session) or redeploy the GCP path.
2. **Recompute the full 45-set correlation table** with
   `predictive_validity_analysis.py` once data is complete.
3. **Phase 3 synthesis**: compare all 7 before/after pairs' task_success_rate
   (before vs. after fixer) against their AgentGauge scores and both baselines —
   does the "improved" description score higher while success drops? (Already
   confirmed true for 2 of 7 — the T18 pairs — in the existing report.)
4. **Update `reports/predictive_validity_study.md`** with the full Stage
   A+B+Phase 3 picture — the current report only covers the original 18.
5. **Final verifier pass** on the updated report before calling it done.
6. **Ask the user about committing** — nothing should be committed without
   explicit authorization (this was violated once already this session).

## Known gotchas for next session

- Local GPU contention is a **recurring, confirmed** issue on this machine — an
  unrelated `aetherart` conda-env process periodically loads heavy models and
  starves Ollama. Check `nvidia-smi` / `ollama ps` before trusting local runs to
  complete quickly; budget for retries either way.
- `OllamaProvider.BASE_URL` is a hardcoded class attribute — the GCP launcher
  scripts monkeypatch it rather than editing the main study script, to avoid
  re-verifying that file every time the routing changes.
- The study script's resume logic keys off `results_raw.ndjson`, deduplicating by
  name and keeping the LAST record per name — safe to relaunch repeatedly.

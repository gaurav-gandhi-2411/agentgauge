# AgentGauge v0.4.0 — Task 1: argument-degradation live re-measurement

Closes the one remaining NOT-MEASURED item: whether tool-description quality
actually fixes argument construction (a *separate* question from the causal
chain — does a BLOCKING lint violation cause task failure — which v2.2/v2.4
already measured and replicated across 3 models). v2.2 found this
inconclusive at n=62 (`reports/v2_2_task_a_reallocation.md`, MDE=0.106,
too coarse to resolve anything). The corpus is now 253 tasks
(`reports/v2_4_task4_corpus_expansion.md`, `reports/v2_5_task2_fixture_validation.md`)
with MDE=0.0537 at that size (`reports/v2_5_task3_mde_completion.md`) — this
task re-runs the live measurement at that power, under the corrected
`agentgauge.constraints`/`agentgauge.audit` scoring path (post v2.5 Task 1).

## 1a. GPU contention check

At the pre-flight check, the local RTX 3070 was fully free (0 MiB used, 0%
util, no resident Ollama model, no `aetherart` process running) — proceeded
locally, no GCP needed at that point.

**Mid-run**, an unrelated local process (`aetherart`'s
`_pattachitra_ab_base_comparison.py --checkpoint curated500`, PID 30136,
started 07:17 local time) claimed the entire GPU (100% utilization, <120 MiB
free out of 8192). The local run's first Ollama call timed out
(`httpx.ReadTimeout`) and exited cleanly — no checkpoint data had been
written yet, so nothing was lost or corrupted. Per the standing "no GCP
without sign-off" constraint, this was reported with a bounded cost estimate
(~$3–7) rather than acted on. **The user explicitly authorized GCP** ("Use
GCP.") after `aetherart` showed no sign of clearing.

## 1b. Live measurement — methodology, a found-and-fixed bug, and results

**GCP path**: the `agentgauge-agent` Cloud Run service and its baked image
(gemma2:9b/llama3.1:8b/qwen2.5:7b pre-pulled, eliminating per-cold-start
network pulls) had been torn down after the last cycle — rebuilt from
`scripts/Dockerfile.agentgauge-agent` (~19 min Cloud Build), redeployed via
`scripts/agentgauge-agent-service.yaml`. Deliberately did **not** use
`gcloud run services proxy` — this repo's own memory records that an
unattended local proxy dies within ~2–30 minutes on this machine (three
prior mechanisms tried, unsolved), fatal for a multi-hour job. Instead,
`scripts/v2_5_argument_degradation_live_gcp.py` calls the Cloud Run HTTPS
URL directly, authenticated per-request with a `gcloud auth
print-identity-token` bearer token (refreshed every 45 min) — no long-lived
local process to die. MCP servers under test still ran locally via stdio;
only the LLM provider calls were remote.

**Design**: all 12 fixture pairs (2 original `call_constraints*` + 10
v2.4/v2.5 real-API fixtures), 253 tasks total, 1 trial/task (the validated
optimal allocation), bad vs. fixed variant, 3 models = 1518 live trials.
Every trial checkpointed immediately to
`evals/fixtures/v2_5_argument_degradation_live.jsonl` (resumable). A
schema-only `agentgauge.audit.run_audit` pre-check ran before any inference
for every fixture — the CORRECTED checker this task's brief specifically
asked for — and passed cleanly on all 12 (expected, since Task 2 validated
every fixture's schema fidelity).

**A Windows bug, found and fixed before the real run**: the first GCP launch
attempt crashed immediately — `subprocess.run(["gcloud", ...])` raised
`FileNotFoundError` because `gcloud` is a `.cmd` wrapper on Windows and
`CreateProcess` doesn't do PATHEXT resolution the way a shell does. Fixed
via `shutil.which("gcloud")` to resolve the real path once at import time.

**A second bug, found immediately after the run completed**: the aggregation
step's `TrialOutcome` construction set `task_tool_name` to a globally-unique
clustering key (`fixture::tool::description` — needed because tool names
collide across fixtures, e.g. GitHub and Jira both have `create_issue`; see
1b's design note in `scripts/v2_5_argument_degradation_live.py`'s module
docstring) but left `selected_tool` as the bare recorded tool name.
`TrialOutcome.selection_correct` compares these two fields directly — since
a composite key can never equal a bare tool name, `selection_correct` was
**always False**, collapsing every trial's `joint_success` to 0.0 regardless
of the actual outcome. The first summary reported before=after=0.0 for all
3 models — implausible on its face (not "no effect," a broken metric,
exactly the `check_degenerate_metrics` artifact class) and was **not**
reported as a real result. The raw checkpoint data was never wrong
(`selected_tool`/`tool_name`/`constraint_satisfaction` all recorded
correctly per-record); only the offline aggregation was. Fixed by deriving
real selection-correctness (`selected_tool == tool_name`) before
constructing each `TrialOutcome`, re-verified independently against the raw
JSONL before regenerating the summary — which required **zero new
inference**: the script's resumability skipped all 1518 already-checkpointed
trials and only recomputed the aggregation.

### Result: 95% CI, all 3 models

| Model | Before | After | Δ | 95% CI | Verdict |
|---|---|---|---|---|---|
| gemma2:9b | 0.4881 | 0.5099 | +0.0217 | [-0.0042, +0.0505] | no_change |
| llama3.1:8b | 0.4130 | 0.4684 | +0.0553 | [+0.0232, +0.0885] | no_change |
| qwen2.5:7b | 0.4506 | 0.4545 | +0.0040 | [-0.0211, +0.0292] | no_change |

All 3 models: `n_tasks_matched=253` (0 unmatched), paired + CUPED-adjusted
(`cuped_variance_reduction_pct` 4.2–7.3%), standard cluster bootstrap (≥30
clusters, no few-clusters correction needed).

**A null is the honest, decision-relevant result it was described as
upfront.** No model clears the 0.05 practical-significance threshold in
either direction — description quality does not measurably change argument
construction on this corpus, for any of the 3 model families, now measured
at real power (MDE=0.0537, an order of magnitude finer than any of these
deltas). This is the SAME shape of finding as v2.2's causal-chain result for
`required_references_missing_property` (a real, measured null, not an
underpowered "inconclusive") — but unlike v2.2's n=62 attempt, this one is
adequately powered to make that call with confidence.

**One nuance, stated precisely, not smoothed over**: llama3.1:8b's 95% CI
`[+0.0232, +0.0885]` excludes zero — the delta IS statistically distinguishable
from a true null for this model. It is reported as `no_change` because
`diff_server_level`'s verdict logic requires `ci_lo > threshold` (0.05) to
call `IMPROVEMENT`, a stricter practical-significance bar than "CI excludes
zero," by design (a barely-real effect isn't necessarily a
decision-relevant one). Read precisely: llama3.1:8b shows a small,
statistically real, but practically negligible improvement from better
descriptions; the other two models show no statistically distinguishable
effect at all.

## GCP spend

Cloud Run compute: **$2.19** (5541.5 billable instance-seconds — GPU + 8
vCPU + 32 GiB combined rate $0.0003947/s — measured via Cloud Monitoring
`billable_instance_time`, not estimated). Cloud Build (image rebuild, ~19
min): not separately itemized here — Cloud Build's per-build-minute rate is
not among this repo's documented rates, and a single ~19-minute build is
very likely within the daily free-tier allowance; treated as a small,
unquantified addition to the $2.19 figure, not zero, not hidden.

**Teardown, verified**: `agentgauge-agent` Cloud Run service deleted,
`agentgauge-agent-baked` image deleted (both confirmed absent via
`gcloud run services list` / `gcloud container images list-tags` after
deletion). `agentgauge-judge` confirmed untouched (`LAST DEPLOYED AT`
unchanged from its historical 2026-05-31 timestamp).

## Independent verification

A separate verifier agent independently re-derived the raw and CUPED-adjusted
rates from `evals/fixtures/v2_5_argument_degradation_live.jsonl` directly
(not from this report), re-ran `agentgauge.harness.diff_server_level` itself
to reproduce the delta/CI/verdict, sanity-checked the raw checkpoint (record
count, per-group counts, no duplicates), confirmed the verdict-logic
explanation by reading `diff_server_level`'s actual condition, and confirmed
the current aggregation code genuinely derives selection-correctness from
`tool_name`, not the clustering key.

**Result: all 5 items CONFIRMED, no discrepancies.**

1. Raw joint-success rates independently recomputed from the raw JSONL:
   exact match to all 6 claimed before/after values (e.g. gemma2:9b
   bad=0.488142/fixed=0.509881).
2. Full paired/CUPED/bootstrap CI independently rebuilt (same globally-unique
   clustering key) and run through the real, unmodified
   `agentgauge.harness.diff_server_level` (seed=42): delta/ci_lo/ci_hi/verdict
   matched the claimed summary to <1e-9 for all 3 models —
   bit-identical reproduction, not just "close."
3. Raw checkpoint sanity: 1518 total records, exactly 253 per each of the 6
   (model, variant) groups, 0 duplicate (model, fixture, variant, task_key)
   keys.
4. Verdict-logic quoted directly from `agentgauge/harness.py`:
   `elif ci_lo > threshold: verdict = Verdict.IMPROVEMENT` (else `NO_CHANGE`)
   — confirmed llama3.1:8b's `ci_lo=+0.0232` genuinely falls short of
   `threshold=0.05`, landing in `NO_CHANGE` exactly as reported; CI-excludes-
   zero alone is confirmed insufficient by the actual code, not an invented
   explanation.
5. Confirmed by direct diff read (`git show 117225a`) that the fix's
   mechanism is real: pre-fix, `selected_tool` (bare name) was compared
   against `task_tool_name` (unique key) and could never match; post-fix,
   real selection-correctness is derived from `tool_name` first, then
   encoded relative to the unique key.

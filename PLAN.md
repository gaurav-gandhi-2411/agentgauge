# AgentGauge — living execution tracker

Tier: **T1** (portfolio project — CI, evals, budgets; no launched users yet).
Branch for all v0.4.0 work: `feat/agentgauge-v2`. No merges to `main` without explicit sign-off.

## v0.4.0 — close the measurement gap, then ship

**Status: COMPLETE.** Both tasks done, verified, pushed. No new hardening/fixtures/axes
was added (explicit constraint this phase) — the one candidate product fix found
(the `TrialOutcome.task_tool_name` clustering-key collision, Task 1b) was disclosed,
not applied, per that constraint.

### Task 1 — argument-degradation live re-measurement

- [x] 1a. GPU contention check: RTX 3070 fully free (8020/8192 MiB free, 0% util,
      no resident Ollama model, no "aetherart" process found) — proceeded locally,
      no GCP needed, no sign-off required.
- [x] 1b. **Done, via GCP with explicit sign-off** after `aetherart` contention never
      cleared. Rebuilt+redeployed `agentgauge-agent` (torn down since last cycle),
      called directly over HTTPS with per-request identity-token auth (NOT
      `gcloud run services proxy` — this repo's memory records that dying within
      minutes on this machine for multi-hour jobs). 1518 live trials (253 tasks x 2
      variants x 3 models), all checkpointed to
      `evals/fixtures/v2_5_argument_degradation_live.jsonl` (committed as provenance).
      **Result: a real, adequately-powered null across all 3 models** (MDE=0.0537,
      no model clears the 0.05 practical-significance threshold) —
      `reports/v0_4_0_task1_argument_degradation.md`. Independently verified,
      bit-identical reproduction, all 5 checks CONFIRMED.
  - **Two bugs found and fixed in-session**: (1) `subprocess.run(["gcloud", ...])`
    raised `FileNotFoundError` on Windows (`.cmd` wrapper, no PATHEXT resolution
    without `shell=True`) — fixed via `shutil.which`. (2) The first post-run
    aggregation compared the wrong two fields (unique clustering key vs. bare tool
    name), collapsing every trial's `joint_success` to 0.0 — caught because
    before=after=0.0 across 1518 trials was recognized as implausible, not reported
    as "no effect"; fixed with zero new inference needed (checkpoint data was
    always correct, only the offline aggregation was wrong).
  - **Finding surfaced while designing this (disclosed, not fixed this phase — see
    CLAUDE.md "no new hardening" constraint)**: `agentgauge/cli.py`'s `_collect_trials`
    sets `TrialOutcome.task_tool_name = r.task.tool_name` (bare tool name), which is
    also the task-CLUSTERING key `agentgauge.harness.aggregate_to_tasks` groups by.
    Every fixture in this corpus has multiple tasks per tool, so the *shipped*
    `agentgauge diff`/`eval` would silently collapse same-tool tasks into one cluster
    (253 tasks → ~48 tool-level clusters), understating true cluster count. This
    script worked around it locally (task-unique clustering key), does not touch
    `cli.py`/`harness.py`. Candidate product fix for a future pass, not v0.4.0.
  - GCP teardown confirmed: `agentgauge-agent` service + baked image deleted,
    `agentgauge-judge` confirmed untouched. Spend: $2.19 Cloud Run compute
    (measured via Cloud Monitoring), plus a small unquantified Cloud Build cost
    (~19min rebuild, likely within free tier, not separately itemized).
- [x] 1c. README.md and reports/v2_product_readiness.md updated — every stale
      "inconclusive at n=62" reference replaced with the measured result; §0-D added
      to the readiness report. Every product claim tracked in either document is now
      MEASURED.

### Task 2 — ship-readiness finalization

- [x] 2a. Orchestrator stop-condition fix: `CLAUDE.md` "Orchestrator discipline" section
      added — subagents waiting on their own background job must read its completed
      output before ending their turn; don't resume a stalled subagent more than once;
      treat `ScheduleWakeup` prompts as plans to re-verify, not facts; recognize
      duplicate task-notifications by content, not id; prefer a single directly-launched
      background job with a durable checkpoint over a subagent asked to "wait."
- [x] 2b. PR #64 opened (draft, `feat/agentgauge-v2` → `main`, unmerged, for review) —
      summarizes the full v2 arc; disclosed that it likely supersedes/subsumes #63
      (already merged into this branch's history via `9cb03af`).
- [x] 2c. Wheel rebuilt fresh at v0.4.0, installed into an isolated venv
      (`wheel_test_venv_v040_final`), verified: `--version`, `--help`, `scan --mock`,
      `lint` all work correctly from the clean install. No PyPI publish.
- [x] 2d. `reports/capability_statement.md` committed — headline numbers, the
      differentiated claim vs. the 97.1%-false-alarm LLM-judge baseline, target user,
      free-CLI/paid-cloud split (paid tier explicitly marked not-yet-built).

## Standing constraints (this phase)

- Local Ollama only. **NO GCP without explicit sign-off BEFORE the action** — missed
  three times previously; report and wait, never act-then-disclose.
- Never `ANTHROPIC_API_KEY`.
- No new hardening scope, new fixtures, or new axes — measurement-closure and
  packaging only.
- Independent verifier on Task 1's measured number.
- Commit and push to `feat/agentgauge-v2` only; no merges to `main`.

## Gotchas discovered this phase

- Backgrounded commands in this environment buffer stdout until process exit —
  `print(..., flush=True)` does not produce visible incremental output via the
  task-output file. Use a checkpoint file on disk (not stdout) to track progress
  of any long-running background job.
- `scripts/v2_5_argument_degradation_live.py`'s smoke test (2 tasks, 1 model) took
  >120s including a cold model load — per-task latency is dominated by Ollama's
  first-request model-load time per model, not per-task; the full run's 1518 trials
  should get much faster once each of the 3 models is warm (Ollama keeps a model
  resident across calls until a different model is requested, and this script
  processes all 12 fixtures for one model before switching).
- GPU contention can appear *mid-run*, not just at the pre-flight check — the 1a
  check found the GPU fully free, but `aetherart` claimed it minutes later. A
  pre-flight check is necessary but not sufficient; a long-running local-inference
  job needs to fail gracefully (this script did: clean crash, zero checkpoint
  corruption, safely resumable) rather than assume contention can't appear later.
- What looked like "two duplicate instances" of the measurement script running
  concurrently (via `wmic process ... get ProcessId,ParentProcessId,CommandLine`)
  was a false alarm: on Windows, `uv run python script.py` cannot exec-replace
  itself (no native `exec()`), so it always shows as a multi-process chain
  (shell → uv wrapper → venv python → any subprocess the script itself spawns,
  e.g. an MCP stdio server) — check `ParentProcessId` to confirm a real single
  chain before assuming a launch was accidentally duplicated.

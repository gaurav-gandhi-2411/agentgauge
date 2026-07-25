# AgentGauge — living execution tracker

Tier: **T1** (portfolio project — CI, evals, budgets; no launched users yet).
Branch for all v0.4.0 work: `feat/agentgauge-v2`. No merges to `main` without explicit sign-off.

## v0.4.0 — close the measurement gap, then ship

Two tasks, no new hardening/fixtures/axes (explicit constraint this phase).

### Task 1 — argument-degradation live re-measurement

- [x] 1a. GPU contention check: RTX 3070 fully free (8020/8192 MiB free, 0% util,
      no resident Ollama model, no "aetherart" process found) — proceeded locally,
      no GCP needed, no sign-off required.
- [ ] 1b. Live cross-model measurement in progress: `scripts/v2_5_argument_degradation_live.py`,
      background task, resumable via `evals/fixtures/v2_5_argument_degradation_live.jsonl`
      checkpoint (one JSON record per trial, flushed immediately). Full 253-task corpus
      (62 original + 191 v2.4/v2.5 real-API), 1 trial/task, bad vs. fixed variant,
      gemma2:9b / llama3.1:8b / qwen2.5:7b. Uses the CORRECTED `agentgauge.constraints`/
      `agentgauge.audit` scoring path (post v2.5 Task 1 fix), gated by a real
      `run_audit` schema-only pre-check per fixture before any inference.
  - **Finding surfaced while designing this (disclosed, not fixed this phase — see
    CLAUDE.md "no new hardening" constraint)**: `agentgauge/cli.py`'s `_collect_trials`
    sets `TrialOutcome.task_tool_name = r.task.tool_name` (bare tool name), which is
    also the task-CLUSTERING key `agentgauge.harness.aggregate_to_tasks` groups by.
    Every fixture in this corpus has multiple tasks per tool, so the *shipped*
    `agentgauge diff`/`eval` would silently collapse same-tool tasks into one cluster
    (253 tasks → ~48 tool-level clusters), understating true cluster count. This
    script works around it locally (task-unique clustering key), does not touch
    `cli.py`/`harness.py`. Candidate product fix for a future pass, not v0.4.0.
- [ ] 1c. Update README.md / reports/v2_product_readiness.md: move argument-degradation
      from NOT MEASURED to MEASURED once 1b completes and is independently verified.

### Task 2 — ship-readiness finalization

- [x] 2a. Orchestrator stop-condition fix: `CLAUDE.md` "Orchestrator discipline" section
      added — subagents waiting on their own background job must read its completed
      output before ending their turn; don't resume a stalled subagent more than once;
      treat `ScheduleWakeup` prompts as plans to re-verify, not facts; recognize
      duplicate task-notifications by content, not id; prefer a single directly-launched
      background job with a durable checkpoint over a subagent asked to "wait."
- [ ] 2b. Open `feat/agentgauge-v2` → `main` PR (draft/unmerged, for review) summarizing
      the full v2 arc.
- [ ] 2c. Final wheel build + clean-venv install verification at v0.4.0 (no PyPI publish).
- [ ] 2d. `reports/capability_statement.md` — 1-page GTM capability statement.

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

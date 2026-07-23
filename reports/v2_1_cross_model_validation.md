# AgentGauge v2.1 — cross-model validation (Task 6)

Tests whether the harness's flagship real-world finding (`call_constraints_server`: tool-selection
accuracy stays near-perfect while argument-construction accuracy has room to degrade under worse
descriptions) — previously measured ONLY with gemma2:9b as the acting agent — replicates across
gemma2:9b, llama3.1:8b, and qwen2.5:7b. Live inference, `scripts/v2_1_cross_model_validation.py`.

## Infrastructure rebuild required

The `agentgauge-agent` Cloud Run service (separate from the pinned `agentgauge-judge` service,
which was left untouched per CLAUDE.md's explicit warning) had been fully torn down since the
prior session — its GCS model-weights bucket no longer existed. Rebuilding it surfaced three
distinct, real problems, each fixed in turn:

1. **gcsfuse-backed volume mount failed outright** (bucket didn't exist — not the previously
   documented gcsfuse/Ollama-downloader incompatibility, a different failure this time). Fixed by
   removing the GCS volume entirely and switching to plain container ephemeral disk (per the
   existing memory note's own recommendation: "use ephemeral disk... instead").
2. **`gcloud run services proxy` (the documented-unreliable local tunnel) died silently** mid-run
   at least twice — the process stayed alive but stopped forwarding traffic, with no error, no
   exit. Fixed by abandoning the proxy entirely: the script now calls the Cloud Run HTTPS URL
   directly with an IAM identity-token bearer header (`gcloud auth print-identity-token`, no
   `--audiences` flag — an explicit audience mismatch caused a spurious 401 on the first attempt).
3. **Ephemeral disk means models do not persist across a cold start**, and this service was
   observed to scale back to zero within single-digit minutes of inter-request gaps — losing
   previously-pulled models between a separate "pull" step and a later "run" step. Fixed by fusing
   pull-then-run into one uninterrupted script execution with per-combo checkpointing
   (`evals/fixtures/v2_1_cross_model_validation.json` written after every model×variant combo, so
   an interruption loses at most one combo, not the whole run).

Two earlier full-scope run attempts were lost entirely to these failures before the fixes above
(reported honestly, not hidden — the previous scripted approach silently died at the "gemma2:9b/
before" step twice with the process exiting and zero output written, before the direct-HTTPS fix).

## Scope: reduced from 32 to 16 tasks

To keep the run inside a single continuous, uninterruptible window (given the demonstrated
Cloud-Run-scale-down risk), the task set was reduced from the full 32 anti-tautology tasks
(`CALL_CONSTRAINTS_SERVER_TASKS`) to 16 — the first 2 tasks per tool, deterministically selected
(not random). This keeps at least one task per all 8 tools (selection-accuracy coverage) and 2
tasks for each of the 4 argument-constrained tools (argument-accuracy coverage). trials=1 (not the
historical 3/task) — justified by Task 1's finding that repeat trials on the same deterministic
task carry almost no independent information (ICC=0.793), so this is a smaller but not a
qualitatively weaker design for the specific question "does the sign of the pattern replicate."

## Results

| Model | Selection (before→after) | Argument accuracy (before→after) | Joint (before→after) |
|---|---|---|---|
| gemma2:9b | 1.000 → 1.000 | 0.500 → 0.500 | 0.500 → 0.500 |
| llama3.1:8b | 0.938 → 1.000 | 0.533 → 0.500 | 0.500 → 0.500 |
| qwen2.5:7b | 1.000 → 0.938 | 0.500 → 0.467 | 0.500 → 0.4375 |

n=16 trials per cell, trials=1, all figures from `evals/fixtures/v2_1_cross_model_validation.json`.

### Selection accuracy: the flat/near-ceiling pattern replicates across all three models

All three models land in 0.938–1.000 across both variants — consistent with the original
gemma2:9b-only finding that tool selection is essentially solved for this tool set regardless of
description quality. This part of the flagship finding **replicates across model families**.

### Argument accuracy: NOT clearly replicated at this sample size — a measured limitation, not a null result

The differences observed (0 to −0.067) are small and could easily be sampling noise at n=16 with
only 1 trial each. More importantly, `argument_accuracy_given_correct_selection` is **diluted by
construction**: `constraint_satisfaction()` returns 1.0 by default for any task with no registered
constraint (`evals/fixtures/predictive_validity/constraints.py`'s documented convention), and half
of `call_constraints_server`'s 8 tools (`ping_server`, `get_server_info`, `list_channels`,
`reset_state`) have empty schemas with no constrained parameters at all. The 16-task subset
includes tasks from all 8 tools, so roughly half of every argument-accuracy figure above is a
guaranteed 1.0 from trivial tools, compressing the visible range and making a real degradation on
the 4 constrained tools much harder to detect in the aggregate number.

**This is reported as an inconclusive-at-this-power result, not as "the effect is model-specific"
or "the effect doesn't replicate."** Neither of those stronger claims is supported by a n=16,
trials=1 sample diluted this way — concluding either would overclaim. What would resolve this: the
full 32-task set (or a subset restricted to just the 4 constrained tools) at trials≥3, run when
this infrastructure can sustain a longer continuous session (see "What would falsify this" in the
consolidated readiness report).

## What this task does and does not establish

- **Established:** the selection-flat half of the flagship pattern is not a gemma2:9b artifact — it
  replicates across 3 model families on this tool set.
- **Not established either way:** whether the argument-degrades half is model-specific or
  universal. The infrastructure cost of reaching a decisive sample size on this specific Cloud Run
  setup was substantial (three distinct infra failures fixed in sequence) and the reduced scope
  taken to fit inside a reliable single run is not sufficient to resolve this half of the question.

---

## Task 2e — single-prompt LLM linter baseline, measured

Deferred in Task 2 (`reports/v2_linter_evaluation.md` §2e) pending GPU. Run here via
`scripts/v2_1_llm_linter_baseline.py`, llama3.1:8b (the study's pinned judge model), same
direct-HTTPS + checkpointing infrastructure as above. **Bounded stratified sample**, not the full
corpus, for the same infrastructure-fragility reason: 174 of 521 clean-corpus tools (every 3rd),
138 of 276 defect-injection cases (every 2nd, stratified so all 5 defect types are still
represented — 24–32 cases per type).

| Metric | Value |
|---|---|
| Clean-corpus false-alarm rate | **97.1%** (169/174 clean tools flagged) |
| Recall, all 5 defect types | **100.0%** (every single case) |

**The 100% recall number is not meaningful in isolation.** A baseline that answers "INCONSISTENT"
on 97.1% of genuinely clean tools will trivially also answer "INCONSISTENT" on 100% of defective
ones — this is a degenerate always-flag baseline, not a working linter. Spot-checked directly (not
assumed): asked the same model the same prompt about an unambiguous, genuinely clean tool
(`add(a: number, b: number)`, schema correctly declaring both `a` and `b`). Response: *"INCONSISTENT:
A parameter 'b' is mentioned in the description but it's missing in the provided JSON Schema."* —
a fabricated claim; `b` is plainly present in the schema passed in the same prompt. This was checked
to rule out a false alarm on the measurement side (e.g. the extraction regex matching "not
inconsistent") — it is not: the model's own stated reason is a hallucinated, checkable-false claim
about content in its own context window, not a borderline judgment call.

**Conclusion: the deterministic linter beats this baseline decisively once precision is accounted
for**, not just on recall — 4.22% false-alarm / 83.3% recall on the single hardest defect type
(`reports/v2_1_linter_recall_fix.md`) is a materially more useful signal than 97.1% false-alarm /
100% recall from a baseline that has, in effect, stopped discriminating at all. This matches the
doctrine's own framing (`reports/v2_eval_doctrine.md`): "a linter that's wrong half the time gets
disabled" — this baseline is wrong on clean input 97% of the time.

**Not measured:** the full corpus (521 tools, 276 defects) — the stratified sample here is large
enough (n=174, n=138) that the qualitative conclusion (baseline is degenerate) is very unlikely to
flip on the remaining cases, but the exact percentages could shift slightly on the full set.

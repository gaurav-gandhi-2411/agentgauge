# Frozen Evaluation Protocol — AgentGauge Research Program

**Version:** 1.0 · **Committed:** 2026-06-22 · **Status:** LOCKED

This document defines the evaluation protocol every experiment in the paper
"When Does Tool-Description Quality Actually Improve Agent Behavior? A Regime
Analysis" must run through. It is committed once and must **not** be edited
after any experiment's results are collected. Post-results edits invalidate
cross-experiment comparisons.

---

## Governance

- **Pre-registration:** each experiment's spec is committed to its branch before
  any run starts. Metric definitions, fixture contents, and thresholds are never
  edited after results are in hand.
- **Null/abort first-class:** a failed headroom gate or inconclusive sign test is
  reported as-is, never suppressed. Negative results appear in the paper.
- **Never tune to a positive:** if a result is negative, report it negative.
- `ANTHROPIC_API_KEY` must **never** be set or used in any experiment.
- **Condition #1 (any judge/scorer/rubric change)** → DRAFT PR + escalate to GG
  before executing.
- **generator ≠ judge ≠ agent**: structural independence enforced at all times.

---

## Frozen Configuration

| Component | Value | Notes |
|-----------|-------|-------|
| Judge model | `llama3.1:8b` | Pinned; calibrated 2026-05-31 |
| Judge seed | `42` | Used in all judge API calls |
| Generator model | `qwen3:8b` | ONE family; must always differ from judge |
| Default agent | `gemma2:9b` | Agent is the variable only in EXP-2 |
| Trials per arm | `5` | Per task per arm |
| Sign test α | `0.05` | Two-sided unless pre-registered as one-sided |
| Headroom ceiling | `0.85` | Arm A must be < 85% to proceed to A/B |
| Min contested tasks | `6` | Below this, power is too low for the sign test |

These values are codified in `agentgauge/frozen_protocol.py` — import from
there rather than redeclaring them in experiment scripts.

---

## Classifier (ONE, always)

Three outcomes + a separate `PARSE-FAILED` flag:

| Label | Meaning |
|-------|---------|
| `SELECTED-CORRECT` | Agent selected the pre-registered gold tool |
| `SELECTED-WRONG` | Agent selected a different tool |
| `ABSTAINED-OR-HEDGED` | Agent produced an output but hedged, or explicitly abstained |
| `PARSE-FAILED` | Agent output could not be parsed into a structured tool selection |

`PARSE-FAILED` is **always reported separately**; it is never aggregated with the
three outcome categories. Parse-failed counts must appear in every result table.

---

## Effect Measurement

**Unit of analysis:** task (not trial). Trials are repeated measures within a task.

### Pre-registration

Before any run, commit to the branch:
1. The pre-registered contested task set (tasks expected to show Arm A < Arm B)
2. The gold tool for each contested task
3. The stability screen procedure
4. Whether the sign test is one- or two-sided

### Headroom gate

Before any A/B comparison, run Arm A alone. If parse-success accuracy on the
contested set is ≥ 85%, abort the experiment (no headroom). Report as a null
result, not as a skip.

### Stability screen

Run Arm A twice, independently (different random seeds). A task is **stable** if
its accuracy (trials correct / total trials per run) differs by ≤ 1 trial between
runs. Unstable tasks are dropped from the primary analysis and listed separately
in the report. The stable set is the unit for the sign test.

### Effect calculation

**Effect = Arm B accuracy − Arm A accuracy** on parse-success stable contested tasks.

Accuracy = (SELECTED-CORRECT trials) / (parse-success trials), where parse-success
trials are those with outcome in {SELECTED-CORRECT, SELECTED-WRONG, ABSTAINED-OR-HEDGED}.

### Sign test

For each stable contested task, classify as:
- **B > A** (n_plus): task-level accuracy higher in Arm B
- **A > B** (n_minus): task-level accuracy higher in Arm A
- **B == A** (n_ties): same accuracy both arms

Sign test p-value: two-sided binomial test on (n_plus, n_plus + n_minus).
Ties excluded from the denominator. One-sided (toward B > A) is acceptable
only if pre-registered.

### Required reporting (every result table)

Every experiment must report all of the following — no omissions:

| Field | Required |
|-------|---------|
| N pre-registered contested tasks | ✓ |
| N stable contested tasks (after screen) | ✓ |
| parse_failed count, Arm A (absolute) | ✓ |
| parse_failed count, Arm B (absolute) | ✓ |
| Arm A accuracy (parse-success stable contested) | ✓ |
| Arm B accuracy (same denominator) | ✓ |
| Effect (B−A) in percentage points | ✓ |
| n_plus / n_minus / n_ties | ✓ |
| Sign test p-value (two-sided) | ✓ |
| Stable-set repeat if flippers were excluded | ✓ |
| Headroom gate result (passed/aborted + Arm A %) | ✓ |

---

## Cross-Experiment Comparisons

Cross-experiment effect-size comparisons are valid **only** if:
- Same fixture (or equivalently-structured fixture, pre-registered as equivalent)
- Same judge (this protocol's frozen judge, seed 42)
- Same classifier (the three-outcome classifier above)
- The **only** variable is the agent

The T18/gemma +34.5pp and FRONTIER-T18/Llama-3.3-70B +40.8pp numbers are **not**
part of EXP-2's controlled ladder (different harness). They are reported separately
with an explicit "not apples-to-apples" caveat.

---

## Parse Control (mandatory in EXP-2; recommended everywhere)

For every model in a multi-model comparison:
- Report `parse_failed` count per model per arm (absolute)
- Report abstain rate per model per arm
- Confirm the effect holds on parse-success-only
- A model showing "no effect" must be ruled out as a parsing artifact before
  claiming the effect is absent for that model

---

## Reproducibility Requirements (per run)

Commit to the experiment branch **before** running any arm:

- Random seeds (Python `random`, `numpy`, model temperature/seed)
- Model strings with version pins (e.g., `llama3.1:8b`, Ollama `manifest_digest`
  if available; Groq/OpenRouter model slug)
- SHA-256[:12] hash of each fixture file (see Appendix)
- Exact commands used to launch each arm

These form the reproducibility artifact that enables one-command re-execution.

---

## Appendix — Fixture Hash Protocol

Generate SHA-256 hashes of all fixture files when pre-registering:

```bash
python -c "
import hashlib, pathlib
for f in sorted(pathlib.Path('evals/fixtures').glob('*.json')):
    h = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
    print(f'{h}  {f.name}')
"
```

Paste the output into the experiment's pre-registration commit message.

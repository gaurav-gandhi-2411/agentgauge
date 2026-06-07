# spec.md — Q2b: catalog-aware description generation (recover the T18 gain without fabricating)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 8e26dd7 ·
**Branch:** `claude/q2b-catalog-aware`
**Routing:** DRAFT PR. Changes the generator's description path in `fixer.py` (generation behavior)
+ validated by a real-agent A/B. Draft-forcing #2/#3. **NOT condition #1** (no judge/scorer/rubric/
calibration changes).

**Pre-registration:** committed at branch start. Recovery metric, the no-fabrication guard, and the
negative-control tasks are fixed before the run.

---

## Why

Q2a proved the per-tool fixer recovers only 12.5% of the T18 oracle gain (F-vs-A not significant),
because the decisive distinctions are CROSS-TOOL (storage medium, op scope, soft/hard delete,
channel, directionality) and the generator never saw the siblings — all 14 misses were classification
(i). Q2b gives the generator its relevant neighbors so it can encode the distinguishing dimension,
and measures whether that recovers the gain.

## The failure mode to design against (not discover)

Q2a also showed the generator FABRICATES under low grounding (store_item cache->"persistent";
forward_record POST->"retrieval"). Prompting it to "distinguish from neighbors" will make it
fabricate DISTINCTIONS — inventing a difference between two genuinely-interchangeable tools because
it was asked to differentiate. So Q2b's success criterion is NOT just "F approaches O." It is:
**recover the gain on tools with REAL distinctions, AND do no harm on tools that are genuinely
ambiguous.** A recovery number without the fabrication guard is not acceptance.

---

## Scope

**IN:** catalog-aware description generation — a neighbor-selection step + a catalog-aware prompt
with an explicit no-fabrication instruction; re-run the Q2a three-arm setup with the new Arm F.

**OUT:** schema generation (unchanged); selection-among-few / call_correctness; scorer changes;
production embedding infra (neighbor-selection kept simple, see below).

## Design

- **Neighbor selection** (in `run_fixer`, passed into `_generate_description`): for each tool, select
  up to K (e.g. 5-8) candidate-confusable neighbors FROM THE CATALOG as an arbitrary server presents
  it — name/token similarity or a lightweight embedding/lexical cluster. **Must NOT read the T18
  fixture's family labels** (that would cheat; real servers have no such labels). Document the
  selection rule; it has to be one that would work on an unlabeled 200-tool catalog. Cap K so the
  prompt stays bounded at scale.
- **Catalog-aware prompt** (new variant of `_DESC_GENERATOR_PROMPT`): show the target tool AND its K
  neighbors (names + schemas + current descriptions). Ask for a description that states what THIS
  tool does and how it differs from the listed neighbors — with an explicit guard:
  "If this tool is NOT meaningfully different from a neighbor on the available evidence, say what it
  does plainly and DO NOT invent a distinction. Only state a difference supported by the names/
  schemas/descriptions shown." Reuse the shared JSON/text extraction helper (no fence bug).
- **Keep the abstain (is_low_grounding) and do-no-harm behavior from Tx** — catalog-awareness adds
  context; it does not license fabrication.

## Required validation (re-run Q2a's exact three-arm setup, new Arm F)

- Arm A = empty (floor). Arm F = Q2b catalog-aware fixer output. Arm O = T18 oracle (ceiling).
  Agent gemma2:9b; generator qwen3:8b; phase-separated GPU (generate -> ollama stop -> A/B with
  gemma-only watchdog). Same fixture, same 18 contested tasks, parse-success, task-clustered.
- **Recovery:** report (F-A)/(O-A) and sign tests F-vs-A, F-vs-O. Target: F significantly > A
  (recovery real), ideally F approaching O.
- **NO-FABRICATION negative control (the guard):** the T18 genuinely-ambiguous tasks (the Q2a/T18
  double-zeros: find_entries/lookup_data, book_slot/plan_event — tools NOT meaningfully distinct on
  evidence). For these, inspect the Q2b-generated descriptions: the generator must NOT assert a false
  distinction. Classify each ambiguous-tool description as FAITHFUL (plain, no invented difference)
  or FABRICATED (asserts a distinction unsupported by evidence). ANY fabrication on the control set
  is a FAIL regardless of recovery number.
- **Per-task diagnosis** (as Q2a): for each contested task, show the Q2b description and whether it
  now encodes the real distinction.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** neighbor-selection is deterministic and does not read
   fixture family labels (assert); catalog-aware prompt assembles target+neighbors; the no-fabrication
   instruction is present; shared extraction helper used; with a MockProvider, a tool with a real
   schema-difference neighbor yields a distinguishing description and an identical-neighbor case
   yields a plain (non-fabricated) one. No real model in committed tests.
2. **Real-agent three-arm (manual, in PR description):**
   - GPU exclusivity + parse_failed FIRST.
   - Recovery table (A/F/O, parse-success contested) + recovery fraction + sign tests.
   - NO-FABRICATION control result: FAITHFUL/FABRICATED per ambiguous tool. Any FABRICATED -> FAIL.
   - Verdict:
     - RECOVERS + FAITHFUL: catalog-awareness delivers the T18 value safely — the product claim
       closes (dimension validated AND tool moves it without harm).
     - RECOVERS but FABRICATES on control: unsafe — recovery bought by invented distinctions; needs
       a stronger grounding guard before it can ship.
     - LOW recovery: neighbor context insufficient (or selection too weak) — report why.
3. fixer schema path / scorer / judge / rubrics / calibration untouched; generator != judge asserted;
   verify.sh green; coverage >= 60%.

## Housekeeping

- TASKS.md: Q2b (TODO -> IN-REVIEW). STATUS.md: record recovery fraction AND the no-fabrication
  control outcome — both, not just recovery. Do not claim the fixer "delivers the T18 value" unless
  it recovered AND stayed faithful on the control.

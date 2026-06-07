# spec.md — Q4: scoped-source generation (does scoping fix the F-BODY misattribution?)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 03e72b1 ·
**Branch:** `claude/q4-scoped-source`
**Routing:** DRAFT PR. Changes generator source-assembly in fixer.py + real-agent A/B. Draft-forcing
#2/#3. **NOT condition #1.** Reuses the Q3 fixture unchanged.

**Pre-registration:** committed at branch start. The scoping rule, the neighbor-surface rule, the
two-failure-mode separation, and the no-misattribution control are fixed before the run.

---

## Why

Q3 showed source-with-docstrings (F-DOC) recovers 83% of the T18 gain and is faithful, but body-only
(F-BODY) FAILED via cross-tool SOURCE MISATTRIBUTION: `find_entries` cited `_db` (a symbol belonging
to OTHER tools in the same file) as a distinction. Root cause (from code): the source-aware prompt
was fed the WHOLE FILE, and `source`/`neighbors` are mutually exclusive, so the generator's only
"neighbor" signal was other functions' full bodies sitting in the blob — exactly what it misattributed
from. This is an attention/scoping defect, not an information defect. Q4 tests whether scoping the
source eliminates the misattribution while keeping the recovery.

## Design — scoped source + neighbor surfaces (the architectural change)

- **Scoped source:** `source` passed to the generator = ONLY the target tool's own function (def +
  body via a scoped extractor), NEVER the whole file.
- **Neighbor surfaces:** ALSO pass the K confusable neighbors as SIGNATURES + DOCSTRINGS ONLY —
  bodies STRIPPED. (Requires allowing source + neighbor-surfaces together; the current source-XOR-
  neighbors convention is broken for this path.) This gives the generator what-to-contrast-against
  without any foreign implementation to misattribute from.
- **Mechanical guarantee (CI-enforced):** neighbor BODIES never appear in the assembled prompt.
  If foreign bodies cannot be in the prompt, cross-tool body-misattribution is impossible by
  construction.
- Keep the no-fabrication guard verbatim. Reuse the shared JSON/text extractor.

## Conditions (reuse Q3 fixture; compare to Q3 full-file results)

- **Q4-DOC-scoped:** target's own body WITH docstring + neighbor surfaces. (Expected safe + recover;
  baseline that scoping didn't break the easy case.)
- **Q4-BODY-scoped:** target's own body, DOCSTRINGS STRIPPED + neighbor surfaces. THE TEST: does
  scoping remove the F-BODY misattribution that whole-file body-only caused?
- Compare both to Q3's F-DOC (83%, faithful) and F-BODY (recovered-but-FABRICATED).

## Separate the two failure modes (do not blur)

- **Misattribution** (cross-tool, e.g. find_entries->_db): should VANISH under scoping — it's the
  primary safety test. Measured on the equivalent-control pairs.
- **Genuine-absence-from-body** (e.g. retire_data read-only was in the docstring, not the body):
  scoping CANNOT fix this — a stripped body lacks the fact. Expected to persist in Q4-BODY-scoped.
- The verdict MUST distinguish "fabricated less" (misattribution gone) from "recovered less" (info
  not in body). Report misattribution rate and multi-way-distinction recovery SEPARATELY.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):**
   - Scoped extractor returns ONLY the target tool's function (assert other tools' bodies/symbols
     absent from the extracted string).
   - Neighbor-surface assembly includes neighbor signatures + docstrings and EXCLUDES neighbor
     bodies — assert no neighbor body line appears in the assembled prompt (the mechanical guarantee).
   - source + neighbor-surfaces compose in one prompt; no-fabrication guard present; shared extractor
     used. MockProvider tests for the scoped path. No real model in committed tests.
2. **Real-agent A/B (manual, in PR description):**
   - GPU exclusivity + parse_failed FIRST.
   - Table: A / Q4-DOC-scoped / Q4-BODY-scoped / O (parse-success contested) + recovery for each +
     sign tests. Show Q3 F-DOC/F-BODY alongside for comparison.
   - No-MISATTRIBUTION control: for the equivalent pairs (find_entries/lookup_data,
     book_slot/plan_event), classify FAITHFUL-EQUIVALENT / INCIDENTAL-BUT-TRUE / FABRICATED, BOTH
     scoped conditions. The Q3 find_entries->_db misattribution MUST NOT recur. Any FABRICATED -> FAIL.
   - Per-task diagnosis splitting misattribution-misses from absent-from-body-misses.
   - Verdict matrix:
     - Q4-BODY-scoped FAITHFUL + recovers ~ Q4-DOC: scoping recovers the undocumented-server case
       SAFELY — body-only is viable with proper scoping.
     - Q4-BODY-scoped FAITHFUL but recovers < DOC (misses multi-way): misattribution FIXED, but body
       genuinely lacks some distinctions -> boundary holds at "docstrings needed for the hardest
       multi-way cases," but the SAFETY defect is solved.
     - Q4-BODY-scoped still FABRICATES: scoping insufficient; body-only remains unsafe.
3. fixer schema path / scorer / judge / rubrics / calibration untouched; generator != judge asserted;
   verify.sh green; coverage >= 60%.

## Housekeeping

- TASKS.md: Q4 (TODO -> IN-REVIEW). STATUS.md: record Q4-DOC-scoped and Q4-BODY-scoped recovery
  SEPARATELY + the misattribution-control outcome + which verdict-matrix cell, explicitly contrasted
  with Q3 (whole-file). State whether scoping solved the safety defect independently of whether it
  recovered the multi-way distinctions.

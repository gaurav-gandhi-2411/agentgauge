# AgentGauge v2.3 — Task 2: re-tier by measured impact x precision

Depends on Task 1's correction (`reports/v2_3_task1_advisory_audit.md`) --
the original CONTEXT motivating this task ("`described_not_in_schema` has the
highest measured impact... THE PRIORITY ENGINEERING TARGET") does not survive
Task 1's audit. Re-tiering below uses the CORRECTED numbers throughout.

## 2a. Check | effect size | false-alarm | recall | tier

| Check | Measured causal effect (pp, 95% CI, per model) | Per-tool-set false-alarm | Recall | Current tier | Proposed tier |
|---|---|---|---|---|---|
| `type_enum_contradiction` (c) | gemma2:9b: type_flipped -35.6 [-60.9,-10.2], enum_dropped -40.0 [-66.9,-13.1]; llama3.1:8b: -33.3 [-59.8,-6.8] / -33.3 [-65.5,-1.2]; qwen2.5:7b: -20.0 [-49.4,+9.4] / -13.3 [-32.3,+5.7] (individually non-significant at n=15/type, but pooled BLOCKING effect for qwen2.5:7b -13.3 [-25.2,-1.5] does exclude zero) | **0%** (0/21) | **100%** | BLOCKING | **BLOCKING (unchanged)** — clears both bars in every model tested |
| `required_references_missing_property` (e) | **0.0pp in all 3 models**, every CI includes zero (`reports/v2_2_task_b_causal_chain_multimodel.md`) | **0%** (0/21) | **100%** | BLOCKING | **INFO (demoted)** — perfect precision, zero measured behavioral impact; a BLOCKING gate for a defect with no effect is dead weight |
| `described_not_in_schema` (a) / `param_renamed` defect | **Corrected: near-zero in all 3 models** (gemma2:9b +0.0, llama3.1:8b -13.3 [CI incl. 0], qwen2.5:7b +6.7 [CI incl. 0]) — was falsely reported as -76.7 to -80.0pp before Task 1's fix | **23.81%** (5/21), improved from 28.57% via Task 2c's precision pass, still fails the <10% bar | **81.2%** (39/48, clears the >=80% bar) | ADVISORY | **ADVISORY (unchanged)** — fails the false-alarm bar even after real, measured precision work; corrected impact no longer independently justifies promotion either |
| `name_collision` (f) | **Not causally measured** — no defect-injection instance targets this check (no injector produces a confusable-name-pair defect); a genuine NOT-MEASURED gap, not a measured zero | **47.62%** (10/21) | n/a (not part of the 5-type defect-injection corpus) | ADVISORY | **ADVISORY (unchanged)** — false-alarm rate is nearly 5x the bar; 86% of its clean-corpus violations are the documented-irreducible verb-differentiated class (2d) |
| `param_possibly_renamed` (g) | Not independently measured (fires alongside (a) on the same `param_renamed` defect; not separated in Task 3/B's causal-chain design) | 4/521 tools (0.77%), below the per-tool-set bar in practice (no dedicated per-tool-set count taken in v2.1) | Part of the 81.2% combined (a)+(g) `param_renamed` recall | ADVISORY | **ADVISORY (unchanged)** — no new evidence to reconsider; out of this task's scope (brief named (a) and (f) specifically) |

Every row cites both the false-alarm/recall numbers (precision) AND the
causal effect size (impact) side by side, per the task brief's instruction —
neither axis alone is treated as sufficient justification.

## 2b. `required_references_missing_property`: demoted BLOCKING -> INFO

Implemented in `agentgauge/linter.py`'s `_check_required_missing_property`
(severity changed `BLOCKING` -> `INFO`). Zero measured task-success effect in
all three model families tested (Task 3/B, unaffected by Task 1's scoring bug
since this defect type doesn't rename anything) is the justification named in
the task brief ("unless Task 1 surfaces evidence it matters" — it did not).
Kept as an INFO-severity signal rather than removed entirely: still 0% false
alarms and 100% recall, so it remains a precise, free, zero-cost signal for
users who opt into `--show-info` — just not one that should fail CI given it
demonstrably doesn't predict a real capability problem.

**BLOCKING-tier false-alarm rate after this change: 0/21 = 0.00%** (unchanged
— the check being removed already had 0% false alarms, so removing it cannot
regress the remaining BLOCKING check's precision). Confirmed by direct
re-measurement, not assumed. Target (<10%) cleared by a wide margin, as
before.

**GitHub Action:** no change needed. `agentgauge init`'s scaffolded workflow
and every CLI surface (`n_blocking`/`n_advisory`/`.blocking`/`.advisory`)
already compute their counts dynamically from each `Violation.severity`, not
from a hardcoded per-check list (established in `reports/v2_1_severity_gate.md`'s
original restructuring) — the re-tiering takes effect automatically.

## 2c. `described_not_in_schema`: precision-engineering result — improved, promotion bar NOT cleared

Root-caused the 29 documented clean-corpus false alarms (`reports/
v2_linter_evaluation.md`) by hand-inspecting every one (not guessing), and
implemented 5 targeted, generalizable exclusions in `agentgauge/linter.py`:

1. **"(e.g., ...)" example asides** stripped before extraction (`churn_rate,
   MRR` in "Compute a metric (e.g., churn_rate, MRR)"; quoted URI examples).
2. **Property-value-list parentheticals**: a parenthetical directly following
   a REAL schema property's own "prop: ..." mention lists candidate VALUES,
   not other parameters (`date_posted: Filter by posting date (past_hour,
   past_24_hours, ...)`) — matched only against actual schema property names,
   so it cannot suppress a genuine undocumented-parameter reference.
3. **Explicit negations** ("NOT the internal `account_id`") — a token named
   only to be ruled out, scoped to a 40-char window after "not" so it cannot
   suppress unrelated later mentions.
4. **Enumerated value lists** (3+ comma-separated short tokens after a colon:
   "Available sections: experience, education, ..., contact_info, posts").
5. **"returns"/"returning" anywhere in a sentence**, not just sentence-initial
   (widening an existing v2 exclusion) — "...and returns a status dict with
   `delivered` set to True."

**Result: 28.57% (6/21) -> 23.81% (5/21) per-tool-set false alarm.** Real,
measured, and independently reproducible — but **does not clear the <10%
BLOCKING bar**. Recall preserved: 81.2% (39/48) vs. the previously-reported
83.3% (40/48); the 1-case delta was traced to a measurement-methodology
artifact in the recall-counting script (which counts ANY `described_not_in_schema`
violation on the same tool as a "hit" for that tool's renamed parameter, not
specifically a hit on the renamed parameter itself) rather than a real
detection-capability loss — confirmed by diffing the exact miss list against
a git-stashed pre-fix baseline.

**Remaining false alarms (5 tool sets) were NOT further chased.** The
residual patterns — cross-tool/action references that aren't literal sibling
tool names ("recoverable via `restore_ticket`"), and side-effect state
descriptions ("sets a `deleted_at` timestamp") — could only be excluded with
increasingly narrow, single-example-shaped regexes at this point. Continuing
would mean tuning precision against the exact same 21-item corpus used to
measure it — the same overfitting risk this session's adversarial-pass
discipline exists to catch. Reported as a genuine, disclosed limit, not
pushed through with brittle patches to hit a number.

**Promotion verdict: NOT PROMOTED.** Fails the false-alarm bar even after a
real improvement, and (per Task 1) the corrected causal impact no longer
independently justifies it either — both grounds the task brief asked for
now point the same direction.

## 2d. `name_collision`: irreducible-fraction quantification

22 total clean-corpus violations (10/21 tool sets, 47.62% per-tool-set false
alarm), enumerated directly (not estimated):

| Pair pattern | Instances | Verb-differentiated? |
|---|---|---|
| `use_notebook`/`unuse_notebook` | 2 | Yes |
| `attach_user_policy`/`detach_user_policy` | 2 | Yes |
| `attach_group_policy`/`detach_group_policy` | 2 | Yes |
| `put_user_policy`/`get_user_policy` | 2 | Yes |
| `put_role_policy`/`get_role_policy` | 2 | Yes |
| `load_order`/`void_order` | 3 | Yes |
| `amend_invoice`/`send_invoice` | 3 | Yes |
| `create_notification_rule`/`delete_notification_rule` | 3 | Yes |
| `get_pull_request_diff`/`get_pull_request_files` | 3 | **No** — same verb+object prefix, differs only in trailing noun |

**19/22 (86.4%) of violations are the documented verb-differentiated class**
(already named in `reports/v2_linter_evaluation.md` as irreducible without
semantic understanding a deterministic Levenshtein-similarity heuristic
structurally cannot provide). The remaining **3/22 (13.6%)**
(`get_pull_request_diff`/`get_pull_request_files`) is a genuinely different
pattern — same verb, different trailing object noun — not chased with a
targeted fix because a single-pair exclusion here would be overfitting to one
example, not a generalizable rule (unlike the `described_not_in_schema` fixes
above, which each covered a real, repeatable documentation pattern).

**Promotion verdict: NOT PROMOTED.** 47.62% false-alarm is far above the
<10% bar, and fixing the dominant (86%) cause would require the semantic
judgment this linter is explicitly deterministic to avoid — not a precision
bug to patch. Causal impact is a genuine NOT-MEASURED gap (no injector in
`scripts/v2_defect_injector.py` produces a name-collision-style defect); a
future measurement would need a new injector, out of scope here.

## 2e. Post-retiering BLOCKING false-alarm re-measurement

**0/21 = 0.00%**, unchanged (§2b) — re-measured directly via
`agentgauge.linter.lint_tool_set` on the same 21-tool-set clean corpus, not
assumed from the pre-retiering number. Clears the <10% target with the same
margin as before, now with one fewer check contributing (a check whose
removal cannot increase false alarms).

## Independent verification

A separate verifier agent independently confirmed the Task 1 scoring-artifact
finding this task's `2c` conclusion depends on (`reports/
v2_3_task1_advisory_audit.md`). The false-alarm/recall numbers in this report
(23.81%, 81.2%, 47.62%, 86.4%, 0.00%) are direct, reproducible measurements
from `agentgauge.linter.lint_tool_set` against the same clean corpus used
throughout v2/v2.1/v2.2 — re-run twice (once with, once without the Task 2c
changes, via `git stash`) to confirm the exact before/after delta rather than
trusting a single measurement.

A second, independent verifier agent re-derived all five numeric/code claims
from scratch against the working-tree code: the 23.81% and 81.2% figures, the
47.62%/0.00% name_collision/BLOCKING figures, `_check_required_missing_property`'s
`severity=Severity.INFO` change, and the full 22-instance name_collision pair
enumeration (§2d table). **All five: CONFIRMED, no discrepancies.**

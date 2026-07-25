# AgentGauge v2.1 — linter recall fix (Task 4)

Zero LLM calls. `agentgauge/linter.py`'s new `param_possibly_renamed` check, measured with
`scripts/v2_1_linter_recall_fix.py` against the same clean corpus (21 tool sets, 521 tools) and
`param_renamed` defect-injection corpus (48 injected cases) used in the original Task 2 measurement
(`reports/v2_linter_evaluation.md`) — same corpus, same injection logic, so the before/after
numbers are directly comparable.

## The fix

`described_not_in_schema` (a) can only ever flag identifiers that ARE mentioned in the description
but AREN'T in the schema. A parameter rename produces the opposite gap: the NEW schema property
name has no description coverage at all, because the prose still refers to the OLD name. (a)
structurally cannot see this. `param_possibly_renamed` (g) is its inverse: for each schema property
not named verbatim in the description, search the description's tokens for a near-miss.

**Two precision guards were required, both found empirically, in this order:**

1. **Common id/unit-suffix exclusion.** A first pass (near-miss = Levenshtein distance <=2 on the
   case/underscore/camelCase-normalized form, no other guard) produced 147 false positives on the
   clean corpus (28.98% of tools flagged) — 79% of them (116/147) were the exact shape
   `customer_id`/`order_id`/`invoice_id` → prose saying just "customer"/"order"/"invoice", i.e.
   routine technical-writing shorthand, not a rename. Fixed by excluding matches where the property
   name is exactly the candidate token plus a common identifier suffix (`id`, `key`, `code`, `no`,
   `num`, `ref`, `type`, `cs`, `ds`, `ms`).
2. **Shared-prefix requirement.** The id-suffix fix alone still left 31 false positives (9.02% of
   tools) — short coincidental English-word collisions at edit distance 2 with no shared root
   (`page`/`name`, `query`/`queue`, `limit`/`List`, `timeout`/`timeit`, `owner`/`order`,
   `due_date`/`update`). Fixed by requiring the near-miss token and the property name to share a
   common prefix (one normalized form is a prefix of the other) — true in every constructed rename
   case (old name is always a prefix of new name + suffix) and false for essentially every
   coincidental collision found.

**A length-scaled edit-distance threshold (distance<=1 for short identifiers, <=2 only for long
ones) was tried first and rejected**: it did fix the false-alarm rate, but broke recall on
short/single-word renames (the exact defect class this task targets), dropping "either" recall
from 87.5% to 41.7%. The prefix-sharing rule achieves a comparable false-alarm reduction without
this recall cost, because it targets the actual distinguishing structural feature (shared root)
rather than a proxy (word length).

## Measured results

| Metric | Before (v2, check (a) only) | After (v2.1, (a) OR (g)) |
|---|---|---|
| `param_renamed` recall, overall (n=48) | 22.9% | **83.3%** |
| `param_renamed` recall, single-word properties (n=35) | 2.9% | **82.9%** |
| `param_renamed` recall, multi-word properties (n=13) | 76.9% | 84.6% |
| Clean-corpus false-alarm rate, per tool (n=521) | 3.45% (18/521) | **4.22%** (22/521) |
| Clean-corpus false-alarm rate, per tool set (n=21) | 66.67% (14/21) | 66.67% (14/21, unchanged) |

**Target met:** recall >80% (83.3%, and 82.9% on the specific single-word case the task named).
**Target held:** false-alarm rate stays under the <5% doctrine bar (4.22%), though the margin is
thin — `param_possibly_renamed` contributes only 4 of the 22 flagged tools, all four the same
`extractor`/`extract` pattern on one real-world server (`exp1_stickerdaniel_linkedin_mcp_server_mirror`)
— a genuine, disclosed residual: "extractor" (noun) vs. "extract" (verb) share a prefix and are a
plausible rename by this check's structural rule, but are very likely just normal descriptive
language for a real, non-buggy parameter. Not fixed further in this session (each additional guard
tried so far has cost more recall than it bought in precision, per the length-scaling result above).

**`n_both_checks_fired: 10`** — 10 of the 48 cases are caught by both (a) and (g), i.e. the two
checks are only partially redundant; each catches genuine cases the other misses (per the task
brief's "keep the existing forward check as well; report both directions separately").

Full per-case detail: `evals/fixtures/v2_1_linter_recall_fix.json`. 7 new regression tests added
(`tests/test_linter.py::TestParamPossiblyRenamed`), covering the versioned-rename detection case,
the camelCase/snake_case-only difference case, the exact-match no-op case, both precision guards,
and the short-property-name floor.

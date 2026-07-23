# AgentGauge v2 — axis triage (Task 1)

Computed entirely from `evals/fixtures/predictive_validity/results_raw.json` (n=44 valid records),
zero inference, reusing `scripts/predictive_validity_analysis.py`'s own Spearman/partial-correlation
helpers for consistency with every number already published in `reports/predictive_validity_study.md`.

## 1a. Inter-axis correlation matrix + correlation with description length

| Axis | ρ vs. description length | p |
|---|---|---|
| `schema_completeness` | +0.048 | 0.758 |
| `description_quality` | +0.590 | 0.0000248 |
| `discoverability` | **+0.836** | 1.6e-12 — **LENGTH PROXY (\|ρ\|>0.7)** |
| `selection_accuracy` | +0.165 | 0.284 |
| `call_correctness` | — DEGENERATE (zero variance across all 44 records) |
| `error_legibility` | -0.166 | 0.281 |
| `robustness` | — DEGENERATE (zero variance across all 44 records) |
| `overall_score` | +0.511 | 0.00039 |

**Redundant pairs (\|ρ\|>0.6) among the 6 non-degenerate fields:**
- `schema_completeness` ↔ `overall_score`: ρ=0.713 (partly mechanical — `schema_completeness` is a
  25%-weighted component of `overall_score`, so some of this correlation is definitional, not new
  evidence of a shared underlying construct)
- `description_quality` ↔ `discoverability`: ρ=0.632 (**not** mechanical — these are two separately
  judged axes with no shared weighting; this is real evidence they capture overlapping, not
  distinct, signal)
- `description_quality` ↔ `overall_score`: ρ=0.867 (partly mechanical, 25% weight)

## 1b. Degenerate axes — deleted outright

**`call_correctness` and `robustness` are deleted from v2.** Both show zero variance across all 44
tool sets in this study's corpus — spanning empty descriptions, hand-curated oracles, and 5
real-world API mirrors. An axis that never moves across that range of inputs contributes nothing
to any product surface, positive or negative; there is no incremental-validity test to even run on
a constant. This is not a new finding — the original PV study already excluded both as
"degenerate — excluded" from its correlation table — but v2 makes the deletion structural (removed
from the scorer entirely) rather than a runtime exclusion flag.

## 1c. Length-residualized re-test of every surviving axis

Partial Spearman correlation of each surviving axis (and `overall_score`) with real task success,
controlling for `baseline_desc_length`, against the pre-committed doctrine bar (`reports/
v2_eval_doctrine.md`, Component 4: must survive Bonferroni correction across the m axes retested).

| Axis | raw ρ | **partial ρ (net of length)** | p | Survives Bonferroni (m=6, α/m=0.00833)? |
|---|---|---|---|---|
| `schema_completeness` | +0.234 | +0.231 | 0.136 | **NO** |
| `description_quality` | +0.417 | +0.308 | 0.044 | **NO** |
| `discoverability` | +0.186 | **-0.132** (sign flip) | 0.399 | **NO** |
| `selection_accuracy` | -0.211 | -0.279 | 0.070 | **NO** |
| `error_legibility` | +0.042 | +0.099 | 0.530 | **NO** |
| `overall_score` (composite) | +0.371 | +0.262 | 0.089 | **NO** |

**Zero of six survive.** `discoverability` is the most striking case: its raw correlation
(ρ=+0.186, already non-significant) doesn't just weaken once length is controlled for — it
**flips sign** to a small negative partial correlation, meaning essentially all of its apparent
(non-significant) raw relationship with success was riding on description length, not independent
"discoverability" signal. This is the single cleanest confirmation in this dataset that a judged
axis can look like it's measuring something real while actually just re-deriving `len()`.

## 1d. Decision

**No axis from v1 survives as a retained, scored "quality" dimension in v2.** Per the eval
doctrine's Component 4 (written before this test ran): the pre-committed gate was partial
correlation surviving Bonferroni correction, and nothing does. This is not a partial or soft
result requiring judgment calls — every one of the six testable fields fails the identical bar,
including the composite `overall_score`.

**What is cut, and why, by category:**
- **Deleted (degenerate):** `call_correctness`, `robustness` — zero variance, nothing to triage.
- **Deleted (no incremental validity net of length):** `schema_completeness`,
  `description_quality`, `discoverability`, `selection_accuracy`, `error_legibility`,
  `overall_score` — all six fail the same pre-committed bar. None is rebuilt as a scored axis;
  rebuilding a scoring formula that has already failed this test twice (raw, then length-controlled)
  is not warranted by anything in this data.
- **Rebuilt, but reclassified out of the "scored axis" product surface entirely:**
  `discoverability`'s own internal structure (per `agentgauge/CLAUDE.md`'s existing calibration
  notes) already blends a deterministic Levenshtein near-duplicate-name collision heuristic (60%
  weight) with an LLM-judged sub-score (40% weight, the part shown above to be almost pure length
  proxy). The **deterministic collision-detection half is not implicated by this triage** — it was
  never a correlational score, it's a structural pairwise check ("do two tool names collide"),
  which is a detection task, not a correlation task, and belongs in the linter (Task 2), not in a
  retained axis. **Action: fold the existing name-collision heuristic into the Task 2 deterministic
  linter as its own check; delete the LLM-judged `discoverability` sub-score entirely** (it is the
  component shown to sign-flip once length is controlled for).

**Net effect:** v2 ships with zero LLM-judged correlational scoring axes. Every one of v1's 8 axes
is either deleted (6 of 8, no incremental validity or zero variance) or has its one genuinely
structural, non-correlational sub-component extracted and moved into the deterministic linter (the
name-collision heuristic, formerly 60% of `discoverability`). This is the intended, honest outcome
of applying the doctrine's pre-committed gate, not a partial rebuild softened by later
convenience — the doctrine said no axis ships without clearing this bar, and none did.

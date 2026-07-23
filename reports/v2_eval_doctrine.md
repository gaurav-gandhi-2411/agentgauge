# AgentGauge v2 — evaluation doctrine

Written before any v2 code, per the rebuild's evaluation doctrine requirement. Each component
below declares its actual task, the metric class that fits that task, the baseline it must beat,
and the target margin — before implementation, not fitted to whatever the code produces.

**Why this document exists:** the v1 predictive-validity study (`reports/predictive_validity_study.md`)
falsified "an 8-axis correlational quality score predicts real task success." The root cause was not
just insufficient data — it was evaluating a **detection task** (does this tool set have a defect
that will hurt an agent) with a **correlational metric** (does a continuous score correlate with a
continuous outcome). A defect either exists or it doesn't; a regression either happened or it
didn't. Those are classification/detection questions. Precision, recall, false-alarm rate, and
minimum detectable effect are the metrics that answer classification/detection questions.
Correlation coefficients are not, and no amount of additional data collection would have fixed that
mismatch — this doctrine exists so v2 does not repeat it with a different metric.

## Component 1: Deterministic schema-consistency linter (Task 2)

- **Actual task:** binary classification — does this tool's description/schema pairing contain a
  detectable, named defect (schema-internal contradiction, description-vs-schema mismatch)?
- **Metric:** precision, recall, F-beta with beta<1 (favoring precision — a linter that's wrong
  half the time gets disabled, per the task brief's own framing), and false-alarm rate on a corpus
  of tool sets known to have no defects (the "clean corpus").
- **Baseline it must beat:** (i) no linter at all (i.e., is the false-alarm rate low enough and the
  recall high enough to be worth running at all), (ii) raw JSON-Schema structural validation (does
  this add anything beyond what a standard schema validator already catches for free), (iii) a
  single-prompt LLM "find inconsistencies" baseline (does a deterministic, zero-cost check beat an
  LLM call on precision, and at what cost ratio).
- **Target margin:** false-alarm rate <5% on the clean corpus (task brief's explicit target).
  Precision must exceed the JSON-Schema-validator baseline's precision (that baseline is expected
  to have near-zero recall on the semantic defects this checker targets, since JSON-Schema
  validation cannot see description text at all — the comparison is there to make explicit which
  defects are structural-only vs. requiring description-schema cross-referencing). No correlation
  number is reported for this component as a measure of quality — only precision/recall/false-alarm.

## Component 2: Regression harness (`agentgauge diff`) (Task 3)

- **Actual task:** hypothesis test — did a change to a tool set's descriptions/schema cause a
  measurable change in real task-success rate? This is an A/B comparison with a null hypothesis
  (no true effect), not a correlation.
- **Metric:** minimum detectable effect (MDE) at fixed sample size and statistical power (80%/95%),
  false-alarm rate under the null (repeated identical-vs-identical comparisons), and replay
  determinism rate (does re-running the identical inputs reproduce the identical classification).
- **Baseline it must beat:** (i) no regression check at all (shipping blind), (ii) a naive
  point-estimate-only comparison with no CI or significance test (which cannot distinguish a real
  regression from sampling noise — exactly the failure mode a CI gate must not have).
- **Target margin:** false-alarm rate under the null <5% (task brief's explicit target). The MDE
  table is reported as a measured fact at whatever n the harness is actually run at, not asserted
  as a target — this doctrine commits to reporting the real MDE numbers, including if they are
  worse than a reader might hope for at small n.

## Component 3: Argument-vs-selection decomposition (Task 4)

- **Actual task:** decompose a single "did the trial succeed" outcome into two conditionally
  distinct sub-outcomes (tool-selection-correct; given selection-correct, was the constructed
  argument correct), because the `call_constraints` family's real failure mode (100%
  argument-construction, 0% selection) is invisible to any metric that only reports the joint
  outcome.
- **Metric:** the same precision/recall-against-labeled-defects framework as Component 1, applied
  specifically to defects that manifest as an argument-construction failure with unchanged
  selection accuracy — this is evaluated as its own row in Component 1's defect-injection
  evaluation table, not a separate metric class.
- **Baseline it must beat:** the v1 joint success-rate metric, which by construction cannot
  distinguish these two failure modes at all (recall = 0 for this defect class, definitionally,
  since it never separates the two components in the first place).
- **Target margin:** any non-zero recall on argument-construction-only defects is an improvement
  over the v1 baseline's structural zero. A specific numeric target is not pre-committed beyond
  that, since this is the first time this decomposition has been measured at all.

## Component 4: Any retained LLM-judged axis (from Task 1's triage)

- **Actual task:** for any of the original 8 axes that survives triage into v2 at all, its actual
  task is still "does this axis's score predict real task success" — the same task the PV study
  tested, not a new one. Retaining an axis does not change what it is being asked to do.
- **Metric:** partial correlation controlling for description length (the exact test that falsified
  most of v1), reported alongside the raw correlation, not instead of it.
- **Baseline it must beat:** `baseline_desc_length` (free, zero-LLM-call). This is the same bar v1
  already applied and already found none of the 8 axes clearing net of length.
- **Target margin:** partial correlation must reach significance surviving the same
  multiple-comparison correction bar used in the PV study (Bonferroni across however many axes are
  actually retested). No axis ships into v2's product surface as a "quality score" without clearing
  this bar — this is the doctrine's hard gate on Task 1's outcome, decided before Task 1 runs, not
  after.

## Cross-cutting rule

**No component in this rebuild is evaluated on a metric chosen after seeing what makes it look
good.** Every metric above was fixed by the task class (detection vs. hypothesis test vs.
correlation) before any v2 code was written or any v2 number was computed. Where a component fails
its own declared bar, that failure is reported as a finding, in the same way the PV study's four
falsified/negative results are reported as its main contribution, not omitted.

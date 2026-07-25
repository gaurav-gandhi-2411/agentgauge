# AgentGauge v2.3 — Task 1: auditing the -80pp ADVISORY effect

Local Ollama only (gemma2:9b, llama3.1:8b; qwen2.5:7b pulled locally mid-task, GPU
was free throughout -- no GCP used anywhere in this task).
`scripts/v2_3_advisory_audit.py`, `scripts/v2_3_corrected_advisory_effect.py`,
`evals/fixtures/v2_3_advisory_audit.json`, `evals/fixtures/v2_3_corrected_advisory_effect.json`.

**Headline: the -76.7 to -80.0pp ADVISORY (`param_renamed`) effect reported in
`reports/v2_2_task_b_causal_chain_multimodel.md` is predominantly a SCORING
ARTIFACT, not a real agent capability degradation. This is measurement artifact
#7.** Corrected effect size: statistically indistinguishable from zero in
**all three model families** (gemma2:9b: +0.0pp; llama3.1:8b: -13.3pp; qwen2.5:7b:
+6.7pp -- all three CIs include zero, no consistent direction across models).

## 1a. Is the injected description obviously broken?

Ten sample `param_renamed` injections inspected directly (deterministic, zero
inference): in every case, **the description text is completely unchanged,
fluent, natural prose** -- only the JSON schema's property KEY changes (e.g.
`field` -> `field_v2`, with `required` updated consistently to the new name so
the mutated schema stays internally valid). A developer reading only the
description would see nothing wrong; the mismatch is visible only by
cross-referencing the description against the actual schema JSON. **Not
obviously malformed -- genuinely subtle**, unlike the BLOCKING-class
injectors' disclosed "bolted-on sentence" caveat (`reports/
v2_2_task_b_causal_chain_multimodel.md` B6). This part of the injection design
is sound.

## 1b. Naturalistic injection -- already the case, and irrelevant to what was actually wrong

The brief asked for a version that "modifies an existing parameter reference
in place... instead of appending a sentence." Checked against the actual
`inject_param_renamed` source: **this is already exactly what it does** --
it never appends anything; it renames the schema key in place and leaves the
description's existing reference to the old name completely untouched. There
is no more-bolted-on alternate version that was run instead of this one. The
premise behind 1b (that this measurement had the same injection-realism
problem as the BLOCKING checks) does not hold -- but auditing it anyway
surfaced a **more fundamental problem**, described in 1c/1d below.

## 1c. Failure-mode decomposition -- overwhelmingly argument-construction, and mostly a scoring bug

Re-ran all 6 original instances locally with full `RunResult` instrumentation
(selected_tool, success, error, parse_failed, constructed_args -- fields the
original measurement's scoring collapsed into a single pass/fail scalar and
did not retain):

| Model | n | argument_construction_failure | wrong_tool_selection | success |
|---|---|---|---|---|
| gemma2:9b | 15 | 93.3% | 0% | 6.7% |
| llama3.1:8b | 15 | 86.7% | 6.7% | 6.7% |
| qwen2.5:7b | 15 | 86.7% | 6.7% | 6.7% |

**Zero refusals or parse failures in 30 observations.** The failure is not
"the agent gives up" and not "the agent picks the wrong tool" (that
confound, relevant to Task 3's confusable-tool-selection question, is absent
here) -- it is concentrated entirely in argument construction. This much was
expected and unremarkable on its own. What was NOT expected:

**Inspecting the actual `constructed_args` for every "argument construction
failure" revealed the agent was mostly getting the task exactly right.**
Example: task "Get all orders where the status field is set to 'pending'",
constraint `param='field', gold='status'`. Agent's constructed_args:
`{'field_v2': 'status', 'value': 'pending'}` -- **both values completely
correct**, using the renamed key exactly as the mutated schema requires. This
was scored as a 50% failure (1 of 2 constraints) purely because the scorer's
constraint checks `constructed_args.get('field')` -- the ORIGINAL,
pre-rename parameter name -- which is absent from a dict keyed `field_v2`.

Re-classifying every "failure" against the RENAMED key (does `constructed_args`
contain the new key with a value satisfying the original constraint's
intent?):

| Model | n | Scoring artifact (agent correct, scorer wrong) | Genuine failure |
|---|---|---|---|
| gemma2:9b | 15 | 12/14 (86%) | 2/14 (wrong value once, one different-shape miss) |
| llama3.1:8b | 15 | 10/13 (77%) | 3/13 (different-shape misses; zero cases of the agent still using the stale old key) |

**Zero cases, in any of the three models, of the agent still using the OLD
(stale) parameter name.** Every genuine failure was either a wrong VALUE
(correct key, wrong content) or a completely different response shape (e.g. a
nested `{"filter": {...}}` object) -- never the specific "agent got fooled by
the stale description name" failure mode this defect type is supposed to
measure.

**Independent verification:** a separate verifier agent re-derived this from
scratch against `evals/fixtures/v2_3_advisory_audit.json` and
`constraints.py`, confirmed the mechanism (`inject_param_renamed` renames the
schema key without touching the description; `constraint_satisfaction` has no
rename-awareness anywhere), and independently estimated ~77% of the
"argument construction failure" category across 22 gemma2:9b/llama3.1:8b
instances is this scoring artifact. A second verifier pass independently
re-checked the qwen2.5:7b-specific numbers (not re-covered by the first pass)
against the same raw data and found **13/13 (100%)** of its "argument
construction failure" entries were scoring artifacts -- every one used the
correctly-renamed key with a value satisfying the original gold constraint.
**CONFIRMED across all three models.**

## 1d. Corrected effect size -- report both numbers

Built `constraint_satisfaction_renamed` (`evals/fixtures/predictive_validity/
constraints.py`) -- scores a mutated-variant call using a rename-aware key
lookup, added as a NEW function rather than changing `constraint_satisfaction`
in place, so no other (non-rename) measurement's already-reported numbers are
retroactively altered. Re-scored the exact same before/after task pairs:

| Model | Original (reported) | Corrected |
|---|---|---|
| gemma2:9b | **-76.7pp** [-103.7, -49.6] | **+0.0pp** [-20.5, +20.5] -- clean null |
| llama3.1:8b | **-80.0pp** [-102.1, -58.0] | **-13.3pp** [-40.8, +14.1] -- CI includes zero |
| qwen2.5:7b | **-76.7pp** [-98.9, -54.4] | **+6.7pp** [-7.1, +20.4] -- CI includes zero |

**Per the task brief's instruction: the corrected (near-null) number is the
shippable claim, not the original one.** Logged as measurement artifact #7.

**Blast radius of this artifact, checked explicitly:** the BLOCKING-class
causal-chain measurements (`type_flipped`, `enum_dropped`,
`contradictory_required_claim`) do not rename any schema key -- they change a
`type` field, an `enum` list, or add a bogus `required` entry, none of which
shift where a constraint's `param` name should be looked up. **This bug is
scoped entirely to the ADVISORY (`param_renamed`) measurement.** The
BLOCKING effect sizes reported in `reports/v2_2_task_b_causal_chain_multimodel.md`
(-13.3 to -28.9pp) are unaffected and stand as previously reported.

## Consequence for Task 2

Task 2c's premise -- "`described_not_in_schema`: highest measured impact...
THE PRIORITY ENGINEERING TARGET" -- **does not hold under the corrected
number.** The corrected `param_renamed` effect looks similar in kind to
`required_references_missing_property`'s already-known null (Task 3's
BLOCKING-side finding): a real defect the linter can detect, with a
real-world causal impact that is much smaller than the pre-correction number
suggested, plausibly comparable to or smaller than the BLOCKING checks
already in place. Task 2's re-tiering table (`reports/v2_3_task2_retiering.md`)
uses the corrected numbers throughout.

# AgentGauge v0.4.0 — pre-publication claim audit

Grepped every named public-facing artifact for a surviving claim that LLM-
rewritten/better descriptions degrade or fix agent success, or that
AgentGauge detects a "blind spot" other tools miss — the argument-
degradation thesis is now a measured null (`reports/v0_4_0_task1_argument_degradation.md`).
Search terms: `degrad`, `blind spot`, plus paraphrase sweeps (`hurt`, `harm`,
`worsen`, `other tools`, `only tool`, `catches what`, `miss`) to catch
restatements that avoid the literal words.

## Findings, one per artifact

### `README.md` — no correction needed

Every "argument-degradation" mention (lines 81, 94, 97, 169, 298, 303) was
already updated in the prior session (v0.4.0 Task 1c, commit `82d2eb5`) to
state the measured null precisely: "Measured, real null," per-model
delta/CI, "No model shows a practically significant effect." No stale
"inconclusive"/"would need more tasks" language survives. One unrelated hit
on "harmful" (line 112) is the separate research paper's finding about
*tool-selection* regime-boundedness (confusable-tool disambiguation), not
the argument-construction question this audit is about — already hedged
("regime-bounded... finds it rare in a pilot sample") and correctly scoped
to a different mechanism. Left unchanged.

### `reports/capability_statement.md` — no correction needed

No match for any search term. The "differentiated claim" section compares
AgentGauge's linter false-alarm rate (4.22%) against a single-prompt
LLM-judge baseline's false-alarm rate (97.1%) — a measured precision
comparison, not a "blind spot" or degradation claim. Does not mention the
argument-degradation question at all (was written before that measurement
completed); not touched here since it contains no flagged claim to correct,
and adding unrelated new content is outside this audit's scope.

### PR #64 description — 1 correction, `gh pr edit`

**`Changes` section, "v0.4.0 (this PR's tip)" bullet** (was): *"re-measures
the argument-degradation cross-model question at full statistical power,
closing the last NOT-MEASURED item (in progress — see `PLAN.md`)."*

Written while the live measurement was still running; stale the moment it
completed. Corrected to state the actual result: *"re-measured the
argument-degradation cross-model question live, at full statistical power
(253 tasks × 3 models) — a real, adequately-powered **null**: no model shows
a practically significant effect from better tool descriptions on argument
construction, closing the last NOT-MEASURED item
(`reports/v0_4_0_task1_argument_degradation.md`). Also fixed the
orchestrator stale-monitor/redundant-rerun pattern (`CLAUDE.md`), verified
the v0.4.0 wheel, and added `reports/capability_statement.md`."*

Also **added a new row to the "Headline measured numbers" table**
(previously silent on this question): *"Does description quality fix
argument construction... | Measured null, 253 tasks × 3 models, adequately
powered (MDE=0.0537) — no model clears the 0.05 practical-significance
threshold | `reports/v0_4_0_task1_argument_degradation.md`"*.

Applied directly via `gh pr edit 64 --body-file ...` (PR descriptions are
not repo files, so this has no corresponding git commit — the correction is
live at https://github.com/gaurav-gandhi-2411/agentgauge/pull/64).

### CLI help text (`agentgauge/cli.py`) — no correction needed

- `agentgauge/cli.py:64-75` (module-level architecture comment): "at most
  one rule with a validated causal effect on task success" — accurate,
  matches the causal-claim confirmation below.
- `agentgauge/cli.py:551-561` (`lint` command docstring): "At most one lint
  rule (`type_enum_contradiction`) has a validated causal effect on real
  task success; the rest are either unvalidated or measured to have zero
  effect" — accurate, precisely worded.
- `agentgauge/cli.py:618` (`_STARTER_TASKS_TEMPLATE`, the `agentgauge init`
  generated task-file description field): mentions "description quality" only
  in the anti-tautology task-authoring convention (don't leak the answer in
  task text) — not a claim about degradation/blind spots.
- `agentgauge/cli.py:763,881,1109`: `"description_quality"` appears only as
  a v1-legacy axis-name string literal (the `scan`/`fix` commands, already
  labeled not-the-recommended-surface) — not prose, no claim.

### GitHub Action docs (`agentgauge/cli.py:626-696`, `_GITHUB_ACTION_TEMPLATE`)

No correction needed. The generated workflow YAML/JS is purely mechanical —
it posts whatever `agentgauge lint`/`diff` actually measured on that PR's
run (delta, 95% CI, verdict, selection/argument/joint-success table) with no
narrative claims of its own to be stale or wrong.

## Causal-claim confirmation (second part of this task)

> **CORRECTION (later same phase, `reports/v0_4_0_effect_size_reconciliation.md`):**
> the "-13.3 to -40.0pp" figure quoted below was itself wrong — a range
> constructed by min/max-ing across two different measurements (a
> twice-verified pooled-per-model figure and an unverified single-defect-
> subtype/single-model figure). The correct, verified range is
> **-13.3 to -28.9pp**. This section is preserved as originally written for
> the historical record of what this audit checked at the time; the
> confirmation's *structure* (only one rule carries a causal claim, every
> other rule is labeled null/unmeasured) still holds — only the specific
> number was wrong, and is corrected in the reconciliation report.

Confirmed the only causal claim stated anywhere in the named artifacts is
`type_enum_contradiction` (-13.3 to -40.0pp, 3 model families, CI excludes
zero in every model), and every other lint rule is explicitly labeled with
no measured effect:

| Rule | Label found | Location |
|---|---|---|
| `type_enum_contradiction` | **-13.3 to -40.0pp**, CI excludes zero (pooled, all 3 models) | `README.md:36` |
| `required_references_missing_property` | **0.0pp in all 3 models — a measured null** | `README.md:37` |
| `described_not_in_schema` | **~0pp in all 3 models — a measured null** | `README.md:38` |
| `param_possibly_renamed` | Not independently measured | `README.md:39` |
| `name_collision` | **Not measured** | `README.md:40` |
| `required_not_mentioned` | Not tested for causal effect | `README.md:41` |

`agentgauge/cli.py:554-556` (`lint`'s docstring) independently states the
same fact in the CLI surface itself: "At most one lint rule
(`type_enum_contradiction`) has a validated causal effect on real task
success; the rest are either unvalidated or measured to have zero effect."
No artifact in this audit's scope contradicts this.

## What this audit did not touch (out of scope, no new scope added)

`docs/paper/` (the academic paper and its evidence table) — not in the
named artifact list, and its selection-regime claim is a different,
already-hedged, separately-measured finding (confusable-tool
disambiguation), not the argument-construction question this null resolves.
Not opened, not edited.

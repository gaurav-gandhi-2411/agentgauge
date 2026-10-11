# Measurement history (moved out of the README on 2026-10-11)

**Status: historical record, not current claims.** This is the version-by-version narrative and the
per-rule table that the README carried through v0.5.3. A 2026-10 integrity audit of the repository
found several statements below false, overstated or superseded. Where a passage is reproduced, a
bracketed `[SUPERSEDED 2026-10-11 ...]` / `[REMOVED 2026-10-11 ...]` note marks the change, and each
section ends with a **Corrections** list. Current, audited numbers live in the README table and in
the files it cites. The audit notes themselves are local working files (`.audit/`, git-excluded) and
are not in the repository.

Three corrections apply to nearly everything below:

1. **Fixed-seed variance study (re-measured 2026-10-11; the first diagnosis was mostly wrong).**
   `agentgauge/runner.py` passed the same default sampler seed (42) to every repeat trial until
   commit `4c3ba84`, and the 5,535-trial corpus behind "ICC=0.793" has 650 of 720 (task) groups with
   exactly zero within-group variance (90.3%). An audit concluded this was a fixed-seed artifact.
   Re-running the same 44 tool sets with per-trial seeds (`evals/fixtures/recalibration_seedfix/`)
   moved the zero-variance share only to 82.9% (paired change -7.4 points, 95% CI -10.7 to -4.5) and
   ICC(1) to 0.731 (from 0.793); the effective sampler is on (default decoding gives 10 distinct
   completions from 10 seeds, `decoding_temperature_check.json`). So "repeat trials add little
   independent information" largely survives; what produces identical scores is a coarse outcome
   metric (a wrong tool always scores 0, and 134 of 343 all-pass tasks with differing arguments have
   no registered constraint), not a deterministic model. The re-measured MDE (0.0878 at 100 tasks x 1
   trial, sensitivity range 0.0768 to 0.1001; 0.0562 at 253), null false-alarm and abstention figures
   are in the README block and `results.md`; the old ones (0.0848, 0.0537, ...) are retired.
2. **MDE is a simulation.** The MDE figures are Monte-Carlo estimates from a Gaussian-clamped model
   with constants calibrated on gemma2:9b data, not a measurement on the 253-task corpus.
3. **The pooled BLOCKING effect is not the `type_enum_contradiction` effect.** See the corrections
   list under the tables.

## Harness and linter tables as published through v0.5.3

The harness is the primary interface: `agentgauge lint`'s static rules mostly do not have a
validated effect on real task success on their own (see the per-rule table below) — the harness is
what actually measures whether a change helped. [SUPERSEDED 2026-10-11: 'Every number below is measured in this repo, not
estimated' - the MDE and ship-target rows are simulations of a model calibrated on a fixed-seed
corpus; see the corrections list.]

| Metric | Measured value | Report |
|---|---|---|
| Minimum detectable effect, 100 tasks/arm × 1 trial/task, 80% power | **8.5 percentage points** | `reports/v2_2_optimal_allocation.md` |
| Ship target (detect a 10-point regression at 80% power) | **MET** | same |
| False-alarm rate under the null, by cluster-count stratum | **<5% in every stratum** (<10 tasks: 1.57%; 10–29: 0.08%; ≥30: 0.00%) | `reports/v2_2_few_clusters_correction.md` |
| Replay determinism (identical inputs → identical verdict) | **100%** (50/50 runs) | `reports/v2_harness_evaluation.md` |
| Abstention rate under the null (`INSUFFICIENT_SENSITIVITY`, correctly declining to call a verdict rather than over-claim) | **21.6%** | `reports/v2_1_estimator_rebuild.md` |
| **Causal chain — does a BLOCKING linter violation actually cause task failure?** (previously assumed, now measured, re-verified on a freshly rebuilt instance) | **Yes: -13.3 to -28.9pp** task success, CI excludes zero in all 3 model families tested (gemma2:9b/llama3.1:8b/qwen2.5:7b) | `reports/v2_4_task1_blast_radius_audit.md` |
| Single-prompt LLM-judge baseline (an alternative to this harness/linter) | **97.1% false-alarm rate** / 100% recall — a degenerate always-flag baseline, spot-checked to confirm genuine model hallucination, not a scoring bug | `reports/v2_1_cross_model_validation.md` §Task 2e |

**Corrections to the two tables above (2026-10-11):**

- *Minimum detectable effect / ship target:* simulation under the original fixed-seed calibration;
  re-measured with per-trial seeds (see top of file and the README block): MDE(100x1) 0.0878,
  sensitivity range 0.0768 to 0.1001, so the 0.10 target is met at the point estimate but not across
  the whole range. (An audit sensitivity run assuming much larger trial noise, 0.145-0.206, was a
  hypothetical; the measured trial noise is resid_sd 0.169 vs 0.139 before.)
- *False-alarm by stratum / abstention 21.6%:* the 21.6% abstention is from the v2.1 estimator
  fixture; re-running the committed script on the current estimator gives 26.7% (588/2200) and 12/2200
  false alarms (0.545%), not 13/2200 (0.59%). Under revision.
- *Replay determinism 100% (50/50):* true as stated but narrow: the same `echo_server` trial split
  passed through the (deterministic) diff engine 50 times. It says nothing about model determinism.
  Source: `evals/fixtures/v2_false_alarm_determinism.json`.
- *"-13.3 to -28.9pp" causal chain:* this pools three injected defect types (45 tasks per model),
  one of which (`contradictory_required_claim`) is a measured null. For `type_enum_contradiction`
  alone (n=30 tasks per model) the effects are -37.8 / -33.3 / -16.7pp (gemma2:9b / llama3.1:8b /
  qwen2.5:7b). The earlier CIs treated tasks as independent although they share 6 injected tool sets;
  clustered CIs are in `evals/fixtures/type_enum_contradiction_clustered.json`
  (`scripts/type_enum_clustered_ci.py`) and, with only 6 clusters, the t-based interval includes zero
  for every model. "CI excludes zero in all 3 model families" is not robust.
- *Single-prompt LLM-judge baseline 97.1%:* 169/174 clean tools (a 174-tool sample of 521) with one
  llama3.1:8b prompt; it characterises that prompt/model, not LLM judges in general.

## Every lint rule's measured task-success effect (as published through v0.5.3)

`agentgauge lint`'s rules are NOT all equally validated. Severity tier tracks measured causal
impact × precision (v2.3 re-tiering), not just false-alarm rate — a rule with no measured effect
is labeled as such below, not presented as if it were proven:

| Rule | Tier | Measured causal effect on task success | False-alarm | Recall |
|---|---|---|---|---|
| `type_enum_contradiction` | **BLOCKING** | **-13.3 to -28.9pp** (gemma2:9b -25.2, llama3.1:8b -28.9, qwen2.5:7b -13.3), CI excludes zero in all 3 models | 0% | 100% |
| `required_references_missing_property` | INFO (demoted from BLOCKING) | **0.0pp in all 3 models — a measured null**, despite perfect precision | 0% | 100% |
| `described_not_in_schema` (catches `param_renamed`) | ADVISORY | **~0pp in all 3 models — a measured null** (corrected in v2.3 from a falsely-reported -76.7 to -80.0pp: a scoring bug looked up a pre-rename parameter name against post-rename arguments) | 23.81% | 81.2% |
| `param_possibly_renamed` | ADVISORY | Not independently measured (fires alongside `described_not_in_schema`, not separated in the causal-chain design) | 0.77%/tool | part of the 81.2% combined |
| `name_collision` | ADVISORY | **Not measured** (no defect-injection instance targets this check) | 47.62% | n/a |
| `required_not_mentioned` | INFO (opt-in) | Not tested for causal effect (demoted on a different basis: fires at nearly the same rate on real professional docs as on bad synthetic ones) | n/a | 94.1% |

Full methodology: `reports/v2_1_linter_recall_fix.md`, `reports/v2_1_severity_gate.md`,
`reports/v2_linter_evaluation.md` (`required_not_mentioned`'s 94.1% recall),
`reports/v2_3_task2_retiering.md`, `reports/v2_4_task1_blast_radius_audit.md`.

**Corrections to the per-rule table above (2026-10-11):**

- `type_enum_contradiction`: use the type_enum-only figures above (-37.8 / -33.3 / -16.7pp, n=30),
  not the pooled -13.3 to -28.9pp.
- `required_references_missing_property`: "0.0pp in all 3 models - a measured null" is false as
  stated. The per-model effects are +0.0 / -20.0 / -6.7pp (n=15 tasks each; llama CI [-41.8, +1.8]).
  It is "not detectably different from zero at n=15", not a clean null.
- `described_not_in_schema` (`param_renamed`): after the v2.3 scoring fix the effects are +0.0 /
  -13.3 / +6.7pp with CIs of roughly +/-20pp at n=15. "~0pp - a measured null" overstates it; the data
  are uninformative at that sample size. (The v2.2 figure of -76.7/-80.0pp is the superseded scoring
  artifact; do not cite it.)
- False-alarm / recall percentages in the last two columns were not re-derived in the 2026-10 audit
  (BELIEVED to match `reports/v2_1_severity_gate.md` etc.; not re-run).

## Version narrative, v2.2 to v0.4.0 (formerly a README callout)

> **v2.2.** A predictive-validity study (`reports/predictive_validity_study.md`) found that v1's
> 8-axis LLM-judged quality score does not predict real agent task success by a margin surviving
> both multiple-comparison correction and controlling for description length. v2 rebuilt around
> what that study showed actually works: a deterministic defect linter and a statistical
> regression harness. v2.1 found the v2 estimator's minimum detectable effect was optimistic —
> trial-level repeats within a task carry almost no independent information (ICC=0.793) — and cut
> MDE at n=20 tasks/arm from 43.3 to 18.8 points (2.3×) via pairing + task-clustering + CUPED,
> still short of the 10-point ship target. **v2.2 closed that gap**: the ICC finding itself implied
> the fix — reallocate trials to tasks (1 trial/task, 100 tasks/arm) instead of repeating trials on
> fewer tasks. Measured MDE at that allocation: **0.0848 — ship target met.** v2.2 also measured
> whether a BLOCKING linter violation actually *causes* agent task failure
> (previously assumed, not tested in this repo): it did — a 13.3–28.9 point drop in real task success,
> replicated across three model families. **v2.3 audited a v2.2 ADVISORY-defect finding before
> trusting it and found the effect was ~77–100% a scoring artifact** (the checker looked up a
> pre-rename parameter name against post-rename arguments, scoring correct agent responses as
> failures) — corrected, the ADVISORY (`param_renamed`) effect is a clean null in all three models,
> not the originally-reported 76.7–80.0pp drop. v2.3 re-tiered the linter by the corrected numbers:
> `required_references_missing_property` demoted BLOCKING→INFO (zero measured task-success effect
> in every model); `described_not_in_schema`'s false-alarm rate improved 28.57%→23.81% via real
> precision fixes but did not clear the promotion bar. **v2.4 audited the blast radius of that
> scoring bug**: only `param_renamed` was ever affected (the other four defect-injection classes
> never rename a schema key — confirmed from source, not assumed), and the ICC/variance-
> decomposition/rho/MDE-calibration numbers above all trace to a 5,535-trial corpus the bug never
> touched — no recomputation needed. The one surviving BLOCKING claim was re-measured on a freshly
> rebuilt instance and holds (**-13.3 to -28.9pp**, unchanged). v2.4 also shipped `agentgauge audit`:
> a standing pre-report gate (task/answer leakage, ceiling/floor, degenerate metrics, and — the
> class this exact bug belongs to — scoring-reference consistency) wired into `diff`/`eval` so a
> failing check blocks the result from being reported as a measurement, and repositioned the
> package around the harness (`diff` is now the primary interface; `lint` a secondary utility — see
> the per-rule table above). **v2.4 also expanded the gold-constraint task pool** from 62 to 253
> tasks across 10 real-API domains (GitHub, Stripe, Google Calendar, Jira, Slack, Docker,
> Kubernetes, Twilio, AWS S3, Spotify), closing the sample-size ceiling that left the
> argument-degradation cross-model question underpowered. **v2.5 found the audit gate's own
> scoring-reference-consistency check (the guard against the exact bug v2.3/v2.4 found) had a gap
> in the shipped product code path itself** — `agentgauge diff`/`eval` ran live inference before
> checking a user's task file against the actually-connected schema, not after — closed by
> reordering to a schema-only pre-check that runs before any inference (`reports/v2_5_task1_shipped_fix.md`).
> **v2.5 also found that 3 of the 10 new real-API fixtures had a hallucinated fact** (GitHub's
> `state_reason` enum was missing a real 4th value, Stripe modeled an optional field as required
> under the wrong name, a Kubernetes naming regex allowed an invalid leading character) — all three
> independently re-verified against live official API docs and fixed in place, logged as
> measurement artifact #8, and closed with a new standing `agentgauge audit` check,
> `check_enum_schema_fidelity` (`reports/v2_5_task2_fixture_validation.md`). **The MDE grid is now
> complete across the full 253-task corpus: 0.0537 at 80% power** (`reports/v2_5_task3_mde_completion.md`)
> — roughly half the 0.10 ship target, up from 0.0848 at the previous 100-task allocation.
> **v0.4.0 closed the loop**: the argument-degradation question is now live-measured at that power
> across all 3 model families — a real, adequately-powered null (no model clears the 0.05
> practical-significance threshold), not the old n=62 "inconclusive"
> (`reports/v0_4_0_task1_argument_degradation.md`). See
> `reports/v2_product_readiness.md` for the consolidated methodology [SUPERSEDED 2026-10-11: the
> sentence 'Every number in this README is measured in this repo' was removed; several were
> simulations or are under re-measurement - see the corrections list]. v1's `scan`/`fix`/`ci`/`try`
> commands still exist in the code but are not the recommended product surface;
> `diff`/`eval`/`lint`/`init` are.

**Corrections to the narrative above (2026-10-11):**

- "ICC=0.793 ... trial-level repeats carry almost no independent information", "the ICC finding itself
  implied the fix", and every MDE/ship-target statement: re-measured with per-trial seeds (ICC 0.731,
  MDE(100x1) 0.0878); the conclusion largely holds, the numbers changed (top of file).
- "13.3-28.9 point drop ... replicated across three model families": pooled over three defect types;
  the type_enum-only figures and the clustered CIs are above. The percentile cluster bootstrap
  excludes zero for all three models, but the t(5) cluster-robust interval includes zero for all
  three; qwen2.5:7b is the weakest.
- "a clean null in all three models" (ADVISORY after the fix): the CIs are wide (about +/-20pp at
  n=15) - not a null, an uninformative estimate.
- "MDE grid ... 0.0537 at 80% power ... roughly half the 0.10 ship target": simulation, see top.
- "argument-degradation ... a real, adequately-powered null (no model clears the 0.05
  practical-significance threshold)": for llama3.1:8b the point estimate (+0.0553) is above 0.05 and
  its CI [+0.023, +0.089] excludes zero; the harness verdict was `no_change` only because the lower
  bound is below 0.05. gemma2:9b (+0.022) and qwen2.5:7b (+0.004) are indistinguishable from zero.
  The contrast tested is empty descriptions + type-only schemas versus authored, constraint-revealing
  descriptions, not "rewriting to be clearer".
- "3 of the 10 new real-API fixtures had a hallucinated fact": this is the repo's own finding
  (30% of hand-built fixtures initially had a factual defect); it also means the 253-task corpus was
  authored and checked largely by AI-assistant sessions against vendor docs, not by independent
  humans.
- "Ten measurement artifacts were found and fixed": the fixed-seed finding above is an eleventh, but a
  small one (it shifted the zero-variance share by 7.4 points, not the headline conclusion).

## Additional measured detail (as published through v0.5.3)

Headline harness and per-rule numbers are above. A few more measured results that don't fit that
table:

| Metric | Measured value | Report |
|---|---|---|
| Linter false-alarm rate, per tool, BLOCKING+ADVISORY combined (521 tools) | 4.22%, still <5% | `reports/v2_1_severity_gate.md` |
| Linter recall vs. raw JSON-Schema structural validation baseline | Linter beats it on every defect type — baseline scores **0%** | `reports/v2_linter_evaluation.md` §2e |
| Cross-model replication, causal chain (gemma2:9b, llama3.1:8b, qwen2.5:7b) | BLOCKING effect significant in **all 3 model families**; qwen2.5:7b measurably more robust to `type_enum_contradiction` specifically than the other two | `reports/v2_4_task1_blast_radius_audit.md` |
| Cross-model replication, argument-degradation (a *separate* question from the causal chain above — does description quality fix argument construction?) | **Measured, real null.** Full 253-task corpus, 1 trial/task (MDE=0.0537), live on all 3 models: gemma2:9b Δ+0.022 95% CI [-0.004,+0.051]; llama3.1:8b Δ+0.055 CI [+0.023,+0.089] (CI excludes zero but doesn't clear the 0.05 practical-significance threshold); qwen2.5:7b Δ+0.004 CI [-0.021,+0.029]. No model shows a practically significant effect — this is an adequately-powered null, not an underpowered "inconclusive" | `reports/v0_4_0_task1_argument_degradation.md` |

**What's not yet measured:** an independent fuzz-test of the shipped
`agentgauge/constraints.py`/`agentgauge diff`/`agentgauge eval` product path's
scoring-reference-consistency exposure (the class that caused the v2.3 ADVISORY scoring bug) is
now closed in the CLI itself, not just guarded after the fact: v2.5 moved the `agentgauge audit`
schema check to run *before* any live inference, and it is covered by integration-level regression
tests exercising the real `diff`/`eval` commands end-to-end (`reports/v2_5_task1_shipped_fix.md`) —
not yet independently fuzz-tested against arbitrary, adversarially-malformed user task files, which
remains open — see `reports/v2_product_readiness.md` for the complete list.

**Corrections (2026-10-11):** the argument-degradation row inherits the llama3.1:8b caveat above
(point estimate +0.0553 > the 0.05 threshold; CI excludes zero). Its CIs treat the 253 tasks as
independent although they are nested in 52 tools / 12 fixtures. The "What's not yet measured"
paragraph is awkwardly worded in the original; its substance is that adversarial fuzzing of the
audit-gate path against malformed user task files has not been done.

## Former README roadmap

v1's 8-axis scoring is complete but methodologically falsified as a predictor of task success
(`reports/predictive_validity_study.md`). v2's linter and regression harness are built, measured,
and CLI-integrated. v2.1 rebuilt the harness's estimator (paired + task-clustered + CUPED) and
found the v2 estimator's MDE was optimistic (ICC=0.793 within task) — the 10-point-regression
ship target was not yet met at the allocation tested (n=20 tasks/arm, 5 trials/task). **v2.2
closed that gap** by reallocating to 100 tasks/arm at 1 trial/task (MDE=0.0848 — ship target
met) and fixed the few-clusters false-alarm concentration v2.1 found (t(G-1)-adjusted CI, <5% in
every stratum). v2.2 also measured that BLOCKING linter violations cause agent task failure on injected
defects (previously assumed). [REMOVED 2026-10-11: the original text here also said ADVISORY
violations cause a *larger* drop; that was the scoring-bug artifact corrected in v2.3 and is
superseded - see the next sentence.]
v2.3 audited the largest v2.2 finding before trusting it (a scoring bug had inflated an ADVISORY
effect to -76.7/-80.0pp; corrected to a clean null) and re-tiered the linter by the corrected
numbers. **v2.4 audited that bug's full blast radius**: confirmed only one of five defect-injection
classes was ever affected (the other four never rename a schema key — verified from source), traced
the ICC/variance/rho/MDE-calibration constants to a corpus the bug never touched (no recomputation
needed), and re-measured the one surviving BLOCKING claim on a freshly rebuilt instance (holds:
-13.3 to -28.9pp, unchanged). v2.4 shipped `agentgauge audit` — a standing pre-report gate encoding
every measurement-artifact class found during this project's development (task/answer leakage,
ceiling/floor, degenerate metrics, and the scoring-reference-consistency class the v2.3 bug
belongs to) as an automated check wired into `diff`/`eval`, with a regression test per class seeded
with the real historical case — and repositioned the package around the harness (`diff` primary,
`lint` secondary, every lint rule labeled with its measured causal effect or lack of one).
**v0.4.0 closed the last open item**: the argument-degradation cross-model question (separate from
the causal-chain question above) is now measured, not inconclusive — the 10-fixture corpus expansion
this section once flagged as "in progress" landed in v2.4/v2.5 (253 real tasks, all validated
against live official API docs), and a live 3-model measurement at that corpus's full power
(MDE=0.0537) found a real, adequately-powered null: no model shows a practically significant effect
from better tool descriptions on argument construction (`reports/v0_4_0_task1_argument_degradation.md`).
**v0.5.0 ships model adapters** (six providers, 100% replay determinism, config-driven — see the
section above) as the release headline. It also built and honestly evaluated a failure-attribution
feature (localize which tool description caused a measured regression): accuracy was fixed (both
strategies clear the ship bar at realistic candidate-set sizes), but the cost of doing so — 1.01x
to 20.24x a full re-evaluation, at every tested configuration — means it is **not shipped as a
product surface**, gated `--experimental` and off by default (see the section above and
`reports/capability_statement.md` for the negative-result writeup). Ten measurement artifacts were
found and fixed across this project's development, each with a standing `agentgauge audit` check
seeded from the real historical case.
[SUPERSEDED 2026-10-11: the sentence that stood here, 'Every product claim in this README is now
measured', was not accurate; see the corrections list below.] `reports/v2_product_readiness.md`
tracks a MEASURED vs. NOT MEASURED breakdown but predates the 2026-10 audit.

The corrections lists above apply to this section as well.

## v1 (legacy)

`agentgauge scan`/`fix`/`ci`/`try` implement an 8-axis LLM-judged correlational score. The
predictive-validity study found none of the 8 axes predicts real task success by a margin
surviving both multiple-comparison correction and length-control (`reports/
predictive_validity_study.md`, `reports/v2_axis_triage.md`). The commands still exist and still
work — deleting working code that some users may already depend on wasn't in scope for this
rebuild — but `diff`/`eval`/`lint`/`init` are the supported product surface going forward.

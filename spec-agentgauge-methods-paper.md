# Methods paper — outline and assembly spec

**Working title:** *Powering Agent Evaluations: Variance Structure, Measurement
Artifacts, and Minimum Detectable Effects in Tool-Use Benchmarks*

**Repo:** `C:\Users\gaura\ml-projects\agentgauge`
**Artifact:** `agentgauge-harness` v0.5.2 on PyPI (Apache-2.0)
**Target:** arXiv cs.SE / cs.LG (cross-list cs.AI). Workshop-to-conference track.
**Status:** every number below is already measured and committed to `reports/`. This
is an assembly job, not a research job. Do not run new experiments to fill sections.

---

## 1. Thesis

Agent evaluations are routinely reported without power analysis, without a stated
detection floor, and without artifact screening. This paper measures the variance
structure of agent task outcomes, shows the consequences for experimental design,
gives an estimator that reaches usable power, catalogues ten measurement-artifact
classes each found in real experiments, and reports a structural negative result on
regression localization.

The paper's credibility rests on it being a record of what went wrong, including the
authors' own falsified commercial thesis. That framing is a feature. Do not soften it.

---

## 2. Contributions (stated explicitly in §1 of the paper)

1. **Variance structure.** ICC = 0.793 within (tool set, task); 56.1% of outcome
   variance is between-task; before/after task correlation r = 0.881. Direct
   consequence: repeated trials on the same task carry little independent
   information, so evaluations that scale trials rather than tasks are underpowered
   by construction.
2. **An estimator that reaches usable power.** Paired design with common random
   numbers + task-clustered bootstrap with t(G−1) small-G correction + CUPED +
   O'Brien–Fleming sequential testing. Component ablation reported. MDE 0.433 →
   0.188 at n = 20; 0.0537 at n = 253. False-alarm under the null 0.59%. Replay
   determinism 100%.
3. **A ten-class measurement-artifact taxonomy**, each class discovered in a real
   experiment in this work, each with an automated detector shipped in
   `agentgauge audit`. This is the paper's strongest contribution — the field has no
   standard artifact taxonomy for agent evals.
4. **A structural negative result on regression localization.** Localization
   accuracy requires task volume (MDE ∝ 1/√n) and task volume is precisely the cost
   a localizer exists to avoid. Crossover against full re-evaluation sits at ~2–4
   changed tools; realistic configurations cost 5–20× a full re-eval. Not a tuning
   miss — a structural tension.
5. **A falsification record.** Four pre-registered hypotheses falsified, including
   the authors' own product thesis that an 8-axis tool-description quality score
   predicts agent task success.

---

## 3. Section outline

### §1 Introduction
Problem: agent evals are reported without detection floors or artifact screening.
State the five contributions. State plainly that the work began as an attempt to
validate a quality-score product and that the thesis was falsified — this frames the
whole paper as a methods record rather than a product pitch.

### §2 Related work
A/B testing and variance reduction (CUPED, common random numbers, cluster-robust
inference, sequential testing); agent and tool-use benchmarks; LLM-as-judge
evaluation and its known failure modes; reproducibility and replay in ML systems.
Position the gap: none of the agent-eval literature reports MDE or screens for
measurement artifacts.

### §3 Experimental setup
Corpus: 253 tasks, including 10 real-API gold-constraint fixtures (GitHub, Stripe,
Google Calendar, Jira, Slack, Docker, Kubernetes, Twilio, AWS S3, Spotify), each
validated against live official documentation — 3 of 10 had factual defects found
and corrected. Anti-tautology task construction. Models: gemma2:9b, llama3.1:8b,
qwen2.5:7b. Byte-exact cassette replay. Outcome scoring: continuous partial credit,
decomposed into selection accuracy and argument accuracy.

### §4 Variance structure of agent task outcomes
ICC, variance decomposition, before/after correlation. n_eff formula and its
consequence. The allocation grid: MDE across {1,2,3,5} trials/task × {20,50,100,150}
tasks/arm, with the compute-optimal cell identified. **Headline claim of the
section:** at fixed compute, task diversity dominates trial repetition.

### §5 An estimator for agent regression detection
Paired design + CRN, task-clustered bootstrap, small-G t(G−1) correction (note: wild
cluster bootstrap was tried and measured *worse* on small-G coverage — report this,
it is a useful negative), CUPED, O'Brien–Fleming sequential testing. Ablation table
showing each component's contribution. Sensitivity gate: abstain
(`INSUFFICIENT_SENSITIVITY`) rather than emit a point estimate the data cannot
support; abstention rate fell 71.5% → 21.6% under the improved estimator.
Results: MDE table, false-alarm under null, determinism.

### §6 A taxonomy of measurement artifacts
The core section. For each of the ten classes: mechanism, how it was discovered, the
spurious result it produced, the automated detector, and the regression test. Include
the two cases where an artifact produced a *false positive* the authors initially
believed (the −80pp ADVISORY effect that corrected to a clean null; the 100%
attribution accuracy at 3pp that corrected to 58%).

The ten classes:
1. Task/answer leakage (gold tool name quoted in task text)
2. Tool-name ceiling (metric collapsing to name matching)
3. Zero-vector empty-string embedding
4. Self-descriptive-name confound (descriptions cannot matter when names suffice)
5. Subset-vs-catalog mismatch between fixture and manifest
6. LCG index saturation (RNG boundary crash)
7. Scoring-reference mismatch (gold resolved against the wrong variant)
8. Fixture-schema hallucination (agent-authored fixtures, 3/10 defective)
9. Benchmark-construction bias (culprit diff size correlated with culprit status,
   producing a below-chance baseline)
10. Probe variance mis-calibration (synthetic probe noise omitting the between-task
    variance component, inflating detection power 3–7×)

### §7 Applications and negative results
**7.1** Which tool-description defects actually cause agent failure. Exactly one
lint rule has a measured causal effect: `type_enum_contradiction`, −13.3 to −28.9pp
across three model families. All other rules measured null or unmeasured. The
LLM-judge baseline is degenerate: 97.1% false-alarm at 100% recall.
**7.2** LLM-rewriting tool descriptions has no measurable effect on argument
construction — an adequately powered null (253 tasks × 3 models, MDE 0.0537),
notable because the underpowered version of this experiment initially appeared to
show a large effect.
**7.3** The attribution impossibility result. Strategy comparison
(exhaustive/bisection/sampled-Shapley), effect-size and scale curves, and the cost
crossover against full re-evaluation.

### §8 Threats to validity
Three open-weight models under ~10B parameters; no frontier-model replication.
Synthetic defect injection for causal claims. Single corpus. Ten artifacts found
suggests an eleventh exists. Be explicit and unhedged.

### §9 Conclusion
Recommendations for the field: report MDE alongside every agent-eval result; allocate
compute to task diversity over trial repetition; screen for artifacts before
reporting; publish falsifications.

### Appendices
Full MDE grids, ablation tables, artifact detector pseudocode, corpus statistics,
reproduction instructions against `agentgauge-harness` v0.5.2.

---

## 4. Source-to-section map

Assembly draws from committed reports only. Every number carries a provenance
pointer (report path + commit SHA) in the draft; provenance is stripped from the
final PDF but kept in a companion `provenance.md`.

| Section | Source reports |
|---|---|
| §4 | `v2_1_*` variance/ICC reports, allocation grid reports |
| §5 | `v2_1_*` estimator ablation, `v2_2_few_clusters_correction.md`, MDE completion reports |
| §6 | `predictive_validity_study.md`, `v0_4_0_task1_argument_degradation.md`, `v0_5_mde_discrepancy.md`, artifact-specific reports, `agentgauge/audit.py` |
| §7.1 | `v2_product_readiness.md`, `v0_4_0_effect_size_reconciliation.md` |
| §7.2 | `v0_4_0_task1_argument_degradation.md` |
| §7.3 | `v0_5_attribution_benchmark.md`, `v0_5_shapley_scaling_audit.md`, `v0_5_probe_power_fix.md` |
| §3 | fixture manifests, corpus validation reports |

---

## 5. Non-negotiables

- **No number enters the paper without a provenance pointer to a committed report
  and SHA.** This project has had metrics fabricated before; the rule is absolute.
- **Superseded numbers must not resurface.** Several figures were corrected
  (−80pp → null; 100% → 58%; −40pp → −28.9pp). Cross-check every figure against the
  latest superseding report, not the first report that mentions it.
- **MEASURED vs NOT MEASURED separated** in every table.
- No new experiments. If a section needs a number that does not exist, flag the gap
  rather than generating it.
- Reproducibility: the paper must state that every result is reproducible against
  `pip install agentgauge-harness==0.5.2` plus the committed fixtures.

---

## 6. Deliverables

1. `docs/paper2/main.tex` — full LaTeX draft, arXiv-ready.
2. `docs/paper2/provenance.md` — every claim mapped to report path + SHA.
3. `docs/paper2/figures/` — MDE curves, ablation table, allocation grid heatmap,
   artifact taxonomy table, attribution cost-crossover plot.
4. `docs/paper2/gaps.md` — anything the outline asks for that is not measured.

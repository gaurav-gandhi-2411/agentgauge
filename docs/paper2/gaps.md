# Gaps — outline items without a measured source

Per spec §5: "No new experiments. If a section needs a number that does not exist, flag the gap
rather than generating it." This file is that flag list. Nothing here was estimated or guessed to
fill a hole in the prose.

## Not measured (cannot be stated as a result, only as a limitation/future-work note)

1. **Argument-degradation effect: model-specific or universal?** Only measured at n=16
   (underpowered). §4/§8 should state this as an open question, not resolve it.
   (`reports/v2_1_cross_model_validation.md`)
2. **Full 521-tool linter-corpus clean false-alarm rate.** Only a 174-tool stratified sample was
   run. The 97.1% degenerate-LLM-judge figure and the linter's own false-alarm rate should both
   carry this sample-size caveat in §7.1. (`reports/v2_product_readiness.md`)
3. **True cross-model argument-degradation effect size at the n=253/MDE=0.0537 allocation.**
   Statistical power was established at this corpus size; no new live-inference run at that exact
   allocation exists. §5's MDE table must not be read as also reporting an effect size at n=253.
   (`reports/v2_5_task3_mde_completion.md`)
4. **O'Brien-Fleming sequential testing is simulated only, not wired into the live CLI.** §5
   should describe it as a validated design choice, not a shipped, callable feature.
   (`reports/v2_product_readiness.md`)
5. **A fresh, empirical 50-run determinism count for the v2.1 paired+CUPED bootstrap estimator
   specifically does not exist.** The 100% figure for this specific estimator is inherited/ASSUMED
   from an earlier estimator's measurement, and independently confirmed only via code inspection +
   exact-value reproduction (not a fresh empirical count). Distinguish this from cassette-replay
   determinism (100%, 6 adapters), which IS freshly, empirically measured.
   (`reports/v2_1_estimator_rebuild.md`, `reports/v2_5_task3_mde_completion.md`)
6. **Attribution (localization) has never been run against a real agent + real LLM judge.** Every
   accuracy/budget/cost-crossover number in §7.3 is a synthetic-benchmark result
   (`make_probe_fn`/`make_multi_probe_fn`). §7.3 and §8 (threats to validity) must say this
   plainly — it is one of the four bullet points the spec requires threats-to-validity to name.
   (`reports/v0_5_mde_discrepancy.md`, `reports/v0_5_probe_power_fix.md`)
7. **`sampled_shapley` has zero real (live-LLM) data points**, synthetic-benchmark only.
8. **Isolated 2-defect-type (excluding the null `required_references_missing_property` subtype),
   n=30 pooled re-measurement of `type_enum_contradiction` does not exist.** The current -13.3 to
   -28.9pp figure pools in the null subtype, which if anything understates the isolated effect —
   stated as a secondary note in the source, not actioned. §7.1 should carry this caveat rather
   than presenting -13.3/-28.9pp as the isolated 2-defect-type figure.
   (`reports/v0_4_0_effect_size_reconciliation.md`)

## Figures the outline asks for that need a framing decision, not fabrication

None of the five requested figures (MDE curves, estimator ablation table, allocation-grid heatmap,
artifact taxonomy table, attribution cost-crossover plot) require a number that isn't already in
`provenance.md`. See `docs/paper2/figures/` for what was built from committed data only, and note
below where a figure had to choose a representative slice of a larger measured table (a
presentation choice, not a data gap):

- The MDE curve (n_tasks -> MDE) uses the single, final grid from `v2_5_task3_mde_completion.md`
  (62/100/150/200/253 tasks). It does not re-plot the earlier n=20 estimator-ablation MDE
  (0.433->0.188), which belongs to the ablation table figure instead — these are two different
  measured tables answering two different questions (per-component ablation at fixed n=20 vs.
  corpus-size scaling at fixed component set), not a single curve.
- The allocation-grid heatmap plots the 80%-power slice of the 32-cell grid
  (`v2_2_optimal_allocation.md`) — the 95%-power slice exists in the same source table but is not
  separately plotted, to keep one figure to one claim (spec's own framing of the section's
  headline). Both power levels are in `provenance.md` if a reviewer wants the 95% slice added.
- The attribution cost-crossover plot uses the `n_tasks` x crossover-n_changed relationship from
  `v0_5_probe_power_fix.md` §5 (24/48/128), which is the only report containing that exact
  three-row crossover table. It does not attempt to interpolate a smooth crossover curve across
  arbitrary n_tasks values not in that table.

## Framing decisions — RESOLVED (GG ruling, this wave)

All four items below were flagged as author judgment calls, not missing numbers (see
provenance.md's "Ambiguous / needs-a-framing-decision" section for the original full detail).
GG ruled on all four; the draft was correct on all four as originally written. Each ruling has
now been made explicit in `main.tex` (a distinguishing sentence, or a footnote), not left as a
silent editorial choice.

1. **§7.2's "underpowered predecessor" framing — Option B CONFIRMED.** The source reports
   contain two distinct narratives (a flat-underpowered null for rewriting-descriptions, and a
   separately-scoped scoring-artifact-inflated effect for the ADVISORY rule in §6.1). Ruling: the
   rewriting-descriptions result was flat/near-null at *both* $n=62$ and $n=253$ -- it was never a
   large effect. The "initially large, later corrected" narrative belongs solely to §6.1's
   ADVISORY story. `main.tex` §7.2 now states this distinction explicitly in prose (an added
   paragraph naming both results and why they don't conflate), rather than only pointing to this
   file.
2. **"rho=0.881" vs. "r=0.881" — r=0.881 CONFIRMED**, cited as Pearson r per the source table's
   own column label. `main.tex` §4 now carries this as a footnote (Spearman $\rho=0.869$ stated
   alongside), with an added note that the paired-design argument this correlation supports holds
   under either statistic.
3. **n=20 MDE 0.188 vs. 0.182 — CONFIRMED acceptable**, each cited only from its own source
   table, never reconciled or mixed. `main.tex` §5 now carries a footnote at the ablation table
   stating the two figures come from different `trials_per_task` defaults on either side of a
   tooling-version boundary (v2.1 estimator vs. the v2.2 grid), so the difference reads as an
   explained methodological artifact, not an unaddressed inconsistency. Per the ruling, this was
   NOT further investigated to reconcile the two — that would require new measurement, out of
   scope for a no-new-numbers wave.
4. **"Continuous partial credit" — CONFIRMED.** The phrase is spec shorthand, not a measured
   term; no report ever states it verbatim. `main.tex` §3 already states the actual fractional
   constraint-satisfaction formula (correct tool selected × fraction of registered
   argument-correctness constraints satisfied) with its provenance pointer, and never uses the
   phrase as if it were a quoted metric name. No change needed this wave beyond confirming the
   existing text already meets the ruling.

## Citations — RESOLVED this wave (compile-and-cite pass)

Previously recorded here as an open gap ("citations not populated"); resolved. `docs/paper2/refs.bib`
now has 12 entries, each verified against a real primary source (DOI resolution / Crossref / dblp /
arXiv API / publisher page) by a dedicated research pass, then independently re-verified entry-by-
entry by a separate verifier pass before being wired into `main.tex` via `\citep{}`. Two real errors
were caught and fixed during the verifier pass (not left in):
- `law2014simulation` (the CRN textbook citation): the researching agent's source (a retailer
  listing) stated the 5th edition shipped in 2015; three independent sources (OpenLibrary, LC
  classification, publisher ship date) place it in 2014. Bibkey and year corrected.
- `yu2026wildtool` (WildToolBench, reused from paper 1's related-work point): the researching
  agent's first-pass author list had the 7th author's given name wrong ("Zhang, Fan"); corrected to
  "Zhang, Feng" against the arXiv API XML for id 2604.06185.

**Separate discovery, not fixed here (flagged for whoever next touches paper 1):** this repo's
existing `docs/paper/latex/references.bib` has systematic author-name errors — independently
confirmed by both the researching agent and the verifier pass against primary sources. `shi2025toolret`
and `lu2025toolde` each have incorrect given names for one author; `yu2026wildtool` in that file has
**6 of 7** author given/family names wrong. Titles, eprint IDs, and venues in that file are correct —
only author-name fields are affected. Out of scope for this wave (a different paper's bibliography);
recorded here so it isn't lost.

## Candidate 11th artifact (not adopted as a numbered class)

Two extraction passes independently surfaced the same shape of problem that doesn't fit taxonomy
classes 1-10: a defect-detection signal calibrated against synthetic "bad" fixtures fires almost
as often on genuine, unremarkable real-world documentation (`required_not_mentioned`: 1.42/tool
real-world vs. 1.37/tool synthetic-bad; `name_collision`/`described_not_in_schema` clean-corpus
noise on verb-differentiated real tool pairs). This is offered in §8 (threats to validity) as
informal substantiation of "ten artifacts found suggests an eleventh exists," not promoted to a
numbered §6 class — it was never isolated as its own investigation with a named detector/fix the
way classes 1-10 were, and doing so now would mean characterizing it more precisely than the
source reports do.

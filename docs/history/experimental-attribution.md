# Experimental failure attribution, moved out of the README on 2026-10-11

The `attribute` command still exists but is hidden from `--help` and gated `--experimental`.

**Corrections (2026-10-11):**

- The study is a simulation on a synthetic noise model that reuses the original
  fixed-seed calibration (re-measured; see `measurement-history.md`, top); attribution was run against a real agent in one case only.
- Artifact #10 (`reports/v0_5_mde_discrepancy.md`) inverted the strategy ranking after the probe
  noise was corrected: `sampled_shapley` clears the single-culprit ship bar at 10/20/40 candidate
  tools in an audit re-run, while `greedy_bisection` degrades with candidate-set size. The first
  and multi-culprit rows below do not reflect that inversion and were not re-verified.
- The cost range "1.01x-20.24x" is as reported in `reports/v0_5_probe_power_fix.md` section 5; the
  paper's "5-20x at every strategy" restatement is wrong (2.53x-20.24x for the 10-40
  changed-tool configurations). The conclusion that attribution is not cost-effective is supported
  by the cost table.
- "a genuine first for this project" has been removed from the multi-culprit row.

## Original section

`agentgauge attribute` exists in the CLI and is gated `--experimental`, off by default, because it
is **measured uneconomical**, not because it doesn't work — accuracy is genuinely solved; the
numbers below are why it isn't a product surface:

| Metric | Measured value | Report |
|---|---|---|
| Accuracy at the probe power needed for reliable localization (`n_tasks=128`) | Both tested strategies clear the ship bar (top-1≥70%, top-3≥90%) at every single-culprit candidate-set size ≥10 tools | `reports/v0_5_probe_power_fix.md` §4 |
| Cost vs. simply re-running the full evaluation | **1.01x–20.24x more expensive**, at every tested configuration — the cheapest case in the whole study (4 changed tools) is already a coin flip against a full re-eval | same, §5 |
| Crossover to cheaper-than-re-evaluating-everything | **~2-4 changed tools** — below the scale at which localization has any practical use | same |
| Multi-culprit (2-3 simultaneous regressions — the realistic multi-file-PR shape) | 4 of 6 tested configurations don't clear the ship bar. `greedy_bisection` **does** clear 2-culprit/20-tool (98.33%/100.00%) and narrowly misses 3-culprit/20-tool on the budget leg alone (21.30 probes vs. exhaustive's 20 — its accuracy there, 98.89%/96.67%, clears). `sampled_shapley` clears none. Neither strategy clears 3-culprit/40-tool. | same, §4 |

**The multi-culprit result is a partial rescue, not a full one — real progress, still not a product.** `greedy_bisection`'s one genuine clear (2-culprit/20-tool) doesn't change the shipping decision: attribution stays gated `--experimental` on cost alone (the row above — 1.01x–20.24x more expensive than a full re-eval, at every tested configuration, including the cases that do clear on accuracy). A feature that's 20x more expensive than the thing it replaces isn't shippable regardless of how its accuracy numbers land.

**Why it isn't fixable by tuning**: minimum detectable effect scales as `1/√n_tasks` — reliable
localization needs real per-probe task volume, and that volume is exactly the cost a localizer
exists to avoid paying. Lower `n_tasks` is cheap but statistically unreliable; higher `n_tasks` is
reliable but each probe alone costs a meaningful fraction of a full corpus re-evaluation. No
`n_tasks` value clears both the accuracy and cost bars at once (`reports/v0_5_probe_power_fix.md`
§5-6) — a structural finding, recorded for the methods paper as a negative result
(`reports/capability_statement.md`), not a bug to be fixed in a later release.

The code, benchmarks, and every measurement behind this table remain in the repo — nothing was
deleted. Research use only, via direct library import
(`agentgauge.attribution`/`agentgauge.attribution_benchmark`) or the scripts under `scripts/`; run
`agentgauge attribute --help` for the gate, or `agentgauge attribute` (no flag) to see the cost
finding printed at the command line.

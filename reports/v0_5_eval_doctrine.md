# AgentGauge v0.5 Wave 1 — evaluation doctrine

Written before any Wave 1 code, per `spec-agentgauge-v0.5.md` §7's standing rule: every
component declares its task, best-suited metric, baseline, and target margin **before**
implementation, recorded here — not fitted after the fact to whatever the code produces.

Wave 1 has two components (spec §4). Wave 2/3 components are out of scope for this
document and this branch; they get their own doctrine entries when their wave starts,
per `v2_eval_doctrine.md`'s precedent of one doctrine document per rebuild/wave.

## Component 1.1: Model-adapter abstraction

- **Actual task:** does replacing the Ollama-coupled inference path with a
  provider-agnostic interface preserve two properties the product already claims: (a)
  100% replay determinism (re-running an identical cassette reproduces an identical
  harness verdict), and (b) verdict fidelity (the harness's classification of a given
  fixed fixture set does not change depending on which adapter served the calls that
  were captured into the cassette). This is a **regression-prevention task** on an
  existing measured claim, not a new capability being scored for the first time — the
  bar is "no regression," not "how good is this."
- **Metric:** replay determinism rate per adapter (fraction of repeated replays of the
  same cassette that produce byte-identical harness output), computed independently for
  each of the six adapters (Ollama, OpenAI-compatible, Anthropic Messages, AWS Bedrock,
  Google Vertex, generic custom-endpoint). Secondary metric: cross-adapter verdict
  agreement on a fixed fixture set (does `diff`'s verdict — regression / improvement /
  no_change / insufficient_sensitivity — stay the same when the same cassette is
  replayed through different adapter code paths that all deserialize to the same
  `Message`/response shape).
- **Baseline it must beat:** the current Ollama-only path's already-measured 100%
  replay-determinism figure (`reports/v2_harness_evaluation.md` / v0.4.0 release
  verification). The abstraction is not being asked to improve on this number — it is
  being asked not to regress it. There is no sense in which a lower number is
  acceptable "on average"; determinism is evaluated per adapter, and the worst adapter
  sets the reported figure, not the mean.
- **Target margin:** 100% replay determinism on every adapter, on the fixed fixture set,
  with **zero** verdict flips attributable to the abstraction layer (spec §4's explicit
  ship bar). This is a hard gate, not a target to approach: if any adapter measures
  below 100%, Wave 1 stops per spec §8 risk 1 and reports the failure rather than
  shipping a caveated number — a "how deterministic" headline claim does not degrade
  gracefully to 97%.
- **Note on live-provider scope:** per spec §7's standing cost constraint (no paid
  provider without an approved bounded estimate; never `ANTHROPIC_API_KEY`), determinism
  for the four non-local, non-free adapters (Anthropic, Bedrock, Vertex, and any paid
  custom-endpoint) is measured against **recorded/mocked wire-format responses**, not
  live paid calls. This measures what the abstraction can measure without spend
  approval: that the adapter code itself (parsing, hashing, cassette I/O) introduces no
  nondeterminism given an identical response. It does NOT measure the live providers'
  own response variance — that is out of scope for this wave and will be labeled
  NOT MEASURED, not silently folded into the 100% figure.

## Component 1.2: Failure attribution / regression localization

- **Actual task:** credit assignment — given a multi-tool, multi-file change already
  known (via `agentgauge diff`) to have regressed task success, identify *which*
  tool description(s) among the changed set caused it. This is a search/ranking problem
  over a known-finite candidate set (the changed tools), not a detection task (detection
  is `diff`'s job, already done) and not a correlational one.
- **Metric:** top-1 and top-3 localization accuracy against known injected culprits
  (does the top-ranked / top-3-ranked suspect list contain the actual injected
  defective tool), and probe budget consumed (number of harness re-measurements /
  ablation probes) to reach that accuracy — reported as a paired (accuracy, budget)
  curve per strategy, not either number alone, since a strategy that is only accurate
  at exhaustive-ablation budget has not solved the problem (spec §8 risk 2).
- **Baselines to beat:** (i) blame the tool with the largest textual diff (a free,
  zero-probe heuristic), (ii) blame the tool with the most lint-violation deltas (a
  free, zero-probe heuristic using the existing deterministic linter), (iii) uniform
  random over the changed-tool set (the floor). All three are zero-additional-inference
  baselines; any strategy that spends probe budget must clear them by more than noise,
  not merely tie.
- **Target margin:** top-1 ≥ 0.70 and top-3 ≥ 0.90 on the injected-culprit benchmark, at
  a probe budget strictly below exhaustive single-tool ablation (spec §4's explicit ship
  bar). If no strategy clears this bar within a sub-exhaustive budget, that is reported
  plainly as a kill finding, per spec §4's own framing: "a feature that costs more than
  a full re-eval has no value and should be killed, not shipped." No strategy ships as a
  product surface without clearing this bar.
- **Benchmark-construction guard (9th-artifact watch):** the injected-culprit benchmark
  itself is a new measurement surface (spec §7: assume a ninth artifact class). The
  specific risk here is **culprit-construction confound** — if injected culprits are
  systematically the tool with the largest diff, or always occupy a fixed position
  (e.g. always tool index 0), baseline (i) or a positional shortcut would win by
  construction rather than by any real localization signal, and the benchmark would be
  measuring its own generation process rather than attribution quality. The benchmark
  generator must randomize injection position and defect-diff-size independently of
  ground truth, and this doctrine records the check as mandatory before any accuracy
  number from this benchmark is reported.

## Cross-cutting rule (inherited from `v2_eval_doctrine.md`)

No component in this wave is evaluated on a metric chosen after seeing what makes it
look good — both metrics above were fixed by the task class before any Wave 1 code was
written. Where a component fails its own declared bar (most likely candidate: 1.2's
probe-budget bar), that failure is reported as a finding in the end-of-wave report, in
the same way this repo's four falsified/negative results have been reported previously,
not omitted or softened into a qualitative caveat.

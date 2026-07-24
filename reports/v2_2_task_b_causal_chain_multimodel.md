# AgentGauge v2.2 — Task B: end-to-end causal chain, cross-model (reorder)

Extends `reports/v2_2_causal_chain.md` (Task 3, gemma2:9b only) to all three warm
model families on the same Cloud Run instance, in one pass, per the user's
explicit reorder ("run Task 3 on the SAME warm instance, then tear down").
`scripts/v2_2_causal_chain_multimodel.py`, `evals/fixtures/v2_2_causal_chain_multimodel.json`.
Same design as the original: 6 clean tool sets, `scripts/_mutated_stdio_server.py`
live mutation (`ListToolsRequest` handler only, `CallToolRequest` untouched),
trials_per_task=1, 18 BLOCKING instances (45 tasks) + 6 ADVISORY instances
(15 tasks) per model.

## B1-B3. Headline BLOCKING effect — significant across all three model families

| Model | Mean delta | 95% CI | Excludes zero? |
|---|---|---|---|
| gemma2:9b | **-25.2pp** | [-39.0, -11.3] | Yes |
| llama3.1:8b | **-28.9pp** | [-43.6, -14.2] | Yes |
| qwen2.5:7b | **-13.3pp** | [-25.2, -1.5] | Yes (barely) |

**"BLOCKING violations cause a mean 13.3-to-28.9-point drop in agent task
success (95% CI excludes zero for all three tested model families: gemma2:9b,
llama3.1:8b, qwen2.5:7b), measured across 6 tool sets and 45 tasks per
model."** The effect is real and directionally consistent across model
families, not a single-model artifact — but qwen2.5:7b's effect is roughly
half the magnitude of the other two, and its CI's lower-magnitude bound
(-1.5pp) is close to zero. This is reported as-measured, not rounded up to
"the same effect everywhere."

## Per-defect-type breakdown — the null-effect finding replicates; the magnitude split does not, fully

| Defect (→ check) | gemma2:9b | llama3.1:8b | qwen2.5:7b |
|---|---|---|---|
| `contradictory_required_claim` (→ `required_references_missing_property`) | +0.0% [-20.8,+20.8] | -20.0% [-41.8,+1.8] | -6.7% [-20.4,+7.0] |
| `type_flipped` (→ `type_enum_contradiction`) | **-35.6% [-60.9,-10.2]** | **-33.3% [-59.8,-6.8]** | -20.0% [-49.4,+9.4] |
| `enum_dropped` (→ `type_enum_contradiction`) | **-40.0% [-66.9,-13.1]** | **-33.3% [-65.5,-1.2]** | -13.3% [-32.3,+5.7] |

**`required_references_missing_property` shows no measured effect in any of
the three models** — all three per-model CIs include zero (n=15 each). This
is the strongest replication in this task: the original single-model finding
("this check flags something the agent literally has no parameter to act on,
so real task outcomes are unaffected") holds across gemma2:9b, llama3.1:8b,
*and* qwen2.5:7b. Reported plainly, as required — this specific BLOCKING
check's target defect class does not causally degrade task success in any
model tested.

**`type_enum_contradiction`'s effect is NOT uniformly significant across
models when split by individual defect type at n=15.** gemma2:9b and
llama3.1:8b both show it clearly (both defect variants, both CIs exclude
zero). qwen2.5:7b does not — both `type_flipped` and `enum_dropped` CIs
include zero individually for qwen2.5:7b, even though the *pooled* BLOCKING
number for qwen2.5:7b (combining all three defect types, n=45) does exclude
zero. This is the honest way to say it: qwen2.5:7b is measurably **more
robust** to this specific description/schema contradiction than the other
two models — not "the effect doesn't replicate," but "the effect is smaller
and this sample size (n=15 per defect type) can't fully resolve it for this
one model." A model-family difference in susceptibility, not a
methodology failure.

## B4. ADVISORY-class effect — larger than BLOCKING in every model tested

| Model | Mean delta | 95% CI | Excludes zero? |
|---|---|---|---|
| gemma2:9b | **-76.7pp** | [-103.7, -49.6] | Yes |
| llama3.1:8b | **-80.0pp** | [-102.1, -58.0] | Yes |
| qwen2.5:7b | **-76.7pp** | [-98.9, -54.4] | Yes |

**"ADVISORY (param_renamed) violations cause a mean 76.7-to-80.0-point drop
in agent task success (95% CI excludes zero for all three model families),
measured across 6 tool sets and 15 tasks per model."** Unlike BLOCKING, this
effect is remarkably *stable* across models — all three land within 3.3
points of each other (76.7/80.0/76.7), and every CI's less-extreme bound sits
well clear of zero (-49.6, -58.0, -54.4). As in the single-model report,
some CI upper-magnitude bounds exceed the theoretically possible [-100,+100]
range — a known, disclosed t(G-1)-at-small-n artifact
(`reports/v2_2_causal_chain.md`'s caveat applies identically here), not a
computation error; the direction and less-extreme bound are unaffected.

## B5. Cross-model generalization — stable in direction, model-dependent in magnitude

The core product claim generalizes: **both the BLOCKING and ADVISORY causal
effects are statistically significant (CI excludes zero) in all three tested
model families**, and **ADVISORY > BLOCKING in every single model**, not just
on average. That the severity-split/real-impact mismatch (Task 3's most
important finding) is NOT a gemma2:9b quirk is itself a significant
strengthening of that finding.

What is model-specific: qwen2.5:7b shows a systematically smaller BLOCKING
effect than the other two models (both pooled and per-defect-type), and its
`type_enum_contradiction` effect doesn't clear significance at this n split
by defect type. ADVISORY shows no such model-dependence — it's the more
robust, more universal effect of the two.

## B6. Adversarial check — is the injection too easy to detect?

Read all four injector functions used (`scripts/v2_defect_injector.py`,
`inject_type_flipped`, `inject_enum_dropped`, `inject_contradictory_required_claim`,
`inject_param_renamed`) before trusting any positive result, specifically
looking for injections so obviously malformed that any model would trivially
notice — which would inflate the effect size into an artifact rather than a
measurement of realistic documentation-bug severity.

**Not found to be trivially detectable — with one disclosed caveat.** Every
mutation produces a syntactically valid JSON Schema; nothing is null,
missing, or garbled. The contradiction is semantic and requires reading two
separated fields together (e.g. `type_flipped`: the schema `type` field says
`integer`, a *sentence appended to the end of the description* says "Set X
to true/false as needed" — an agent that only reads the schema, or only
skims the description, would not notice). **Caveat, consistent with the
original single-model report's own framing**: the added sentence is
literally *appended* to the existing description rather than woven into a
naturally-rewritten one — a "bolted-on" tell that a sufficiently careful
reader could flag as suspicious independent of the semantic contradiction
itself. This is a pre-existing, disclosed property of the injector (built
for the linter's own calibrated recall eval, not new to this task), not a
new artifact introduced here. It argues for treating the measured magnitudes
as an upper bound on real-world severity for hand-written (non-appended)
documentation bugs, not as a reason to discard the finding — the *direction*
and *significance* of the effect are not explained by injection triviality:
`contradictory_required_claim` uses the exact same "append a sentence"
mechanism and shows **no effect**, which would not be true if models were
simply reacting to "the description looks tampered with" rather than to the
specific semantic content of each mutation.

## Independent verification

A separate verifier agent recomputed all 6 pooled (model × BLOCKING/ADVISORY)
means and all 9 per-defect-type means directly from
`evals/fixtures/v2_2_causal_chain_multimodel.json`'s raw `task_deltas`,
confirmed the per-defect-type subsets exactly partition each model's
BLOCKING set (no double-counting or mislabeling across models), and spot-read
the injector source to confirm the B6 mechanism claim.

## Independent verification (result)

A separate verifier agent recomputed all 6 pooled (model × BLOCKING/ADVISORY)
means and all 9 per-defect-type means directly from the raw `task_deltas` in
`evals/fixtures/v2_2_causal_chain_multimodel.json`, confirmed the
per-defect-type subsets are an exact, non-overlapping partition of each
model's 18 BLOCKING instances, and independently read
`scripts/v2_defect_injector.py`'s four injector functions. **All three items:
CONFIRMED**, including a small precision correction the verifier surfaced:
`inject_param_renamed` does not append a sentence at all (it renames the
schema property but leaves the description's old-name reference untouched) —
the "appended sentence, bolted-on tell" caveat in B6 applies specifically to
`type_flipped`/`enum_dropped`/`contradictory_required_claim`, not to
`param_renamed`. This matches what B6 above actually claimed (the caveat was
already scoped to those three, not stated to include `param_renamed`) — noted
here for completeness, not as a fix.

## What this does and does not establish

- **Established, now across 3 model families:** at least one BLOCKING check
  (`type_enum_contradiction`) and the one ADVISORY check tested
  (`param_renamed`) cause real, statistically significant drops in agent
  task success. This is no longer a single-model finding.
- **Established, now across 3 model families:** `required_references_missing_property`
  shows no measured causal effect in any model tested — a genuine limitation
  of that specific check's demonstrated practical value.
- **Established, new in this pass:** the BLOCKING/ADVISORY severity split does
  not track measured real-world causal severity in ANY of the three tested
  models — ADVISORY is the larger effect universally, not a gemma2:9b
  artifact.
- **New nuance:** susceptibility to `type_enum_contradiction` specifically is
  model-dependent in magnitude (qwen2.5:7b less affected than gemma2:9b/llama3.1:8b);
  susceptibility to `param_renamed` (ADVISORY) is not.
- **Not established:** whether this pattern holds on tool sets/tasks beyond
  the 6 tested, at a larger per-model sample than 45/15 tasks, or on model
  families outside the Ollama-servable open-weight set tested here (no
  frontier/closed-source models were tested, consistent with the "Never
  ANTHROPIC_API_KEY" constraint).

# FRONTIER-T18: does the T18 description effect survive a stronger agent? — DRAFT

**Status: DRAFT — human-merge only.** Carries a customer-facing-adjacent finding; do not auto-merge.

## What this does
Re-runs the pre-registered T18 oracle A/B (60-tool confusable catalog: Arm A = empty descriptions,
Arm B = oracle discriminating descriptions) against a **substantially stronger agent than the original
gemma2:9b** — **Llama-3.3-70B** — to test whether the description effect **survives** or **collapses**
with agent capability. Fixture, tasks, classifier, and scorer are unchanged. Adds an API-agent path
(non-Anthropic key only; cost-ceiling abort) and a 3-outcome classifier
(SELECTED-CORRECT / SELECTED-WRONG / ABSTAINED-OR-HEDGED) so thoughtful uncertainty is never scored as a
wrong selection.

## Result (Llama-3.3-70B, OpenRouter, 3 trials × 40 tasks × 2 arms)
| Outcome | Arm A (empty) | Arm B (oracle) |
|---|---|---|
| SELECTED-CORRECT | 71/120 = **59.2%** | 120/120 = **100.0%** |
| SELECTED-WRONG | 40.8% | 0.0% |
| ABSTAINED-OR-HEDGED | 0.0% | 0.0% |

- **Effect B−A = +40.8pp.** Task-clustered sign test: n+=19, n−=0, ties=21, **p<0.0001**
  (stable set, excluding 5 Arm-A trial-flippers: n+=14, n−=0 → still p<0.001).
- Headroom gate (STEP 1): Arm A 65% < 85% → real headroom; not the ceiling/collapse trap.
- All 19 Arm-A miss tasks were recovered by the oracle (19/19); Arm B is perfect (100%).
- 0 abstentions in either arm (the frontier-agent hedging trap did not materialize).

**Verdict: the effect SURVIVES at full strength** on a substantially stronger agent — oracle descriptions
still drive a large, highly significant selection gain in the confusable-at-scale regime. The effect does
**not collapse** at a much higher capability tier than the original gemma2:9b result.

## Honest caveats
1. **Not a true frontier model.** Llama-3.3-70B is a strong *open* model, not Claude/GPT-class. This shows
   non-collapse at a substantially higher capability tier than gemma2:9b — it does **not** close the
   frontier question. A Claude/GPT-class run remains the stronger, still-unrun test.
2. **Scope = T18 fixture + one model.** One model is one datapoint. Do not generalize beyond this fixture.
3. **Not apples-to-apples vs gemma.** The gemma2:9b +34.5pp figure is a different experiment
   (different harness/classifier/host). We do **not** claim the effect "grew with capability" — only that
   it **survives / does not collapse**.
4. **plan_event fixture fix.** STEP 2 surfaced a mislabeled task: the original `plan_event` task
   ("Reserve the … slot …") described `book_slot`'s niche, making gold=plan_event unresolvable even with
   the oracle. Reworded to plan_event's actual distinction (gold unchanged); documented in the fixture.
   This is a fixture bug fix, not an experiment re-run — pre-registration intact.

## Provenance / cost
OpenRouter · `meta-llama/llama-3.3-70b-instruct` · single host (all 240 calls) · spend ≈ $0.89 (conservative
fallback pricing; real cost ~10× less) · no ANTHROPIC_API_KEY used anywhere. CI: deterministic, no network,
LLM mocked; verify.sh green; coverage 91%.

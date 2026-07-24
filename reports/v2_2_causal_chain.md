# AgentGauge v2.2 — end-to-end causal chain (Task 3)

Live inference (gemma2:9b, `agentgauge-agent` Cloud Run, direct HTTPS + IAM bearer token).
`scripts/_mutated_stdio_server.py`, `scripts/v2_2_causal_chain.py`,
`evals/fixtures/v2_2_causal_chain.json`.

## What was measured, and why it wasn't measured before

Prior sessions measured that the linter catches injected defects (recall) and that the harness
detects success-rate deltas in general (MDE). Neither measured that a BLOCKING violation *causes*
agent task failure — this task closes that gap directly, with real agent runs.

**Mechanism, checked before trusting any result:** `_mutated_stdio_server.py` monkeypatches only
the target server's `ListToolsRequest` handler (what the agent sees when it asks "what tools
exist") — the `CallToolRequest` handler (actual tool execution) is untouched. A measured `delta`
therefore reflects a change in what the live agent *chose to construct* given a different declared
schema/description, scored against the task's real gold constraints via `constraint_satisfaction`
— not an artificially flipped success flag. (`call_constraints_server`'s own docstring: "Server
always echoes success — validation is done by comparing constructed_args against
GOLD_CONSTRAINTS.") Confirmed structurally, not assumed.

## Design

6 diverse, clean (0 BLOCKING violations) tool sets with existing hand-authored anti-tautology
tasks and constraint definitions (`confusable_server_oracle`, `call_constraints_server_oracle`,
`call_constraints_v2_server_oracle`, `t18_oracle_server`, `rw1_arm_oracle`, `p2a_arm_oracle`). One
eligible target tool per (tool_set, defect_type), using the same injector functions and eligibility
logic already used and measured for the linter's own recall evaluation
(`scripts/v2_defect_injector.py`). trials_per_task=1 (Task 1's optimal allocation finding).

**BLOCKING-class** (3 defect types, mapping to the 2 BLOCKING checks): `contradictory_required_claim`
(→ `required_references_missing_property`), `type_flipped` and `enum_dropped` (both →
`type_enum_contradiction`). 18 instances, 45 tasks total.

**ADVISORY-class**: `param_renamed` (→ `described_not_in_schema` / `param_possibly_renamed`), the
only ADVISORY check with a ready-made injector — `name_collision` and the other half of
`param_possibly_renamed`'s coverage are not schema/description mutations in the existing injector
framework and are out of scope here (disclosed, not silently assumed covered). 6 instances, 15
tasks total.

**Scope note:** 45+15=60 total live tasks, smaller than Task 1's own 100-task optimal allocation
for a single regression test — this measurement pools across *multiple* tool sets/defect types to
build up its sample, a different design than a single `agentgauge diff` run, and was bounded
deliberately given this session's live-inference cost/time constraints.

## 3b/3c. Headline result — pooled BLOCKING effect

**"BLOCKING violations cause a mean 25.2-point drop in agent task success (95% CI [11.3, 39.0]
points), measured across 6 tool sets and 45 tasks."** The CI excludes zero — this is a real,
measured causal effect, not an assumed one.

## 3c (continued) — the pooled number hides a critical split

Breaking the 45 BLOCKING tasks down by which of the 2 BLOCKING checks they target reveals the
pooled number is not representative of either check individually:

| Defect type (→ check) | n | Mean delta | 95% CI | Excludes zero? |
|---|---|---|---|---|
| `contradictory_required_claim` (→ `required_references_missing_property`) | 15 | **+0.0000** | [-20.8, +20.8] pp | **No — a clean null** |
| `type_flipped` (→ `type_enum_contradiction`) | 15 | **-35.6pp** | [-60.9, -10.2] pp | Yes |
| `enum_dropped` (→ `type_enum_contradiction`) | 15 | **-40.0pp** | [-66.9, -13.1] pp | Yes |

**`required_references_missing_property` shows a genuine, clean null effect** — not "small," a CI
that straddles zero almost perfectly symmetrically (mean literally 0.0000). Precisely: 13 of 15
tasks show delta=0.0 exactly; the mean is not uniform inertness but an exact cancellation of one
+1.0 task and one -1.0 task, both from the same instance (`call_constraints_v2_server_oracle`'s
`register_channel`). Noted precisely, not glossed as "every task was unaffected" — the honest
reading is "83% (13/15) of tasks were unaffected, and the 2 that were affected happened to cancel."
Mechanistically this makes sense on
reflection: a bogus `required` entry that references a nonexistent property is something the agent
*cannot act on either way* — there is no real parameter to fill, so the agent's actual argument
construction for the parameters that DO exist is unaffected. **This is reported plainly, as the
task brief required: this specific BLOCKING check's target defect class, at least as tested here,
does not measurably change real task outcomes.**

`type_enum_contradiction` (tested via both `type_flipped` and `enum_dropped`) shows a real,
substantial effect in both cases (~36–40 point drop, both CIs excluding zero) — this check's
target defect class does causally degrade task success, consistent with its mechanism (the
description now describes the wrong value type/enum for a parameter the agent must actually fill).

## 3d. ADVISORY-class effect — larger than either BLOCKING check

**"ADVISORY (param_renamed) violations cause a mean 76.7-point drop in agent task success (95% CI
[49.6, 103.7] points), measured across 6 tool sets and 15 tasks."** 13 of 15 tasks show a large
negative delta (mostly a full -1.0 flip from success to failure); mechanistically the most direct
possible failure mode — the schema property the agent needs literally does not exist under the
name the description tells it to use, so any task requiring that parameter has almost no path to
success.

**This is the most important, must-not-soften finding of this task**: the BLOCKING/ADVISORY
severity split (justified in Task 5, `reports/v2_1_severity_gate.md`, on *false-alarm-rate*
grounds — BLOCKING checks measured 0% false alarms on the clean corpus) does **not** track
measured real-world causal severity uniformly. One BLOCKING check
(`required_references_missing_property`) shows zero measured behavioral impact; the one ADVISORY
check tested (`param_renamed`) shows the *largest* measured impact of anything tested — larger than
either BLOCKING check. Precision-as-a-linter-signal and severity-of-real-world-impact are different
axes, and this measurement is the first time they've been compared directly rather than assumed to
align.

**Caveat on the ADVISORY CI's exact bounds:** the reported upper-magnitude bound (-103.7pp) exceeds
the theoretically possible range (`delta ∈ [-100pp, +100pp]` by construction, since
`joint_success ∈ [0,1]`). This is a known artifact of applying a normal-theory-style
t(G-1)-multiplier CI to a small (n=15), high-effect-size, bounded-outcome sample — the interval's
mathematical construction doesn't clip to the plausible range. The *direction* and even the
*less-extreme* bound (-49.6pp) are unaffected by this artifact and still represent a large, real
effect; only the interval's extreme edge should be read as "very wide, not literally -103.7%."

## Independent verification

A separate verifier agent recomputed all four pooled/per-defect-type means directly from the raw
`task_deltas` arrays, independently re-ran `t_adjusted_cluster_bootstrap_mean_ci`, confirmed the
per-defect-type subsets exactly partition the pooled BLOCKING set (no inconsistent selection), and
confirmed the mutation mechanism only touches tool discovery, not execution. **All four numeric
claims and the mechanism check: CONFIRMED**, with the one nuance already folded into this report
above (the null-effect check's mean is an exact +1.0/-1.0 cancellation on one instance, not uniform
inertness across all 15 tasks).

## What this does and does not establish

- **Established:** at least one BLOCKING check (`type_enum_contradiction`) and the one ADVISORY
  check tested (`param_renamed`) both cause real, measured, statistically distinguishable-from-zero
  drops in agent task success. The linter is not just flagging static description/schema
  inconsistencies that don't matter — for these two checks, they demonstrably do.
- **Established:** one BLOCKING check (`required_references_missing_property`) does NOT show a
  measured causal effect in this sample — a genuine, reportable limitation of that check's
  practical value, not evidence it should be removed (it may still have value as a
  documentation-hygiene signal even without a demonstrated task-success effect).
- **Not established:** whether this pattern holds on tool sets/tasks beyond the 6 tested, on models
  other than gemma2:9b (Task 4 addresses cross-model, but for the harness's flagship pattern, not
  this specific causal-chain measurement), or at a larger sample size than 45/15 tasks.

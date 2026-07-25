# AgentGauge v2.4 — Task 1: blast-radius audit of artifact #7

Zero inference for 1a/1c (pure code + data-provenance audit). GCP re-deploy
(user-approved after a GPU-contention check found qwen3:8b resident locally)
for 1b's live re-measurement.

## 1a. Every injection class scored by `constraint_satisfaction` — per-class verdict

Re-read `scripts/v2_defect_injector.py`'s five injector functions line by
line (not from memory) to find every place a property's SCHEMA KEY changes
between the state a gold constraint was authored against and the state the
agent actually saw — the specific mechanism behind artifact #7.

| Defect type | Does it rename/remove a property KEY? | Verdict | Code citation |
|---|---|---|---|
| `param_renamed` | **Yes** — `props[new_name] = props.pop(pname)` | **AFFECTED** (confirmed, fixed in v2.3 via `constraint_satisfaction_renamed`) | `inject_param_renamed`, line 142 |
| `type_flipped` | No — mutates `pschema["type"]` in place; the dict KEY (`pname`) is untouched | **CLEAN** | `inject_type_flipped`, line 162 (`pschema["type"] = "integer"`, no `pop`/rename) |
| `enum_dropped` | No — mutates `pschema["enum"]` in place; KEY untouched | **CLEAN** | `inject_enum_dropped`, line 181 |
| `contradictory_required_claim` | No — appends a bogus name to `required`; no EXISTING property is renamed or removed | **CLEAN** | `inject_contradictory_required_claim`, line 222 (`required.append(bogus_name)`) |
| `required_unmentioned_prose` | No — edits only the description string via regex substitution; schema untouched entirely | **CLEAN** | `inject_required_unmentioned_prose`, line 201 |

**Mechanism confirmation:** `constraint_satisfaction`'s only failure point is
`constructed_args.get(c.param)` (`evals/fixtures/predictive_validity/
constraints.py`) returning `None` because `c.param` (the gold constraint's
property name, authored against the PRE-mutation schema) no longer exists as
a key in `constructed_args` (built against the POST-mutation schema). This
can only happen if a property's KEY changes between constraint-authoring
time and runtime. Of the five injectors, only `param_renamed` does that —
the other four mutate a property's VALUE-level fields (`type`, `enum`) or
add an unrelated bogus entry, never touching an existing property's
dictionary key. **No other injection class is affected by this specific
bug.** This is a structural argument (verified against the actual
`json.loads(json.dumps(tools))`-based mutation code for all five functions),
not an inference from outcomes.

**Independent verification:** a separate verifier agent re-read all five
injector functions from scratch and independently confirmed the same
per-class verdicts before this was accepted. **CONFIRMED, no discrepancies.**

## 1c. Do the ICC / variance-decomposition / rho / MDE-calibration numbers depend on the buggy checker?

**No — traced the numbers to their source data and confirmed they never
touch the injector-mutation pathway at all.**

`reports/v2_variance_structure.md`'s ICC (0.793), variance decomposition
(25.9%/56.1%/18.0%), and `agentgauge/harness.py`'s `CALIBRATED_BASELINE_RATE`/
`CALIBRATED_SIGMA_TASK`/`CALIBRATED_RESID_SD` are all computed from
`evals/fixtures/predictive_validity/results_raw.json` — **5,535 trial
records across 45 STATIC, real (non-mutated) tool-set variants**, confirmed
by direct inspection:

```
45 tool sets, e.g.: call_constraints_server, call_constraints_server_fixed,
call_constraints_server_oracle, confusable_server, confusable_server_fixed,
exp1_blazickjp_arxiv_mcp_server_mirror, p2a_arm_oracle, t18_oracle_server, ...
```

None of these is a `scripts/_mutated_stdio_server.py`-produced (dynamically
renamed) tool set — that mutation mechanism didn't exist yet when this
corpus was collected (it was built specifically for v2.2's Task 3
causal-chain study, which came after the predictive-validity study this
corpus is from). `CALIBRATED_RHO` (0.881, "pooled Pearson r, before/after
task means, 40 matched Phase-3 tasks") is computed from 5 matched
bad/mediocre → LLM-rewritten `_fixed` server pairs — again, hand-authored
alternate servers with **identical parameter names** to their originals
(only descriptions differ), not runtime-renamed schemas.

**Conclusion: ICC, the variance decomposition, rho, and the MDE calibration
constants are entirely outside artifact #7's blast radius. No recomputation
needed — verified from the underlying data files, not assumed because "it
sounds unrelated."** The Task 1 (v2.2) compute-optimal allocation (100
tasks/arm × 1 trial/task, MDE=0.0848) stands unchanged; the default
`--trials=1` configuration is not revisited by this audit.

**Independent verification:** a separate verifier agent independently opened
`results_raw.json`, confirmed all 45 entries, confirmed none resemble a
dynamically-mutated tool set, summed `run_results` to 5,535, and confirmed
both `v2_variance_structure.md` and `CALIBRATED_RHO`'s defining comment cite
this same source. **CONFIRMED, no discrepancies.**

## 1b. Re-measuring the surviving BLOCKING claim

(GCP redeploy required — local GPU had contention from a resident qwen3:8b;
user approved GCP use for this specific measurement after being asked.
`agentgauge-agent` was rebuilt from scratch — image + service had been fully
torn down after v2.2/v2.3 — then re-measured, exercising the exact same
instance selection as `scripts/v2_2_causal_chain_multimodel.py`, restricted
to the 3 BLOCKING defect types. `scripts/v2_4_blocking_remeasurement.py`,
`evals/fixtures/v2_4_blocking_remeasurement.json`.)

**The claim survives, exactly.**

| Model | Original (v2.2) | Re-measured (v2.4) |
|---|---|---|
| gemma2:9b | -25.2pp [-39.0,-11.3] | **-25.19pp [-39.02,-11.35]** |
| llama3.1:8b | -28.9pp [-43.6,-14.2] | **-28.89pp [-43.58,-14.20]** |
| qwen2.5:7b | -13.3pp [-25.2,-1.5] | **-13.33pp [-25.15,-1.52]** |

All three CIs still exclude zero. **"NO linter check collapsing to null" —
refuted directly: `type_enum_contradiction` still shows a real, measured,
statistically significant task-success drop in every model tested.** This
is the one claim in the whole v2.2-v2.4 arc that has now been checked twice,
independently deployed, and holds both times.

**A finding surfaced by the independent verifier, checked before accepting
this result:** the raw per-task deltas in the v2.4 re-measurement are
**byte-identical** to the original v2.2 run — not just statistically
similar, the exact same before/after/delta float values for all 45
tasks × 3 models, down to full precision. Two possible explanations were
weighed: (a) the re-measurement script accidentally reused old data instead
of calling the model live, or (b) Ollama's seeded decoding (`seed=42`,
passed on every `/api/chat` call in both scripts) is fully deterministic
given identical prompts on the same model, so identical inputs genuinely
produce identical outputs. **(a) is ruled out**: `evals/fixtures/
v2_4_blocking_remeasurement.json` did not exist before this run (confirmed
via `ls` before launch) and Cloud Monitoring's `request_count` metric shows
**542 real HTTP requests** hit the service during the exact re-measurement
window — genuine live inference occurred, not a shortcut. **(b) is the
correct explanation.** This means the v2.4 result is not independent
statistical evidence in the sense of "fresh sampling variance that could
have landed elsewhere" — given fixed inputs and Ollama's deterministic
seeding, a third run would reproduce the same numbers again. What it DOES
confirm: no drift, no infrastructure-dependent instability, and no residual
concern that the original number was a one-off fluke of that specific Cloud
Run session — the pipeline reproduces stably from scratch, on a freshly
rebuilt service, hours later. Reported precisely rather than oversold as
"independently replicated."

**Independent verification:** a separate verifier agent recomputed the
pooled mean+CI for all 3 models directly from the raw JSON (exact match),
confirmed each model has exactly 18 non-duplicated instances with
`task_deltas` lengths matching `BLIND_TASKS` filtered by target tool
(5 instances spot-checked), and confirmed the byte-identical-deltas finding
independently before flagging it for this precision check. **CONFIRMED.**

## GCP teardown (post Task 1b)

User approved teardown after Task 1b completed. `gcloud run services delete
agentgauge-agent` and `gcloud container images delete
gcr.io/expense-tracker-498014/agentgauge-agent-baked` (0 tags/digests remain,
confirmed directly). `agentgauge-judge` confirmed still running and healthy,
untouched. `expense-tracker` (unrelated) also untouched.

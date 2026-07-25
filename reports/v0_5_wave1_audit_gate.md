# AgentGauge v0.5 Wave 1 — audit-gate pass over new result sets

Per spec-agentgauge-v0.5.md section 7's standing rule ("run `agentgauge audit` against
every new result set... eight artifact classes found to date; assume a ninth"), this
document is the orchestrator-level check applied to the two result sets Wave 1
produced that are not already covered by the CLI's existing gate.

## 1. What is already covered by the existing gate (no new check needed)

`agentgauge/audit.py`'s `run_audit` is wired into `_diff_async`/`_eval_async`
unconditionally (`agentgauge/cli.py:234,469,613`) and fires regardless of which
adapter or provider-config serves a live run — confirmed by reading the code, not
assumed: `_collect_trials` (cli.py:363) always runs after `_schema_audit_or_exit` and
before `run_audit`'s full pass, for every adapter path. **Any live `agentgauge
diff`/`eval` run using any of the six adapters is already gated exactly as it was
before this wave.** The adapter abstraction introduces no new bypass of the standing
gate.

## 2. New result set: cassette determinism proof (`tests/test_cassette.py`)

This is an engineering proof (does replay reproduce byte-identical output), not a
product measurement subject to `run_audit`'s BlindTask/tool-schema-shaped checks —
most of the 8 classes (task/answer leakage, tool-name ceiling, zero-vector embedding,
self-descriptive-name confound, subset-vs-catalog mismatch, scoring-reference
mismatch, fixture-schema hallucination) don't structurally apply to a fixed 8-prompt
replay fixture. Two were worth checking directly rather than assumed inapplicable:

- **LCG index-saturation** (class #6): would manifest as the replay proof itself
  becoming nondeterministic across runs — this is exactly what the proof tests for and
  reports 100%/100%/100%/100%/100%/100% (all six adapters) against, so this class
  would have been caught, not missed, had it been present.
- **Candidate 9th-class check — cassette key content-insensitivity**: a cassette
  wrapper that (bug) keyed only on `(provider_name, model, seed)` and ignored message
  content would still pass a naive "replay the same prompt N times, get the same
  answer" test, while silently returning the wrong recorded response for a
  *different* prompt under the same seed in production. Checked directly: (a)
  `cassette_key()` hashes message content (`agentgauge/cassette.py:33-53`); (b)
  `tests/test_cassette.py::test_cassette_key_changes_with_message_content` asserts two
  distinct prompts hash to distinct keys; (c) the fixed fixture set itself
  (`_FIXTURE_PROMPTS`, 8 distinct prompts) uses distinct canned responses per position,
  deliberately mixing correct/incorrect selections rather than one repeated
  response — so a content-insensitive key bug would have broken the non-degenerate
  `DecomposedRate` the proof also asserts. **Checked and not found** — this is not a
  live gap, but it was worth verifying rather than assuming, since it's exactly the
  shape of bug this repo's artifact history (self-descriptive-name confound, class #4)
  shows this project is prone to missing until it's specifically tested for.

No blocking or warn-worthy finding on this result set.

## 3. New result set: attribution benchmark (`reports/v0_5_attribution_benchmark.md`)

This report already runs its own mandatory confound guard (culprit position not
fixed; decoys not systematically smaller-diff than the culprit) and its own
MEASURED-vs-NOT-MEASURED split before reporting any accuracy number — independently
re-read and confirmed present and non-trivial (6 distinct culprit positions across 50
cases; 96% of cases have at least one decoy with a larger diff than the true
culprit). This is the same rigor `run_audit` enforces for the `diff` pipeline, applied
by the report's own authors rather than by a shared code path (the benchmark's data
shape — synthetic `TrialOutcome` pairs from a declared ground-truth model, not
BlindTasks scored against a live schema — doesn't fit `run_audit`'s function
signature without a nontrivial adapter; not attempted this wave, noted as a gap
below).

One additional finding, not raised in the benchmark report itself:

- **Ceiling effect on `exhaustive_ablation` (100%/100%)** is structurally the same
  concern `audit.check_ceiling_floor` flags for a real diff run (a rate at the ceiling
  leaves no room to show it could be *better*, i.e. distinguishing "correct" from
  "even more correct" is not possible). Here this is not a defect — exhaustive
  ablation probing the true culprit directly is *expected* to find it every time by
  construction, that's the whole point of using it as the accuracy reference — but it
  does mean the benchmark cannot show whether exhaustive ablation would ever miss a
  culprit under a harder (noisier-decoy) regime. The attribution report's own §4
  ("NOT MEASURED") already states this same limitation in different words ("unusually
  clean ground-truth signal... a real benign textual edit might have a small nonzero
  effect the harness's CI can't distinguish"). Recorded here to confirm the two
  documents' independent self-critiques agree, not to add a new caveat.

No blocking finding on this result set. One gap, disclosed rather than silently
accepted: **`run_audit` itself was not extended to cover the attribution benchmark's
data shape this wave** — the check above was performed by direct code/report reading
(an orchestrator-level manual pass), not by running the standing automated gate
against this new surface. If Wave 2 builds further on the attribution benchmark
generator, extending `run_audit` (or a sibling gate) to accept synthetic
`TrialOutcome`-pair result sets directly is worth doing rather than repeating a manual
review each time.

## 4. Ninth-artifact-class candidate actually worth naming going forward

Neither result set produced a genuine new *statistical* artifact this wave (unlike
the historical 8, which were each found the hard way, after the fact). The one real
new-surface risk worth naming for future waves is **process/scope, not statistics**:
`agentgauge/cassette.py`'s provider-level record/replay mechanism and the CLI's
pre-existing `--replay-before`/`--replay-after`/`--replay` flags (post-hoc replay of
already-scored `TrialOutcome` JSON, unrelated code path, unchanged this wave) share
the word "replay" but are different mechanisms operating at different layers.
Confirmed by reading `agentgauge/cli.py`: `CassetteProvider` is **not wired into any
CLI command this wave** — it exists only as a library mechanism exercised by
`tests/test_cassette.py`. This is deliberate (out of this wave's committed scope) but
worth stating explicitly in the end-of-wave report's NOT MEASURED section: a reader
should not assume `agentgauge diff --provider-config ...` gets cassette-backed replay
caching today. It doesn't, yet.

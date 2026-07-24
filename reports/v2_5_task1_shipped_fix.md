# AgentGauge v2.5 — Task 1: fix the artifact #7 pattern in shipped product code

The v2.4 blast-radius audit (`reports/v2_4_task1_blast_radius_audit.md`)
found the same pre/post scoring-reference vulnerability in
`agentgauge/constraints.py` (used by the real `agentgauge diff`/`eval`
commands), not only in the research script — but reported it as FOUND, not
FIXED. This closes that gap.

## 1a. Every location, cited

`agentgauge/cli.py`'s `_collect_trials` (previously the only place shipped
code scores a user's task-file constraints against live agent output):

```python
score = (
    constraint_satisfaction(r.constructed_args, constraints)
    if r.selected_tool == r.task.tool_name
    else 0.0
)
```

`constraints` comes from `constraints_by_key`, keyed by `(tool_name,
description)` from the user's `--tasks` JSON file — authored at whatever
point the user last wrote it, against whatever schema they had in mind at
the time. `constructed_args` comes from a LIVE `run_tasks(...)` call against
whichever server `--before`/`--after`/`target` currently connects to.
`agentgauge.constraints.constraint_satisfaction` (the function itself,
`agentgauge/constraints.py:91-105`) does `constructed_args.get(c.param)` with
no way to know whether `c.param` is even a real property of the schema the
agent just saw. If a user runs `agentgauge diff old.py new.py --tasks
tasks.json` to test exactly the kind of change this tool exists to check —
a renamed parameter — and their task file's constraint still names the old
parameter, a correctly-adapting agent is silently scored as a failure. This
is the exact artifact #7 mechanism, in the primary product surface, not a
research fixture.

Both `_diff_async` (diffing `before`/`after`) and `_eval_async` (evaluating
one `target`) call `_collect_trials`, so both were exposed.

## 1b. The fix

Not a "correct the constraint automatically" fix — there is no rename
mapping available in the general case (unlike the research script, which
knew exactly which property the injector renamed). The sound fix is
fail-fast, fail-loud: check every task's constraints against the ACTUAL,
freshly-introspected schema **before spending any live inference**, not
just before reporting a result (the v2.4 `agentgauge audit` gate already
did the latter, but only after `_collect_trials` had already run a full,
wasted set of live trials).

`agentgauge/cli.py`:
- New `_introspect_tools(target)`: connect, introspect, disconnect — no
  trials.
- `_collect_trials` no longer introspects internally; it only runs trials
  (signature simplified from `-> tuple[list[TrialOutcome], list[Any]]` to
  `-> list[TrialOutcome]`).
- New `_schema_audit_or_exit(...)`: runs `agentgauge.audit.run_audit` with
  ONLY the introspected tools (no trial data yet), and raises `typer.Exit(2)`
  immediately on a BLOCKING finding.
- `_diff_async`: now introspects both `before`/`after` FIRST, runs the
  schema-only audit, and only THEN calls `_collect_trials` (live inference)
  for both variants — the full post-trial audit (ceiling/floor, degenerate
  metrics, which need trial data) still runs afterward, unchanged.
- `_eval_async`: reuses the introspection it already did for linting (no
  extra connection needed) for the same schema-only pre-check.

## 1c. Regression tests, seeded with the real historical case

`tests/test_cli.py::TestScoringReferenceConsistencyGate` — three
integration-level tests using the REAL `agentgauge diff`/`eval` Typer
commands (via `CliRunner`, not the isolated `agentgauge.audit` unit tests
from v2.4 Task 2), seeded with the exact historical case
(`confusable_server_oracle`'s `query_records` tool, `'field'` renamed to
`'field_v2'` — `evals/fixtures/v2_3_advisory_audit.json`):

1. `test_diff_blocks_before_any_live_trial_on_renamed_param`: a mocked MCP
   client whose `introspect()` returns the schema with `field_v2` (the
   renamed property); the task file's constraint still names `field`
   (stale). The mocked client's `call_tool` is set to **raise an
   AssertionError if ever invoked** — proving the block happens before any
   live inference reaches the server, not merely before a result prints.
   Asserts `exit_code == 2`, the `scoring_reference_consistency` finding
   appears in output, and no verdict (`REGRESSION`/`NO_CHANGE`/
   `INSUFFICIENT_SENSITIVITY`) is ever printed.
2. `test_eval_blocks_before_any_live_trial_on_renamed_param`: same pattern
   for `agentgauge eval`.
3. `test_diff_proceeds_normally_when_schema_matches`: control case — the
   SAME constraint against the correct (non-renamed) schema must NOT be
   blocked, confirming the gate doesn't over-fire on legitimate runs.

All 3 pass; full suite re-run afterward with no regressions.

## 1d. Confirmed: the gate catches this in product code paths, not just research fixtures

The three tests above exercise the actual `agentgauge diff`/`eval` CLI
commands end-to-end (Typer `CliRunner`, real `_diff_async`/`_eval_async`,
real `agentgauge.audit.run_audit`) — not a standalone call to
`run_audit()` with hand-built fixtures, which is what v2.4's Task 2 test
suite (`tests/test_audit.py`) exercised. This closes the exact gap Task 1d
asked about: the audit module's logic was already correct in isolation, but
it wasn't previously proven to actually run, in the right place, in the
shipped CLI surface, before this pass. No extension to `agentgauge.audit`
itself was needed — the gap was in *when* the CLI called it, not in the
check's own logic.

## 1e. v0.4.0 gate

v0.4.0 was already built and verified as a wheel (v2.4, Task 3) but never
published to PyPI (per standing instruction). This fix is now included in
that same unpublished build state — the gate ("do not ship v0.4.0 until
this is closed") is satisfied: nothing has been published, and the fix
lands before any future publish would happen.

## Independent verification

A separate verifier agent re-ran the 3 new integration tests independently
(all pass), confirmed `_collect_trials`'s signature no longer returns tools,
confirmed `_schema_audit_or_exit` is called before `_collect_trials` in both
`_diff_async` and `_eval_async`, confirmed the test mechanism genuinely
proves a pre-inference block (the mocked `call_tool` raises if ever
invoked), and confirmed `mypy`/`ruff` clean. **CONFIRMED, no discrepancies.**

One non-blocking observation from the verifier: `_collect_trials` still
triggers a second, independent `client.introspect()` call inside
`agentgauge.runner.run_tasks` (to build the tool listing shown to the
agent), on a fresh connection, separate from the schema-audit introspection.
This doesn't undermine the fix (the audit's schema snapshot and the trial
run's schema snapshot come from the same live server, so they can't
diverge in a way that reintroduces the vulnerability) but is a minor
design redundancy — noted for a future pass, not fixed here since it's out
of this task's scope and doesn't affect correctness.

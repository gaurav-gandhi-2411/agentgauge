# AgentGauge v2.1 — severity-gate restructuring (Task 5)

Zero LLM calls. Fixes the CI-gate false-alarm profile identified in `reports/v2_linter_evaluation.md`
§2c: per-tool false-alarm rate passed (3.45% < 5%), but per-tool-SET false-alarm rate did not
(66.67%) — a naive "any HIGH flag blocks the PR" gate would reject two-thirds of genuinely clean
tool sets, which would get the linter disabled in practice regardless of its per-tool precision.

## The restructuring

`agentgauge.linter.Severity` changes from a single `HIGH`/`INFO` split to three tiers:

| Tier | Checks | Clean-corpus false alarms | Behavior |
|---|---|---|---|
| **BLOCKING** | `type_enum_contradiction` (c), `required_references_missing_property` (e) | **0** (measured, both checks) | Fails CI (`agentgauge lint` exits 1, `flagged=True`) |
| **ADVISORY** | `described_not_in_schema` (a), `name_collision` (f), `param_possibly_renamed` (g) | 22/521 tools (a: 29 violations, f: 22, g: 4 — some tools carry more than one) | Printed, does NOT fail CI |
| **INFO** | `required_not_mentioned` (b) | n/a (off by default) | Opt-in only (`--show-info`) |

`param_possibly_renamed` (g, added in Task 4) is placed in ADVISORY, not BLOCKING: its clean-corpus
false-alarm count (4/521) is low but not measured at exactly zero, the same bar (c) and (e) clear.
BLOCKING is reserved for checks with a **measured** 0% false-alarm rate on this corpus, not a
merely-low one.

`LintReport.flagged` (the property the CLI's exit code and CI gate key off) now means "has any
BLOCKING violation" — ADVISORY and INFO violations are surfaced in output but never block a PR.

## Measured result

| Granularity | Metric | Value | Target |
|---|---|---|---|
| Per tool set (n=21) | False-alarm rate, BLOCKING-only | **0.00%** (0/21) | <10% — passes decisively |
| Per tool (n=521) | False-alarm rate, BLOCKING-only | **0.00%** (0/521) | (not a separate target; reported for completeness) |
| Per tool set (n=21) | False-alarm rate, ADVISORY+BLOCKING combined (the old v2 "HIGH" definition) | 66.67% (14/21, unchanged from v2) | n/a — this is exactly the rate the restructuring is designed to route around, not eliminate |

The 66.67% per-tool-set rate on the OLD single-tier definition does not go away — the same
`described_not_in_schema`/`name_collision`/`param_possibly_renamed` noise still exists and is still
surfaced to the user. What changes is which tier that noise sits in: it no longer determines the
CI exit code. A team that wants zero-tolerance on ADVISORY findings can still wire `--show-info`
and their own stricter gate on top; the shipped default only blocks on the checks measured to have
zero false alarms.

## What changed in the CLI

- `agentgauge lint`: exit code now keys off BLOCKING only. Console output prints BLOCKING first
  (red, "fails CI"), then ADVISORY (yellow, "does not fail CI"), then INFO if `--show-info`.
- `--json` output: `blocking`/`advisory`/`info` lists and `n_blocking`/`n_advisory`/`n_info` counts
  (replaces the old `high`/`n_high` keys).
- `agentgauge eval`: same `n_blocking`/`n_advisory` fields in its JSON payload.
- `agentgauge init`'s scaffolded GitHub Action: the PR-comment step now reports BLOCKING and
  ADVISORY findings separately; the CI-failing step's title and behavior reflect BLOCKING-only
  gating (no logic change needed there beyond the comment/labels, since `agentgauge lint`'s exit
  code already reflects the new tiering).

## Regression note

This is a backward-incompatible API change to `agentgauge.linter`'s public surface
(`ToolLintResult.high`/`LintReport.high`/`.n_high` are removed, replaced by `.blocking`/`.advisory`
and `.n_blocking`/`.n_advisory`). Acceptable here: the package is unpublished (Task 6c explicitly
did not publish to PyPI), so there are no external consumers of the old attribute names. All
existing tests referencing the old severity model were updated in the same change, not left
broken.

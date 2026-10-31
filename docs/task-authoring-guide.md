# Task-authoring guide

Practical guidance for writing the tasks file that `agentgauge diff` and `agentgauge eval` read
(`--tasks`). Every claim below cites a file committed in this repo; the evidence table at the end
lists claim, file and key. Where the repo has little or no evidence, the section says so, and any
advice with no committed measurement is marked **not measured in this repo**. All example tool names
and tasks are fictional and illustrative.

## How a task is scored (the part that drives every rule below)

A task is a tool name, a description (the text the agent sees) and a list of constraints. Each
constraint checks one top-level argument by name. `enum` is an exact, case-sensitive match;
`contains` is a case-insensitive substring match; `format`, `range` and `numeric_equals` are the
other kinds (`agentgauge/constraints.py`, `Constraint` docstring). A task with no constraints scores
1.0 on arguments once the right tool is picked, because there is nothing to check
(`agentgauge/constraints.py`, `constraint_satisfaction` docstring). A task can only be scored on
what its constraints check and what its text makes knowable.

## 1. State every required argument value in the task text

An agent cannot be scored fairly on a value the task never tells it. The shipped worked example
describes a ticket with its project, title and priority in the text, and constrains the project,
the title (via its order number) and the priority (`agentgauge/cli.py`,
`_STARTER_TASKS_TEMPLATE`). Note the README quickstart and the predictive-validity report say to
never quote "the gold tool name or a required literal value" in the task text, because that makes
selection trivial (`README.md`, Quickstart step 2; `reports/predictive_validity_study.md`,
artifact 1). That wording seems to conflict with this section. This guide's reconciliation, which
is a synthesis and **not measured in this repo**: state the values the agent must pass in natural
language, without naming the tool and without lifting them verbatim from the tool's own
description, as the starter template does.

Illustrative:

- Weak: "Open a ticket for the refund problem." (Project, priority and order number are
  unknowable, so any constraint on them tests a guess.)
- Better: "Open a high-priority ticket in the billing project titled 'Refund not received for
  order 4417'." (Every checked value is stated.)

The coverage check (section 5) flags a stated value that no constraint covers. It cannot flag the
reverse case, a constraint on a value the text never states. No committed check detects that;
review it by hand.

## 2. Do not rely on wrapper-object inference

Evidence here is thin. What is committed:

- Constraints are looked up by top-level argument name only (`constructed_args.get(c.param)`,
  `agentgauge/constraints.py`). A constraint on a parameter that lives inside an object the agent
  builds will not be found.
- The committed fixtures flatten real nested APIs into flat parameters. The Jira fixture notes
  state that the real API nests `fields.project.key`, and the S3 fixture notes call each tool a
  "simplified wrapper" with flat parameters (`evals/fixtures/v2_4_corpus/jira_issues_NOTES.md`,
  "Honesty about sourcing"; `evals/fixtures/v2_4_corpus/aws_s3_NOTES.md`, opening section).
- A constraint whose `param` is not a top-level property of the tool schema is a BLOCKING audit
  finding (`check_scoring_reference_consistency`, `agentgauge/audit.py`). It runs before any live
  trial in `diff` and `eval` and exits 2 (`_schema_audit_or_exit`, `agentgauge/cli.py`). So a
  nested-path constraint stops the run instead of silently scoring 0.

Guidance that follows from this, **not measured in this repo**: if a tool takes its required
arguments inside a wrapper object, say in the task text that they belong together, and check that
your constraints can reach them. This repo has no measurement of how often wrapper inference
fails, and no audit rule for that specific failure (the check above only catches a constraint
naming a missing top-level parameter).

## 3. Watch near-duplicate tools

When two tools are confusable, a task aimed at one of them must carry whatever distinguishes it.
The committed example is the T18 run: two tasks stayed tied at the floor (0% in both arms) because
the gold was ambiguous, not because the agent failed. `find_entries` competed with `lookup_data`
because the "task text doesn't specify backend", and `book_slot` competed with `plan_event` because
the double-booking criterion "is not cued by the task" (`STATUS.md`, T18 section, "Scope").

Two commands flag near-duplicate names, so run them on your server first:

- `agentgauge lint` reports `name_collision` as an ADVISORY finding when the normalized
  edit-distance similarity of two names is at least 0.8 (`agentgauge/linter.py`,
  `check_name_collisions`; threshold in `agentgauge/scorer.py`, `_COLLISION_THRESHOLD`).
- `agentgauge scan` deducts 0.15 per near-duplicate pair, capped at 0.30, from the discoverability
  heuristic sub-score, not the overall scan score (`agentgauge/scorer.py`, `_COLLISION_PENALTY`).

The advice to write one task per member of each confusable pair, each cuing its own discriminator,
is **not measured in this repo**. The T18 note above is the only committed evidence, and it
describes the failure, not a tested fix.

## 4. Free-text required arguments

Exact-match scoring and paraphrase do not mix. `enum` demands the exact, case-sensitive string
(`agentgauge/constraints.py`), so use it only for values that are a closed set, such as `"high"`
or `"billing"` in the starter example. For free text such as titles or messages, the starter
example uses `contains` on a distinctive stated token (`"4417"`), which tolerates rewording around
that token (`agentgauge/cli.py`, `_STARTER_TASKS_TEMPLATE`).

So: put a distinctive token in the task text (an ID, a number, a short quoted phrase), and
constrain on that token with `contains`. The audit's "stated value" detector is a heuristic that
looks only at quoted strings and tokens containing a digit, and counts a literal as covered only
if a matching `enum`/`contains`/`numeric_equals`/`range`/`format` constraint accepts it
(`agentgauge/audit.py`, `_task_literals`, `_literal_is_checked`; `enum` and `contains` match by
substring in either direction, and the check does not look at which parameter the constraint is
on). A bare unquoted word is
invisible to it.

No committed measurement says how often agents paraphrase a free-text value, so the size of this
problem is **not measured in this repo**. The advice above follows from how the matchers are
defined, not from an observed failure rate.

## 5. Constraint coverage

Every live `diff` or `eval` run with `--tasks` prints a line of the form
`constraint coverage over N tasks: X selection-only, Y partial, Z full`
(`agentgauge/audit.py`, `CoverageSummary.line`; printed from `agentgauge/cli.py`, where the
coverage object is initialised to `None` with the comment "needs the tasks file, so live runs
only", so replay runs do not print it). Classes
(`agentgauge/audit.py`, `classify_task_coverage`):

- **selection-only**: no constraint at all. Any arguments score 1.0 once the tool is chosen.
- **partial**: some constraint, but a required parameter has none, or a value stated in the task
  text is not covered by one.
- **full**: every required parameter is constrained and every stated value is covered.

If more than half the tasks are selection-only, the verdict is labelled "(selection-only)" and
the audit emits a WARN, which never blocks (`agentgauge/audit.py`,
`SELECTION_ONLY_LABEL_THRESHOLD`, `check_constraint_coverage`). Required parameters come from the
tool schema, so the counts are most accurate when the tools are visible to the check.

How to fix a flagged task. For selection-only, add constraints (`agentgauge init` scaffolds a
full-coverage example). For partial, each task's `unconstrained` list names what is missing,
either `required param '<name>'` or `stated value '<literal>'` (`classify_task_coverage`). The CLI
prints only the counts, so to see the per-task list call
`summarize_constraint_coverage(tasks, tools)` from `agentgauge.audit` in Python. Then add a
constraint for each item, or remove the literal from the text if you do not intend it to be
checked.

Why this matters, with numbers from the committed corpus report
(`evals/fixtures/constraint_coverage_corpora.json`): the 253-task argument-degradation corpus has
26 full, 211 partial and 16 selection-only tasks; the 1136-task predictive-validity corpus has
517 full, 389 partial and 230 selection-only. Partial is the common outcome, so expect to
iterate. The detector is a heuristic and can over- or under-count (`agentgauge/audit.py`,
comment above `_QUOTED`).

## How to check your tasks

Flags verified against `uv run agentgauge --help` and each subcommand's `--help`. There is no
standalone `audit` subcommand: the "agentgauge audit" the README mentions is the in-process audit
inside `diff` and `eval`, and a blocking finding (for example a task that contains its own gold
tool name) stops the run.

```bash
# scaffold a starter tasks file and CI workflow into a directory
agentgauge init --out .

# static check of the server itself (no LLM); reports name_collision and other findings
agentgauge lint path/to/your_server.py

# single run with the mock provider: no inference needed, runs the audit on your tasks
agentgauge eval path/to/your_server.py --tasks agentgauge_tasks.json --mock

# compare two variants on your tasks (needs an agent model, or --mock / --replay-before / --replay-after)
agentgauge diff before_server.py after_server.py --tasks agentgauge_tasks.json
```

## Evidence table

| Claim | File | Key / location |
|---|---|---|
| Constraint kinds; `enum` exact case-sensitive; `contains` case-insensitive | `agentgauge/constraints.py` | `Constraint` docstring |
| No constraints scores 1.0 on arguments | `agentgauge/constraints.py` | `constraint_satisfaction` docstring |
| Constraints read top-level args by name | `agentgauge/constraints.py` | `constructed_args.get(c.param)` |
| Constraint on a non-top-level param is BLOCKING, pre-trial, exit 2 | `agentgauge/audit.py`; `agentgauge/cli.py` | `check_scoring_reference_consistency`; `_schema_audit_or_exit` |
| Coverage line only on live runs with tasks | `agentgauge/cli.py` | `coverage: CoverageSummary | None = None  # needs the tasks file, so live runs only` |
| Worked example constrains project, title (`contains` "4417") and priority | `agentgauge/cli.py` | `_STARTER_TASKS_TEMPLATE` |
| Do not quote gold tool name or required literal values | `README.md` | Quickstart step 2 |
| Same, as a fixed measurement artifact | `reports/predictive_validity_study.md` | artifact 1 ("Task-name leakage") |
| Real Jira API nests `fields.project.key`; fixtures flatten | `evals/fixtures/v2_4_corpus/jira_issues_NOTES.md` | "Honesty about sourcing" |
| S3 tools are simplified wrappers with flat params | `evals/fixtures/v2_4_corpus/aws_s3_NOTES.md` | opening paragraph |
| Floor ties from ambiguous gold: `find_entries`/`lookup_data`, `book_slot`/`plan_event` | `STATUS.md` | T18 "Scope" paragraph ("2 tied at floor") |
| `name_collision` advisory at similarity >= 0.8 | `agentgauge/linter.py`; `agentgauge/scorer.py` | `check_name_collisions`; `_COLLISION_THRESHOLD = 0.8` |
| Scan deducts 0.15 per pair, capped 0.30 | `agentgauge/scorer.py` | `_COLLISION_PENALTY` and the comment above it |
| Coverage classes and `unconstrained` entries | `agentgauge/audit.py` | `classify_task_coverage` |
| Stated-value detector: quoted strings and digit tokens only | `agentgauge/audit.py` | `_QUOTED`, `_DIGIT_TOKEN`, `_task_literals` |
| More than half selection-only gives label and WARN, never blocks | `agentgauge/audit.py` | `SELECTION_ONLY_LABEL_THRESHOLD`, `check_constraint_coverage` |
| 253-task corpus: 26 full, 211 partial, 16 selection-only | `evals/fixtures/constraint_coverage_corpora.json` | `corpora.argument_degradation_253` |
| 1136-task corpus: 517 full, 389 partial, 230 selection-only | `evals/fixtures/constraint_coverage_corpora.json` | `corpora.predictive_validity_44_tool_sets` |
| CLI flags `--tasks`, `--mock`, `--out`, `--replay-before/after` | `agentgauge/cli.py` | `diff`, `eval_cmd`, `init` option definitions |

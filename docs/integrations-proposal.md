# Integrations proposal: pytest, GitHub Actions, MLflow / W&B, Inspect AI / promptfoo

Status: proposal, nothing built. Written 2026-10-23 against `origin/main` (`03588c6`, 0.5.3) and
`origin/release/v0.6.0` (`ac553db`). Each section covers user value, effort, maintenance cost, risks
and what would show it worked; the recommended order is at the end.

**Evidence rules.** Every external API named below comes from an official docs page in
[Sources](#sources), read 2026-10-23 through a summarizing fetch tool: treat signatures as
"confirmed to exist, re-read before coding", not verbatim copies. Unconfirmed items are marked
**unverified**. There are no user counts, download figures or market sizes here, measured or
implied. **Assumption** marks a judgment call, not a finding.

---

## 0. What exists today, and the gaps every integration hits

### Surface on `main` (0.5.3)

- `agentgauge diff BEFORE AFTER --tasks T.json`: a live run with bootstrap CI over joint success,
  decomposed into selection accuracy and argument accuracy.
  `--replay-before/--replay-after` read pre-collected trial outcomes instead and need no model.
  Exit codes: 0 = `improvement` / `no_change` / `insufficient_sensitivity` / `ceiling` / `floor`;
  1 = `regression`; 2 = usage error, failed audit, or backend unreachable. `--json` emits `verdict`,
  `delta`, `ci_lo`, `ci_hi`, `threshold`, `message`, per-arm decomposed rates, `before_cost` /
  `after_cost`, and `constraint_coverage`.
- `agentgauge eval TARGET [--tasks | --replay]`: lint plus a single-point rate. **It always connects
  to `TARGET`**, even with `--replay`, because it lints the live tool list. So `eval` replay is not
  server-free.
- `agentgauge lint`: a deterministic linter that uses no model.
- `agentgauge init`: scaffolds `agentgauge_tasks.json` and `.github/workflows/agentgauge.yml`. On
  `main` that workflow runs lint and then a **live** diff that needs Ollama reachable from the runner.
  It posts a PR comment through `actions/github-script` and needs `pull-requests: write`.
- The replay file format is a bare JSON list of
  `{task_tool_name, selected_tool, constraint_satisfaction}`. It is loaded by `_load_replay_trials`,
  a private function in `cli.py`.
- `agentgauge/cassette.py` (`CassetteProvider`) replays provider `chat()` calls; library-only.

### Only on `release/v0.6.0` (from unmerged PR #123 and the follow-up branches)

| Feature | Why an integration needs it |
|---|---|
| `diff` with `--replay-before/--replay-after` and **no server paths** (`before`/`after` become optional) | On `main` the two positional paths are still required, so a replay-only caller has to pass dummy strings. The Action and the pytest fixture should not ship that wart. |
| `agentgauge demo` plus bundled `agentgauge/demo/replay_{before,after}.json` | A ready-made, provenance-documented replay pair for self-tests of the Action and the plugin. |
| Lint-only `init` workflow (live diff opt-in via `vars.AGENTGAUGE_LIVE_DIFF`) that tees to `$GITHUB_STEP_SUMMARY` | It already establishes the "no model in CI by default" posture the Action builds on. |
| n=1 per arm returns `insufficient_sensitivity` with `ci_lo`/`ci_hi` = `null` | The verdict-to-outcome mappings below assume null CIs can occur. |
| `diff`/`eval --mock` refused (exit 2) | Integrations must never offer a mock verdict. |

**Assumption:** the integrations target 0.6.0 or later. Building them on 0.5.3 would mean
re-solving problems that #123 already solves.

### Gaps that exist even on `release/v0.6.0` (prerequisite "P0")

1. **No CLI way to write the replay files.** The v0.6.0 workflow comment says to "commit the
   recorded trials", but neither `diff` nor `eval` has an output flag for trial outcomes. The demo
   replays were produced by `scripts/record_demo_replays.py`, which calls the private
   `cli._collect_trials`. Every replay-mode integration needs a supported recording path, for
   example `diff ... --save-trials-before B.json --save-trials-after A.json`, or a single
   `--save-trials DIR`.
2. **Replay files carry no provenance.** A bare list records nothing about the model, seed,
   agentgauge version, tasks-file hash or tool-schema hash that produced it. A CI gate that runs on
   committed replays therefore validates the statistics of *whatever was committed*, not the PR's
   actual server change. Proposal: a versioned wrapper of the form
   `{"format": 1, "provenance": {...}, "trials": [...]}`. The loader keeps accepting a bare list,
   so existing files and the demo still load. Integrations can then offer a **staleness check**:
   start the server (no model needed), hash its introspected tool schemas, and refuse the replay
   if the hashes differ.
3. **No public library API.** `_load_replay_trials` and `_collect_trials` are private. A pytest
   plugin should import from a public module (for example `agentgauge.replay`), not from `cli.py`.

P0 effort: **S (1–2 days)** (flag, wrapper with back-compatible loader, public functions, tests).
None of the four integrations is sound without it.

---

## 1. pytest plugin

### User value

**Who:** maintainers of Python MCP servers who already run pytest in CI. **Pain:** a description
or schema change goes out with no regression signal inside the test suite they already run. Today
they have to call the CLI separately and parse exit codes. **Assumption:** this group overlaps
heavily with the people who installed `agentgauge-harness`, because the package is Python and its
examples are Python servers. No usage data supports or refutes this.

### Extension points (confirmed)

- Packaging: pytest discovers installed plugins through the `pytest11` entry point:
  `[project.entry-points.pytest11] agentgauge = "agentgauge.pytest_plugin"` (writing_plugins page).
  Installed plugins **auto-load**. Users can turn one off with `-p no:agentgauge`, or turn off all
  auto-loading with `--disable-plugin-autoload` / `PYTEST_DISABLE_PLUGIN_AUTOLOAD` (pytest ≥ 8.4)
  (plugins page).
- Plugins provide hooks and fixtures, and should register their markers in `pytest_configure` via
  `config.addinivalue_line("markers", ...)` (writing_plugins page). `pytest_addoption(parser, ...)`
  with `parser.addoption(...)` adds CLI flags (writing_hook_functions page).
- Outcomes: `pytest.skip(reason)`, `pytest.xfail(reason)` (imperative; code after it does not
  run), and `pytest.mark.xfail(condition, *, reason, raises, run, strict)`. With `strict=True` an
  XPASS fails the suite. pytest 9.0 added `strict_xfail` as an alias of `xfail_strict` and a
  global `strict` ini option (skipping page; 9.0.0 changelog).
- Testing the plugin: the built-in `pytester` fixture, enabled with `pytest_plugins = ["pytester"]`
  (writing_plugins page). `pytest_terminal_summary` / `config.getoption`: **unverified** today.

### Proposed design

- **Fixture** `agentgauge_diff`: a factory that returns the `DiffResult` (verdict, delta, CI,
  decomposed rates). It takes `replay_before=` / `replay_after=`, or `before=` / `after=` /
  `tasks=` for a live run.
- **Marker** `@pytest.mark.agentgauge(...)` for the declarative form, plus the helper
  `assert_no_regression(result)`.
- **Verdict mapping.** Default: never turn an inconclusive result into a pass silently.

| Verdict / condition | Default pytest outcome | Rationale |
|---|---|---|
| `regression` | **fail** | It is the CLI's exit-1 case. |
| `improvement`, `no_change` | pass | Matches CLI exit 0. The message is attached to the report. |
| `insufficient_sensitivity` | **skip**, with the MDE message as the reason | Inconclusive is not a pass. `skip` is honest ("could not evaluate"), and `xfail` is not, because nothing was expected to fail. Configurable with `--agentgauge-inconclusive={skip,fail}`. |
| `ceiling` / `floor` | skip, with reason | The task set has no headroom or no signal. That is a finding about the tasks, not a pass. |
| audit BLOCKING finding, unreachable backend, stale replay (P0 check) | **error/fail** | Mirrors CLI exit 2. A broken measurement must not show up as a skip. |
| user-declared known regression | `pytest.mark.xfail(strict=True)` | This is the only legitimate use of xfail: an accepted regression whose fix should turn XPASS into a failure. |

- **Replay in CI:** the replay files are the cassettes. Tests point at committed
  `tests/agentgauge/replay_*.json`. CI runs with no model, keys or network. The P0 staleness check
  makes the test fail when the server's schemas changed but the replays were not re-recorded. A
  `--agentgauge-live` flag, off by default, allows a local re-record.
  **Assumption:** most users will not want live inference inside `pytest` runs, because of runtime
  and cost.

### Effort: **M (3–5 days) after P0**

`agentgauge/pytest_plugin.py` (hooks, marker, fixture, mapping; all imports lazy, so auto-loading
in every pytest session costs close to nothing); the `pytest11` entry point in `pyproject.toml`
(in this distribution, not a separate `pytest-agentgauge`: one release train, no version skew);
`tests/test_pytest_plugin.py` (`pytester`, one case per verdict row, over the demo replays and
synthetic replays); a README section.

### Maintenance cost

Low; no new hard dependency. The 9.0 strictness aliases show pytest's configuration surface still
moves, so CI should cover the oldest and newest supported pytest.

### Risks

- Auto-load side effects: an import-time failure in the plugin would break **unrelated** test
  suites in the same environment. Mitigation: lazy imports, plus a test that runs `pytest
  --collect-only` on an empty project with the plugin installed.
- Users may read skip as pass. Mitigation: the inconclusive option, and a terminal summary line
  counting skipped agentgauge verdicts. The hook signature is unverified (see above).

### What would prove it worked

- Every verdict row produces the documented outcome in `pytester` tests, and an empty-project
  collection is clean.
- An external sample repo (FastMCP-style server plus committed replays) passes in CI with no
  network. Changing a tool schema without re-recording makes the staleness check fail it.
- Adoption signal: only observable through public GitHub code search for `pytest.mark.agentgauge`.
  There is no baseline, and none is claimed.

---

## 2. GitHub Actions marketplace action (replay mode)

### User value

**Who:** MCP server maintainers who want a PR gate without copying the ~70-line workflow `init`
writes. **Pain:** the `main` template needs a live Ollama on a CPU runner. The v0.6.0 comment
documents a ~5.4 GB model pull and a 90-minute cap. Replay mode needs no model, no GPU and no
secrets. A versioned `uses: …@v1` also gives users fixes without re-scaffolding. **Assumption:**
Marketplace listing improves discoverability for people who never find the PyPI package. This is
unmeasured.

### Action type (confirmed)

| Type | Runners | Fit |
|---|---|---|
| Docker container | **Linux only** | It is slower (image build or pull), and it adds a Dockerfile to maintain. No benefit here. |
| JavaScript | Linux, Windows, macOS | It "should be pure JavaScript and not depend on other binaries". agentgauge is Python, so this would be a Node wrapper around a Python CLI: two runtimes and two dependency trees. |
| **Composite** | Linux, Windows, macOS | It bundles `run` / `uses` steps. It can `uses: actions/setup-python` and then `pip install agentgauge-harness==<pin>`. **Recommended.** |

Composite specifics (metadata-syntax page): `runs.using: 'composite'`. Every `run` step **must**
set `shell`. Inputs are read as `${{ inputs.<id> }}`, and composite actions do not get `INPUT_*`
env vars. Outputs need `outputs.<id>.value`, usually `${{ steps.<id>.outputs.<name> }}`, plus a
`description`. `branding` (icon and color) is optional.

### Proposed `action.yml` sketch

- **Inputs:** `replay-before`, `replay-after` (required); `threshold` (default `0.05`);
  `agentgauge-version` (pinned default, so a new release cannot change verdicts silently);
  `python-version`; `fail-on` (`regression` by default; `inconclusive` optional);
  `check-staleness` + `server-before` / `server-after` + `tasks` (optional, P0 provenance check);
  `lint-target` (optional; runs `agentgauge lint`, which needs only the server, not a model).
- **Steps:** setup-python, then a pinned pip install, then `agentgauge diff --replay-before …
  --replay-after … --json > diff.json`. The exit code is captured, not swallowed. A small inline
  Python step renders `diff.json` to a Markdown table and appends it to `$GITHUB_STEP_SUMMARY`.
  Values are written to `$GITHUB_OUTPUT`, and the step exits with the CLI's code.
- **Outputs:** `verdict`, `delta`, `ci-lo`, `ci-hi`, `exit-code`, `json-path`.
- **Annotations:** `::error title=agentgauge::…` on regression, `::warning` on inconclusive,
  ceiling or floor. Job summaries are GitHub-flavoured Markdown, max **1 MiB per step**, max 20 per
  job (workflow-commands page); a diff summary is a few KB.
- **Permissions:** `contents: read` only. The current template's PR comment moves to the job
  summary, which needs no `pull-requests: write`; a comment can stay as an opt-in input.

### Where the action lives

Marketplace requires a **public repo with a single `action.yml` at the root**. The repo should
contain only the action's files, the `name` must be unique, publishing needs 2FA and acceptance of
the Marketplace Developer Agreement, and publishing goes through a release with a version tag. So a
listed action means a **new repo** (for example `agentgauge-action`). An `action.yml` in a
subfolder of this repo works through `uses: owner/agentgauge/action@v1`, but it is not listed.
Versioning: semver release tags, plus a moving major tag `v1`. Consumers can pin a full commit SHA
(manage-custom-actions page). **Unverified:** whether a Marketplace name containing "agentgauge"
is free. Creating a new public repo is GG's call.

### Effort: **S–M (2–4 days) after P0 and 0.6.0**

`agentgauge-action/{action.yml, scripts/summary.py, README.md, LICENSE}`;
`.github/workflows/selftest.yml` (ubuntu/windows/macos matrix over the bundled demo replays plus a
synthetic regression pair that must fail); tags `v1.0.0` and `v1`; Marketplace listing (manual,
GG).

### Maintenance cost

Low to moderate. Each agentgauge release needs a pin bump in the action, and the self-test catches
verdict drift. Dependabot already runs for Actions in this repo, and the new repo would need the
same. Pinned upstream actions (`actions/setup-python`) need periodic bumps.

### Risks

- **Replay-gate theatre.** Without the P0 staleness check, a PR can change the server and keep old
  replays, and the gate stays green. This is the most important risk in the proposal. With the
  check off, the action must say in the summary that it verified recordings, not the change.
- The person who re-records the replays chooses the model and seed. The verdict then holds only for
  that model (see the judge-comparability notes in `CLAUDE.md`). The summary must print the
  recorded provenance (model, seed, version).
- Windows/macOS composite behaviour differs by `shell`. The self-test matrix covers it.

### What would prove it worked

- Self-test matrix green on three OSes. The regression fixture fails with exit 1 and an `::error`
  annotation. Action outputs equal the fields from `agentgauge diff --json` on the same files.
- The workflow file contains no `secrets.*` reference and no GPU or Ollama step.
- A stale-replay fixture fails when `check-staleness: true`.
- Adoption signal: the repo's "Used by" / dependents count. There is no baseline.

---

## 3. MLflow and Weights & Biases logging of verdicts

### User value

**Who:** teams that already track prompt or model experiments in MLflow or W&B and want
tool-description changes in the same place. **Pain:** verdicts live only in CI logs or terminal
output, with no history across runs or models. **Assumption:** this is a smaller group than 1–2,
and these users usually also have a CI gate. It complements those integrations rather than
replacing them.

### APIs (confirmed)

- **MLflow:** `mlflow.start_run(run_id=None, experiment_id=None, run_name=None, …, tags=…)`,
  `log_params(dict)`, `log_metrics(dict[str, float], step=None)`, `set_tags(dict)`,
  `log_dict(dict, artifact_file)` (JSON or YAML chosen by extension), `log_artifact(local_path)`,
  `active_run()` (thread-local), `set_tracking_uri(uri)`. Limits: keys up to 250 characters on
  every backend store. Param values are stringified, up to 6000 characters. Metrics are floats, and
  ±Infinity may be replaced depending on the store.
- **W&B:** `wandb.init(project=…, config=…, job_type=…, mode=…)`, where `mode` is one of
  `"online"`, `"offline"`, `"disabled"`, `"shared"`. In `"disabled"` mode, run methods become
  no-ops. `Run.log(data: dict, step=None, commit=None)` updates the summary. `Run.summary` is
  dict-like. `Run.log_artifact(artifact_or_path, name, type, aliases, tags)`. `wandb.Table` is
  mentioned for structured data. **Note:** `docs.wandb.ai/ref/...` now 301-redirects to
  `docs.coreweave.com/ref/...`. The docs host changed. That is a mild churn signal, not an API
  change. **Unverified:** the `WANDB_MODE` env var, which the page read did not mention.

### Proposed mapping

| agentgauge field | MLflow | W&B |
|---|---|---|
| model / provider / seed / trials / threshold / agentgauge version / tasks & schema hashes (P0) | `log_params` | `config` |
| `delta`, `ci_lo`, `ci_hi`, per-arm `selection_accuracy`, `argument_accuracy_given_correct_selection`, `joint_success_rate`, cost USD, duration | `log_metrics` (skip `None`: n=1 CIs are null on 0.6.0) | `run.log` / `summary` |
| `verdict` (string), `selection-only` label | `set_tags` | `summary["verdict"]` + `tags` |
| full `--json` payload, replay files | `log_dict("agentgauge/diff.json")`, `log_artifact` | `log_artifact(type="agentgauge-diff")` |

### Design

- Optional extras: `agentgauge-harness[mlflow]` and `agentgauge-harness[wandb]`. Neither SDK
  becomes a core dependency.
- A `--log-to mlflow|wandb` flag on `diff`/`eval`, plus a library function
  `agentgauge.tracking.log_diff(result, backend=…)`.
- **No-op when unavailable:** a missing extra or an unreachable tracking server produces one
  warning line, and the CLI's verdict and exit code stay unchanged (per CLAUDE.md rule 42: tracking
  failure never fails the run). W&B also gets `mode="disabled"` in tests.
- The verdict itself is never computed differently because a tracker is attached.

### Effort: **S–M (2–3 days for both)**

`agentgauge/tracking.py` (`Tracker` Protocol with `Mlflow`/`Wandb`/`Null` implementations); the
flag in `cli.py`; extras with `<NEXT_MAJOR` upper bounds in `pyproject.toml`;
`tests/test_tracking.py` (MLflow file-store URI in `tmp_path`, W&B disabled/offline, import-missing
path).

### Maintenance cost

Moderate. Both SDKs are large, fast-moving dependency trees. They add `pip-audit` surface, though
only for users who install the extras, and they should get extras-specific CI jobs. Upper bounds
mean periodic bump PRs.

### Risks

- Extras pulling transitive CVEs into the audit job. Mitigation: audit extras in a separate,
  non-blocking or separately-required job. Deciding which is GG's call.
- Logging a verdict string as a metric is lossy. Keep it as a tag.

### What would prove it worked

- Round-trip tests: log, then read back through each SDK's client, and the fields match the
  `--json` payload.
- With the extra uninstalled or the tracker unreachable, the CLI output and exit code are
  byte-identical to the run with no `--log-to`.

---

## 4. Inspect AI and promptfoo adapters

### 4a. Inspect AI

**Extension points (confirmed).** Model APIs (`ModelAPI` subclass and a `@modelapi(name=…)`
factory), components (tasks, solvers, scorers, tools), sandboxes, approvers, hooks and filesystems.
Packages register through `[project.entry-points.inspect_ai] <pkg> = "<pkg>._registry"`, and
components are referenced as `pkg/name`. MCP: `mcp_server_stdio()`, `mcp_server_http()`,
`mcp_server_sandbox()`, `mcp_server_sse()` (deprecated), `mcp_tools(server, tools=[…])`, and
`mcp_connection()`. They are used through `react(tools=[server])` or `use_tools()`. Scorers:
`@scorer(metrics=[accuracy(), stderr()])` wrapping `async def score(state: TaskState, target:
Target) -> Score`. `Score` has `value`, `answer`, `explanation`, and `metadata`. Logs:
`read_eval_log`, `read_eval_log_samples` (streaming), `.eval` (default) and `.json`. The hooks API
details were **not** documented on the page read and are **unverified**.

**Direction: Inspect → agentgauge (Inspect runs the trials, agentgauge computes the verdict).**
Inspect is a trial runner with many model providers and native MCP tools. agentgauge's value is
the constraint scoring and the paired verdict. So the adapter:

1. ships an Inspect **scorer** `agentgauge/constraint_scorer`. It reads the first tool call from
   `state.messages`, applies agentgauge's constraint scoring, and returns a `Score` with
   `metadata = {selected_tool, constraint_satisfaction, task_tool_name}`;
2. ships a **task factory** that turns an agentgauge tasks file into an Inspect dataset, with an
   MCP server wired through `mcp_server_stdio`;
3. ships a **converter**, `agentgauge from-inspect LOG.eval > replay.json`, built on
   `read_eval_log_samples`. Its output feeds `agentgauge diff --replay-*` unchanged.

A model-provider adapter (agentgauge's six adapters exposed as Inspect models, the other
direction) adds nothing, because Inspect already has providers. Not proposed.

**Unverified:** the exact `ChatMessageAssistant.tool_calls` field shape the scorer would read.
It was not read today and must be checked before building.

**Effort: L (6–10 days).** It covers `agentgauge/integrations/inspect/{_registry.py, scorer.py,
task.py, convert.py}`, an `[inspect]` extra, and tests over a recorded `.eval` fixture. The
`.eval` format is binary, so the fixture must be generated by a pinned Inspect version. It also
needs a parity study (below).

**Maintenance cost: high.** The search results listed `inspect-ai` releases up to `0.3.251`, so
the release cadence is very fast and the version is pre-1.0. The log schema, message types and MCP
helpers can move between patch releases. This is an observation from PyPI search-result titles,
not a documented policy.

**Risks:** Inspect's agent loop differs from agentgauge's two-prompt (select, then arguments)
runner. A verdict produced from Inspect trials is a different measurement, and its MDE and
false-alarm calibration (`reports/v2_2_*`) **do not transfer** until re-measured.

**Proof:** a parity run in which the same tasks and model go through both runners. Report selection
and joint-success agreement with CIs, and present the result honestly, whichever way it falls. The
converter round-trip is byte-stable on a fixture log.

### 4b. promptfoo

**Extension points (confirmed).** Python custom provider (`id: 'file://provider.py'`,
`call_api(prompt, options, context)` returning a dict with `output` or `error`, plus optional token
usage and cost). Python assertion (`type: python`, `value: file://x.py[:fn]`, `get_assert(output,
context)` returning `bool`, `float`, or a `GradingResult` with `pass`/`score`/`reason`). An `mcp`
provider that calls MCP tools directly from JSON `{tool, args}` prompts. Chat providers with MCP
enabled record executed calls in `metadata.toolCalls` (`id`, `name`, `input`, `output`,
`is_error`). Built-in tool assertions: `is-valid-function-call`, `tool-call-f1` (names only),
and `trajectory:tool-used` / `tool-args-match` / `tool-sequence` / `step-count`, which need tracing.
Exports: `--output` to JSON, JSONL, CSV, JUnit XML and others.

**Direction: promptfoo → agentgauge (converter), plus an optional per-case assertion.**
promptfoo assertions are per output, but agentgauge's verdict compares two arms as distributions,
so the verdict cannot be a promptfoo assertion. The useful shape is:

1. a Python assertion `agentgauge_constraints.py:get_assert` that scores one case's tool-call
   arguments against agentgauge constraints and returns `GradingResult` with `score =
   constraint_satisfaction`. This adds argument checking that `tool-call-f1` explicitly does not do;
2. `agentgauge from-promptfoo before.jsonl after.jsonl` converts two promptfoo runs (one per arm)
   into replay files for `diff`.

**Effort: M (4–6 days).** `integrations/promptfoo/{agentgauge_constraints.py, convert.py}`, an
example `promptfooconfig.yaml`, and fixture exports. No new Python dependency, because promptfoo is
a separate Node tool the user installs.

**Maintenance cost: high.** The outputs page gives **no stability guarantee for the export
schema**. Its examples are internally inconsistent (`pass` in the JSON example, `success` in
JSONL), and it advises checking your actual file before relying on a path. The converter would
break silently on schema drift unless pinned and tested against a recorded export per supported
promptfoo version. CI would need Node to regenerate fixtures, or it would freeze them.

**Risks:** the same measurement-transfer issue as Inspect, plus the silent-schema-drift risk
above. The `metadata.toolCalls` path is documented for the MCP integration of chat providers. Its
presence in every export format is **unverified**.

**Proof:** converter round-trip tests on recorded exports from a pinned promptfoo version. The
assertion's score matches agentgauge's own scorer on the same tool call for every constraint kind.
Then a parity run, as for Inspect.

**User value (4a/4b).** Evaluation engineers on Inspect or promptfoo who want the verdict without
a second runner. **Assumption:** they are the furthest from today's entry point and the most able
to script around a missing adapter once P0's documented replay format exists. That format is the
cheapest "adapter".

---

## 5. Recommended order

Criteria, applied in order: customer value, then reach, then effort, then maintenance.

| Rank | Item | Value | Reach | Effort | Maintenance | One-line reason |
|---|---|---|---|---|---|---|
| 0 | **P0: `--save-trials`, provenance wrapper, public API** | prerequisite | all | S (1–2 d) | low | Without it, every replay-mode integration either cannot be fed or gates stale recordings. |
| **1** | **GitHub Action (composite, replay mode)** | high | high | S–M (2–4 d) | low–moderate | It turns the existing `init` workflow into a versioned one-line PR gate with no model, GPU or secrets, at the point where description changes are reviewed. |
| 2 | pytest plugin | high | medium–high | M (3–5 d) | low | The same gate inside the test suite Python MCP maintainers already run. Slightly more design surface (outcome mapping, auto-load safety). |
| 3 | MLflow / W&B logging | medium | medium | S–M (2–3 d) | moderate | Cheap and contained behind extras, but it records verdicts rather than preventing regressions, and it brings heavy optional dependency trees. |
| 4 | Inspect AI adapter | medium | low–medium | L (6–10 d) | high | It is a real fit (native MCP tools, scorer API), but it needs a parity study before any verdict is trustworthy, and the upstream moves fast. |
| 5 | promptfoo adapter | low–medium | low–medium | M (4–6 d) | high | The verdict cannot be a promptfoo assertion, and the export schema has no documented stability. |

**Why the Action beats pytest for first place:** both serve the same user and the same pain. The
Action is reached by everyone who runs `agentgauge init`, needs no change to the user's test code,
and has the cheaper failure mode, because a broken action fails only its own job, while a broken
auto-loaded pytest plugin can break unrelated suites. pytest is a close second and shares most of
its code (P0's public API) with the Action. **Assumption:** "reach" here is a judgment about where
MCP maintainers already look (PR checks), not a measured figure.

**Top-ranked pick: the GitHub Actions composite action in replay mode, built after P0 and on top
of the 0.6.0 surface (#123).** Its staleness check must be on whenever the server paths are
available.

**Decisions this leaves for GG:** whether P0 lands in 0.6.x or 0.7.0; creating the public
`agentgauge-action` repo and the Marketplace listing (2FA and the Developer Agreement are on the
owning account); and whether optional-extra CVEs block CI.

---

## Sources

All read on 2026-10-23 through a summarizing fetch tool. "Partial" means the page was truncated
before every section of interest was read.

pytest
- https://docs.pytest.org/en/stable/how-to/writing_plugins.html
- https://docs.pytest.org/en/stable/how-to/writing_hook_functions.html
- https://docs.pytest.org/en/stable/how-to/plugins.html
- https://docs.pytest.org/en/stable/how-to/skipping.html
- https://docs.pytest.org/en/stable/reference/reference.html (partial: `xfail` `strict` only)
- https://docs.pytest.org/en/stable/changelog.html (9.0.0 entries for #13823)

GitHub Actions
- https://docs.github.com/en/actions/sharing-automations/creating-actions/about-custom-actions
- https://docs.github.com/en/actions/reference/workflows-and-actions/metadata-syntax
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands
- https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace
- https://docs.github.com/en/actions/how-tos/create-and-publish-actions/manage-custom-actions

MLflow / W&B
- https://mlflow.org/docs/latest/python_api/mlflow.html (read in two parts)
- https://docs.coreweave.com/ref/python/functions/init (redirect target of
  https://docs.wandb.ai/ref/python/functions/init)
- https://docs.coreweave.com/ref/python/experiments/run

Inspect AI
- https://inspect.aisi.org.uk/extensions.html
- https://inspect.aisi.org.uk/extensions-components.html
- https://inspect.aisi.org.uk/extensions-model-api.html
- https://inspect.aisi.org.uk/tools.html
- https://inspect.aisi.org.uk/tools-mcp.html
- https://inspect.aisi.org.uk/scorers.html
- https://inspect.aisi.org.uk/custom-scorers.html
- https://inspect.aisi.org.uk/eval-logs.html

promptfoo
- https://www.promptfoo.dev/docs/providers/python/
- https://www.promptfoo.dev/docs/providers/mcp/
- https://www.promptfoo.dev/docs/configuration/expected-outputs/python/
- https://www.promptfoo.dev/docs/configuration/expected-outputs/deterministic/
- https://www.promptfoo.dev/docs/configuration/outputs/

### Not verified (re-check before building)

pytest `pytest_terminal_summary` / `config.getoption`; `WANDB_MODE`; the full `mlflow.start_run`
signature (truncated); the Inspect hooks API and the `ChatMessageAssistant.tool_calls` shape;
promptfoo `metadata.toolCalls` in exports, and export-schema stability; Inspect release cadence
(from PyPI search-result titles only); Marketplace name availability. Codebase claims (flags, exit
codes, JSON fields, replay format, the missing save-trials flag) come from reading `cli.py` and
`harness.py` on `origin/main` and `origin/release/v0.6.0`, not from running the CLI.

"""Standing pre-report measurement-validity gate (AgentGauge v2.4, Task 2; extended v0.5 Wave 1).

Nine measurement artifacts have been found during this project's own development
(task/answer leakage, a tool-name-alone selection ceiling, a zero-vector
embedding degeneracy, a self-descriptive-name confound, a test-subset-vs-full-
catalog mismatch, a PRNG index-saturation bug, a pre/post-mutation
scoring-key mismatch, hallucinated fixture-authoring facts, and a benchmark-
construction diff-size confound -- see `reports/v2_3_task1_advisory_audit.md`,
`reports/v2_4_task1_blast_radius_audit.md`, `reports/v2_5_task2_fixture_validation.md`
for the seventh and eighth, and `reports/v0_5_attribution_benchmark.md` for the
ninth). Eight of the nine were found by hand, after the fact, on results that had
already been reported. This module encodes each artifact CLASS as a standing,
automated check that runs BEFORE any effect size is emitted, so the same
class of bug blocks the report instead of quietly shipping in it.

Wired into `agentgauge diff`/`agentgauge eval` (`agentgauge/cli.py`): a
BLOCKING finding here stops the result from being reported as a measurement.
WARN findings are surfaced but do not block -- they flag a real limitation
(low power, an asymmetric catalog) that doesn't make the number wrong, only
weaker.

`check_benchmark_construction_diffsize_bias` (artifact #9) is wired into
`run_audit` via its optional `benchmark_cases` parameter (v0.5 Wave 1 Task 5a):
when a caller passes a sequence of injected-culprit benchmark cases (duck-typed
to `agentgauge.attribution_benchmark.BenchmarkCase`'s `.diff_chars`/`.true_culprit`
shape, per `_case_diffsize_fractional_rank`'s docstring), `run_audit` additionally
runs the diff-size-bias check and folds its findings in. `benchmark_cases` defaults
to `None` so every existing `BlindTask`/tool-based caller (`agentgauge/cli.py`'s
`diff`/`eval` commands) is unaffected. `scripts/attribution_benchmark_report.py`
calls `run_audit(tasks=[], benchmark_cases=<generated cases>)` after generating a
benchmark and before reporting any accuracy number, refusing to print the table on
a BLOCKING finding -- the same gate pattern `cli.py` already uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentgauge.constraints import BlindTask
from agentgauge.harness import DecomposedRate, TrialOutcome


@dataclass
class AuditFinding:
    check: str
    severity: str  # "block" | "warn"
    detail: str


@dataclass
class AuditReport:
    findings: list[AuditFinding] = field(default_factory=list)

    @property
    def blocking(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "block"]

    @property
    def warnings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "warn"]

    @property
    def passed(self) -> bool:
        """True if no BLOCKING finding exists -- a measurement may be reported."""
        return not self.blocking


def _tool_props(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or {}
    return schema.get("properties", {}) or {}


def check_task_leakage(tasks: list[BlindTask]) -> list[AuditFinding]:
    """Artifact class: task/answer leakage. A task whose description contains
    its own gold tool name (or a schema property name distinctive enough to
    name the tool) lets an agent "solve" the task from the task text alone,
    regardless of description/schema quality -- the exact confound the
    predictive-validity study's original task-leakage artifact was."""
    findings = []
    for t in tasks:
        if t.tool_name and t.tool_name.lower() in t.description.lower():
            findings.append(
                AuditFinding(
                    check="task_leakage",
                    severity="block",
                    detail=f"task for {t.tool_name!r} contains its own gold tool name in the "
                    f"description text: {t.description!r}",
                )
            )
    return findings


def check_scoring_reference_consistency(
    tasks: list[BlindTask], schema_by_tool: dict[str, dict[str, Any]], *, variant_label: str
) -> list[AuditFinding]:
    """Artifact #7 class: a gold constraint's `param` name must exist in the
    schema of the variant it is actually being scored against. If a schema
    property was renamed (or a task's constraints were authored against a
    different variant than the one an agent actually saw), every constraint
    on the missing name silently scores every response as a failure --
    `evals/fixtures/predictive_validity/constraints.py`'s
    `constraint_satisfaction` (and the identical pattern in the shipped
    `agentgauge.constraints.constraint_satisfaction`) has no way to detect
    this on its own; it just returns 0.0 for a missing key. This check
    validates the reference BEFORE scoring, not after."""
    findings = []
    for t in tasks:
        props = schema_by_tool.get(t.tool_name)
        if props is None:
            continue  # a different check (empty/unknown tool) covers this
        for c in t.constraints:
            if c.param not in props:
                findings.append(
                    AuditFinding(
                        check="scoring_reference_consistency",
                        severity="block",
                        detail=(
                            f"[{variant_label}] task {t.tool_name!r}'s constraint references "
                            f"parameter {c.param!r}, which is not a property of {t.tool_name!r} "
                            f"in the {variant_label} variant's actual schema ({sorted(props)}) -- "
                            "every response would silently score as a failure regardless of "
                            "correctness (the artifact #7 class)"
                        ),
                    )
                )
    return findings


def check_enum_schema_fidelity(
    tasks: list[BlindTask], schema_by_tool: dict[str, dict[str, Any]], *, variant_label: str
) -> list[AuditFinding]:
    """Artifact #8 class: a task's `enum` constraint asserts a specific
    `gold_value` as THE correct answer, but that assertion's only source is
    whatever the fixture's author (human or LLM) believed about the real
    domain -- there is no way for this tool, or the agent under test, to
    verify it against anything, because `agentgauge`'s own enum-constrained
    tool schemas are deliberately type-only (`{"type": "string"}`, no
    `"enum": [...]` array) to test whether an agent can infer valid values
    from a description alone. v2.5 Task 2 found exactly this: 3 of 10
    real-API fixtures (GitHub Issues, Stripe Payments, Kubernetes Workloads)
    had a `gold_value`/pattern that didn't match the real API, authored from
    an LLM's memory of the domain rather than a fetched schema, and nothing
    in the schema itself could have caught it. This check does not (and, run
    offline, cannot) verify the gold_value against any external ground
    truth -- it only surfaces that this class of assertion is unverifiable
    from the schema, as a standing reminder to source-check it by hand (a
    live official API doc/OpenAPI spec, or calibrated multi-model consensus
    per `reports/v2_5_task2_fixture_validation.md` 2b) before trusting it."""
    findings = []
    seen: set[tuple[str, str]] = set()
    for t in tasks:
        props = schema_by_tool.get(t.tool_name)
        if props is None:
            continue
        for c in t.constraints:
            if c.kind != "enum":
                continue
            key = (t.tool_name, c.param)
            if key in seen:
                continue
            prop_schema = props.get(c.param) or {}
            if "enum" not in prop_schema:
                seen.add(key)
                findings.append(
                    AuditFinding(
                        check="enum_schema_fidelity",
                        severity="warn",
                        detail=(
                            f"[{variant_label}] {t.tool_name!r}'s {c.param!r} carries an enum "
                            f"constraint (gold_value={c.gold_value!r}) but the schema declares "
                            f"no 'enum' array for it -- this gold_value cannot be verified "
                            "against the schema and depends entirely on the constraint "
                            "author's own knowledge of the real domain (the artifact #8 class); "
                            "confirm it against a live official source before trusting it"
                        ),
                    )
                )
    return findings


def check_ceiling_floor(
    rate: DecomposedRate, *, variant_label: str, margin: float = 0.05
) -> list[AuditFinding]:
    """A joint success rate at (or within `margin` of) 0.0 or 1.0 leaves
    little room to show a before/after effect -- not wrong, but underpowered
    by construction. margin=0.05 is calibrated to the real historical case
    this check targets (the RW1 family's measured 0.9524-1.0 spread across
    every description-quality arm, `reports/predictive_validity_study.md`) --
    a tighter margin (e.g. 0.02) would miss that exact case. WARN, not BLOCK:
    a genuinely near-perfect or broken server is a real result, just one this
    comparison can't move much."""
    if rate.n_trials == 0:
        return []
    r = rate.joint_success_rate
    if r <= margin or r >= 1.0 - margin:
        which = "floor" if r <= margin else "ceiling"
        return [
            AuditFinding(
                check="ceiling_floor",
                severity="warn",
                detail=(
                    f"[{variant_label}] joint success rate {r:.3f} is at the {which} "
                    f"(n={rate.n_trials}) -- little to no room for a before/after delta to show up"
                ),
            )
        ]
    return []


def check_degenerate_metrics(
    trials: list[TrialOutcome], *, variant_label: str
) -> list[AuditFinding]:
    """Zero variance across every trial in a corpus (not just one tool/task)
    is a stronger signal than ceiling/floor on a single rate -- it suggests
    the scoring function itself is constant (e.g. always returning the same
    value regardless of input), not that the server happens to be uniformly
    good or bad. BLOCK: a metric that cannot vary cannot measure anything."""
    if len(trials) < 2:
        return []
    values = {t.joint_success for t in trials}
    if len(values) == 1:
        return [
            AuditFinding(
                check="degenerate_metrics",
                severity="block",
                detail=(
                    f"[{variant_label}] every one of {len(trials)} trials scored exactly "
                    f"{next(iter(values))} -- the metric shows zero variance across the whole "
                    "corpus, which cannot distinguish any input from any other"
                ),
            )
        ]
    return []


def check_empty_tasks(tasks: list[BlindTask]) -> list[AuditFinding]:
    """Empty task text makes whatever it touches meaningless to score."""
    return [
        AuditFinding(
            check="empty_input",
            severity="block",
            detail=f"task for {task.tool_name!r} has an empty description",
        )
        for task in tasks
        if not (task.description or "").strip()
    ]


def check_empty_schema(
    tools: list[Any], tasks: list[BlindTask], *, variant_label: str
) -> list[AuditFinding]:
    """Empty tool descriptions or empty schemas make whatever they touch
    meaningless to score -- the general class the old v1 zero-vector-
    embedding degeneracy was one specific instance of (an empty description
    embeds to an all-zero vector, which is then "similar" to nothing and
    everything). Only checks tools that are actually targeted by a task, so
    an unrelated sparse tool elsewhere in the catalog doesn't fire this."""
    findings = []
    by_name = {getattr(t, "name", None): t for t in tools}
    targeted = {task.tool_name for task in tasks}
    for name in targeted:
        tool = by_name.get(name)
        if tool is None:
            continue
        if not (getattr(tool, "description", None) or "").strip():
            findings.append(
                AuditFinding(
                    check="empty_input",
                    severity="warn",
                    detail=f"[{variant_label}] tool {name!r} has an empty description in its schema",
                )
            )
        if not _tool_props(tool):
            findings.append(
                AuditFinding(
                    check="empty_input",
                    severity="warn",
                    detail=f"[{variant_label}] tool {name!r} has no declared input properties",
                )
            )
    return findings


def check_catalog_subset_mismatch(
    before_tools: list[Any], after_tools: list[Any], *, ratio_threshold: float = 0.5
) -> list[AuditFinding]:
    """A before/after comparison where one side has a very different tool
    COUNT than the other suggests a subset was compared against a full
    catalog by mistake (the T18 subset-vs-catalog artifact) -- selection
    accuracy measured against a small friendly subset is not comparable to
    the same measurement against the full, more confusable catalog. WARN:
    a genuine tool-count change (adding/removing tools) is a real, valid
    thing to diff; this only flags a large asymmetry for a human to check."""
    nb, na = len(before_tools), len(after_tools)
    if nb == 0 or na == 0:
        return []
    smaller, larger = min(nb, na), max(nb, na)
    if smaller / larger < ratio_threshold:
        return [
            AuditFinding(
                check="catalog_subset_mismatch",
                severity="warn",
                detail=(
                    f"before has {nb} tools, after has {na} -- a >{int((1 - ratio_threshold) * 100)}% "
                    "size asymmetry; confirm this is an intentional catalog change, not a "
                    "subset accidentally compared against the full catalog"
                ),
            )
        ]
    return []


def _case_diffsize_fractional_rank(culprit_diff: int, decoy_diffs: list[int]) -> float | None:
    """Independent re-implementation of `agentgauge.attribution_benchmark.
    fractional_rank_from_diffs` (0=biggest/1=smallest, ties averaged; `None` if there are no
    decoys to rank against). Deliberately duplicated rather than imported -- see this module's
    docstring: a generic construction-validity gate should not import a specific benchmark
    generator module, so any generator producing case-like objects (`.diff_chars`,
    `.true_culprit`) can be checked without agentgauge.audit depending on
    agentgauge.attribution_benchmark's existence or internal shape beyond that minimal contract."""
    all_diffs = [culprit_diff, *decoy_diffs]
    n = len(all_diffs)
    if n <= 1:
        return None
    sorted_desc = sorted(all_diffs, reverse=True)
    positions = [i for i, v in enumerate(sorted_desc) if v == culprit_diff]
    avg_pos = sum(positions) / len(positions)
    return avg_pos / (n - 1)


def check_benchmark_construction_diffsize_bias(
    cases: list[Any],
    *,
    min_cases: int = 20,
    rank_deviation_threshold: float = 0.15,
) -> list[AuditFinding]:
    """Artifact #9 class (found and fixed, v0.5 Wave 1: see
    `reports/v0_5_attribution_benchmark.md` and `agentgauge.attribution_benchmark`'s module
    docstring "Measurement artifact #9" section): an injected-culprit benchmark generator can
    satisfy simple edge-condition guards (the culprit is not ALWAYS positioned first; the culprit
    is not ALWAYS the single largest-diff tool) while still having a real, systematic
    DISTRIBUTIONAL correlation between a cheap structural feature (here, textual diff size) and
    culprit-vs-decoy role -- letting a zero-probe heuristic baseline win or lose by construction
    rather than by real localization signal. `agentgauge.attribution_benchmark`'s original
    generator had exactly this bug: the culprit's fixed-length defect sentence was smaller than
    2 of 3 decoy tiers by construction, giving `baseline_largest_textual_diff` a below-random 4%
    top-1 accuracy that looked like a real (if surprising) measurement but was actually a
    construction artifact.

    `cases`: any sequence of objects exposing `.diff_chars: dict[str, int]` (tool name -> textual
    diff size, must include the true culprit's own entry) and `.true_culprit: str` -- duck-typed
    to `agentgauge.attribution_benchmark.BenchmarkCase`'s shape without importing that module (see
    `_case_diffsize_fractional_rank`'s docstring). Cases with fewer than 2 diff_chars entries
    (no decoys to rank against) are skipped.

    Statistic: mean fractional rank of the true culprit's diff size among itself + its case's
    decoys (0=biggest, 1=smallest). Under a role-independent generating process this has
    expectation exactly 0.5; `rank_deviation_threshold` (default 0.15, i.e. a [0.35, 0.65] pass
    band) is calibrated to the real measured pre-fix (~0.66-0.73) vs post-fix (~0.55-0.61)
    regimes in `agentgauge.attribution_benchmark` -- wide enough to absorb ordinary sampling noise
    at realistic benchmark sizes, narrow enough to decisively reject the pre-fix bias. BLOCK: this
    is exactly the class of bias that made a baseline's reported accuracy number untrustworthy
    (not just weaker) in this project's own history, so it fails closed like the other
    construction-validity BLOCK checks (`check_scoring_reference_consistency`,
    `check_degenerate_metrics`), not WARN.

    Returns `[]` (not enough data to assess, not a pass) if fewer than `min_cases` cases have at
    least one decoy to rank the culprit against."""
    ranks: list[float] = []
    for case in cases:
        diff_chars: dict[str, int] = getattr(case, "diff_chars", {}) or {}
        true_culprit = getattr(case, "true_culprit", None)
        if true_culprit is None or true_culprit not in diff_chars:
            continue
        culprit_diff = diff_chars[true_culprit]
        decoy_diffs = [v for k, v in diff_chars.items() if k != true_culprit]
        rank = _case_diffsize_fractional_rank(culprit_diff, decoy_diffs)
        if rank is not None:
            ranks.append(rank)

    if len(ranks) < min_cases:
        return []

    mean_rank = sum(ranks) / len(ranks)
    if abs(mean_rank - 0.5) > rank_deviation_threshold:
        return [
            AuditFinding(
                check="benchmark_construction_diffsize_bias",
                severity="block",
                detail=(
                    f"mean culprit diff-size fractional rank {mean_rank:.4f} over {len(ranks)} "
                    f"cases is outside the [{0.5 - rank_deviation_threshold:.2f}, "
                    f"{0.5 + rank_deviation_threshold:.2f}] band around the 0.5 null -- the "
                    "culprit's textual diff size is systematically correlated with its role "
                    "(the artifact #9 class): a diff-size-based heuristic would win or lose by "
                    "construction, not by real localization signal"
                ),
            )
        ]
    return []


def run_audit(
    tasks: list[BlindTask],
    *,
    before_tools: list[Any] | None = None,
    after_tools: list[Any] | None = None,
    before_trials: list[TrialOutcome] | None = None,
    after_trials: list[TrialOutcome] | None = None,
    benchmark_cases: list[Any] | None = None,
) -> AuditReport:
    """Run every check applicable given what's available. Called from
    `agentgauge diff`/`agentgauge eval` before any effect size is printed, and from
    `scripts/attribution_benchmark_report.py` before reporting benchmark accuracy.

    `benchmark_cases`, if given, is any sequence of injected-culprit benchmark cases
    (duck-typed to `agentgauge.attribution_benchmark.BenchmarkCase`'s `.diff_chars`/
    `.true_culprit` shape) and triggers `check_benchmark_construction_diffsize_bias`
    in addition to whatever else is computed. It is fine -- expected -- for `tasks`
    to be `[]` and `before_tools`/`after_tools`/`before_trials`/`after_trials` to be
    `None` when `run_audit` is called purely for a benchmark-case audit: every other
    check here already no-ops on an empty/`None` input."""
    findings: list[AuditFinding] = []
    findings += check_task_leakage(tasks)
    findings += check_empty_tasks(tasks)

    for label, tools in (("before", before_tools), ("after", after_tools)):
        if tools is None:
            continue
        schema_by_tool: dict[str, dict[str, Any]] = {
            name: _tool_props(t) for t in tools if (name := getattr(t, "name", None)) is not None
        }
        findings += check_scoring_reference_consistency(tasks, schema_by_tool, variant_label=label)
        findings += check_empty_schema(tools, tasks, variant_label=label)
        findings += check_enum_schema_fidelity(tasks, schema_by_tool, variant_label=label)

    if before_tools is not None and after_tools is not None:
        findings += check_catalog_subset_mismatch(before_tools, after_tools)

    for label, trials in (("before", before_trials), ("after", after_trials)):
        if not trials:
            continue
        findings += check_ceiling_floor(DecomposedRate.from_trials(trials), variant_label=label)
        findings += check_degenerate_metrics(trials, variant_label=label)

    if benchmark_cases is not None:
        findings += check_benchmark_construction_diffsize_bias(benchmark_cases)

    return AuditReport(findings=findings)

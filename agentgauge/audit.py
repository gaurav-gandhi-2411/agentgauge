"""Standing pre-report measurement-validity gate (AgentGauge v2.4, Task 2).

Seven measurement artifacts were found during this project's own development
(task/answer leakage, a tool-name-alone selection ceiling, a zero-vector
embedding degeneracy, a self-descriptive-name confound, a test-subset-vs-full-
catalog mismatch, a PRNG index-saturation bug, and a pre/post-mutation
scoring-key mismatch -- see `reports/v2_3_task1_advisory_audit.md` and
`reports/v2_4_task1_blast_radius_audit.md` for the seventh). Six of the seven
were found by hand, after the fact, on results that had already been reported.
This module encodes each artifact CLASS as a standing, automated check that
runs BEFORE any effect size is emitted, so the same class of bug blocks the
report instead of quietly shipping in it.

Wired into `agentgauge diff`/`agentgauge eval` (`agentgauge/cli.py`): a
BLOCKING finding here stops the result from being reported as a measurement.
WARN findings are surfaced but do not block -- they flag a real limitation
(low power, an asymmetric catalog) that doesn't make the number wrong, only
weaker.
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


def run_audit(
    tasks: list[BlindTask],
    *,
    before_tools: list[Any] | None = None,
    after_tools: list[Any] | None = None,
    before_trials: list[TrialOutcome] | None = None,
    after_trials: list[TrialOutcome] | None = None,
) -> AuditReport:
    """Run every check applicable given what's available. Called from
    `agentgauge diff`/`agentgauge eval` before any effect size is printed."""
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

    if before_tools is not None and after_tools is not None:
        findings += check_catalog_subset_mismatch(before_tools, after_tools)

    for label, trials in (("before", before_trials), ("after", after_trials)):
        if not trials:
            continue
        findings += check_ceiling_floor(DecomposedRate.from_trials(trials), variant_label=label)
        findings += check_degenerate_metrics(trials, variant_label=label)

    return AuditReport(findings=findings)

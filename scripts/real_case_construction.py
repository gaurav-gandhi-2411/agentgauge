"""Real, deterministic injected-culprit case construction for the real-agent attribution
validation pilot (v0.5 Wave 1 -- see `reports/v0_5_real_agent_validation.md`).

Unlike `agentgauge.attribution_benchmark.generate_benchmark` (randomly generated, seed-driven,
50+ synthetic cases per run), this module builds a SMALL, FIXED, hand-scripted set of real
cases: one real example MCP server file (`examples/*_fixed.py`, already shipped in this repo,
with real, well-written tool descriptions) per case, with the real, causally-validated
`type_enum_contradiction` defect (reused via import from `agentgauge.attribution_benchmark`,
not reimplemented a third time) injected into exactly one tool (the true culprit), plus benign
paraphrase decoy edits (also reused from `agentgauge.attribution_benchmark`'s tier suffixes) on
the server's other tools, at varying diff-size tiers per the task's instruction to vary decoy
size "at least a little" so this isn't trivially gameable by a largest-diff heuristic.

Real, anti-tautology tasks (`evals/fixtures/v2_4_corpus/*_fixture.py` -- already-shipped,
hand-authored `Task` lists whose descriptions never leak the gold tool's name or its
enum/format answer, exactly the property a REAL live-agent selection-accuracy measurement
needs) are reused unchanged as the blind task set for each case.

This module performs NO live LLM calls -- it only introspects the real (but non-LLM) MCP server
processes via stdio to extract their real tool catalogs, then mutates them deterministically.
`tests/test_real_case_construction.py` mocks `connect_stdio` (matching every other test file in
this repo's convention -- see e.g. `tests/test_cli.py`) so this module's tests stay fully
offline/subprocess-free too.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentgauge.attribution_benchmark import (
    _DECOY_TIER_SUFFIXES,
    _inject_benign_decoy,
    _inject_type_enum_contradiction,
)
from agentgauge.client import cleanup_connection, connect_stdio
from agentgauge.constraints import BlindTask
from agentgauge.scorer import _levenshtein
from agentgauge.tasks import Task
from scripts.real_probe import RealAttributionCase

REPO_ROOT = Path(__file__).resolve().parent.parent


async def introspect_catalog(server_path: str | Path) -> list[dict[str, Any]]:
    """Connect to a real MCP server script over stdio (subprocess), introspect its tool
    catalog, disconnect. Returns plain dicts (name/description/inputSchema) -- the same
    catalog-dict convention `agentgauge.attribution_benchmark.BenchmarkCase` uses. No LLM call
    is made anywhere in this function; this is schema introspection only, identical in kind to
    `agentgauge.cli._introspect_tools`, reimplemented locally here rather than importing a
    private CLI helper across module boundaries."""
    client, ctx = await connect_stdio(sys.executable, [str(server_path)])
    try:
        info = await client.introspect()
        return [
            {"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema or {}}
            for t in info.tools
        ]
    finally:
        await cleanup_connection(ctx)


def select_blind_tasks(
    fixture_tasks: list[Task], tool_names: list[str], n_per_tool: int
) -> list[BlindTask]:
    """Pick the first `n_per_tool` real, anti-tautology tasks per tool (in fixture order) from
    an already-shipped `evals/fixtures/v2_4_corpus/*_fixture.py` task list, converted to
    `BlindTask` (no constraints attached -- this pilot only scores tool-selection accuracy, per
    the task's explicit instruction not to wire up an argument-correctness judge)."""
    picked: list[BlindTask] = []
    for name in tool_names:
        matching = [t for t in fixture_tasks if t.tool_name == name][:n_per_tool]
        picked.extend(BlindTask(tool_name=t.tool_name, description=t.description) for t in matching)
    return picked


def build_real_case(
    case_id: str,
    server_name: str,
    clean_catalog: list[dict[str, Any]],
    culprit: str,
    decoy_tiers: dict[str, str],
    blind_tasks: list[BlindTask],
) -> RealAttributionCase:
    """Deterministically build one `RealAttributionCase`: inject the real
    `type_enum_contradiction` defect (via `agentgauge.attribution_benchmark
    ._inject_type_enum_contradiction`, imported unchanged, not duplicated) into `culprit`'s
    description, and a benign paraphrase decoy (`_inject_benign_decoy`, same tier vocabulary
    the synthetic benchmark uses: 'small'/'medium'/'large') into each tool named in
    `decoy_tiers`. Unlike `agentgauge.attribution_benchmark.generate_benchmark`, there is no RNG
    anywhere here -- `culprit` and `decoy_tiers` are explicit caller-supplied choices, disclosed
    in `reports/v0_5_real_agent_validation.md` rather than drawn from a seed, since this is a
    small, hand-scripted real pilot, not a randomized benchmark generator.

    `changed_tools` is `[culprit, *decoy_tiers.keys()]` -- every tool named in `decoy_tiers` plus
    the culprit; any tool in `clean_catalog` not named here is left byte-identical in both arms
    (present in the case's full catalog, per `RealAttributionCase`'s convention for
    `baseline_most_lint_violations`'s sibling-aware linting, but not part of the localization
    problem itself).
    """
    culprit_tool = next((t for t in clean_catalog if t["name"] == culprit), None)
    if culprit_tool is None:
        raise ValueError(f"culprit tool {culprit!r} not found in clean_catalog")
    # A medium-tier camouflage suffix (matching the synthetic benchmark's own default choice for
    # a case with no further diff-size-decorrelation requirement -- this pilot's n is too small
    # for a distributional confound-guard check to mean anything, see the report's disclosure).
    mutated_culprit = _inject_type_enum_contradiction(
        culprit_tool, camouflage_suffix=_DECOY_TIER_SUFFIXES["medium"]
    )
    if mutated_culprit is None:
        raise ValueError(
            f"culprit tool {culprit!r} has no string-typed schema property eligible for the "
            "type_enum_contradiction mutation"
        )

    after_tools: list[dict[str, Any]] = []
    diff_chars: dict[str, int] = {}
    for t in clean_catalog:
        if t["name"] == culprit:
            after_tools.append(mutated_culprit)
            diff_chars[t["name"]] = _levenshtein(t["description"] or "", mutated_culprit["description"])
        elif t["name"] in decoy_tiers:
            mutated = _inject_benign_decoy(t, decoy_tiers[t["name"]])
            after_tools.append(mutated)
            diff_chars[t["name"]] = _levenshtein(t["description"] or "", mutated["description"])
        else:
            after_tools.append(json.loads(json.dumps(t)))

    changed_tools = [culprit, *decoy_tiers.keys()]
    return RealAttributionCase(
        case_id=case_id,
        server_name=server_name,
        all_tools_before=json.loads(json.dumps(clean_catalog)),
        all_tools_after=after_tools,
        changed_tools=changed_tools,
        true_culprit=culprit,
        blind_tasks=blind_tasks,
        diff_chars=diff_chars,
    )


@dataclass(frozen=True)
class RealCaseSpec:
    """One real case's construction parameters -- disclosed here as data, not buried in
    control flow, so `reports/v0_5_real_agent_validation.md` can cite exactly what was chosen."""

    case_id: str
    server_name: str
    server_path: Path
    fixture_module: str
    culprit: str
    decoy_tiers: dict[str, str]
    n_tasks_per_tool: int


# Four real cases, all 4-tool servers (satisfies the task's "at least 4-6 tools total" floor:
# every tool in each server is part of the changed set here -- 1 culprit + 3 decoys). Culprit
# POSITION (1st/2nd/3rd/2nd-defined tool respectively) and decoy TIER PATTERN deliberately vary
# across the four cases -- disclosed here as explicit, hand-scripted choices (this pilot's n is
# far too small for a randomized/confound-guarded generator to mean anything; see the report's
# "case construction" section for the same disclosure). `scripts/real_agent_validation.py`
# decides, from the pilot's measured pace, how many of these four to actually RUN live -- not
# every spec listed here is guaranteed to appear in the final report if the pace budget forces a
# smaller n; that reduction (if any) is disclosed explicitly in the report, not silently applied.
REAL_CASE_SPECS: list[RealCaseSpec] = [
    RealCaseSpec(
        case_id="real_github_issues",
        server_name="github-issues-real-case",
        server_path=REPO_ROOT / "examples" / "github_issues_server_fixed.py",
        fixture_module="evals.fixtures.v2_4_corpus.github_issues_fixture",
        culprit="update_issue_state",
        decoy_tiers={"create_issue": "small", "add_assignee": "medium", "add_label": "large"},
        n_tasks_per_tool=1,
    ),
    RealCaseSpec(
        case_id="real_jira_issues",
        server_name="jira-issues-real-case",
        server_path=REPO_ROOT / "examples" / "jira_issues_server_fixed.py",
        fixture_module="evals.fixtures.v2_4_corpus.jira_issues_fixture",
        culprit="set_issue_priority",
        decoy_tiers={"create_issue": "large", "transition_issue": "small", "add_issue_comment": "medium"},
        n_tasks_per_tool=1,
    ),
    # stripe/slack's 4th tool (`create_customer` / `set_channel_topic` respectively) is the
    # fixture's deliberately "inert" tool -- documented in the server file's own header comment
    # as having no constrained param and NOT appearing in `TASKS` at all. Including it as a decoy
    # would leave it with zero real tasks probing it, so it is excluded from `decoy_tiers` here
    # (left as an untouched, present-but-not-in-`changed_tools` catalog member) -- these two
    # cases therefore have 1 culprit + 2 decoys rather than 1 + 3, still within the task's
    # "2-3 benign decoy changes" instruction.
    RealCaseSpec(
        case_id="real_stripe_payments",
        server_name="stripe-payments-real-case",
        server_path=REPO_ROOT / "examples" / "stripe_payments_server_fixed.py",
        fixture_module="evals.fixtures.v2_4_corpus.stripe_payments_fixture",
        culprit="create_refund",
        decoy_tiers={"create_charge": "large", "update_subscription": "small"},
        n_tasks_per_tool=1,
    ),
    RealCaseSpec(
        case_id="real_slack_messaging",
        server_name="slack-messaging-real-case",
        server_path=REPO_ROOT / "examples" / "slack_messaging_server_fixed.py",
        fixture_module="evals.fixtures.v2_4_corpus.slack_messaging_fixture",
        culprit="invite_to_channel",
        decoy_tiers={"post_message": "medium", "set_user_presence": "large"},
        n_tasks_per_tool=1,
    ),
]


async def build_case_from_spec(spec: RealCaseSpec) -> RealAttributionCase:
    """Introspect `spec.server_path`'s real tool catalog, load its real fixture's `TASKS`, and
    build a `RealAttributionCase` per `spec`'s explicit culprit/decoy-tier choices."""
    clean_catalog = await introspect_catalog(spec.server_path)
    fixture = importlib.import_module(spec.fixture_module)
    fixture_tasks: list[Task] = fixture.TASKS
    tool_names = [spec.culprit, *spec.decoy_tiers.keys()]
    blind_tasks = select_blind_tasks(fixture_tasks, tool_names, spec.n_tasks_per_tool)
    return build_real_case(
        case_id=spec.case_id,
        server_name=spec.server_name,
        clean_catalog=clean_catalog,
        culprit=spec.culprit,
        decoy_tiers=spec.decoy_tiers,
        blind_tasks=blind_tasks,
    )

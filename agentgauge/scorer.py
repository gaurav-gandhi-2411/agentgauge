from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mcp.types import Tool

from agentgauge.providers import Message, Provider

if TYPE_CHECKING:
    from agentgauge.client import MCPClient, ToolCallResult
    from agentgauge.runner import RunResult


@dataclass
class DimensionScore:
    name: str
    score: float  # 0-100
    details: dict[str, Any] = field(default_factory=dict)
    fix_hints: list[str] = field(default_factory=list)


@dataclass
class ScoredReport:
    overall: float
    dimensions: list[DimensionScore]
    tool_count: int


# Weights must sum to 1.0
DIMENSION_WEIGHTS: dict[str, float] = {
    "schema_completeness": 0.25,
    "description_quality": 0.25,
    "discoverability": 0.15,
    "selection_accuracy": 0.15,
    "call_correctness": 0.10,
    "error_legibility": 0.05,
    "robustness": 0.03,
    "docs_manifest": 0.02,
}


def score_schema_completeness(tools: list[Tool]) -> DimensionScore:
    """Static analysis — no LLM needed."""
    if not tools:
        return DimensionScore(
            name="schema_completeness",
            score=0.0,
            details={"reason": "no tools"},
            fix_hints=["Add tools to your MCP server"],
        )

    total_params = 0
    scored_params = 0
    fix_hints: list[str] = []

    for tool in tools:
        schema = tool.inputSchema or {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        if not properties:
            fix_hints.append(f"Tool '{tool.name}': add parameter definitions to inputSchema")
            continue

        for param_name, param_schema in properties.items():
            total_params += 1
            param_score = 0

            if param_schema.get("description"):
                param_score += 1
            else:
                fix_hints.append(f"Tool '{tool.name}', param '{param_name}': add a description")

            if param_schema.get("type"):
                param_score += 1
            else:
                fix_hints.append(f"Tool '{tool.name}', param '{param_name}': add a type")

            if param_name in required or param_schema.get("default") is not None:
                param_score += 1

            scored_params += param_score

    raw = 0.0 if total_params == 0 else (scored_params / (total_params * 3)) * 100

    return DimensionScore(
        name="schema_completeness",
        score=round(raw, 1),
        details={"total_params": total_params, "scored_params": scored_params},
        fix_hints=fix_hints[:5],  # cap noise
    )


async def score_description_quality(
    tools: list[Tool], provider: Provider, *, trials: int = 1
) -> DimensionScore:
    """LLM-as-judge: ask the provider to rate each tool description 0-10."""
    if not tools:
        return DimensionScore(
            name="description_quality",
            score=0.0,
            details={"reason": "no tools"},
            fix_hints=["Add tools with descriptions to your MCP server"],
        )

    scores_by_tool: dict[str, list[float]] = {}
    fix_hints: list[str] = []

    for tool in tools:
        tool_scores: list[float] = []
        for trial_idx in range(trials):
            prompt = (
                f"Rate this MCP tool description on a scale of 0-10 for clarity and completeness "
                f"for an AI agent. Reply with ONLY a number.\n\n"
                f"Tool name: {tool.name}\n"
                f"Description: {tool.description or '(none)'}\n"
                f"Input schema: {tool.inputSchema}"
            )
            resp = await provider.chat([Message(role="user", content=prompt)], seed=42 + trial_idx)
            match = re.search(r"\b(\d+(?:\.\d+)?)\b", resp)
            if match:
                raw_score = float(match.group(1))
                tool_scores.append(min(raw_score, 10.0))

        if tool_scores:
            avg = sum(tool_scores) / len(tool_scores)
            scores_by_tool[tool.name] = tool_scores
            if avg < 7.0:
                fix_hints.append(
                    f"Tool '{tool.name}' scored {avg:.1f}/10 — improve its description"
                )

    if not scores_by_tool:
        return DimensionScore(
            name="description_quality",
            score=0.0,
            details={},
            fix_hints=["Could not parse LLM scores"],
        )

    all_scores = [s for scores in scores_by_tool.values() for s in scores]
    overall = (sum(all_scores) / len(all_scores)) * 10  # 0-10 -> 0-100

    return DimensionScore(
        name="description_quality",
        score=round(overall, 1),
        details={"per_tool": {k: round(sum(v) / len(v), 2) for k, v in scores_by_tool.items()}},
        fix_hints=fix_hints[:5],
    )


def score_selection_accuracy(run_results: list[RunResult]) -> DimensionScore:
    """Score how often the agent picked the correct tool for each task."""
    if not run_results:
        return DimensionScore(
            name="selection_accuracy",
            score=0.0,
            details={"reason": "no run results"},
            fix_hints=["Run tasks to generate selection accuracy data"],
        )
    correct = sum(1 for r in run_results if r.selected_tool == r.task.tool_name)
    total = len(run_results)
    score = (correct / total) * 100
    return DimensionScore(
        name="selection_accuracy",
        score=round(score, 1),
        details={"correct": correct, "total": total},
        fix_hints=(
            ["Improve tool names and descriptions so agents can identify the right tool"]
            if score < 75
            else []
        ),
    )


def score_call_correctness(run_results: list[RunResult]) -> DimensionScore:
    """Score how often the agent's tool call succeeded (server accepted the arguments)."""
    if not run_results:
        return DimensionScore(
            name="call_correctness",
            score=0.0,
            details={"reason": "no run results"},
            fix_hints=["Run tasks to generate call correctness data"],
        )
    successful = sum(1 for r in run_results if r.success)
    total = len(run_results)
    score = (successful / total) * 100
    return DimensionScore(
        name="call_correctness",
        score=round(score, 1),
        details={"successful": successful, "total": total},
        fix_hints=(
            ["Improve parameter descriptions and examples so agents construct valid arguments"]
            if score < 75
            else []
        ),
    )


@dataclass
class ErrorProbe:
    label: str
    args: dict[str, Any]


def _error_probes(tool: Tool) -> list[ErrorProbe]:
    """Generate 2 bad-input cases for a tool derived from its JSON schema.

    Case 1 (when required params exist): empty args — triggers missing-required errors.
    Case 2 (when required params exist): wrong type on the first required param.
    Fallback (no required params): inject an unknown field.
    """
    schema = tool.inputSchema or {}
    properties: dict[str, Any] = schema.get("properties", {})
    required: list[str] = schema.get("required", [])

    if not required:
        return [ErrorProbe(label="unknown_param", args={"__bad_field__": True})]

    probes: list[ErrorProbe] = [ErrorProbe(label="missing_required", args={})]

    first = required[0]
    prop = properties.get(first, {})
    wrong: dict[str, Any] = {
        "string": 99999,
        "integer": "not_a_number",
        "number": "not_a_number",
        "boolean": [1, 2, 3],
        "array": "not_an_array",
        "object": 42,
    }
    bad_val: Any = wrong.get(prop.get("type", "string"))
    probes.append(ErrorProbe(label=f"wrong_type_{first}", args={first: bad_val}))

    return probes


def _extract_error_text(result: ToolCallResult) -> str:
    """Pull the human-readable error string out of a ToolCallResult."""
    if result.error:
        return result.error
    # Some servers return error content in the content list rather than raising.
    for item in result.content:
        text = getattr(item, "text", None)
        if text:
            return str(text)
    return "(no error message returned)"


async def score_error_legibility(
    tools: list[Tool],
    client: MCPClient,
    provider: Provider,
    *,
    trials: int = 3,
) -> DimensionScore:
    """LLM-judge whether error responses are understandable and actionable to an agent.

    For each tool, injects 2 classes of bad input (missing required param, wrong type).
    Runs the judge `trials` times per case and aggregates mean + variance across all cases.
    """
    if not tools:
        return DimensionScore(
            name="error_legibility",
            score=0.0,
            details={"reason": "no tools"},
            fix_hints=["Add tools to your MCP server"],
        )

    all_case_means: list[float] = []
    all_variances: list[float] = []
    per_tool: dict[str, float] = {}
    fix_hints: list[str] = []

    for tool in tools:
        probes = _error_probes(tool)
        tool_case_means: list[float] = []

        for probe in probes:
            result = await client.call_tool_with_bad_input(tool.name, probe.args)
            error_text = _extract_error_text(result)

            judge_scores: list[float] = []
            for trial_idx in range(trials):
                # Rubric calibration note (llama3.1:8b, 2026-05-31):
                # The 5-6 anchor for "diagnosis-only" is the INTENDED target but
                # is aspirational: llama3.1:8b rates such errors at ~7/10 (~70/100).
                # The dimension guarantees ORDERING (what+how > diag > opaque) and
                # ACTIONABILITY GAP (~20 pts), not absolute band membership.
                # Revisit if the pinned judge model changes. See CLAUDE.md.
                prompt = (
                    f"An AI agent called MCP tool '{tool.name}' with invalid arguments "
                    f"and received the error below. Rate it 0-10 on TWO dimensions:\n"
                    f"(a) DIAGNOSIS — does it name what was wrong (which field, which type)?\n"
                    f"(b) ACTIONABILITY — does it state how to fix it (the corrective step)?\n\n"
                    f"Scoring guide:\n"
                    f"- 9-10: Names what was wrong AND states the corrective action "
                    f"(e.g. \"Required field 'user_id' (string) is missing — add it and retry\")\n"
                    f"- 5-6: Names the failing field/type but gives NO corrective instruction "
                    f"(e.g. \"Required field 'user_id' (string) is missing.\")\n"
                    f"- 3-4: Vague — something failed but not which field or why "
                    f'(e.g. "Invalid input")\n'
                    f"- 0-2: No field-level information — bare status code, empty string, "
                    f'or stack trace. Score "Error 500" as 1, "Internal Server Error" as 1. '
                    f"Any response naming no specific field scores <= 2.\n\n"
                    f"Bad input used: {probe.args}\n"
                    f"Error response: {error_text!r}\n\n"
                    f"Reply with ONLY a number 0-10."
                )
                resp = await provider.chat(
                    [Message(role="user", content=prompt)], seed=42 + trial_idx
                )
                m = re.search(r"\b(\d+(?:\.\d+)?)\b", resp)
                if m:
                    judge_scores.append(min(float(m.group(1)), 10.0))

            if judge_scores:
                case_mean = sum(judge_scores) / len(judge_scores)
                case_var = sum((s - case_mean) ** 2 for s in judge_scores) / len(judge_scores)
                tool_case_means.append(case_mean)
                all_variances.append(case_var)

        if tool_case_means:
            tool_avg = sum(tool_case_means) / len(tool_case_means)
            per_tool[tool.name] = round(tool_avg * 10, 1)  # 0-10 → 0-100
            all_case_means.extend(tool_case_means)
            if tool_avg < 6.0:
                fix_hints.append(
                    f"Tool '{tool.name}' error messages scored {tool_avg:.1f}/10 — "
                    f"return structured errors that name the failing field, expected type, "
                    f"and corrective action (e.g. '— add it and retry')"
                )

    if not all_case_means:
        return DimensionScore(
            name="error_legibility",
            score=0.0,
            details={"reason": "no scores collected", "judge_trials": trials},
            fix_hints=fix_hints,
        )

    overall_mean = sum(all_case_means) / len(all_case_means)
    overall_score = round(overall_mean * 10, 1)  # 0-10 → 0-100
    avg_var = sum(all_variances) / len(all_variances) if all_variances else 0.0

    return DimensionScore(
        name="error_legibility",
        score=overall_score,
        details={
            "per_tool": per_tool,
            "judge_trials": trials,
            "avg_variance": round(avg_var, 4),
        },
        fix_hints=fix_hints[:5],
    )


def _robustness_probes(tool: Tool) -> list[ErrorProbe]:
    schema = tool.inputSchema or {}
    properties: dict[str, Any] = schema.get("properties", {})
    required: list[str] = schema.get("required", [])

    first_required = required[0] if required else None
    first_prop = list(properties.keys())[0] if properties else None
    target = first_required or first_prop

    wrong_type_map: dict[str, Any] = {
        "string": 99999,
        "integer": "not_a_number",
        "number": "not_a_number",
        "boolean": [1, 2, 3],
        "array": "not_an_array",
        "object": 42,
    }

    # Probe 1: null value on a known param
    null_args: dict[str, Any] = {target: None} if target else {"__null__": None}
    # Probe 2: extra unknown field injected
    extra_args: dict[str, Any] = {"__unknown_field__": "unexpected_value"}
    # Probe 3: wrong type on first required param (or all-nulls fallback)
    if first_required:
        prop_type = properties.get(first_required, {}).get("type", "string")
        bad_val: Any = wrong_type_map.get(prop_type, 99999)
        wrong_args: dict[str, Any] = {first_required: bad_val}
        wrong_label = f"wrong_type_{first_required}"
    else:
        wrong_args = {k: None for k in properties} if properties else {"__all_nulls__": None}
        wrong_label = "all_nulls"

    return [
        ErrorProbe(label="null_value", args=null_args),
        ErrorProbe(label="extra_fields", args=extra_args),
        ErrorProbe(label=wrong_label, args=wrong_args),
    ]


async def score_robustness(tools: list[Tool], client: MCPClient) -> DimensionScore:
    """Score each tool on three-way probe outcome classification.

    Per probe:
      graceful_rejection — call_tool returns success=False (server signalled an error).
                           Full credit: the server handles bad input safely.
      silent_accept      — call_tool returns success=True on deliberately malformed input.
                           Zero credit: the server accepted invalid arguments without complaint.
                           Distinct from a crash — this is a validation gap, not a runtime failure.
      crash              — call_tool raises an unhandled exception.
                           Zero credit: the server has an unhandled error path.

    Scoring weight: graceful_rejection=1, silent_accept=0, crash=0.
    score = graceful_rejections / total_probes * 100
    """
    if not tools:
        return DimensionScore(
            name="robustness",
            score=0.0,
            details={"reason": "no tools"},
            fix_hints=["Add tools to your MCP server"],
        )

    total_probes = 0
    graceful_count = 0
    crash_count = 0
    silent_accept_count = 0
    per_tool: dict[str, dict[str, Any]] = {}
    fix_hints: list[str] = []

    for tool in tools:
        probes = _robustness_probes(tool)
        tool_graceful = 0
        tool_crashes = 0
        tool_silent = 0

        for probe in probes:
            total_probes += 1
            try:
                result = await client.call_tool(tool.name, probe.args)
                if result.success:
                    # Server returned success=True on malformed input — silent accept.
                    tool_silent += 1
                    silent_accept_count += 1
                else:
                    # Server signalled an error (success=False) — graceful rejection.
                    tool_graceful += 1
                    graceful_count += 1
            except Exception:
                # call_tool itself raised — unhandled crash.
                tool_crashes += 1
                crash_count += 1

        tool_pct = (tool_graceful / len(probes)) * 100
        per_tool[tool.name] = {
            "graceful_rejections": tool_graceful,
            "crashes": tool_crashes,
            "silent_accepts": tool_silent,
            "total": len(probes),
            "score": round(tool_pct, 1),
        }
        if tool_crashes > 0:
            fix_hints.append(
                f"Tool '{tool.name}' crashed on "
                f"{tool_crashes}/{len(probes)} malformed-input probes — "
                f"ensure all error paths return structured errors"
            )
        if tool_silent > 0:
            fix_hints.append(
                f"Tool '{tool.name}' silently accepted malformed input on "
                f"{tool_silent}/{len(probes)} probes — "
                f"add input validation to reject bad arguments with an error"
            )

    overall = (graceful_count / total_probes) * 100 if total_probes else 0.0
    return DimensionScore(
        name="robustness",
        score=round(overall, 1),
        details={
            "total_probes": total_probes,
            "graceful_rejections": graceful_count,
            "crashes": crash_count,
            "silent_accepts": silent_accept_count,
            "per_tool": per_tool,
        },
        fix_hints=fix_hints[:5],
    )


DOCS_MANIFEST_FLOOR = 20.0


async def score_docs_manifest(
    tools: list[Tool],
    fetched_doc: str | None,
    provider: Provider,
    *,
    trials: int = 3,
) -> DimensionScore:
    """LLM-judge quality of an llms.txt manifest.

    absent/404/error/stdio → floor score (20.0) with a fix hint.
    present → LLM-judge 0–10, mapped linearly to 20–100 so absent and present-garbage
    converge near the floor while present-good rises.

    Fetch path validation (real sites, 2026-05-31):
    - redirect-following confirmed: sites like docs.anthropic.com (301→200) are now reached.
    - 404/connection-error path confirmed: floors at 20.0 with fix hint.
    - stdio (no base_url) confirmed: floors at 20.0.

    Judge prompt targets agent-usefulness explicitly:
    (a) what the server does overall
    (b) which tools exist and their purpose
    (c) when and how to use each tool
    These three questions are present verbatim. The prompt does not collapse to generic
    "is this good documentation?".

    What this dimension GUARANTEES (model-independent, locked by tests):
    - Ordering: present-good scores above present-poor (gap ≥ 40 pts by mock assertion)
    - Floor: absent/stdio/404 always returns exactly 20.0

    What is NOT guaranteed (absolute bands are model-dependent):
    - Unlike error_legibility, this dimension has no real-model calibration run against
      llama3.1:8b. The 20–100 mapping is structurally sound but exact band values (e.g.
      where a "good" MCP llms.txt actually lands) are unmeasured. Use ordering and gap
      comparisons, not absolute thresholds, until a calibration run is done.

    Known limitation: only the first 8000 chars of the fetched document are fed to the judge.
    Files where substantive tool descriptions begin after 8000 chars will score below their
    full content warrants.
    """
    if fetched_doc is None:
        return DimensionScore(
            name="docs_manifest",
            score=DOCS_MANIFEST_FLOOR,
            details={"status": "absent"},
            fix_hints=[
                "No llms.txt found — agents have no manifest to discover capabilities. "
                "Add one at /llms.txt."
            ],
        )

    judge_scores: list[float] = []
    for trial_idx in range(trials):
        prompt = (
            "You are evaluating an MCP server's llms.txt manifest for AI agent readiness.\n"
            "Rate this document 0-10 on how well it helps an AI agent understand:\n"
            "(a) what the server does overall\n"
            "(b) which tools exist and their purpose\n"
            "(c) when and how to use each tool\n\n"
            "Scoring guide:\n"
            "- 9-10: Comprehensive — all tools described with purpose, parameters, and when to use\n"
            "- 6-8: Good — most tools described clearly\n"
            "- 3-5: Partial — few tools described or very brief coverage\n"
            "- 0-2: Poor — present but useless (no tool descriptions, placeholder content)\n\n"
            # 8000 chars (~4000 tokens) gives the judge enough window to read real tool
            # descriptions without overflowing an 8B context. 2000 chars was too small —
            # it chopped before any tool content on link-index files like the MCP docs.
            f"llms.txt content:\n{fetched_doc[:8000]}\n\n"
            "Reply with ONLY a number 0-10."
        )
        resp = await provider.chat([Message(role="user", content=prompt)], seed=42 + trial_idx)
        m = re.search(r"\b(\d+(?:\.\d+)?)\b", resp)
        if m:
            judge_scores.append(min(float(m.group(1)), 10.0))

    if not judge_scores:
        return DimensionScore(
            name="docs_manifest",
            score=DOCS_MANIFEST_FLOOR,
            details={"status": "parse_error"},
            fix_hints=["Could not parse LLM scores for llms.txt"],
        )

    mean = sum(judge_scores) / len(judge_scores)
    variance = sum((s - mean) ** 2 for s in judge_scores) / len(judge_scores)
    # Map 0–10 → 20–100 so absent and present-garbage converge near the floor
    score = DOCS_MANIFEST_FLOOR + (mean / 10.0) * (100.0 - DOCS_MANIFEST_FLOOR)

    fix_hints: list[str] = []
    if mean < 6.0:
        fix_hints.append(
            f"llms.txt scored {mean:.1f}/10 — expand it to describe each tool's "
            "purpose, parameters, and when to use it"
        )

    return DimensionScore(
        name="docs_manifest",
        score=round(score, 1),
        details={
            "judge_score_mean": round(mean, 2),
            "judge_trials": trials,
            "avg_variance": round(variance, 4),
        },
        fix_hints=fix_hints,
    )


def _levenshtein(a: str, b: str) -> int:
    """Standard dynamic-programming Levenshtein distance (edit distance)."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for ca in a:
        curr = [prev[0] + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[-1] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


# Names that are obviously generic/placeholder and carry no semantic signal.
_GENERIC_NAMES: frozenset[str] = frozenset(
    {
        "tool",
        "tool1",
        "tool2",
        "tool3",
        "test",
        "foo",
        "bar",
        "baz",
        "qux",
        "do_thing",
        "run_it",
        "my_tool",
        "some_tool",
        "func",
        "function",
        "method",
        "handler",
        "process",
        "action",
        "cmd",
        "command",
        "op",
        "operation",
        "util",
        "utility",
        "helper",
        "misc",
        "other",
        "thing",
        "stuff",
        "new_tool",
        "example",
    }
)

# Two tool names whose normalized edit-distance similarity meets this threshold
# are flagged as a confusable (near-duplicate) collision.
_COLLISION_THRESHOLD = 0.8

# Per-collision deduction from the aggregate heuristic (0–1 scale), capped at 0.30.
_COLLISION_PENALTY = 0.15

# Blend weight for the deterministic heuristic sub-score.  ≥ 0.50 guarantees that
# a name-collision penalty from the heuristic is never fully overridden by a noisy
# judge trial that happens to rate confusable tools highly.
_HEURISTIC_BLEND_WEIGHT = 0.60


def _heuristic_subscore(
    tools: list[Tool],
) -> tuple[float, list[str], list[tuple[str, str]], dict[str, int]]:
    """Deterministic heuristic sub-score for discoverability (0–100).

    Per-tool rules (each earns 0–3 points):
    - +1  name is not in the generic/placeholder set
    - +1  name length > 3 characters (very short names are uninformative)
    - +1  description is present and non-empty

    Collision penalty: each near-duplicate pair (normalized edit-distance similarity
    >= 0.8) deducts 0.15 from the aggregate, capped at 0.30 total.

    Returns: (score_0_100, fix_hints, collision_pairs, per_tool_points)
    """
    fix_hints: list[str] = []
    per_tool: dict[str, int] = {}
    total_points = 0

    for tool in tools:
        name_lower = tool.name.lower()
        pts = 0

        if name_lower not in _GENERIC_NAMES:
            pts += 1
        else:
            fix_hints.append(
                f"Tool '{tool.name}' has a non-descriptive placeholder name — "
                "rename it to describe its action (e.g. 'send_email', not 'do_thing')"
            )

        if len(tool.name) > 3:
            pts += 1
        else:
            fix_hints.append(
                f"Tool '{tool.name}' has a very short name — "
                "use a longer, action-based name so agents can identify its purpose"
            )

        if tool.description and tool.description.strip():
            pts += 1
        else:
            fix_hints.append(
                f"Tool '{tool.name}' has no description — add one so agents understand what it does"
            )

        per_tool[tool.name] = pts
        total_points += pts

    aggregate = total_points / (len(tools) * 3)

    # Pairwise near-duplicate detection via normalized edit distance.
    names = [t.name for t in tools]
    collision_pairs: list[tuple[str, str]] = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i].lower(), names[j].lower()
            max_len = max(len(a), len(b), 1)
            sim = 1.0 - _levenshtein(a, b) / max_len
            if sim >= _COLLISION_THRESHOLD:
                collision_pairs.append((names[i], names[j]))
                fix_hints.append(
                    f"Tools '{names[i]}' and '{names[j]}' have confusingly similar names — "
                    "consider renaming one to make them clearly distinct"
                )

    collision_penalty = min(len(collision_pairs) * _COLLISION_PENALTY, 0.30)
    score = max(0.0, aggregate - collision_penalty) * 100
    return score, fix_hints, collision_pairs, per_tool


def _parse_distinguish_score(resp: str) -> float | None:
    """Extract the DISTINGUISH score from a judge response.

    Tries three strategies in order:
    1. Labeled: finds 'DISTINGUISH: N' (case-insensitive) — the intended format.
    2. Last number: takes the last digit sequence in the response.  When the model
       answers with two lines (CLARITY first, then DISTINGUISH), the last number is
       the DISTINGUISH score.
    3. First number: plain bare-number fallback for single-number responses.

    Returns None only when the response contains no digit at all.
    """
    # Strategy 1: explicit DISTINGUISH label
    m = re.search(r"DISTINGUISH\s*:?\s*(\d+(?:\.\d+)?)", resp, re.IGNORECASE)
    if m:
        return min(float(m.group(1)), 10.0)

    # Strategy 2: last number (handles "CLARITY: 8\nDISTINGUISH: 4" even without label)
    all_nums = re.findall(r"\b(\d+(?:\.\d+)?)\b", resp)
    if len(all_nums) >= 2:
        return min(float(all_nums[-1]), 10.0)

    # Strategy 3: single bare number
    if all_nums:
        return min(float(all_nums[0]), 10.0)

    return None


async def _judge_discoverability(
    tools: list[Tool], provider: Provider, *, trials: int
) -> tuple[float, float, list[str]]:
    """LLM judge sub-score for tool-catalog discoverability (0–100).

    Asks the model to rate the catalog on two explicit dimensions and extracts only
    the DISTINGUISH score, which is the signal this dimension cares about.  Using
    two labeled lines prevents the model from silently blending clarity and
    distinguishability into one opaque number — the behaviour observed in spot-checks
    where a confusable trio scored 8/10 because individual tool clarity was high even
    though distinguishability was rated 4/10 internally.

    Parser priority: DISTINGUISH label > last number > first number.  The last-number
    fallback handles the common case where the model answers both dimensions but omits
    labels.

    Returns: (score_0_100, variance, fix_hints)
    """
    catalog = "\n".join(
        f"- {t.name}: {(t.description or '(no description)').splitlines()[0]}" for t in tools
    )
    prompt = (
        "You are evaluating an MCP server's tool catalog for AI agent discoverability.\n"
        f"Here are the available tools (name and one-line description only):\n{catalog}\n\n"
        "Rate the catalog on TWO dimensions (each 0-10):\n"
        "CLARITY: How well does each tool's name and description explain what it does?\n"
        "DISTINGUISH: How easily can an AI agent tell confusable or similarly-named tools apart "
        "and pick the right one?\n\n"
        "Scoring guide for DISTINGUISH (the key metric for this evaluation):\n"
        "- 9-10: No confusable pairs; every tool has a clearly distinct name and purpose\n"
        "- 6-8: Minor overlap — 1-2 tools are somewhat similar but differentiable from context\n"
        "- 3-5: Several tools share similar names or purposes; an agent would frequently confuse them\n"
        "- 0-2: Multiple near-identical names or purposes; an agent cannot reliably pick the right tool\n\n"
        "Reply with EXACTLY two lines, no other text:\n"
        "CLARITY: <number>\n"
        "DISTINGUISH: <number>"
    )

    judge_scores: list[float] = []
    for trial_idx in range(trials):
        resp = await provider.chat([Message(role="user", content=prompt)], seed=42 + trial_idx)
        val = _parse_distinguish_score(resp)
        if val is not None:
            judge_scores.append(val)

    if not judge_scores:
        return 50.0, 0.0, []

    mean = sum(judge_scores) / len(judge_scores)
    variance = sum((s - mean) ** 2 for s in judge_scores) / len(judge_scores)
    score = mean * 10  # 0-10 → 0-100

    fix_hints: list[str] = []
    if mean < 6.0:
        fix_hints.append(
            f"Tool catalog scored {mean:.1f}/10 for agent clarity — "
            "review names and descriptions for distinctness and specificity"
        )
    return score, variance, fix_hints


async def score_discoverability(
    tools: list[Tool], provider: Provider, *, trials: int = 1
) -> DimensionScore:
    """Score how navigable the tool catalog is for an agent discovering the right tool.

    60/40 blend of two sub-scores, both reported in details for transparency:
    - heuristic_score (60%): deterministic static analysis (name quality + collision detection)
    - judge_score (40%): LLM judge rating catalog distinguishability specifically

    The heuristic weight is >= 0.50 so that a name-collision penalty is never fully
    overridden by a noisy judge trial.  The judge contributes signal on semantic
    clarity that the heuristic cannot measure.

    This dimension is STATIC — it judges the catalog surface itself, not agent task
    performance (that is selection_accuracy's job).
    """
    if not tools:
        return DimensionScore(
            name="discoverability",
            score=0.0,
            details={"reason": "no tools"},
            fix_hints=["Add tools to your MCP server"],
        )

    heuristic, h_hints, collision_pairs, per_tool_pts = _heuristic_subscore(tools)
    judge, judge_var, j_hints = await _judge_discoverability(tools, provider, trials=trials)

    final = _HEURISTIC_BLEND_WEIGHT * heuristic + (1.0 - _HEURISTIC_BLEND_WEIGHT) * judge

    # Surface most-actionable hints first; cap noise at 5.
    all_hints = (h_hints + j_hints)[:5]

    return DimensionScore(
        name="discoverability",
        score=round(final, 1),
        details={
            "heuristic_score": round(heuristic, 1),
            "judge_score": round(judge, 1),
            "judge_trials": trials,
            "avg_variance": round(judge_var, 4),
            "per_tool_heuristic": per_tool_pts,
            "collision_pairs": collision_pairs,
        },
        fix_hints=all_hints,
    )


def _stub_dimension(name: str) -> DimensionScore:
    return DimensionScore(
        name=name,
        score=0.0,
        details={"status": "not_implemented"},
        fix_hints=[f"{name} scoring is not yet implemented — see TASKS.md"],
    )


async def score_all(
    tools: list[Tool],
    provider: Provider,
    *,
    client: MCPClient | None = None,
    trials: int = 1,
    base_url: str | None = None,
) -> ScoredReport:
    from agentgauge.client import fetch_llms_txt
    from agentgauge.runner import run_tasks
    from agentgauge.tasks import generate_tasks

    schema = score_schema_completeness(tools)
    description = await score_description_quality(tools, provider, trials=trials)
    fetched_doc = await fetch_llms_txt(base_url)
    docs = await score_docs_manifest(tools, fetched_doc, provider, trials=trials)

    if client is not None:
        tasks = generate_tasks(tools)
        run_results = await run_tasks(tasks, client, provider, trials=trials)
        selection = score_selection_accuracy(run_results)
        correctness = score_call_correctness(run_results)
        error_leg = await score_error_legibility(tools, client, provider, trials=trials)
        robustness = await score_robustness(tools, client)
    else:
        selection = _stub_dimension("selection_accuracy")
        correctness = _stub_dimension("call_correctness")
        error_leg = _stub_dimension("error_legibility")
        robustness = _stub_dimension("robustness")

    discoverability = await score_discoverability(tools, provider, trials=trials)

    dimensions = [
        schema,
        description,
        discoverability,
        selection,
        correctness,
        error_leg,
        robustness,
        docs,
    ]

    dim_map = {d.name: d for d in dimensions}
    overall = sum(
        dim_map[name].score * weight
        for name, weight in DIMENSION_WEIGHTS.items()
        if name in dim_map
    )

    return ScoredReport(overall=round(overall, 1), dimensions=dimensions, tool_count=len(tools))

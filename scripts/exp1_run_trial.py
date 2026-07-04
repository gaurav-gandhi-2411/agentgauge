from __future__ import annotations

# EXP-1 STEP 4/5/6 -- Arm A (real docstrings) and Arm B (oracle) trial runner,
# frozen protocol.
#
# Connects to a generated mirror stub server over real stdio, runs contested tasks
# through the REAL agent model (gemma2:9b via Ollama, local), and classifies each
# trial deterministically:
#   - selected_tool == gold_tool (case-insensitive)            -> SELECTED-CORRECT
#   - selected_tool is None, or doesn't match ANY known tool   -> ABSTAINED-OR-HEDGED
#   - selected_tool matches a DIFFERENT known tool name        -> SELECTED-WRONG
#
# Methodological note (disclosed, not a silent deviation): classification here is
# DETERMINISTIC exact-string-match against the tool catalog, not LLM-judged. The
# selection prompt (agentgauge.runner._build_tool_listing + "reply with ONLY the
# tool name") is designed to elicit a single clean tool name, making judgment
# unnecessary for this specific behavioral test. The frozen protocol's judge_model
# (llama3.1:8b) is reserved for AgentGauge's OTHER, genuinely subjective scoring
# dimensions (error_legibility, description_quality) -- not required here.
#
# Seed per trial is 42 + trial_idx, matching the established codebase convention
# (agentgauge/scorer.py, agentgauge/fixer.py) -- a fixed seed=42 for every trial
# repetition was an early bug here (fixed 2026-07-04): it made "5 trials" identical
# repeated calls, sampling zero real trial-to-trial variance.
#
# This is genuine REAL AGENT SPEND: actual Ollama inference calls, not mocked.
import asyncio
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from exp1_generate_mirror_server import generate_server_source  # noqa: E402

from agentgauge.client import cleanup_connection, connect_stdio  # noqa: E402
from agentgauge.exp1_classifier import (  # noqa: E402
    ContestedTask,
    TrialOutcome,
    compute_family_result,
)
from agentgauge.exp1_mirror import load_mirror  # noqa: E402
from agentgauge.frozen_protocol import (  # noqa: E402
    ABSTAINED_OR_HEDGED,
    DEFAULT_AGENT_MODEL,
    SELECTED_CORRECT,
    SELECTED_WRONG,
    TRIALS_PER_ARM,
)
from agentgauge.providers import Message, OllamaProvider  # noqa: E402
from agentgauge.runner import _build_tool_listing  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIRRORS_DIR = REPO_ROOT / "evals" / "fixtures" / "exp1_mirrors"


def to_json_safe(result: dict) -> dict:
    """TrialOutcome dataclass lists (arm_a_outcomes/arm_b_outcomes) aren't JSON-
    serializable directly; convert them for file output while callers keep using
    the original dict (with real dataclass instances) in-memory."""
    safe = dict(result)
    for key in ("arm_a_outcomes", "arm_b_outcomes"):
        if key in safe and safe[key] is not None:
            safe[key] = [dataclasses.asdict(o) for o in safe[key]]
    return safe


def classify_selection(selected_tool: str | None, gold_tool: str, known_tools: set[str]) -> str:
    """Deterministic classification -- see module docstring."""
    if selected_tool is None:
        return ABSTAINED_OR_HEDGED
    normalized = selected_tool.strip().lower()
    if normalized == gold_tool.lower():
        return SELECTED_CORRECT
    if normalized in {t.lower() for t in known_tools}:
        return SELECTED_WRONG
    return ABSTAINED_OR_HEDGED


async def _run_trials_against_server(
    mirror_server_path: Path,
    tasks: list[ContestedTask],
    trials: int,
    agent_model: str,
) -> tuple[list[TrialOutcome], list[dict]]:
    client, ctx = await connect_stdio(sys.executable, [str(mirror_server_path)])
    try:
        info = await client.introspect()
        known_tools = {t.name for t in info.tools}
        tool_listing = _build_tool_listing(info.tools)
        provider = OllamaProvider(model=agent_model)

        outcomes: list[TrialOutcome] = []
        raw_log: list[dict] = []
        for task in tasks:
            for trial in range(trials):
                resp = await provider.chat(
                    [
                        Message(
                            role="user",
                            content=(
                                f"Available tools:\n{tool_listing}\n\n"
                                f"Task: {task.task_text}\n"
                                "Reply with ONLY the tool name to call, nothing else."
                            ),
                        )
                    ],
                    seed=42 + trial,
                )
                raw = resp.strip()
                selected = raw.split()[0] if raw else None
                if selected:
                    selected = selected.strip(".,:;\"'`")
                outcome = classify_selection(selected, task.gold_tool, known_tools)
                outcomes.append(
                    TrialOutcome(
                        task_id=task.task_id, trial=trial, outcome=outcome, selected_tool=selected
                    )
                )
                raw_log.append(
                    {
                        "task_id": task.task_id,
                        "trial": trial,
                        "raw_response": raw,
                        "selected_tool": selected,
                        "gold_tool": task.gold_tool,
                        "outcome": outcome,
                    }
                )
                print(
                    f"  [{task.task_id}][trial {trial}] gold={task.gold_tool} "
                    f"selected={selected!r} -> {outcome}"
                )
    finally:
        await cleanup_connection(ctx)
    return outcomes, raw_log


async def run_arm_a(
    server_id: str,
    family_id: str,
    tasks: list[ContestedTask],
    trials: int = TRIALS_PER_ARM,
    agent_model: str = DEFAULT_AGENT_MODEL,
) -> dict:
    mirror_server_path = REPO_ROOT / "examples" / f"exp1_{server_id.replace('-', '_')}_mirror.py"
    outcomes, raw_log = await _run_trials_against_server(
        mirror_server_path, tasks, trials, agent_model
    )

    family_result = compute_family_result(
        server_id=server_id,
        family_id=family_id,
        tool_names=list({t.gold_tool for t in tasks}),
        arm_a_outcomes=outcomes,
        arm_b_outcomes=[],
        contested_tasks=tasks,
    )

    return {
        "server_id": server_id,
        "family_id": family_id,
        "agent_model": agent_model,
        "trials_per_task": trials,
        "n_contested": family_result.n_contested,
        "parse_failed_a": family_result.parse_failed_a,
        "arm_a_accuracy": family_result.arm_a_accuracy,
        "headroom_gated": family_result.headroom_gated,
        "aborted": family_result.aborted,
        "abort_reason": family_result.abort_reason,
        "arm_a_outcomes": outcomes,
        "raw_log_a": raw_log,
    }


async def run_arm_b(
    server_id: str,
    family_id: str,
    tasks: list[ContestedTask],
    arm_a_outcomes: list[TrialOutcome],
    oracle_descriptions: dict[str, str],
    trials: int = TRIALS_PER_ARM,
    agent_model: str = DEFAULT_AGENT_MODEL,
) -> dict:
    """Generates a TEMPORARY oracle-variant mirror (oracle_descriptions override only
    the contested family's tools; every other tool keeps its real Arm A docstring),
    runs trials against it, and classifies IN-REGIME using BOTH arms per the frozen
    protocol (Arm A fails >=1 task AND Arm B recovers it)."""
    mirror = load_mirror(MIRRORS_DIR / f"{server_id}.json")
    oracle_source = generate_server_source(mirror, description_overrides=oracle_descriptions)
    oracle_path = REPO_ROOT / "examples" / f"exp1_{server_id.replace('-', '_')}_mirror_oracle.py"
    oracle_path.write_text(oracle_source, encoding="utf-8")

    outcomes, raw_log = await _run_trials_against_server(oracle_path, tasks, trials, agent_model)

    family_result = compute_family_result(
        server_id=server_id,
        family_id=family_id,
        tool_names=list({t.gold_tool for t in tasks}),
        arm_a_outcomes=arm_a_outcomes,
        arm_b_outcomes=outcomes,
        contested_tasks=tasks,
    )

    return {
        "server_id": server_id,
        "family_id": family_id,
        "agent_model": agent_model,
        "trials_per_task": trials,
        "n_contested": family_result.n_contested,
        "parse_failed_a": family_result.parse_failed_a,
        "parse_failed_b": family_result.parse_failed_b,
        "arm_a_accuracy": family_result.arm_a_accuracy,
        "arm_b_accuracy": family_result.arm_b_accuracy,
        "effect_pp": family_result.effect_pp,
        "headroom_gated": family_result.headroom_gated,
        "in_regime": family_result.in_regime,
        "aborted": family_result.aborted,
        "abort_reason": family_result.abort_reason,
        "oracle_descriptions": oracle_descriptions,
        "raw_log_b": raw_log,
    }


# ── lucasastorian-llmwiki: create vs create_knowledge_base contested tasks ────────
# Both tools have substantial real descriptions post-correction (create: page/note/
# asset creation within an existing vault; create_knowledge_base: new top-level KB/
# course container). Anti-tautological: task text never says "create" or "knowledge
# base" as the tool name would be invoked; distinguishes by whether the user wants a
# NEW top-level container vs. content within an existing one.
LLMWIKI_CREATE_FAMILY_TASKS = [
    ContestedTask(
        task_id="llmwiki_1",
        family_id="create_family",
        task_text=(
            "We're kicking off a brand-new engineering handbook from scratch -- nothing "
            "exists yet for this team. Set up a self-contained space we can build out "
            "over time."
        ),
        gold_tool="create_knowledge_base",
    ),
    ContestedTask(
        task_id="llmwiki_2",
        family_id="create_family",
        task_text=(
            "Our onboarding vault already exists -- please add a fresh document walking "
            "through the deployment process for new hires."
        ),
        gold_tool="create",
    ),
    ContestedTask(
        task_id="llmwiki_3",
        family_id="create_family",
        task_text=(
            "I want to launch a self-paced course on Python basics, complete with "
            "lessons learners can progress through -- this is a totally new resource, "
            "not part of anything we currently have."
        ),
        gold_tool="create_knowledge_base",
    ),
    ContestedTask(
        task_id="llmwiki_4",
        family_id="create_family",
        task_text=(
            "Save this architecture diagram, as an SVG, into our existing product "
            "vault so the team can reference it."
        ),
        gold_tool="create",
    ),
]


async def main() -> None:
    print("Running Arm A (real docstrings) for lucasastorian-llmwiki, create_family...")
    result = await run_arm_a(
        server_id="lucasastorian-llmwiki",
        family_id="create_family",
        tasks=LLMWIKI_CREATE_FAMILY_TASKS,
    )
    out_path = REPO_ROOT / "evals" / "fixtures" / "exp1_trial_lucasastorian-llmwiki_arm_a.json"
    out_path.write_text(
        json.dumps(to_json_safe(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print()
    print(f"Arm A accuracy: {result['arm_a_accuracy']:.1%}")
    print(f"Headroom gated (< 85%): {result['headroom_gated']}")
    print(f"Aborted: {result['aborted']} ({result['abort_reason']})")
    print(f"Written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

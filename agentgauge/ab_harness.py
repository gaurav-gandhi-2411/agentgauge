from __future__ import annotations

from dataclasses import dataclass, field

from agentgauge.client import MCPClient
from agentgauge.providers import Provider
from agentgauge.runner import RunResult, run_tasks
from agentgauge.scorer import score_call_correctness, score_selection_accuracy
from agentgauge.tasks import Task, generate_tasks

# Families pinned for judge (llama3.1:8b) and generator (qwen3:8b).
# Agent must come from a third family — enforced by assert_agent_ne_judge_ne_generator.
JUDGE_MODEL_FAMILY = "llama3.1"
GENERATOR_MODEL_FAMILY = "qwen3"


def assert_agent_ne_judge_ne_generator(agent_model: str) -> None:
    """Raise ValueError if agent_model shares a family with the pinned judge or generator.

    Uses substring match on lowercased model string.
    Judge=llama3.1:8b, Generator=qwen3:8b. Agent must be e.g. gemma2, mistral, phi3.
    """
    m = agent_model.lower()
    if JUDGE_MODEL_FAMILY.lower() in m:
        raise ValueError(
            f"agent_model '{agent_model}' shares family '{JUDGE_MODEL_FAMILY}' with the judge. "
            "Use a third family (e.g. gemma2, mistral, phi3)."
        )
    if GENERATOR_MODEL_FAMILY.lower() in m:
        raise ValueError(
            f"agent_model '{agent_model}' shares family '{GENERATOR_MODEL_FAMILY}' with the "
            "generator. Use a third family (e.g. gemma2, mistral, phi3)."
        )


@dataclass
class ArmResult:
    selection_accuracy: float  # 0–100
    call_correctness: float  # 0–100
    run_results: list[RunResult] = field(default_factory=list)


@dataclass
class McNemar:
    """McNemar's test for paired binary outcomes.

    b: trials where arm A wrong, arm B right (improvements)
    c: trials where arm A right, arm B wrong (regressions)
    statistic: chi-square with continuity correction (|b-c|-1)^2/(b+c),
               or raw (b-c) when b+c<10 (unreliable chi-square)
    p_approx: human-readable significance verdict
    """

    b: int
    c: int
    statistic: float
    p_approx: str


@dataclass
class PairedABResult:
    """Full result of a paired A/B experiment."""

    arm_a: ArmResult
    arm_b: ArmResult
    noise_arm: ArmResult  # second run of arm A for noise floor
    selection_delta: float  # arm_b.selection_accuracy - arm_a.selection_accuracy
    correctness_delta: float  # arm_b.call_correctness - arm_a.call_correctness
    noise_floor_selection: float  # |noise_arm.selection - arm_a.selection|
    noise_floor_correctness: float  # |noise_arm.correctness - arm_a.correctness|
    mcnemar_selection: McNemar
    mcnemar_correctness: McNemar
    tasks: list[Task]
    trials: int


def compute_mcnemar(
    results_a: list[RunResult],
    results_b: list[RunResult],
    *,
    key: str,
) -> McNemar:
    """McNemar's test with continuity correction for paired binary outcomes.

    key: 'selection' (selected_tool == task.tool_name) or 'correctness' (success flag).
    Applies (|b-c|-1)^2 / (b+c) with continuity correction.
    When b+c < 10: returns raw b-c statistic and flags for exact binomial.
    Critical value chi2=3.841 for p<0.05 (df=1).
    """
    if len(results_a) != len(results_b):
        raise ValueError(f"Arm result counts must match: {len(results_a)} != {len(results_b)}")
    if key not in ("selection", "correctness"):
        raise ValueError(f"key must be 'selection' or 'correctness', got {key!r}")

    if key == "selection":
        wins_a = [r.selected_tool == r.task.tool_name for r in results_a]
        wins_b = [r.selected_tool == r.task.tool_name for r in results_b]
    else:
        wins_a = [r.success for r in results_a]
        wins_b = [r.success for r in results_b]

    b = sum(1 for a, bv in zip(wins_a, wins_b, strict=True) if not a and bv)
    c = sum(1 for a, bv in zip(wins_a, wins_b, strict=True) if a and not bv)

    if b + c == 0:
        return McNemar(b=0, c=0, statistic=0.0, p_approx="b+c=0 (no discordant pairs)")

    if b + c < 10:
        return McNemar(
            b=b,
            c=c,
            statistic=float(b - c),
            p_approx=f"b+c={b + c}<10 (use exact binomial; chi-square unreliable)",
        )

    chi2 = (abs(b - c) - 1.0) ** 2 / (b + c)
    p_text = "p<0.05 (significant)" if chi2 > 3.841 else "p≥0.05 (not significant)"
    return McNemar(b=b, c=c, statistic=round(chi2, 4), p_approx=p_text)


async def run_paired_ab(
    client_a: MCPClient,
    client_b: MCPClient,
    provider_a: Provider,
    provider_b: Provider,
    provider_a_noise: Provider,
    *,
    tasks: list[Task] | None = None,
    trials: int = 1,
) -> PairedABResult:
    """Paired A/B experiment: arm A (original metadata) vs arm B (fixed metadata).

    Arms must expose identical tool names — only schema/description metadata may differ.
    If tasks=None, they are generated from arm A's tool list and used on both arms (identical
    task set by construction). provider_a and provider_b may be the same OllamaProvider
    instance for real runs; they're separate MockProvider instances in CI tests.
    provider_a_noise is a fresh instance to measure A-vs-A noise floor (should give the
    same responses as provider_a for deterministic noise=0 in mock tests).

    Raises AssertionError if arms expose different tool names or result counts mismatch.
    """
    info_a = await client_a.introspect()
    info_b = await client_b.introspect()

    names_a = sorted(t.name for t in info_a.tools)
    names_b = sorted(t.name for t in info_b.tools)
    if names_a != names_b:
        raise AssertionError(f"Arms must expose identical tool names. A={names_a!r} B={names_b!r}")

    if tasks is None:
        tasks = generate_tasks(info_a.tools)

    expected = len(tasks) * trials
    results_a = await run_tasks(tasks, client_a, provider_a, trials=trials)
    results_b = await run_tasks(tasks, client_b, provider_b, trials=trials)
    results_a_noise = await run_tasks(tasks, client_a, provider_a_noise, trials=trials)

    if len(results_a) != expected:
        raise AssertionError(f"Arm A: expected {expected} results, got {len(results_a)}")
    if len(results_b) != expected:
        raise AssertionError(f"Arm B: expected {expected} results, got {len(results_b)}")
    if len(results_a_noise) != expected:
        raise AssertionError(
            f"Arm A noise: expected {expected} results, got {len(results_a_noise)}"
        )

    arm_a = ArmResult(
        selection_accuracy=score_selection_accuracy(results_a).score,
        call_correctness=score_call_correctness(results_a).score,
        run_results=results_a,
    )
    arm_b = ArmResult(
        selection_accuracy=score_selection_accuracy(results_b).score,
        call_correctness=score_call_correctness(results_b).score,
        run_results=results_b,
    )
    noise_arm = ArmResult(
        selection_accuracy=score_selection_accuracy(results_a_noise).score,
        call_correctness=score_call_correctness(results_a_noise).score,
        run_results=results_a_noise,
    )

    return PairedABResult(
        arm_a=arm_a,
        arm_b=arm_b,
        noise_arm=noise_arm,
        selection_delta=round(arm_b.selection_accuracy - arm_a.selection_accuracy, 1),
        correctness_delta=round(arm_b.call_correctness - arm_a.call_correctness, 1),
        noise_floor_selection=round(
            abs(noise_arm.selection_accuracy - arm_a.selection_accuracy), 1
        ),
        noise_floor_correctness=round(abs(noise_arm.call_correctness - arm_a.call_correctness), 1),
        mcnemar_selection=compute_mcnemar(results_a, results_b, key="selection"),
        mcnemar_correctness=compute_mcnemar(results_a, results_b, key="correctness"),
        tasks=tasks,
        trials=trials,
    )

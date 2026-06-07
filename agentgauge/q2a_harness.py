from __future__ import annotations

import json
import math
from pathlib import Path

from agentgauge.runner import RunResult
from agentgauge.tasks import Task

_DEFAULT_ARM_F_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "t18_arm_f_descriptions.json"
)


def load_arm_f_descriptions(path: Path = _DEFAULT_ARM_F_PATH) -> dict[str, str]:
    """Load fixer-generated descriptions from a persisted JSON file. Returns {} if missing."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: str(v) for k, v in data.items()}


def compute_recovery_fraction(f_acc: float, a_acc: float, o_acc: float) -> float | None:
    """(F-A)/(O-A). Returns None if O-A ≈ 0 (no headroom)."""
    denom = o_acc - a_acc
    if abs(denom) < 1e-9:
        return None
    return (f_acc - a_acc) / denom


def identify_contested_indices(
    results_a: list[RunResult],
    tasks: list[Task],
    trials: int,
    valid_tool_names: set[str],
) -> list[int]:
    """Return task indices where parse-success Arm A selection accuracy == 0%.

    A task with ALL trials parse-failed (selected_tool not in valid_tool_names) is
    skipped — it has no parse-success signal to define "contested".
    """
    contested = []
    for i, task in enumerate(tasks):
        task_results = results_a[i * trials : (i + 1) * trials]
        ps_results = [r for r in task_results if r.selected_tool in valid_tool_names]
        if not ps_results:
            continue
        correct = sum(1 for r in ps_results if r.selected_tool == task.tool_name)
        if correct == 0:
            contested.append(i)
    return contested


def parse_success_accuracy(
    results: list[RunResult],
    tasks: list[Task],
    trials: int,
    valid_tool_names: set[str],
    indices: list[int],
) -> float:
    """Selection accuracy on parse-success calls only, for tasks at given indices."""
    total_correct = 0
    total_ps = 0
    for i in indices:
        task = tasks[i]
        task_results = results[i * trials : (i + 1) * trials]
        ps_results = [r for r in task_results if r.selected_tool in valid_tool_names]
        total_ps += len(ps_results)
        total_correct += sum(1 for r in ps_results if r.selected_tool == task.tool_name)
    return total_correct / total_ps if total_ps > 0 else 0.0


def parse_failed_count(results: list[RunResult], valid_tool_names: set[str]) -> int:
    """Count results where selected_tool is not in valid_tool_names."""
    return sum(1 for r in results if r.selected_tool not in valid_tool_names)


def _sign_test(deltas: list[float]) -> tuple[int, int, float]:
    """Two-tailed sign test on task-level deltas. Ignores ties (delta == 0)."""
    n_plus = sum(1 for d in deltas if d > 0)
    n_minus = sum(1 for d in deltas if d < 0)
    n = n_plus + n_minus
    if n == 0:
        return 0, 0, 1.0
    k = min(n_plus, n_minus)
    p_one_tail = sum(math.comb(n, i) * (0.5**n) for i in range(k + 1))
    return n_plus, n_minus, round(min(1.0, 2.0 * p_one_tail), 4)

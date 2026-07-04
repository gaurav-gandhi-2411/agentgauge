from __future__ import annotations

# EXP-3 -- runs the pairwise confusability localizer over the 24 pre-registered
# ground-truth pairs (evals/fixtures/exp3_ground_truth.json) and reports
# precision/recall against the pre-committed bar (docs/research/exp3_pre_registration.md
# Section 5). Uses each pair's already-collected docstring_a/docstring_b verbatim --
# no re-fetching, no fixture edits.
#
# --mock: MockProvider, deterministic, no network -- fast plumbing check only.
#         Output under --mock is NOT a science result.
# default: OllamaProvider(model=JUDGE_MODEL) -- the frozen judge (llama3.1:8b).
#          Before running this mode, confirm VRAM is free
#          (nvidia-smi --query-gpu=memory.free --format=csv, ollama ps).
import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.frozen_protocol import JUDGE_MODEL  # noqa: E402
from agentgauge.localizer import localize_pair  # noqa: E402
from agentgauge.providers import MockProvider, OllamaProvider, Provider  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
GROUND_TRUTH_PATH = REPO_ROOT / "evals" / "fixtures" / "exp3_ground_truth.json"
OUTPUT_PATH = REPO_ROOT / "evals" / "fixtures" / "exp3_localizer_result.json"


def _load_ground_truth() -> dict[str, Any]:
    """Load the pre-registered EXP-3 ground-truth fixture (read-only)."""
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def _fixture_hash(path: Path) -> str:
    """SHA-256[:12] of the fixture file at run time, per the frozen protocol appendix."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _make_provider(mock: bool) -> Provider:
    """Build the judge provider: MockProvider for --mock, else the frozen judge."""
    if mock:
        # Deterministic uniform NO -- this is a plumbing check, not a science result.
        return MockProvider(responses=["CONFUSABLE: NO"])
    return OllamaProvider(model=JUDGE_MODEL)


async def _run_all_pairs(provider: Provider, pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run the localizer over every ground-truth pair, in fixture order."""
    records: list[dict[str, Any]] = []
    for pair in pairs:
        result = await localize_pair(
            pair["tool_a"],
            pair["docstring_a"],
            pair["tool_b"],
            pair["docstring_b"],
            provider,
        )
        records.append(
            {
                "pair_id": pair["pair_id"],
                "server_id": pair["server_id"],
                "tool_a": pair["tool_a"],
                "tool_b": pair["tool_b"],
                "label": pair["label"],
                "adversarial": pair["adversarial"],
                "votes": result.votes,
                "verdict": result.verdict,
                "parse_failed_count": result.parse_failed_count,
            }
        )
    return records


def _confusion_matrix(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute TP/FP/FN/TN per exp3_pre_registration.md Section 4.

    Pairs whose verdict is UNDETERMINED (all 3 trials parse-failed) are not
    counted in any of TP/FP/FN/TN -- they are reported separately, since the
    pre-reg's formulas are defined over predicted CONFUSABLE/NOT-CONFUSABLE only.
    """
    tp = fp = fn = tn = 0
    undetermined_pair_ids: list[int] = []

    for r in records:
        if r["verdict"] == "UNDETERMINED":
            undetermined_pair_ids.append(r["pair_id"])
            continue

        predicted_confused = r["verdict"] == "CONFUSABLE"
        actual_confused = r["label"] == "CONFUSED"

        if predicted_confused and actual_confused:
            tp += 1
        elif predicted_confused and not actual_confused:
            fp += 1
        elif not predicted_confused and actual_confused:
            fn += 1
        else:
            tn += 1

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "undetermined_pair_ids": undetermined_pair_ids,
    }


def _precision_recall(matrix: dict[str, Any]) -> tuple[float | str, float | str]:
    """Precision/recall per exp3_pre_registration.md Section 4 formulas.

    Precision = TP / (TP + FP); undefined (reported as a string, not coerced to
    0) when TP + FP == 0 -- i.e. no positive predictions at all.
    Recall = TP / (TP + FN); reported the same defensive way if TP + FN == 0
    (not expected given the fixture's 4 CONFUSED-labeled pairs, but guarded).
    """
    tp, fp, fn = matrix["tp"], matrix["fp"], matrix["fn"]

    precision: float | str
    if tp + fp == 0:
        precision = "undefined (no positive predictions)"
    else:
        precision = tp / (tp + fp)

    recall: float | str
    if tp + fn == 0:
        recall = "undefined (no CONFUSED-labeled pairs with a determined verdict)"
    else:
        recall = tp / (tp + fn)

    return precision, recall


def _interpretation(precision: float | str, recall: float | str) -> str:
    """Apply the pre-committed interpretation bar (Section 5): precision >= 0.50
    AND recall >= 0.50 => "real positive method", else "honest negative"."""
    if isinstance(precision, float) and isinstance(recall, float):
        if precision >= 0.50 and recall >= 0.50:
            return "real positive method"
    return "honest negative"


def _print_table(records: list[dict[str, Any]]) -> None:
    """Print the full per-pair result table."""
    header = (
        f"{'#':>3}  {'server_id':<34} {'tool_a':<26} {'tool_b':<26} "
        f"{'label':<13} {'votes':<20} {'verdict':<16} {'adv':<4}"
    )
    print(header)
    print("-" * len(header))
    for r in records:
        votes_str = ",".join(r["votes"])
        print(
            f"{r['pair_id']:>3}  {r['server_id']:<34} {r['tool_a']:<26} {r['tool_b']:<26} "
            f"{r['label']:<13} {votes_str:<20} {r['verdict']:<16} "
            f"{'yes' if r['adversarial'] else 'no':<4}"
        )


async def _amain(mock: bool) -> None:
    data = _load_ground_truth()
    pairs = data["pairs"]

    provider = _make_provider(mock)
    records = await _run_all_pairs(provider, pairs)

    matrix = _confusion_matrix(records)
    precision, recall = _precision_recall(matrix)
    interpretation = _interpretation(precision, recall)

    summary = {
        "experiment_id": "EXP-3",
        "mode": "mock (plumbing check only -- NOT a science result)" if mock else "real",
        "judge_model": provider.model_name,
        "fixture_hash": _fixture_hash(GROUND_TRUTH_PATH),
        "n_pairs": len(records),
        "n_confused_labeled": data["n_confused"],
        "n_not_confused_labeled": data["n_not_confused"],
        "confusion_matrix": matrix,
        "precision": precision,
        "recall": recall,
        "interpretation": interpretation,
    }

    OUTPUT_PATH.write_text(
        json.dumps({"pairs": records, "summary": summary}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _print_table(records)
    print()
    print(f"Confusion matrix: {matrix}")
    print(f"Precision: {precision}")
    print(f"Recall: {recall}")
    print(f"Interpretation (bar: precision>=0.50 AND recall>=0.50): {interpretation}")
    if mock:
        print(
            "\n[NOTE] --mock mode used a deterministic MockProvider (uniform 'CONFUSABLE: NO'). "
            "This result is a plumbing check only -- it is NOT a science result."
        )
    print(f"\nWritten to {OUTPUT_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EXP-3 pairwise confusability localizer runner")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockProvider for a fast, network-free dry run (plumbing check only).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(_amain(args.mock))


if __name__ == "__main__":
    main()

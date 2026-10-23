from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "type_enum_clustered_ci", _ROOT / "scripts" / "type_enum_clustered_ci.py"
)
assert _SPEC is not None and _SPEC.loader is not None
tec = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tec)


def _doc(deltas_by_set: dict[str, list[float]]) -> dict:
    """One-model fixture: each tool set gets one type_flipped instance with the given deltas."""
    return {
        "m": {
            "blocking_instances": [
                {
                    "tool_set": name,
                    "defect_type": "type_flipped",
                    "task_deltas": [{"delta": d} for d in deltas],
                }
                for name, deltas in deltas_by_set.items()
            ]
        }
    }


def test_clusters_keep_only_type_enum_defects() -> None:
    doc = _doc({"a": [-1.0, 0.0]})
    doc["m"]["blocking_instances"].append(
        {
            "tool_set": "a",
            "defect_type": "contradictory_required_claim",
            "task_deltas": [{"delta": 1.0}],
        }
    )
    assert tec.clusters_for(doc, "m", tec.TYPE_ENUM_DEFECTS) == {"a": [-1.0, 0.0]}


def test_percentile_interpolates() -> None:
    assert tec.percentile([0.0, 10.0], 0.5) == 5.0
    assert tec.percentile([1.0, 2.0, 3.0], 0.0) == 1.0
    assert tec.percentile([1.0, 2.0, 3.0], 1.0) == 3.0


def test_cluster_bootstrap_is_deterministic_and_bounded() -> None:
    clusters = {"a": [-1.0, -1.0], "b": [0.0], "c": [-1.0, 0.0, 0.0]}
    first = tec.cluster_bootstrap(clusters, 500, 42)
    assert first == tec.cluster_bootstrap(clusters, 500, 42)
    assert -1.0 <= first[0] <= first[-1] <= 0.0


def test_clustering_widens_interval_when_clusters_differ() -> None:
    # Perfectly homogeneous within a tool set, very different across sets: clustering matters.
    clusters = {"a": [-1.0] * 5, "b": [0.0] * 5, "c": [-1.0] * 5, "d": [0.0] * 5}
    deltas = [d for v in clusters.values() for d in v]
    cl = tec.cluster_bootstrap(clusters, 2000, 42)
    tk = tec.task_bootstrap(deltas, 2000, 42)
    assert tec.percentile(cl, 0.975) - tec.percentile(cl, 0.025) > tec.percentile(
        tk, 0.975
    ) - tec.percentile(tk, 0.025)


def test_t_ci_is_centred_on_pooled_mean() -> None:
    clusters = {"a": [-1.0, -1.0], "b": [0.0, 0.0], "c": [-0.5, -0.5]}
    lo, hi = tec.t_cluster_ci(clusters)
    assert lo < -0.5 < hi
    assert (lo + hi) / 2 == pytest.approx(-0.5)


def test_committed_output_matches_recomputation_and_audit_values() -> None:
    out = json.loads((_ROOT / tec.OUTPUT).read_text(encoding="utf-8"))
    te = out["type_enum_only"]
    assert {m: v["n_tasks"] for m, v in te.items()} == {
        "gemma2:9b": 30,
        "llama3.1:8b": 30,
        "qwen2.5:7b": 30,
    }
    assert [te[m]["mean_delta_pp"] for m in te] == [-37.78, -33.33, -16.67]
    for m in te:
        assert te[m]["n_tool_sets"] == 6
        lo, hi = te[m]["cluster_bootstrap_ci_pp"]
        t_lo, t_hi = te[m]["cluster_t_ci_pp"]
        assert t_hi - t_lo > hi - lo  # t(5) is the more conservative interval
    for p, meta in out["inputs"].items():
        assert tec.sha256_of(_ROOT / p) == meta["sha256"]
    assert tec.main(["--check"]) == 0

from __future__ import annotations

# EXP-1: mechanical doc-density scoring over the vetted 30-server pool + 2 anchors.
# Deterministic script only — git clone --depth 1, static parsing, no LLM/agent calls.
# Replaces an earlier LLM-agent-based extraction approach that was slow and repeatedly
# stalled (extraction is retrieval, not research).
import json
import shutil
import stat
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.exp1_doc_density import compute_doc_density  # noqa: E402
from agentgauge.exp1_tool_def_extractor import (  # noqa: E402
    CloneError,
    clone_shallow,
    extract_tools_for_repo,
)

REPO_ROOT = Path(__file__).parent.parent
FRAME_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_server_frame.json"
OUTPUT_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_doc_density_scores.json"


def _rmtree_windows_safe(path: Path) -> None:
    """shutil.rmtree that clears read-only bits git sets on .git/objects (Windows)."""

    def _on_error(func, p, exc_info):  # noqa: ANN001, ANN202 -- shutil onerror callback signature
        Path(p).chmod(stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=_on_error)


def load_target_repos() -> list[dict]:
    frame = json.loads(FRAME_PATH.read_text(encoding="utf-8"))
    targets: list[dict] = []
    for stratum_name, stratum in frame["strata"].items():
        for server in stratum["servers"]:
            targets.append(
                {
                    "server_id": server["server_id"],
                    "source_repo": server["source_repo"],
                    "language": server["language"],
                    "prior_stratum": stratum_name,
                    "is_anchor": False,
                }
            )
    for anchor in frame["validation_anchors"]:
        targets.append(
            {
                "server_id": anchor["server_id"],
                "source_repo": anchor["source_repo"],
                "language": anchor.get("language", "unknown"),
                "source_subpath": anchor.get("source_subpath", ""),
                "prior_stratum": "anchor",
                "is_anchor": True,
            }
        )
    return targets


def score_one(target: dict, workdir: Path) -> dict:
    repo_dir = workdir / target["server_id"]
    try:
        clone_shallow(target["source_repo"], repo_dir)
    except (CloneError, OSError) as exc:
        return {
            **target,
            "clone_ok": False,
            "clone_error": str(exc),
            "extraction_method": "n/a",
            "n_tools_extracted": 0,
            "metrics": None,
        }

    try:
        extraction_root = repo_dir
        subpath = target.get("source_subpath", "")
        if subpath:
            extraction_root = repo_dir / subpath
        tools, method = extract_tools_for_repo(extraction_root, target["language"])
    finally:
        _rmtree_windows_safe(repo_dir)

    metrics = compute_doc_density(target["server_id"], tools)
    return {
        **target,
        "clone_ok": True,
        "clone_error": None,
        "extraction_method": method,
        "n_tools_extracted": len(tools),
        "metrics": {
            "n_tools": metrics.n_tools,
            "mean_description_length": round(metrics.mean_description_length, 1),
            "pct_tools_with_description": round(metrics.pct_tools_with_description, 3),
            "pct_name_echo_only": round(metrics.pct_name_echo_only, 3),
            "param_description_coverage": round(metrics.param_description_coverage, 3),
            "composite_score": round(metrics.composite_score, 1),
        },
    }


def main() -> None:
    targets = load_target_repos()
    print(f"[exp1_score_doc_density] {len(targets)} repos to clone + score")

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="exp1_doc_density_") as tmp:
        workdir = Path(tmp)
        for i, target in enumerate(targets, 1):
            print(
                f"[{i}/{len(targets)}] {target['source_repo']} ({target['language']}) ...", end=" "
            )
            result = score_one(target, workdir)
            results.append(result)
            if result["clone_ok"]:
                m = result["metrics"]
                print(
                    f"n_tools={m['n_tools']} method={result['extraction_method']} "
                    f"composite={m['composite_score']}"
                )
            else:
                print(f"CLONE FAILED: {result['clone_error']}")

    n_clone_failed = sum(1 for r in results if not r["clone_ok"])
    n_zero_tools = sum(1 for r in results if r["clone_ok"] and r["n_tools_extracted"] == 0)
    n_regex_method = sum(1 for r in results if r.get("extraction_method") == "regex_best_effort")

    output = {
        "generated_date": str(date.today()),
        "frame_ref": "evals/fixtures/exp1_server_frame.json",
        "n_targets": len(targets),
        "n_clone_failed": n_clone_failed,
        "n_zero_tools_extracted": n_zero_tools,
        "n_regex_best_effort_extraction": n_regex_method,
        "note": (
            "n_zero_tools_extracted servers had extraction FAIL, not 'zero documented tools' -- "
            "treat as missing data, not a near-empty doc-density tier, when stratifying."
        ),
        "results": results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\n[done] {len(targets) - n_clone_failed}/{len(targets)} cloned+scored, "
        f"{n_zero_tools} zero-tool extractions, {n_regex_method} regex-best-effort."
    )
    print(f"[done] Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

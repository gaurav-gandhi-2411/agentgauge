from __future__ import annotations

# EXP-1 STEP 1 (mirroring) -- deterministic script, no LLM/agent calls.
#
# For the 23 fresh, doc-density-scored servers (frame v2, ratified 2026-07-04):
# git clone --depth 1 -> agentgauge.exp1_tool_def_extractor.extract_tools_for_repo()
# (same extractor already used and tested for doc-density scoring) -> ServerMirror
# fixture with verbatim name/description, hash-stamped, commit-pinned.
#
# For the 2 validation anchors (github-mcp, aws-iam-mcp): reuse the EXISTING,
# already-real, already-vetted RW1/RW2 catalogs (evals/fixtures/rw1_github_catalog.py,
# rw2_aws_iam_catalog.py) rather than re-deriving a weaker mechanical extraction --
# those are higher-fidelity (hand-verified against source, real JSON schemas) and are
# the SAME fixtures that already produced the published OUT-OF-REGIME finding these
# anchors exist to reproduce.
#
# Simplification, disclosed: EXP-1's regime classifier tests only tool SELECTION
# (task -> tool), never call-correctness, so mirrored params for the 23 fresh servers
# carry name only (annotation="Any", no defaults) -- full JSON-schema-typed params are
# not measured by the frozen protocol and are out of scope for this pass.
import json
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.exp1_doc_density import ExtractedTool  # noqa: E402
from agentgauge.exp1_mirror import (  # noqa: E402
    MirrorParam,
    MirrorTool,
    ServerMirror,
    save_mirror,
    tool_docstring_hash,
)
from agentgauge.exp1_tool_def_extractor import (  # noqa: E402
    CloneError,
    clone_shallow,
    extract_tools_for_repo,
)

REPO_ROOT = Path(__file__).parent.parent
FRAME_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_server_frame.json"
MIRRORS_DIR = REPO_ROOT / "evals" / "fixtures" / "exp1_mirrors"
MANIFEST_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_mirrors_manifest.json"


def _rmtree_windows_safe(path: Path) -> None:
    def _on_error(func, p, exc_info):  # noqa: ANN001, ANN202 -- shutil onerror callback signature
        Path(p).chmod(stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=_on_error)


def _git_head_sha(repo_dir: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15.0,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _extracted_to_mirror_tools(tools: list[ExtractedTool]) -> list[MirrorTool]:
    return [
        MirrorTool(
            name=t.name,
            docstring=t.description,
            params=[MirrorParam(name=p.name, annotation="Any") for p in t.params],
            source_hash=tool_docstring_hash(t.description),
        )
        for t in tools
    ]


def build_fresh_mirror(entry: dict, tier: str, workdir: Path) -> dict:
    server_id = entry["server_id"]
    repo_dir = workdir / server_id
    try:
        clone_shallow(entry["source_repo"], repo_dir)
    except (CloneError, OSError) as exc:
        return {"server_id": server_id, "mirrored_ok": False, "error": str(exc)}

    try:
        commit_sha = _git_head_sha(repo_dir)
        tools, method = extract_tools_for_repo(repo_dir, entry["language"])
    finally:
        _rmtree_windows_safe(repo_dir)

    if not tools:
        return {
            "server_id": server_id,
            "mirrored_ok": False,
            "error": f"0 tools extracted (method={method}) -- inconsistent with doc-density pass",
        }

    mirror = ServerMirror(
        server_id=server_id,
        source_repo=entry["source_repo"],
        language=entry["language"],
        stars=entry.get("stars") or 0,
        stratum=tier,
        tools=_extracted_to_mirror_tools(tools),
        notes=(
            f"commit={commit_sha}; extraction_method={method}; "
            f"doc_density_composite={entry['composite_score']}; "
            "params are name-only placeholders (annotation='Any') -- EXP-1 classifier "
            "tests selection only, not call-correctness."
        ),
    )
    save_mirror(mirror, MIRRORS_DIR / f"{server_id}.json")
    return {
        "server_id": server_id,
        "mirrored_ok": True,
        "n_tools": len(mirror.tools),
        "commit_sha": commit_sha,
        "extraction_method": method,
        "doc_density_tier": tier,
        "composite_score": entry["composite_score"],
    }


def build_anchor_mirrors() -> list[dict]:
    """Port the existing, already-real RW1/RW2 catalogs into ServerMirror format --
    higher fidelity than re-deriving via the mechanical extractor, and these are the
    SAME fixtures that already produced the published OUT-OF-REGIME finding."""
    from evals.fixtures.rw1_github_catalog import (
        ALL_TOOLS as RW1_ALL_TOOLS,
    )
    from evals.fixtures.rw1_github_catalog import (
        GITHUB_DOCSTRINGS,
    )
    from evals.fixtures.rw1_github_catalog import (
        TOOL_SCHEMAS as RW1_SCHEMAS,
    )
    from evals.fixtures.rw2_aws_iam_catalog import (
        ALL_TOOLS as RW2_ALL_TOOLS,
    )
    from evals.fixtures.rw2_aws_iam_catalog import (
        AWS_IAM_DOCSTRINGS,
    )
    from evals.fixtures.rw2_aws_iam_catalog import (
        TOOL_SCHEMAS as RW2_SCHEMAS,
    )

    def _schema_params(schema: dict) -> list[MirrorParam]:
        properties = schema.get("properties", {})
        return [
            MirrorParam(name=pname, annotation=pinfo.get("type", "Any"))
            for pname, pinfo in properties.items()
        ]

    rw1_tools = [
        MirrorTool(
            name=name,
            docstring=GITHUB_DOCSTRINGS[name],
            params=_schema_params(RW1_SCHEMAS.get(name, {})),
            source_hash=tool_docstring_hash(GITHUB_DOCSTRINGS[name]),
        )
        for name in RW1_ALL_TOOLS
    ]
    rw2_tools = [
        MirrorTool(
            name=name,
            docstring=AWS_IAM_DOCSTRINGS[name],
            params=_schema_params(RW2_SCHEMAS.get(name, {})),
            source_hash=tool_docstring_hash(AWS_IAM_DOCSTRINGS[name]),
        )
        for name in RW2_ALL_TOOLS
    ]

    github_mirror = ServerMirror(
        server_id="github-mcp",
        source_repo="github/github-mcp-server",
        language="go",
        stars=0,
        stratum="validation_anchor",
        tools=rw1_tools,
        notes=(
            "Ported from evals/fixtures/rw1_github_catalog.py (RW1, already real, "
            "already hash-asserted vs pkg/github/*.go source). known_result=OUT-OF-REGIME "
            "(exp4_regime_map.md: Arm A 100% (21/21), no headroom)."
        ),
    )
    aws_iam_mirror = ServerMirror(
        server_id="aws-iam-mcp",
        source_repo="awslabs/mcp (src/iam-mcp-server)",
        language="python",
        stars=0,
        stratum="validation_anchor",
        tools=rw2_tools,
        notes=(
            "Ported from evals/fixtures/rw2_aws_iam_catalog.py (RW2, already real, "
            "already asserted ARM_A_DESCRIPTIONS == AWS_IAM_DOCSTRINGS vs source). "
            "known_result=OUT-OF-REGIME (exp4_regime_map.md: Arm A 100% (29/29), no headroom)."
        ),
    )

    save_mirror(github_mirror, MIRRORS_DIR / "github-mcp.json")
    save_mirror(aws_iam_mirror, MIRRORS_DIR / "aws-iam-mcp.json")

    return [
        {
            "server_id": "github-mcp",
            "mirrored_ok": True,
            "n_tools": len(github_mirror.tools),
            "source": "ported from RW1 catalog",
            "doc_density_tier": "validation_anchor",
        },
        {
            "server_id": "aws-iam-mcp",
            "mirrored_ok": True,
            "n_tools": len(aws_iam_mirror.tools),
            "source": "ported from RW2 catalog",
            "doc_density_tier": "validation_anchor",
        },
    ]


def main() -> None:
    MIRRORS_DIR.mkdir(parents=True, exist_ok=True)
    frame = json.loads(FRAME_PATH.read_text(encoding="utf-8"))

    fresh_entries: list[tuple[dict, str]] = []
    for tier, servers in frame["strata"].items():
        for s in servers:
            fresh_entries.append((s, tier))

    print(f"[exp1_build_mirrors] {len(fresh_entries)} fresh servers to mirror")
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="exp1_mirror_") as tmp:
        workdir = Path(tmp)
        for i, (entry, tier) in enumerate(fresh_entries, 1):
            print(f"[{i}/{len(fresh_entries)}] {entry['server_id']} ({tier}) ...", end=" ")
            r = build_fresh_mirror(entry, tier, workdir)
            results.append(r)
            print(f"OK n_tools={r['n_tools']}" if r["mirrored_ok"] else f"FAILED: {r['error']}")

    print("[exp1_build_mirrors] anchors ...")
    anchor_results = build_anchor_mirrors()
    for r in anchor_results:
        print(f"  {r['server_id']}: OK n_tools={r['n_tools']} ({r['source']})")
    results.extend(anchor_results)

    n_ok = sum(1 for r in results if r["mirrored_ok"])
    manifest = {
        "experiment_id": "EXP-1",
        "step": "STEP 1 -- mirroring (pre-reg per_server_procedure)",
        "frame_ref": "evals/fixtures/exp1_server_frame.json (v2, RATIFIED 2026-07-04)",
        "n_targets": len(results),
        "n_mirrored_ok": n_ok,
        "n_failed": len(results) - n_ok,
        "framing_locks": [
            "Only 2/23 fresh servers are absolutely near-empty (0% description coverage) -- "
            "public-server under-documentation is RARE. This reproduces RW1/RW2 + the "
            "pre-registered 'public skews documented' caveat as the DOMINANT effect, not a "
            "sampling problem. A mostly-OUT-OF-REGIME result is the finding.",
            "doc_density_tier labels (well_documented/thin/near_empty) are RELATIVE to this "
            "23-server sample, not absolute bands. 'near_empty tier' = the least-documented "
            "third of a well-documented pool, NOT the under-documented segment. State this "
            "wherever per-tier prevalence is reported.",
        ],
        "results": results,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[done] {n_ok}/{len(results)} mirrored. Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()

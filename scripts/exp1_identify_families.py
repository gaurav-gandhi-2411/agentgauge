from __future__ import annotations

# EXP-1 STEP 2 (family identification) -- MECHANICAL COMPONENT ONLY.
#
# Pre-reg STEP 2 combines three signals: (a) prefix clustering, (b) embedding
# similarity (nomic-embed-text -- a model call), (c) manual domain review (a human
# judgment step). This script implements ONLY (a): deterministic, no model calls,
# no LLM/agent spend. Its output is CANDIDATE families requiring (b)+(c) before any
# contested task is authored -- do not treat this as the final family set.
#
# Prefix clustering here groups tool names by their leading snake_case/camelCase
# TOKEN (not raw longest-common-prefix), since that's what makes RW1/RW2's own
# hand-curated families cohere (e.g. "list_pull_requests" / "list_issues" /
# "list_commits" share the token "list", not a long literal string prefix). A raw
# LCP would either under- or over-cluster depending on incidental prefix overlap.
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.exp1_mirror import load_mirror  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIRRORS_DIR = REPO_ROOT / "evals" / "fixtures" / "exp1_mirrors"
MANIFEST_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_mirrors_manifest.json"
OUTPUT_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_family_candidates.json"

_MIN_TOKEN_LEN = 3  # pre-reg's ">=3-char" prefix threshold, applied to the leading token
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _leading_token(tool_name: str) -> str:
    spaced = _CAMEL_BOUNDARY.sub("_", tool_name)
    tokens = re.split(r"[_\-.\s]+", spaced)
    tokens = [t for t in tokens if t]
    return tokens[0].lower() if tokens else tool_name.lower()


def identify_candidate_families(tool_names: list[str]) -> dict[str, list[str]]:
    """Group tool names by leading token; keep only groups with >=2 tools and a
    leading token of length >=3 (pre-reg's prefix-clustering threshold)."""
    by_token: dict[str, list[str]] = {}
    for name in tool_names:
        token = _leading_token(name)
        if len(token) < _MIN_TOKEN_LEN:
            continue
        by_token.setdefault(token, []).append(name)
    return {f"{token}_family": names for token, names in by_token.items() if len(names) >= 2}


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    server_ids = [r["server_id"] for r in manifest["results"] if r["mirrored_ok"]]

    per_server: dict[str, dict] = {}
    n_with_candidate_family = 0
    for server_id in server_ids:
        mirror = load_mirror(MIRRORS_DIR / f"{server_id}.json")
        tool_names = [t.name for t in mirror.tools]
        families = identify_candidate_families(tool_names)
        n_in_family = sum(len(v) for v in families.values())
        per_server[server_id] = {
            "stratum": mirror.stratum,
            "n_tools": len(tool_names),
            "n_candidate_families": len(families),
            "n_tools_in_candidate_family": n_in_family,
            "candidate_families": families,
        }
        if families:
            n_with_candidate_family += 1

    output = {
        "experiment_id": "EXP-1",
        "step": "STEP 2 -- family identification, MECHANICAL COMPONENT ONLY (prefix clustering)",
        "method_note": (
            "Prefix clustering (pre-reg criterion a) only. Embedding similarity (b) and manual "
            "domain review (c) have NOT been run -- these are CANDIDATE families, not the final "
            "pre-registered set. No contested tasks should be authored from this file alone."
        ),
        "n_servers": len(server_ids),
        "n_servers_with_candidate_family": n_with_candidate_family,
        "n_servers_with_no_candidate_family": len(server_ids) - n_with_candidate_family,
        "servers": per_server,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"{n_with_candidate_family}/{len(server_ids)} servers have >=1 candidate family "
        f"(>=2 tools sharing a leading token)."
    )
    for server_id, info in per_server.items():
        print(
            f"  {server_id:38s} ({info['stratum']:18s}) "
            f"n_tools={info['n_tools']:4d} candidate_families={info['n_candidate_families']}"
        )
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

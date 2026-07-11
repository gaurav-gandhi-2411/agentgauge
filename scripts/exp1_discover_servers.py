from __future__ import annotations

# Discovery script for EXP-1: queries GitHub for MCP servers, applies stratification,
# and outputs a candidate list JSON for GG review before any scoring begins.
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OUTPUT_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_candidate_list.json"

# Known validation anchors — excluded from fresh sample, added separately
VALIDATION_ANCHORS = [
    {
        "server_id": "github-mcp",
        "source_repo": "github/github-mcp-server",
        "known_result": "OUT-OF-REGIME",
        "prior_experiment": "RW1",
    },
    {
        "server_id": "aws-iam-mcp",
        "source_repo": "awslabs/mcp",
        "known_result": "OUT-OF-REGIME",
        "prior_experiment": "RW2",
    },
]

ANCHOR_REPOS = {a["source_repo"] for a in VALIDATION_ANCHORS}

TARGET_PER_STRATUM = 10
TARGET_TOTAL = 30


def fetch_mcp_servers(max_results: int = 200) -> list[dict]:
    """Query GitHub for mcp-server topic repos via gh CLI.

    Returns parsed list of repo dicts (name, stars, language, url, description, topics).
    Uses NDJSON output from --jq for safe multi-page parsing.
    """
    cmd = [
        "gh",
        "api",
        "--paginate",
        ("search/repositories?q=topic:mcp-server&sort=stars&order=desc&per_page=100"),
        "--jq",
        (
            ".items[] | "
            "{name: .full_name, stars: .stargazers_count, language: .language, "
            "url: .html_url, description: .description, topics: .topics}"
        ),
    ]
    print(f"[fetch] Running: {' '.join(cmd[:3])} search/repositories?... --jq ...")
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
    )
    if result.returncode != 0:
        print(f"[ERROR] gh api failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    repos: list[dict] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            repos.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"[warn] Could not parse line: {line[:80]!r} — {exc}", file=sys.stderr)

    return repos[:max_results]


def deduplicate(repos: list[dict]) -> list[dict]:
    """Deduplicate by full repo name (owner/repo), keeping first (highest-star) occurrence."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in repos:
        key = r["name"]
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def compute_percentiles(values: list[int]) -> dict[str, float]:
    """Return p33 and p67 of a sorted list of integers."""
    if not values:
        return {"p33": 0.0, "p67": 0.0}
    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _pct(p: float) -> float:
        idx = (p / 100.0) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        frac = idx - lo
        return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

    return {"p33": _pct(33), "p67": _pct(67)}


def assign_strata(repos: list[dict]) -> tuple[list[dict], dict[str, float]]:
    """Assign stratum labels (high/mid/low) based on empirical star percentiles.

    Returns (annotated_repos, strata_bands) where strata_bands has
    {high_gte, mid_gte, low_lt} star cutoffs.
    """
    stars_list = [r["stars"] for r in repos]
    pcts = compute_percentiles(stars_list)
    high_gte = pcts["p67"]
    mid_gte = pcts["p33"]

    for r in repos:
        s = r["stars"]
        if s >= high_gte:
            r["stratum"] = "high"
        elif s >= mid_gte:
            r["stratum"] = "mid"
        else:
            r["stratum"] = "low"

    return repos, {
        "high_gte": round(high_gte, 1),
        "mid_gte": round(mid_gte, 1),
        "low_lt": round(mid_gte, 1),
    }


def select_candidates(repos: list[dict]) -> list[dict]:
    """Pick up to TARGET_PER_STRATUM per stratum, excluding validation anchors.

    Repos are already sorted by stars desc from the API. Within each stratum
    we preserve that order (highest stars first).
    """
    by_stratum: dict[str, list[dict]] = {"high": [], "mid": [], "low": []}
    for r in repos:
        if r["name"] in ANCHOR_REPOS:
            continue
        stratum = r.get("stratum", "low")
        if stratum in by_stratum and len(by_stratum[stratum]) < TARGET_PER_STRATUM:
            by_stratum[stratum].append(r)

    candidates: list[dict] = []
    rank = 1
    for stratum in ("high", "mid", "low"):
        for r in by_stratum[stratum]:
            name = r["name"]
            server_id = name.replace("/", "-")
            candidates.append(
                {
                    "rank": rank,
                    "stratum": stratum,
                    "server_id": server_id,
                    "source_repo": name,
                    "stars": r["stars"],
                    "language": r.get("language") or "unknown",
                    "url": r.get("url", ""),
                    "description": r.get("description") or "",
                    "topics": r.get("topics") or [],
                }
            )
            rank += 1

    return candidates


def print_summary(repos: list[dict], candidates: list[dict], bands: dict[str, float]) -> None:
    """Print human-readable summary for GG review."""
    print()
    print("=" * 60)
    print(f"EXP-1 Discovery Summary — {date.today()}")
    print("=" * 60)
    print(f"Total repos fetched (after dedup): {len(repos)}")
    stars = sorted(r["stars"] for r in repos)
    if stars:
        print(f"Stars range: {stars[0]} – {stars[-1]}")
        print(f"  p33={bands['mid_gte']:.0f}  p67={bands['high_gte']:.0f}")
    print()
    print("Stratum bands (fixed from empirical distribution):")
    print(f"  high  : >= {bands['high_gte']:.0f} stars")
    print(f"  mid   : >= {bands['mid_gte']:.0f} and < {bands['high_gte']:.0f} stars")
    print(f"  low   : <  {bands['low_lt']:.0f} stars")
    print()
    by_stratum: dict[str, list[dict]] = {"high": [], "mid": [], "low": []}
    for c in candidates:
        by_stratum[c["stratum"]].append(c)
    for stratum in ("high", "mid", "low"):
        grp = by_stratum[stratum]
        print(f"  {stratum.upper():4s} ({len(grp)}/{TARGET_PER_STRATUM}):")
        for c in grp[:5]:
            print(
                f"    [{c['rank']:2d}] {c['source_repo']:40s} {c['stars']:>6d} stars  {c['language']}"
            )
        if len(grp) > 5:
            print(f"         ... and {len(grp) - 5} more")
    print()
    print(f"Total candidates selected: {len(candidates)} / {TARGET_TOTAL} target")
    print(f"Validation anchors (separate): {len(VALIDATION_ANCHORS)}")
    print()
    print(f"Output: {OUTPUT_PATH}")
    print("=" * 60)


def main() -> None:
    print("[exp1_discover_servers] Fetching MCP servers from GitHub...")
    raw = fetch_mcp_servers(max_results=500)
    print(f"[fetch] Got {len(raw)} raw results")

    deduped = deduplicate(raw)
    print(f"[dedup] {len(deduped)} unique repos after deduplication")

    annotated, bands = assign_strata(deduped)
    candidates = select_candidates(annotated)

    # Backup pool (top 40/stratum, anchors excluded) so replacement candidates can be
    # swapped in during vetting without a second, non-reproducible discovery run.
    backup_pool: dict[str, list[dict]] = {"high": [], "mid": [], "low": []}
    for r in annotated:
        if r["name"] in ANCHOR_REPOS:
            continue
        stratum = r.get("stratum", "low")
        if stratum in backup_pool and len(backup_pool[stratum]) < 70:
            backup_pool[stratum].append(
                {
                    "server_id": r["name"].replace("/", "-"),
                    "source_repo": r["name"],
                    "stars": r["stars"],
                    "language": r.get("language") or "unknown",
                    "url": r.get("url", ""),
                    "description": r.get("description") or "",
                    "topics": r.get("topics") or [],
                }
            )

    output = {
        "generated_date": str(date.today()),
        "query": "topic:mcp-server",
        "total_found": len(deduped),
        "strata_bands": bands,
        "candidates": candidates,
        "validation_anchors": VALIDATION_ANCHORS,
        "backup_pool": backup_pool,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print_summary(annotated, candidates, bands)
    print(f"[done] Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

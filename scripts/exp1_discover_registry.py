from __future__ import annotations

# EXP-1 second discovery source: the official MCP registry (registry.modelcontextprotocol.io),
# the FIRST source named in the pre-registration but not used in the first (superseded)
# star-stratified frame -- see GG's ISSUE B correction. This is a self-published catalog
# (no popularity/quality signal), so it trades one bias (GitHub-topic-search skew toward
# repos that tag themselves well) for another (self-registration skew) -- both are combined
# and deduplicated with the GitHub pool for the doc-density re-stratification, not used alone.
import json
import re
import sys
from datetime import date
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).parent.parent
OUTPUT_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_registry_candidates.json"
GITHUB_CANDIDATES_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_candidate_list.json"

REGISTRY_BASE = "https://registry.modelcontextprotocol.io/v0/servers"
PAGE_LIMIT = 100
MAX_PAGES = 40  # bounds runtime; ~4000 entries, generous given cursor-order is stable

_GITHUB_REPO_RE = re.compile(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?/?$")


def fetch_registry_page(cursor: str | None) -> dict:
    params: dict[str, str | int] = {"limit": PAGE_LIMIT}
    if cursor:
        params["cursor"] = cursor
    resp = httpx.get(REGISTRY_BASE, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def fetch_all_registry_entries(max_pages: int = MAX_PAGES) -> list[dict]:
    entries: list[dict] = []
    cursor: str | None = None
    for page_num in range(max_pages):
        page = fetch_registry_page(cursor)
        servers = page.get("servers", [])
        if not servers:
            break
        entries.extend(servers)
        cursor = page.get("metadata", {}).get("nextCursor")
        print(f"[registry] page {page_num + 1}: +{len(servers)} (total {len(entries)})")
        if not cursor:
            break
    return entries


def extract_github_repo(entry: dict) -> str | None:
    """Return 'owner/repo' if this entry's repository points at GitHub, else None."""
    server = entry.get("server", {})
    repo = server.get("repository")
    if not repo or repo.get("source") != "github":
        return None
    url = repo.get("url", "")
    m = _GITHUB_REPO_RE.search(url)
    return m.group(1) if m else None


def is_latest(entry: dict) -> bool:
    meta = entry.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
    return bool(meta.get("isLatest", False)) and meta.get("status") == "active"


def dedupe_latest_github_only(entries: list[dict]) -> list[dict]:
    """Keep only isLatest+active entries with a GitHub repository; one per repo."""
    seen: set[str] = set()
    out: list[dict] = []
    for e in entries:
        if not is_latest(e):
            continue
        repo = extract_github_repo(e)
        if not repo or repo in seen:
            continue
        seen.add(repo)
        server = e["server"]
        out.append(
            {
                "server_id": repo.replace("/", "-"),
                "source_repo": repo,
                "mcp_registry_name": server.get("name", ""),
                "description": server.get("description", ""),
                "language": "unknown",  # registry doesn't report language; filled during vetting
                "url": f"https://github.com/{repo}",
                "registry_source": True,
            }
        )
    return out


def load_github_topic_search_repos() -> set[str]:
    if not GITHUB_CANDIDATES_PATH.exists():
        return set()
    data = json.loads(GITHUB_CANDIDATES_PATH.read_text(encoding="utf-8"))
    repos: set[str] = set()
    for c in data.get("candidates", []):
        repos.add(c["source_repo"])
    for stratum_list in data.get("backup_pool", {}).values():
        for c in stratum_list:
            repos.add(c["source_repo"])
    return repos


def main() -> None:
    print("[exp1_discover_registry] Fetching official MCP registry...")
    try:
        raw_entries = fetch_all_registry_entries()
    except httpx.HTTPError as exc:
        print(f"[ERROR] registry fetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"[fetch] {len(raw_entries)} raw entries (all versions)")

    github_only = dedupe_latest_github_only(raw_entries)
    print(f"[dedup] {len(github_only)} unique GitHub-backed servers (latest+active)")

    already_known = load_github_topic_search_repos()
    new_candidates = [c for c in github_only if c["source_repo"] not in already_known]
    overlap = len(github_only) - len(new_candidates)
    print(f"[overlap] {overlap} already present in GitHub-topic-search pool")
    print(f"[new] {len(new_candidates)} candidates unique to the registry source")

    output = {
        "generated_date": str(date.today()),
        "source": "registry.modelcontextprotocol.io/v0/servers",
        "total_registry_entries_fetched": len(raw_entries),
        "total_latest_active_github_backed": len(github_only),
        "overlap_with_github_topic_search": overlap,
        "new_candidates": new_candidates,
        "all_registry_github_candidates": github_only,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[done] Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

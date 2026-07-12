from __future__ import annotations

# EXP-1 STEP 4 -- batch runner for the remaining 9 servers (frame v5, N=10 total;
# lucasastorian-llmwiki already scored, see exp1_trial_lucasastorian-llmwiki_arm_a.json).
#
# Reuses run_arm_a from exp1_run_trial.py unchanged (same real gemma2:9b agent,
# same deterministic exact-match classification, same frozen protocol).
#
# Family selection: for each server, mechanical prefix-clustering candidates
# (evals/fixtures/exp1_family_candidates.json) were reviewed by hand for GENUINE
# confusability (a real within-family distinguishing dimension), not just a shared
# literal prefix -- e.g. LycheeMem's "lycheemem_family" (health/append_turn/
# consolidate) shares a prefix but has no real selection ambiguity, so no family is
# tested for it. 3 of 9 servers (Dataojitori-nocturne_memory, blazickjp-arxiv-mcp-server,
# LycheeMem-LycheeMem) have NO genuinely confusable family and are reported as such,
# not forced.
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from exp1_run_trial import run_arm_a, run_arm_b, to_json_safe  # noqa: E402

from agentgauge.exp1_classifier import ContestedTask  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent

NO_GENUINE_FAMILY = {
    "Dataojitori-nocturne_memory": (
        "No mechanical prefix-clustering candidate at all (7 tools, all distinct leading "
        "verbs: read/create/update/delete/add/manage/search)."
    ),
    "blazickjp-arxiv-mcp-server": (
        "No mechanical prefix-clustering candidate at all (8 tools, all distinct leading "
        "verbs/nouns: check/citation/download/get/list/read/search/reindex)."
    ),
    "LycheeMem-LycheeMem": (
        "Mechanical candidate found (lycheemem_family: health/append_turn/consolidate/"
        "lycheemem) but rejected on review -- these are a health-check, a turn-append, a "
        "consolidation trigger, and a status/dispatch tool; genuinely different operations "
        "with no real selection ambiguity, not a confusable pair despite the shared prefix."
    ),
}

FAMILIES: dict[str, list[ContestedTask]] = {
    "AminForou-mcp-gsc": [
        ContestedTask(
            task_id="gsc_1",
            family_id="delete_family",
            task_text=(
                "We're shutting down example.com entirely -- it should no longer be "
                "tracked as a Search Console property at all."
            ),
            gold_tool="delete_site",
        ),
        ContestedTask(
            task_id="gsc_2",
            family_id="delete_family",
            task_text=(
                "We restructured our XML feed for example.com and the old one at "
                "example.com/sitemap-old.xml is stale -- stop Google from crawling it, "
                "but keep monitoring the domain itself."
            ),
            gold_tool="delete_sitemap",
        ),
        ContestedTask(
            task_id="gsc_3",
            family_id="delete_family",
            task_text=(
                "One of our verified properties, https://old-brand.example.com, is being "
                "fully decommissioned -- remove it from our GSC account altogether."
            ),
            gold_tool="delete_site",
        ),
        ContestedTask(
            task_id="gsc_4",
            family_id="delete_family",
            task_text=(
                "We submitted the wrong XML feed by mistake for our domain property -- "
                "please unsubmit it so it stops showing in our sitemap list."
            ),
            gold_tool="delete_sitemap",
        ),
    ],
    "stefanoamorelli-sec-edgar-mcp": [
        ContestedTask(
            task_id="secedgar_1",
            family_id="discover_family",
            task_text=(
                "Before I pull specific numbers for Apple, show me what financial metrics "
                "are even tracked for this company so I know what's available to query."
            ),
            gold_tool="discover_company_metrics",
        ),
        ContestedTask(
            task_id="secedgar_2",
            family_id="discover_family",
            task_text=(
                "I need to see the full list of structured data fields reported inside "
                "Apple's most recent 10-K filing before extracting anything specific "
                "from it."
            ),
            gold_tool="discover_xbrl_concepts",
        ),
        ContestedTask(
            task_id="secedgar_3",
            family_id="discover_family",
            task_text=(
                "I want to search for any metrics related to 'revenue' that we could "
                "pull for Tesla -- just show me what exists first."
            ),
            gold_tool="discover_company_metrics",
        ),
        ContestedTask(
            task_id="secedgar_4",
            family_id="discover_family",
            task_text=(
                "Show me every structured tag present in this specific filing's "
                "accession number, filtered to the us-gaap namespace."
            ),
            gold_tool="discover_xbrl_concepts",
        ),
    ],
    "stickerdaniel-linkedin-mcp-server": [
        ContestedTask(
            task_id="linkedin_1",
            family_id="search_family",
            task_text="Find LinkedIn organizations working in the electric vehicle space.",
            gold_tool="search_companies",
        ),
        ContestedTask(
            task_id="linkedin_2",
            family_id="search_family",
            task_text=(
                "Look for open software engineer roles posted recently that offer remote work."
            ),
            gold_tool="search_jobs",
        ),
        ContestedTask(
            task_id="linkedin_3",
            family_id="search_family",
            task_text="I'm trying to find recruiters at Google I could connect with.",
            gold_tool="search_people",
        ),
        ContestedTask(
            task_id="linkedin_4",
            family_id="search_family",
            task_text=(
                "Search through my LinkedIn messages for anything mentioning a contract renewal."
            ),
            gold_tool="search_conversations",
        ),
    ],
    "taylorwilsdon-google_workspace_mcp": [
        ContestedTask(
            task_id="gws_1",
            family_id="send_family",
            task_text="Reply in our team's Google Chat space thread about tomorrow's standup.",
            gold_tool="send_message",
        ),
        ContestedTask(
            task_id="gws_2",
            family_id="send_family",
            task_text="Send an email to the client with the signed contract attached.",
            gold_tool="send_gmail_message",
        ),
        ContestedTask(
            task_id="gws_3",
            family_id="send_family",
            task_text="Forward that email thread about the outage to our on-call engineer.",
            gold_tool="send_gmail_message",
        ),
        ContestedTask(
            task_id="gws_4",
            family_id="send_family",
            task_text=(
                "Post an update to the on-call Chat space letting the team know the "
                "deploy finished."
            ),
            gold_tool="send_message",
        ),
    ],
    "mrexodia-ida-pro-mcp": [
        ContestedTask(
            task_id="ida_1",
            family_id="xrefs_family",
            task_text=(
                "Show me every place in the binary that calls or references this "
                "function's address."
            ),
            gold_tool="xrefs_to",
        ),
        ContestedTask(
            task_id="ida_2",
            family_id="xrefs_family",
            task_text=(
                "I need to find everywhere in the code that reads or writes to this "
                "specific struct member."
            ),
            gold_tool="xrefs_to_field",
        ),
        ContestedTask(
            task_id="ida_3",
            family_id="xrefs_family",
            task_text="What other functions reference this global symbol?",
            gold_tool="xrefs_to",
        ),
        ContestedTask(
            task_id="ida_4",
            family_id="xrefs_family",
            task_text="Find all the places that touch the 'flags' member of this structure.",
            gold_tool="xrefs_to_field",
        ),
    ],
    "datalayer-jupyter-mcp-server": [
        ContestedTask(
            task_id="jupyter_1",
            family_id="read_family",
            task_text=(
                "Give me an overview of all the cells in this notebook so I can figure "
                "out which one to edit."
            ),
            gold_tool="read_notebook",
        ),
        ContestedTask(
            task_id="jupyter_2",
            family_id="read_family",
            task_text=(
                "Show me exactly what's in cell number 5 of the currently open "
                "notebook, including its output."
            ),
            gold_tool="read_cell",
        ),
        ContestedTask(
            task_id="jupyter_3",
            family_id="read_family",
            task_text=(
                "I need a quick summary of the structure of this whole notebook "
                "before I decide where to insert new code."
            ),
            gold_tool="read_notebook",
        ),
        ContestedTask(
            task_id="jupyter_4",
            family_id="read_family",
            task_text="What's the output of the specific cell at index 12 right now?",
            gold_tool="read_cell",
        ),
    ],
}


# ── Oracle descriptions for families that show Arm A headroom (STEP 5) ────────────
# Human-authored (me, having read each server's real source/full docstrings above),
# targeting the WITHIN-family distinguishing dimension the truncated first-line
# listing (agentgauge.runner._build_tool_listing shows only line 1 of each
# docstring) doesn't surface. NOT generated, NOT quoting the tool's own name.
ORACLE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "AminForou-mcp-gsc": {
        "delete_sitemap": (
            "Immediately delete one specific sitemap from a property; does not list, "
            "inspect, or submit sitemaps."
        ),
        "manage_sitemaps": (
            "General-purpose sitemap tool for listing, inspecting, or submitting "
            "sitemaps; the dedicated delete tool is preferred for a straightforward "
            "single-sitemap removal."
        ),
    },
    "taylorwilsdon-google_workspace_mcp": {
        "send_message": "Posts a message into an internal team Google Chat space, not an email.",
        "send_gmail_message": ("Sends an email via Gmail to an email address, not a chat space."),
    },
    "mrexodia-ida-pro-mcp": {
        "xrefs_to": "Find references to a function, address, or symbol by its location in the binary.",
        "xrefs_to_field": (
            "Find references to one specific named field inside a struct or type "
            "definition, not a whole symbol or address."
        ),
    },
    "datalayer-jupyter-mcp-server": {
        "read_notebook": (
            "Read the full cell-by-cell content and structure of ONE specific "
            "notebook you already have open."
        ),
        "list_notebooks": (
            "Enumerate the names of MULTIPLE notebooks that have been used; does "
            "not show any notebook's content."
        ),
    },
}


async def main() -> None:
    results: dict[str, dict] = {}

    for server_id, reason in NO_GENUINE_FAMILY.items():
        print(f"[{server_id}] NO GENUINE FAMILY: {reason}")
        results[server_id] = {"server_id": server_id, "no_family_reason": reason}

    for server_id, tasks in FAMILIES.items():
        family_id = tasks[0].family_id
        print(f"\n[{server_id}] Running Arm A, family={family_id} ({len(tasks)} tasks)...")
        result_a = await run_arm_a(server_id=server_id, family_id=family_id, tasks=tasks)
        out_path = REPO_ROOT / "evals" / "fixtures" / f"exp1_trial_{server_id}_arm_a.json"
        out_path.write_text(
            json.dumps(to_json_safe(result_a), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(
            f"  -> accuracy={result_a['arm_a_accuracy']:.1%} "
            f"headroom_gated={result_a['headroom_gated']} aborted={result_a['aborted']}"
        )

        if not result_a["headroom_gated"]:
            results[server_id] = result_a
            continue

        oracle = ORACLE_DESCRIPTIONS.get(server_id)
        if oracle is None:
            print(
                f"  [WARN] headroom found but no oracle authored for {server_id} -- skipping Arm B"
            )
            results[server_id] = result_a
            continue

        print(f"[{server_id}] Running Arm B (oracle), family={family_id}...")
        result_b = await run_arm_b(
            server_id=server_id,
            family_id=family_id,
            tasks=tasks,
            arm_a_outcomes=result_a["arm_a_outcomes"],
            oracle_descriptions=oracle,
        )
        out_path_b = REPO_ROOT / "evals" / "fixtures" / f"exp1_trial_{server_id}_arm_b.json"
        out_path_b.write_text(
            json.dumps(to_json_safe(result_b), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(
            f"  -> arm_a={result_b['arm_a_accuracy']:.1%} arm_b={result_b['arm_b_accuracy']:.1%} "
            f"effect={result_b['effect_pp']:+.1f}pp in_regime={result_b['in_regime']}"
        )
        results[server_id] = result_b

    summary_path = REPO_ROOT / "evals" / "fixtures" / "exp1_trial_batch_summary.json"
    summary = {sid: _summarize(r) for sid, r in results.items()}
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nBatch summary written to {summary_path}")


def _verdict(r: dict) -> str:
    if r["aborted"]:
        return "OUT-OF-REGIME"
    if "in_regime" not in r:
        return "HEADROOM-NO-ORACLE-AUTHORED"
    return "IN-REGIME" if r["in_regime"] else "OUT-OF-REGIME (no recovery)"


def _summarize(r: dict) -> dict:
    if "no_family_reason" in r:
        return {"no_family": True, "reason": r["no_family_reason"]}
    return {
        "family_id": r["family_id"],
        "arm_a_accuracy": r["arm_a_accuracy"],
        "arm_b_accuracy": r.get("arm_b_accuracy"),
        "headroom_gated": r["headroom_gated"],
        "aborted": r["aborted"],
        "verdict": _verdict(r),
    }


if __name__ == "__main__":
    asyncio.run(main())

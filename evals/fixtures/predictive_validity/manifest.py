"""Predictive-validity study manifest.

Defines the fixed set of MCP tool-set fixtures used to test whether AgentGauge's
8-axis scoring correlates with real agent task success (see
``scripts/predictive_validity_study.py`` for the data-collection run and
``scripts/predictive_validity_analysis.py`` for the correlation analysis).

This module is import-only: constructing ``MANIFEST`` and validating the
agent/judge/generator model-family hygiene invariant (rule enforced by
``agentgauge.ab_harness.assert_agent_ne_judge_ne_generator``) are the only
module-level side effects. No MCP/Ollama connections happen here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentgauge.ab_harness import assert_agent_ne_judge_ne_generator
from evals.fixtures.t18_catalog import FAMILIES

# Repo root, resolved relative to this file
# (evals/fixtures/predictive_validity/manifest.py -> 3 parents up = repo root).
REPO_ROOT = Path(__file__).resolve().parents[3]

# Pinned models for this study. Agent must not share a model family with either
# the judge (llama3.1) or the T18 generator (qwen3) — enforced below at import time.
AGENT_MODEL = "gemma2:9b"
JUDGE_MODEL = "llama3.1:8b"

# Raises ValueError at import time if the hygiene invariant is violated. Keeping this
# as a module-level call (rather than only documenting it) means any future edit to
# AGENT_MODEL that collides with the judge/generator family fails fast, in code.
assert_agent_ne_judge_ne_generator(AGENT_MODEL)


@dataclass(frozen=True)
class ToolSetEntry:
    """One tool-set fixture in the predictive-validity manifest.

    Attributes:
        name: Stable identifier for this entry, used as the record key in
            ``results_raw.json`` and in analysis output.
        server_path: Path to the example MCP server script, relative to the repo
            root (e.g. ``"examples/echo_server.py"``). Resolve with
            ``resolve_server_path`` before spawning a stdio subprocess.
        tier: Free-text quality label (e.g. "bad" / "mediocre" / "good" / "mixed" /
            "real-world-mirror"). Only used for human-readable grouping in reports;
            not consumed by any scoring logic.
        tool_name_filter: When set, only tools whose ``.name`` is in this list are
            used for task generation and scoring. ``None`` means use all tools the
            server exposes.
    """

    name: str
    server_path: str
    tier: str
    tool_name_filter: list[str] | None = None


def resolve_server_path(entry: ToolSetEntry) -> Path:
    """Return the absolute path to ``entry``'s server script."""
    return REPO_ROOT / entry.server_path


# Two of the ten pre-registered T18 families (see evals/fixtures/t18_catalog.py),
# picked arbitrarily-but-fixed: this study measures whether AgentGauge's axis scores
# track task success across manifest entries, not family-specific selection dynamics,
# so any 2-of-10 families give an equally valid 12-tool subset. "data_fetch" and
# "notify" were chosen because they span distinct domains (read-path lookups vs.
# push/alerting) rather than two read-adjacent or two write-adjacent families, giving
# the subset some internal variety without needing all 10. Fixed here for
# reproducibility — do not change without re-running the study.
_T18_FAMILY_SUBSET: list[str] = FAMILIES["data_fetch"] + FAMILIES["notify"]

# Real-world-mirror tool-count rule: exp1 mirror servers build their tool list from a
# DOCSTRINGS dict (see agentgauge/CLAUDE.md note on this — a naive grep for repeated
# `types.Tool(` calls undercounts them). Verified by reading each file's DOCSTRINGS
# dict directly: jupyter mirror = 17 tools, arxiv mirror = 8 tools, linkedin mirror =
# 17 tools. All three are <= 20 tools, so no tool_name_filter slicing is needed. All
# three use a generic stub `call_tool` body (no live network calls, no external
# credentials) — safe to run as local stdio subprocesses.
MANIFEST: list[ToolSetEntry] = [
    # Core hand-authored fixtures.
    ToolSetEntry("echo_server", "examples/echo_server.py", "mixed"),
    ToolSetEntry("confusable_server", "examples/confusable_server.py", "bad"),
    ToolSetEntry("confusable_server_oracle", "examples/confusable_server_oracle.py", "good"),
    ToolSetEntry("grounded_server", "examples/grounded_server.py", "bad"),
    ToolSetEntry("grounded_server_oracle", "examples/grounded_server_oracle.py", "good"),
    ToolSetEntry("mediocre_server", "examples/mediocre_server.py", "mediocre"),
    ToolSetEntry("call_constraints_server", "examples/call_constraints_server.py", "bad"),
    ToolSetEntry(
        "call_constraints_server_oracle", "examples/call_constraints_server_oracle.py", "good"
    ),
    ToolSetEntry("call_constraints_v2_server", "examples/call_constraints_v2_server.py", "bad"),
    ToolSetEntry(
        "call_constraints_v2_server_oracle",
        "examples/call_constraints_v2_server_oracle.py",
        "good",
    ),
    # T18 family fixtures, all filtered to the same 12-tool subset
    # (data_fetch + notify families) across all 4 arms for a controlled comparison.
    ToolSetEntry(
        "t18_vague_server",
        "examples/t18_vague_server.py",
        "bad",
        tool_name_filter=list(_T18_FAMILY_SUBSET),
    ),
    ToolSetEntry(
        "t18_fixer_server",
        "examples/t18_fixer_server.py",
        "mediocre",
        tool_name_filter=list(_T18_FAMILY_SUBSET),
    ),
    ToolSetEntry(
        "t18_q2b_server",
        "examples/t18_q2b_server.py",
        "mediocre-good",
        tool_name_filter=list(_T18_FAMILY_SUBSET),
    ),
    ToolSetEntry(
        "t18_oracle_server",
        "examples/t18_oracle_server.py",
        "good",
        tool_name_filter=list(_T18_FAMILY_SUBSET),
    ),
    # Real-world mirrors: real tool names + verbatim public docstrings, generic stub
    # bodies (see EXP-1 generation note in each file's header). No filter needed —
    # all three have <= 20 tools.
    ToolSetEntry(
        "exp1_datalayer_jupyter_mcp_server_mirror",
        "examples/exp1_datalayer_jupyter_mcp_server_mirror.py",
        "real-world-mirror",
    ),
    ToolSetEntry(
        "exp1_datalayer_jupyter_mcp_server_mirror_oracle",
        "examples/exp1_datalayer_jupyter_mcp_server_mirror_oracle.py",
        "real-world-mirror-improved",
    ),
    ToolSetEntry(
        "exp1_blazickjp_arxiv_mcp_server_mirror",
        "examples/exp1_blazickjp_arxiv_mcp_server_mirror.py",
        "real-world-mirror",
    ),
    ToolSetEntry(
        "exp1_stickerdaniel_linkedin_mcp_server_mirror",
        "examples/exp1_stickerdaniel_linkedin_mcp_server_mirror.py",
        "real-world-mirror",
    ),
]

# ── Manifest expansion (18 -> 40): see PLAN note in blind_tasks.py / constraints.py
# for the sourcing rationale of each tier below. Existing 18 entries above are
# UNCHANGED — nothing here may edit them.

# Tier 1 (11 entries): RW1 (21 tools), RW2 (29 tools), P2A (48 tools) — each entry's
# tasks come 1:1 from that catalog's own pre-registered TASKS list (verified in
# blind_tasks.py). "_mirror" entries serve the catalog's real/thin baseline
# descriptions (same content class as "_arm_a"); "_arm_guardb" entries serve
# generator-produced descriptions (fall back to the baseline if not yet generated);
# "_arm_oracle"/"_arm_o" entries serve the hand-derived ceiling. RW2 has no oracle arm.
MANIFEST += [
    # RW1 — GitHub MCP mirror (21 tools, 4 arms, all filtered to the same catalog)
    ToolSetEntry("rw1_github_mirror", "examples/rw1_github_mirror.py", "real-world-mirror"),
    ToolSetEntry("rw1_arm_a", "examples/rw1_arm_a.py", "bad"),
    ToolSetEntry("rw1_arm_guardb", "examples/rw1_arm_guardb.py", "mediocre-good"),
    ToolSetEntry("rw1_arm_oracle", "examples/rw1_arm_oracle.py", "good"),
    # RW2 — AWS IAM MCP mirror (29 tools, 3 arms — no oracle variant exists for RW2)
    ToolSetEntry("rw2_aws_iam_mirror", "examples/rw2_aws_iam_mirror.py", "real-world-mirror"),
    ToolSetEntry("rw2_arm_a", "examples/rw2_arm_a.py", "bad"),
    ToolSetEntry("rw2_arm_guardb", "examples/rw2_arm_guardb.py", "mediocre-good"),
    # P2A — synthetic internal-proxy mirror (48 tools, 4 arms)
    ToolSetEntry(
        "p2a_internal_proxy_mirror", "examples/p2a_internal_proxy_mirror.py", "real-world-mirror"
    ),
    ToolSetEntry("p2a_arm_a", "examples/p2a_arm_a.py", "bad"),
    ToolSetEntry("p2a_arm_guardb", "examples/p2a_arm_guardb.py", "mediocre-good"),
    ToolSetEntry("p2a_arm_oracle", "examples/p2a_arm_oracle.py", "good"),
]

# Tier 2 (6 entries): Q3 (12 tools) and Q6 (23 tools) — catalog TASKS cover most but
# not all tools; blind_tasks.py tops up the gap tools (Q3: lookup_data, plan_event;
# Q6: save_record, archive_item, lookup_data, plan_event) the same way the original
# 18's T18 entries topped up their gap tools.
MANIFEST += [
    # Q3 — 12-tool store/delete/control catalog (empty-description arms + oracle)
    ToolSetEntry("q3_real_server", "examples/q3_real_server.py", "bad"),
    ToolSetEntry("q3_arm_a", "examples/q3_arm_a.py", "bad"),
    ToolSetEntry("q3_arm_o", "examples/q3_arm_o.py", "good"),
    # Q6 — Q3's 12 tools + 11 new already-passing tools (23 total)
    ToolSetEntry("q6_real_server", "examples/q6_real_server.py", "bad"),
    ToolSetEntry("q6_arm_a", "examples/q6_arm_a.py", "bad"),
    ToolSetEntry("q6_arm_f_doc_guarded", "examples/q6_arm_f_doc_guarded.py", "mediocre-good"),
]

# Tier 3 (4 entries): same 4 T18 server files already in the manifest above, but
# filtered to a DIFFERENT 2-family, 12-tool subset (data_write + validate) than the
# existing 4 entries (which use data_fetch + notify). Named with a "_set2" suffix so
# they don't collide with the existing entry names. Picked data_write/validate for
# the same reason the original pick documented: two families spanning distinct
# domains (mutating writes vs. non-mutating checks) rather than two similar ones.
_T18_FAMILY_SUBSET_SET2: list[str] = FAMILIES["data_write"] + FAMILIES["validate"]

MANIFEST += [
    ToolSetEntry(
        "t18_vague_server_set2",
        "examples/t18_vague_server.py",
        "bad",
        tool_name_filter=list(_T18_FAMILY_SUBSET_SET2),
    ),
    ToolSetEntry(
        "t18_fixer_server_set2",
        "examples/t18_fixer_server.py",
        "mediocre",
        tool_name_filter=list(_T18_FAMILY_SUBSET_SET2),
    ),
    ToolSetEntry(
        "t18_q2b_server_set2",
        "examples/t18_q2b_server.py",
        "mediocre-good",
        tool_name_filter=list(_T18_FAMILY_SUBSET_SET2),
    ),
    ToolSetEntry(
        "t18_oracle_server_set2",
        "examples/t18_oracle_server.py",
        "good",
        tool_name_filter=list(_T18_FAMILY_SUBSET_SET2),
    ),
]

# Tier 4 (1 entry): a 5th real-world mirror (7 tools, single arm, no existing task
# catalog) — a memory/knowledge-graph MCP server (Dataojitori/nocturne_memory). Real
# tool names + verbatim public docstrings, generic stub call_tool body (confirmed by
# direct read — no live network calls, no external credentials).
MANIFEST += [
    ToolSetEntry(
        "exp1_dataojitori_nocturne_memory_mirror",
        "examples/exp1_Dataojitori_nocturne_memory_mirror.py",
        "real-world-mirror",
    ),
]

# ── Phase 3 (5 entries): LLM-fixer-improved variants of 5 existing "before"
# fixtures, produced by agentgauge.fixer.run_fixer (generator=qwen3:8b,
# judge=llama3.1:8b — see scripts/build_fixed_fixtures.py). run_fixer only ever
# edits description text and per-parameter schema metadata (type/description) for
# EXISTING params, or adds brand-new schema metadata for previously-untyped
# params — it never renames or removes a tool or a parameter. Verified directly
# (not assumed): each pair below was loaded in-process and its list_tools() tool-
# name set AND per-tool parameter-name set were confirmed identical to the
# "before" counterpart before this entry was added. tier="fixer-improved" is a
# new, distinct label (not "good"/"oracle") because these are LLM-rewrite outputs
# scored automatically by the fixer's own accept/reject gate, not a hand-authored
# ceiling — worth separating in the Phase 3 predictive-validity analysis.
MANIFEST += [
    ToolSetEntry("grounded_server_fixed", "examples/grounded_server_fixed.py", "fixer-improved"),
    ToolSetEntry(
        "confusable_server_fixed", "examples/confusable_server_fixed.py", "fixer-improved"
    ),
    ToolSetEntry("mediocre_server_fixed", "examples/mediocre_server_fixed.py", "fixer-improved"),
    ToolSetEntry(
        "call_constraints_server_fixed",
        "examples/call_constraints_server_fixed.py",
        "fixer-improved",
    ),
    ToolSetEntry(
        "call_constraints_v2_server_fixed",
        "examples/call_constraints_v2_server_fixed.py",
        "fixer-improved",
    ),
]

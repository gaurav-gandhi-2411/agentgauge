from __future__ import annotations

import re
from dataclasses import dataclass, field

# Mechanical doc-density scoring for EXP-1 sampling-frame stratification.
#
# GG's correction (2026-07-02): stratifying the sampling frame by GitHub stars holds
# documentation quality roughly CONSTANT across strata (popularity correlates with
# polish), so a star-stratified sample cannot represent the "documented vs
# under-documented" axis the paper's thesis is actually about. This module scores
# doc density DIRECTLY from extracted tool definitions (name/description/param
# descriptions as they appear in source — the schema the AGENT sees) rather than from
# README prose, so the sampling frame can be re-stratified on the input axis the
# regime classifier is meant to explain.

# ── Extraction types ─────────────────────────────────────────────────────────────


@dataclass
class ExtractedParam:
    name: str
    description: str = ""  # verbatim from the tool's schema; "" if genuinely absent


@dataclass
class ExtractedTool:
    name: str
    description: str = ""  # verbatim MCP-level tool description; "" if genuinely absent
    params: list[ExtractedParam] = field(default_factory=list)


@dataclass
class DocDensityMetrics:
    server_id: str
    n_tools: int
    mean_description_length: float  # mean chars per tool description
    pct_tools_with_description: float  # fraction in [0, 1]
    pct_name_echo_only: float  # fraction in [0, 1]; among tools WITH a description
    param_description_coverage: float  # fraction in [0, 1]; 1.0 if no params exist
    composite_score: float  # 0-100, weighted combination — see compute_doc_density


# Target description length (chars) for a solid one-sentence tool description.
# Descriptions at or above this length score full marks on the length sub-metric;
# shorter descriptions score proportionally. Chosen from eyeballing "what+how"-style
# descriptions in the error_legibility calibration (docs/research — CLAUDE.md).
_DESC_LENGTH_TARGET = 60.0

_STOPWORDS = frozenset(
    {"a", "an", "the", "to", "of", "for", "and", "or", "this", "that", "with", "in", "on"}
)

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Split on non-alphanumerics, camelCase, and snake_case; drop stopwords/short tokens."""
    spaced = _CAMEL_BOUNDARY.sub(" ", text)
    words = _WORD.findall(spaced.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def is_name_echo_only(name: str, description: str) -> bool:
    """True iff a NON-EMPTY description adds no token beyond what the tool name already says.

    Empty descriptions are a separate failure mode (see pct_tools_with_description) and
    are never considered "echo-only" here.
    """
    if not description.strip():
        return False
    name_tokens = _tokenize(name)
    desc_tokens = _tokenize(description)
    novel = desc_tokens - name_tokens
    return len(novel) == 0


def compute_doc_density(server_id: str, tools: list[ExtractedTool]) -> DocDensityMetrics:
    """Compute mechanical doc-density metrics from extracted tool definitions.

    All four sub-metrics are measured directly from tool/param descriptions as they
    appear in source (the MCP schema surface an agent actually sees), never from
    README prose. composite_score weights: 30% description length, 25% description
    presence, 25% non-echo descriptions, 20% param-description coverage.
    """
    n = len(tools)
    if n == 0:
        return DocDensityMetrics(
            server_id=server_id,
            n_tools=0,
            mean_description_length=0.0,
            pct_tools_with_description=0.0,
            pct_name_echo_only=0.0,
            param_description_coverage=0.0,
            composite_score=0.0,
        )

    desc_lengths = [len(t.description.strip()) for t in tools]
    mean_len = sum(desc_lengths) / n
    with_desc = sum(1 for d in desc_lengths if d > 0)
    pct_with_desc = with_desc / n

    echo_count = sum(1 for t in tools if is_name_echo_only(t.name, t.description))
    pct_echo = echo_count / n

    all_params = [p for t in tools for p in t.params]
    if all_params:
        params_with_desc = sum(1 for p in all_params if p.description.strip())
        param_coverage = params_with_desc / len(all_params)
    else:
        # No params anywhere in the catalog — nothing to under-document; vacuously full
        # coverage rather than penalizing servers whose tools are legitimately niladic.
        param_coverage = 1.0

    desc_length_score = min(100.0, mean_len / _DESC_LENGTH_TARGET * 100.0)
    composite = (
        0.30 * desc_length_score
        + 0.25 * (pct_with_desc * 100.0)
        + 0.25 * ((1.0 - pct_echo) * 100.0)
        + 0.20 * (param_coverage * 100.0)
    )

    return DocDensityMetrics(
        server_id=server_id,
        n_tools=n,
        mean_description_length=mean_len,
        pct_tools_with_description=pct_with_desc,
        pct_name_echo_only=pct_echo,
        param_description_coverage=param_coverage,
        composite_score=composite,
    )


# ── Doc-density tiering ────────────────────────────────────────────────────────────

DocDensityTier = str  # "well_documented" | "thin" | "near_empty"


def assign_tiers(
    metrics: list[DocDensityMetrics],
) -> dict[str, DocDensityTier]:
    """Bucket servers into empirical terciles of composite_score.

    Mirrors the star-percentile stratification method from the original (superseded)
    star-based frame, but on the doc-density axis: bands are fixed from the empirical
    distribution of the candidate pool, not assumed in advance. Ties at a boundary are
    resolved by keeping the boundary inclusive on the lower tier.
    """
    if not metrics:
        return {}
    scores = sorted(m.composite_score for m in metrics)
    n = len(scores)

    def _percentile(p: float) -> float:
        idx = (p / 100.0) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        frac = idx - lo
        return scores[lo] * (1 - frac) + scores[hi] * frac

    p33 = _percentile(33)
    p67 = _percentile(67)

    tiers: dict[str, DocDensityTier] = {}
    for m in metrics:
        if m.composite_score >= p67:
            tiers[m.server_id] = "well_documented"
        elif m.composite_score >= p33:
            tiers[m.server_id] = "thin"
        else:
            tiers[m.server_id] = "near_empty"
    return tiers

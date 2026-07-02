from __future__ import annotations

import pytest

from agentgauge.exp1_doc_density import (
    DocDensityMetrics,
    ExtractedParam,
    ExtractedTool,
    assign_tiers,
    compute_doc_density,
    is_name_echo_only,
)

# ── is_name_echo_only ────────────────────────────────────────────────────────────


def test_name_echo_only_true_for_bare_restatement() -> None:
    assert is_name_echo_only("get_user", "Get user.") is True


def test_name_echo_only_true_for_camel_case_restatement() -> None:
    assert is_name_echo_only("getUserProfile", "Get user profile") is True


def test_name_echo_only_false_when_description_adds_info() -> None:
    assert (
        is_name_echo_only(
            "get_user", "Fetch the user's profile including email and last login timestamp."
        )
        is False
    )


def test_name_echo_only_false_when_description_empty() -> None:
    # Empty description is a distinct failure mode, never "echo-only".
    assert is_name_echo_only("get_user", "") is False
    assert is_name_echo_only("get_user", "   ") is False


def test_name_echo_only_stopwords_dont_count_as_novel() -> None:
    # "the" and "a" are stopwords; description is still just a restatement of the name.
    assert is_name_echo_only("delete_project", "Delete the project.") is True


# ── compute_doc_density ──────────────────────────────────────────────────────────


def test_compute_doc_density_empty_tools() -> None:
    result = compute_doc_density("empty-server", [])
    assert result.n_tools == 0
    assert result.composite_score == 0.0


def test_compute_doc_density_well_documented() -> None:
    tools = [
        ExtractedTool(
            name="search_papers",
            description=(
                "Search arXiv for papers matching a query string, filtered by category "
                "and date range, returning titles and abstracts."
            ),
            params=[
                ExtractedParam(name="query", description="The search query string."),
                ExtractedParam(name="category", description="arXiv category to filter by."),
            ],
        ),
        ExtractedTool(
            name="read_paper",
            description="Download and extract the full text of a specific arXiv paper by ID.",
            params=[ExtractedParam(name="paper_id", description="The arXiv paper identifier.")],
        ),
    ]
    result = compute_doc_density("arxiv-mcp-server", tools)
    assert result.n_tools == 2
    assert result.pct_tools_with_description == pytest.approx(1.0)
    assert result.pct_name_echo_only == pytest.approx(0.0)
    assert result.param_description_coverage == pytest.approx(1.0)
    assert result.composite_score > 80.0


def test_compute_doc_density_near_empty() -> None:
    tools = [
        ExtractedTool(name="get_user", description="", params=[ExtractedParam(name="id")]),
        ExtractedTool(name="set_user", description="", params=[ExtractedParam(name="id")]),
        ExtractedTool(
            name="list_users", description="List users.", params=[]
        ),  # echo-only, non-empty
    ]
    result = compute_doc_density("bare-server", tools)
    assert result.n_tools == 3
    assert result.pct_tools_with_description == pytest.approx(1 / 3)
    # Only list_users has a non-empty description, and it's echo-only.
    assert result.pct_name_echo_only == pytest.approx(1 / 3)
    assert result.param_description_coverage == pytest.approx(0.0)
    assert result.composite_score < 40.0


def test_compute_doc_density_no_params_is_vacuous_full_coverage() -> None:
    tools = [ExtractedTool(name="ping", description="Ping the server and return pong.", params=[])]
    result = compute_doc_density("ping-server", tools)
    assert result.param_description_coverage == pytest.approx(1.0)


def test_compute_doc_density_mean_description_length() -> None:
    tools = [
        ExtractedTool(name="a", description="x" * 10, params=[]),
        ExtractedTool(name="b", description="x" * 30, params=[]),
    ]
    result = compute_doc_density("s", tools)
    assert result.mean_description_length == pytest.approx(20.0)


def test_compute_doc_density_well_documented_scores_higher_than_near_empty() -> None:
    good = compute_doc_density(
        "good",
        [
            ExtractedTool(
                name="create_memory",
                description=(
                    "Create a new persistent memory entry with the given content and tags, "
                    "returning its unique identifier for later retrieval."
                ),
                params=[
                    ExtractedParam(name="content", description="The text content to store."),
                    ExtractedParam(name="tags", description="Optional list of tags."),
                ],
            )
        ],
    )
    bad = compute_doc_density(
        "bad",
        [ExtractedTool(name="create_memory", description="", params=[ExtractedParam(name="x")])],
    )
    assert good.composite_score > bad.composite_score + 40.0


# ── assign_tiers ──────────────────────────────────────────────────────────────────


def _metrics(server_id: str, score: float) -> DocDensityMetrics:
    return DocDensityMetrics(
        server_id=server_id,
        n_tools=5,
        mean_description_length=score,  # irrelevant to tiering; composite_score matters
        pct_tools_with_description=1.0,
        pct_name_echo_only=0.0,
        param_description_coverage=1.0,
        composite_score=score,
    )


def test_assign_tiers_empty() -> None:
    assert assign_tiers([]) == {}


def test_assign_tiers_splits_into_three_bands() -> None:
    metrics = [_metrics(f"s{i}", float(i)) for i in range(9)]  # scores 0..8
    tiers = assign_tiers(metrics)
    assert set(tiers.values()) == {"well_documented", "thin", "near_empty"}
    # highest scores land well_documented, lowest land near_empty
    assert tiers["s8"] == "well_documented"
    assert tiers["s0"] == "near_empty"


def test_assign_tiers_all_identical_scores_go_to_one_tier() -> None:
    metrics = [_metrics(f"s{i}", 50.0) for i in range(5)]
    tiers = assign_tiers(metrics)
    # p33 == p67 == 50.0 here, so every score >= p67 -> well_documented
    assert all(t == "well_documented" for t in tiers.values())

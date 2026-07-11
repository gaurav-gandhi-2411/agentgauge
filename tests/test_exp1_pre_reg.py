from __future__ import annotations

import json
import pathlib

from agentgauge.frozen_protocol import JUDGE_MODEL, JUDGE_SEED

PRE_REG_PATH = pathlib.Path("evals/fixtures/exp1_pre_registration.json")


def _load() -> dict:
    return json.loads(PRE_REG_PATH.read_text(encoding="utf-8"))


def test_pre_registration_parses() -> None:
    data = _load()
    assert isinstance(data, dict)


def test_required_top_level_keys() -> None:
    data = _load()
    for key in ("experiment_id", "regime_classifier", "sampling_frame", "frozen_protocol"):
        assert key in data, f"Missing required key: {key}"


def test_experiment_id() -> None:
    assert _load()["experiment_id"] == "EXP-1"


def test_sampling_frame_counts() -> None:
    sf = _load()["sampling_frame"]
    assert sf["target_count"] == 30
    assert sf["freshly_sampled_count"] == 28
    assert sf["validation_anchor_count"] == 2


def test_validation_anchors() -> None:
    data = _load()
    anchors = data["validation_anchors"]["servers"]
    assert len(anchors) == 2
    ids = {a["id"] for a in anchors}
    assert "github-mcp" in ids
    assert "aws-iam-mcp" in ids


def test_frozen_protocol_matches_module() -> None:
    fp = _load()["frozen_protocol"]
    assert fp["judge_model"] == JUDGE_MODEL
    assert fp["judge_seed"] == JUDGE_SEED


def test_score_every_one_and_no_post_hoc_drop() -> None:
    sf = _load()["sampling_frame"]
    assert sf["score_every_one"] is True
    assert sf["drop_post_hoc"] is False


def test_stratified_sampling() -> None:
    sf = _load()["sampling_frame"]
    strata = sf["strata"]
    assert set(strata.keys()) == {"high", "mid", "low"}
    total = sum(s["target_count"] for s in strata.values())
    assert total == 30


def test_go_not_excluded() -> None:
    sf = _load()["sampling_frame"]
    filters = sf["filters"]
    lang = filters.get("languages", "")
    assert "Go" in lang or "all" in lang.lower() or "ALL" in lang

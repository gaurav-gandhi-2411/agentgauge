from __future__ import annotations

import json
from pathlib import Path

import typer.main

from agentgauge.cli import app

RESULTS = Path(__file__).parent.parent / "evals/fixtures/recalibration_seedfix/results.json"


def _trials_help(command: str) -> str:
    cmd = typer.main.get_command(app).commands[command]  # type: ignore[attr-defined]
    return next(p.help for p in cmd.params if p.name == "trials")


def test_trials_help_quotes_the_measured_icc() -> None:
    """The --trials help states ICC from results.json; fails if the fixture is re-measured and
    the text is not updated (published numbers regenerate with the metric, same change)."""
    icc = json.loads(RESULTS.read_text(encoding="utf-8"))["new_gold"]["metrics"]["icc"]
    expected = f"ICC(1)={icc['point']:.2f} (95% CI {icc['ci_lo']:.2f}-{icc['ci_hi']:.2f})"
    assert expected in _trials_help("diff")
    assert expected in _trials_help("eval")


def test_diff_trials_help_quotes_the_simulated_mde_and_sensitivity_range() -> None:
    cells = json.loads(RESULTS.read_text(encoding="utf-8"))["mde"]["cells"]
    gold = next(
        c["mde"]
        for c in cells
        if c["label"].startswith("NEW constants, gold-tool grouping") and c["n_tasks"] == 100
    )
    sens = [c["mde"] for c in cells if "bootstrap quantile" in c["label"] and c["n_tasks"] == 100]
    help_text = _trials_help("diff")
    assert f"MDE is {gold:.3f}" in help_text
    assert f"{min(sens):.3f}-" in help_text and f"{max(sens):.3f})" in help_text


def test_trials_help_recommends_more_tasks_over_more_trials() -> None:
    for command in ("diff", "eval"):
        text = " ".join(_trials_help(command).split()).lower()
        assert "distinct tasks" in text and "not more trials per task" in text

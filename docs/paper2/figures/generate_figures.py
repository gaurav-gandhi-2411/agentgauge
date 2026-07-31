"""Generate docs/paper2/figures/*.png from already-committed, already-measured data only.

No new experiments, no re-derivation. Every constant below is either read directly from a
committed evals/fixtures/*.json file, or hard-coded from a reports/*.md table with an inline
provenance comment -- both are cited in docs/paper2/provenance.md and must not be edited here
without updating that ledger too.

Run: python docs/paper2/figures/generate_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "evals" / "fixtures"
OUT_DIR = Path(__file__).resolve().parent

plt.rcParams.update({"font.size": 10, "figure.dpi": 150, "savefig.dpi": 150})


def fig_mde_curve() -> None:
    """MDE vs. corpus size (n_tasks), full-corpus grid. Source: reports/v2_5_task3_mde_completion.md
    lines 17-23 (trials_per_task=1, n_simulations=2000, 80% power), independently re-verified to
    4 decimals by a separate agent (lines 67-88). SHA 78fff2f."""
    n_tasks = [62, 100, 150, 200, 253]
    mde = [0.1061, 0.0848, 0.0689, 0.0605, 0.0537]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(n_tasks, mde, marker="o", color="#1f5aa6", linewidth=2)
    ax.axhline(0.10, color="#a63f1f", linestyle="--", linewidth=1, label="0.10 ship target")
    ax.set_ylim(0.04, 0.12)
    # Text anchored in axes-fraction coordinates so it can never force the y-axis to
    # autoscale around it (the bug this replaced: xytext in DATA coords at y=0.16, far above
    # the y<=0.11 data range, silently expanded the axis and squashed the real plot).
    ax.annotate(
        f"n=253\nMDE={mde[-1]}",
        xy=(253, mde[-1]),
        xycoords="data",
        xytext=(0.62, 0.55),
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "->", "color": "gray"},
    )
    ax.set_xlabel("Tasks per arm (trials_per_task=1)")
    ax.set_ylabel("Minimum detectable effect (MDE)")
    ax.set_title("MDE vs. corpus size, paired+CUPED estimator, 80% power")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "mde_curve.png")
    plt.close(fig)


def fig_estimator_ablation() -> None:
    """Estimator component ablation at n=20 tasks/arm, 80% power.
    Source: evals/fixtures/v2_1_mde_ablation.json (mde_ablation_table, n_tasks=20, power=0.8),
    matching reports/v2_1_estimator_rebuild.md lines 26-45. SHA 78fff2f."""
    with (FIXTURES / "v2_1_mde_ablation.json").open(encoding="utf-8") as f:
        data = json.load(f)
    row = next(r for r in data["mde_ablation_table"] if r["n_tasks"] == 20 and r["power"] == 0.8)

    stages = ["Trial-level\nbaseline", "+ Task-level\nunit", "+ Paired\n+ CRN", "+ CUPED\n(full stack)"]
    values = [
        row["mde_v2_baseline_trial_level"],
        row["mde_task_level_unpaired"],
        row["mde_paired"],
        row["mde_paired_cuped"],
    ]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(stages, values, color=["#a6a6a6", "#7fa8d9", "#3d7ebf", "#1f5aa6"])
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f"{v:.3f}", ha="center", fontsize=9)
    ax.set_ylabel("MDE (n=20 tasks/arm, 80% power)")
    ax.set_title("Estimator component ablation")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "estimator_ablation.png")
    plt.close(fig)


def fig_allocation_grid_heatmap() -> None:
    """Full 16-cell (4 trials/task x 4 tasks/arm) MDE grid at 80% power.
    Source: evals/fixtures/v2_2_optimal_allocation.json ("grid", power=0.8 rows) -- the
    committed fixture backing reports/v2_2_optimal_allocation.md's 12-row markdown excerpt;
    the fixture itself has all 16 cells at 80% power (some cells were omitted from the
    report's prose table for brevity, not because they weren't run). SHA 78fff2f."""
    with (FIXTURES / "v2_2_optimal_allocation.json").open(encoding="utf-8") as f:
        data = json.load(f)
    grid = [r for r in data["grid"] if r["power"] == 0.8]

    trials_vals = [1, 2, 3, 5]
    tasks_vals = [20, 50, 100, 150]
    matrix = [[float("nan")] * len(tasks_vals) for _ in trials_vals]
    for r in grid:
        i = trials_vals.index(r["trials_per_task"])
        j = tasks_vals.index(r["n_tasks"])
        matrix[i][j] = r["mde"]

    fig, ax = plt.subplots(figsize=(6, 4.5))
    im = ax.imshow(matrix, cmap="RdYlGn_r", aspect="auto", vmin=0.05, vmax=0.19)
    ax.set_xticks(range(len(tasks_vals)))
    ax.set_xticklabels([f"{t}" for t in tasks_vals])
    ax.set_yticks(range(len(trials_vals)))
    ax.set_yticklabels([f"{t}" for t in trials_vals])
    ax.set_xlabel("Tasks per arm")
    ax.set_ylabel("Trials per task")
    ax.set_title("MDE across the allocation grid (80% power)")
    for i in range(len(trials_vals)):
        for j in range(len(tasks_vals)):
            v = matrix[i][j]
            if v == v:  # not NaN
                is_optimal = trials_vals[i] == 1 and tasks_vals[j] == 100
                ax.text(
                    j, i, f"{v:.3f}", ha="center", va="center",
                    fontsize=9, fontweight="bold" if is_optimal else "normal",
                    color="black",
                )
            else:
                ax.text(j, i, "n/a", ha="center", va="center", fontsize=8, color="gray")
    fig.colorbar(im, ax=ax, label="MDE")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "allocation_grid_heatmap.png")
    plt.close(fig)


def fig_artifact_taxonomy_table() -> None:
    """Compact visual index of the ten artifact classes -- summary only; full mechanism/
    discovery/detector detail lives in main.tex Table 1 and provenance.md SS4. No numbers
    plotted here beyond the class list itself, so no separate provenance line is needed."""
    classes = [
        "1. Task/answer leakage",
        "2. Tool-name ceiling",
        "3. Zero-vector empty-string embedding",
        "4. Self-descriptive-name confound",
        "5. Subset-vs-catalog mismatch",
        "6. LCG index saturation",
        "7. Scoring-reference mismatch*",
        "8. Fixture-schema hallucination",
        "9. Benchmark-construction bias",
        "10. Probe variance mis-calibration*",
    ]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.axis("off")
    y0 = 0.95
    dy = 0.09
    ax.text(0.02, 1.0, "Ten measurement-artifact classes", fontsize=13, fontweight="bold",
            transform=ax.transAxes)
    for i, c in enumerate(classes):
        starred = c.endswith("*")
        label = c[:-1] if starred else c
        color = "#a63f1f" if starred else "#1f1f1f"
        ax.text(0.04, y0 - i * dy, label, fontsize=11, color=color, transform=ax.transAxes)
    ax.text(0.02, y0 - len(classes) * dy - 0.03,
            "* produced a false positive the authors initially believed (see main.tex SS6.1-6.2)",
            fontsize=8.5, style="italic", color="#555555", transform=ax.transAxes)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "artifact_taxonomy_table.png")
    plt.close(fig)


def fig_attribution_cost_crossover() -> None:
    """Cost-crossover: full re-eval-equivalent trial cost vs. n_tasks, and the n_changed value
    above which exhaustive_ablation / sampled_shapley stop being cheaper than a full re-eval.
    Source: reports/v0_5_probe_power_fix.md SS5 (Task 2e) crossover-analysis table, the only
    report containing this exact three-row table. SHA 3d79172."""
    n_tasks_vals = [24, 48, 128]
    exhaustive_crossover = [10.5, 5.3, 2.0]
    shapley_crossover = [21.1, 10.5, 4.0]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(n_tasks_vals, exhaustive_crossover, marker="o", label="exhaustive_ablation crossover",
            color="#a63f1f")
    ax.plot(n_tasks_vals, shapley_crossover, marker="s", label="sampled_shapley crossover",
            color="#1f5aa6")
    ax.fill_between(n_tasks_vals, 0, exhaustive_crossover, alpha=0.08, color="#a63f1f")
    ax.set_xlabel("n_tasks (probe-level allocation)")
    ax.set_ylabel("n_changed tools above which the\nstrategy costs more than a full re-eval")
    ax.set_title("Attribution cost-crossover vs. full re-evaluation")
    ax.annotate(
        "accuracy-adequate\nregime (n_tasks=128):\ncrossover at ~2-4 tools",
        xy=(128, 2.0), xytext=(60, 12),
        arrowprops={"arrowstyle": "->", "color": "gray"}, fontsize=8.5,
    )
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "attribution_cost_crossover.png")
    plt.close(fig)


if __name__ == "__main__":
    fig_mde_curve()
    fig_estimator_ablation()
    fig_allocation_grid_heatmap()
    fig_artifact_taxonomy_table()
    fig_attribution_cost_crossover()
    print("Wrote 5 figures to", OUT_DIR)

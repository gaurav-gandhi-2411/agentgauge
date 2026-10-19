"""Fill README.md's recalibration-metrics block from the Task 2 re-measurement output.

The README must never present the fixed-seed numbers (MDE, ship target, null false-alarm per
stratum, abstention, ICC / zero-variance share) as current. Those figures are being re-measured with
per-trial seeds; ``scripts/recalibration_analyze.py`` writes
``evals/fixtures/recalibration_seedfix/results.json``. This script owns the generated block:

    <!-- BEGIN recalibration-metrics (generated) -->
    ...
    <!-- END recalibration-metrics -->

* No results file  -> the block says ``Re-measurement pending - these figures are under revision``
  and shows no number.
* Results file     -> old-vs-new tables with 95% CIs, the tool-set subset used, n, the source file
  path and the git commit the block was rendered at.

``--check`` re-renders in memory and exits 1 if the README block differs (the rendered-at-commit
line is ignored: it changes on every commit and would make the check permanently stale).

Exit codes: 0 ok / up to date, 1 stale (``--check`` only), 2 error (missing markers, unreadable or
malformed results). A malformed results file is an error, never silently rendered as "pending":
a gate that cannot read its input must not report success (fail closed).

Usage::

    python scripts/render_readme_metrics.py            # rewrite the block in README.md
    python scripts/render_readme_metrics.py --check    # CI: non-zero if the block is stale
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BEGIN = "<!-- BEGIN recalibration-metrics (generated) -->"
END = "<!-- END recalibration-metrics -->"
PENDING_LINE = "Re-measurement pending - these figures are under revision"
DEFAULT_RESULTS = "evals/fixtures/recalibration_seedfix/results.json"
DEFAULT_README = "README.md"
SHA_PREFIX = "Rendered at commit: "
# MDE simulations below this are a preview, not the 2000-simulation grid the old figures used.
FULL_MDE_SIMS = 2000
SHIP_TARGET = 0.10  # smallest regression the harness is meant to detect (10 points)

OLD_LABEL = "OLD constants"
GOLD_LABEL = "NEW constants, gold-tool grouping (point)"
TRUE_LABEL = "NEW constants, true-task grouping (point)"
SENSITIVITY_MARK = "bootstrap quantile"


class RenderError(Exception):
    """Raised for unusable input; the CLI maps it to exit code 2."""


def git_short_sha(root: Path = ROOT) -> str:
    """Return ``git rev-parse --short HEAD`` or ``unknown`` if git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


def _num(value: Any, digits: int = 3) -> str:
    return "n/a" if value is None else f"{float(value):.{digits}f}"


def _ci(metric: dict[str, Any] | None, digits: int = 3) -> str:
    """Format ``{point, ci_lo, ci_hi}`` as ``point [lo, hi]``."""
    if not metric or metric.get("point") is None:
        return "n/a"
    lo, hi = metric.get("ci_lo"), metric.get("ci_hi")
    if lo is None or hi is None:
        return _num(metric["point"], digits)
    return f"{_num(metric['point'], digits)} [{_num(lo, digits)}, {_num(hi, digits)}]"


def _rate(cell: dict[str, Any] | None) -> str:
    """Format a ``{k, N, rate_pct, wilson_lo_pct, wilson_hi_pct}`` block."""
    if not cell:
        return "n/a"
    return (
        f"{cell['k']}/{cell['N']} = {cell['rate_pct']:.2f}% "
        f"[{cell['wilson_lo_pct']:.2f}, {cell['wilson_hi_pct']:.2f}]"
    )


def _require(results: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = results
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            raise RenderError(f"results file is missing key {'.'.join(path)!r}")
        cur = cur[key]
    return cur


def validate(results: dict[str, Any]) -> None:
    """Fail loudly if the results do not have the keys the renderer reads."""
    for path in (
        ("tool_sets_used",),
        ("tool_sets_dropped_partial_or_incomplete",),
        ("n_new_rows_used",),
        ("inputs",),
        ("old_full", "metrics"),
        ("old_restricted", "metrics"),
        ("new_gold", "metrics"),
        ("diff_new_minus_old",),
        ("null", "old_full", "by_stratum"),
        ("null", "old_restricted", "by_stratum"),
        ("null", "new", "by_stratum"),
        ("mde", "cells"),
        ("mde", "sims"),
    ):
        _require(results, path)


def _variance_table(results: dict[str, Any]) -> list[str]:
    rows = (
        ("Zero-variance share of (tool set, task) groups, %", "zero_var_share_pct", 1),
        ("ICC(1)", "icc", 3),
        ("Between-task share of variance, %", "pct_between_task", 1),
        ("Between-trial (within-task) share, %", "pct_between_trial", 1),
        ("Baseline success rate", "baseline", 3),
        ("sigma_task", "sigma_task", 3),
        ("resid_sd (within-task trial noise)", "resid_sd", 3),
    )
    out = [
        "| Quantity | Old, all tool sets | Old, same subset as new | New (per-trial seeds) "
        "| New - old (paired) |",
        "|---|---|---|---|---|",
    ]
    for label, key, digits in rows:
        out.append(
            f"| {label} | {_ci(results['old_full']['metrics'].get(key), digits)} "
            f"| {_ci(results['old_restricted']['metrics'].get(key), digits)} "
            f"| {_ci(results['new_gold']['metrics'].get(key), digits)} "
            f"| {_ci(results['diff_new_minus_old'].get(key), digits)} |"
        )
    return out


def _mde_cells(results: dict[str, Any], prefix: str, n_tasks: int) -> list[dict[str, Any]]:
    return [
        c
        for c in results["mde"]["cells"]
        if c["label"].startswith(prefix) and c["n_tasks"] == n_tasks
    ]


def _sensitivity_note(point: float, sens: list[float]) -> str:
    """Say so when the calibration-uncertainty range straddles the ship target."""
    if sens and min(sens) <= SHIP_TARGET < max(sens):
        return (
            f" The target is met at the point estimate but not across the sensitivity range "
            f"({_num(min(sens), 4)} to {_num(max(sens), 4)}): with resid_sd at its upper bootstrap "
            "quantile the MDE exceeds it."
        )
    return ""


def _mde_table(results: dict[str, Any]) -> list[str]:
    sims = results["mde"]["sims"]
    out = [
        "| Tasks per arm x trials | MDE, old constants | MDE, new constants (gold grouping) "
        "| MDE, new constants (true-task grouping) | New-constant sensitivity range |",
        "|---|---|---|---|---|",
    ]
    for n_tasks in (100, 253):
        cells: dict[str, str] = {}
        for key, prefix in (("old", OLD_LABEL), ("gold", GOLD_LABEL), ("true", TRUE_LABEL)):
            found = _mde_cells(results, prefix, n_tasks)
            cells[key] = _num(found[0]["mde"], 4) if found else "n/a"
        sens = [
            c["mde"]
            for c in results["mde"]["cells"]
            if SENSITIVITY_MARK in c["label"] and c["n_tasks"] == n_tasks
        ]
        rng = f"{_num(min(sens), 4)} to {_num(max(sens), 4)}" if sens else "n/a"
        out.append(
            f"| {n_tasks} x 1 | {cells['old']} | {cells['gold']} | {cells['true']} | {rng} |"
        )
    gold100 = _mde_cells(results, GOLD_LABEL, 100)
    sens_100 = [
        c["mde"]
        for c in results["mde"]["cells"]
        if SENSITIVITY_MARK in c["label"] and c["n_tasks"] == 100
    ]
    if gold100:
        met = gold100[0]["mde"] <= SHIP_TARGET
        out.append("")
        n_old = len(results.get("old_full", {}).get("tool_sets", []))
        partial = (
            int(sims) < FULL_MDE_SIMS
            or bool(results["tool_sets_dropped_partial_or_incomplete"])
            or len(results["tool_sets_used"]) < n_old
        )
        out.append(
            f"Ship target (detect a 10-point regression, i.e. {SHIP_TARGET:.2f}, at 80% power "
            "with 100 tasks x 1 trial), evaluated on the new gold-grouping constants: "
            f"**{'met' if met else 'not met'}** (MDE {_num(gold100[0]['mde'], 4)})"
            + (
                " - PROVISIONAL: fewer simulations, or fewer tool sets, than the original grid."
                if partial
                else "."
            )
            + _sensitivity_note(gold100[0]["mde"], sens_100)
            + " MDE is a Monte-Carlo simulation of a Gaussian task model, not a measurement on a "
            "corpus; it has no CI of its own."
        )
    note = f"MDE simulations per cell: {sims}."
    if int(sims) < FULL_MDE_SIMS:
        note += (
            f" This is a low-simulation preview (the earlier grid used {FULL_MDE_SIMS}); "
            "do not quote it as final."
        )
    out.append(note)
    return out


def _null_table(results: dict[str, Any]) -> list[str]:
    old, sub, new = (
        results["null"][k]["by_stratum"] for k in ("old_full", "old_restricted", "new")
    )
    strata = list(dict.fromkeys([*old, *sub, *new]))
    out = [
        "| Cluster stratum | False alarm, old (all) | False alarm, new | Abstention, old (all) "
        "| Abstention, new |",
        "|---|---|---|---|---|",
    ]
    overall = {k: results["null"][k].get("overall") or {} for k in ("old_full", "new")}
    out.append(
        f"| **All strata** | {_rate(overall['old_full'].get('false_alarm'))} "
        f"| {_rate(overall['new'].get('false_alarm'))} "
        f"| {_rate(overall['old_full'].get('abstention'))} "
        f"| {_rate(overall['new'].get('abstention'))} |"
    )
    for s in strata:
        out.append(
            f"| {s} | {_rate(old.get(s, {}).get('false_alarm'))} "
            f"| {_rate(new.get(s, {}).get('false_alarm'))} "
            f"| {_rate(old.get(s, {}).get('abstention'))} "
            f"| {_rate(new.get(s, {}).get('abstention'))} |"
        )
    return out


def _diagnosis(results: dict[str, Any], extras: dict[str, Any]) -> list[str]:
    """The plain-language correction of the earlier "fixed seed explains it" diagnosis.

    Every number is read from results.json or the sibling audit fixtures, never hard-coded.
    """
    old = results["old_full"]["metrics"]
    new = results["new_gold"]["metrics"]
    diff = results["diff_new_minus_old"]
    out = [
        "**Correction to an earlier diagnosis.** The original corpus drew every repeat trial with "
        "the same sampler seed, and an October 2026 audit concluded that this explained the high "
        "share of groups with zero variance. Re-measuring with per-trial seeds shows that "
        "diagnosis was mostly wrong. The zero-variance share moved from "
        f"{_ci(old.get('zero_var_share_pct'), 1)}% to {_ci(new.get('zero_var_share_pct'), 1)}% "
        f"(paired change {_ci(diff.get('zero_var_share_pct'), 1)} points) and ICC(1) from "
        f"{_ci(old.get('icc'), 3)} to {_ci(new.get('icc'), 3)}: about "
        f"{_num((new.get('zero_var_share_pct') or {}).get('point'), 0)}% of (tool set, gold tool) "
        "groups still score identically on every repeat when the seed varies.",
    ]
    div = extras.get("output_diversity", {}).get("gold_groups(tool_set,task_tool_name)")
    if div:
        out += [
            "",
            f"That is not because the model repeats itself: of the {div['zero_variance_groups']} "
            "zero-variance groups, "
            f"{div['zero_variance_all_trials_identical_call']} issued the identical tool call on "
            f"every trial and {div['zero_variance_differing_calls_same_score']} issued different "
            f"calls that scored the same ({div['of_which_same_tool_only_args_differ']} differ only "
            f"in arguments, {div['of_which_selected_tool_differs']} in the selected tool). "
            "Source: `output_diversity.json`.",
        ]
    audit = extras.get("zero_variance_audit")
    if audit:
        p1, p3 = audit["part1_selected_tool_differs"], audit["part3_arguments_differ"]
        out += [
            "",
            f"All {p1['n_groups']} groups whose selected tool differs are all-fail "
            f"({p1['n_all_pass_with_non_gold_tool']} all-pass with a non-gold tool); a wrong tool "
            "always scores 0. The identical scores in the argument-only groups "
            f"({p3['n_all_pass']} all-pass, {p3['n_all_fail']} all-fail) come from a lenient "
            f"argument check: of {p3['all_pass_tasks_with_differing_args']} all-pass tasks whose "
            f"arguments differ across trials, {p3['of_which_task_has_NO_registered_constraint']} "
            "have no registered constraint at all (any call scores 1.0), "
            f"{p3['of_which_constrained_but_differing_params_all_unconstrained']} are constrained "
            "but the arguments that differ are not, and only "
            f"{p3['of_which_a_differing_param_is_constrained']} vary in an argument the scorer "
            'checks. A score of 1.0 therefore means "right tool plus the checked identifiers", '
            'not "fully correct call". Source: `zero_variance_audit.json`.',
        ]
    out += [
        "",
        "Practical reading: repeat trials on the same task still add little independent "
        "information (ICC above), so spend effort on more distinct tasks, not more trials per "
        "task. The coarse outcome metric, not sampler determinism, is what limits the variance "
        "structure.",
    ]
    return out


def render_block(
    results: dict[str, Any] | None,
    sha: str,
    source: str = DEFAULT_RESULTS,
    extras: dict[str, Any] | None = None,
) -> str:
    """Return the full generated block, markers included (no trailing newline)."""
    lines = [BEGIN, ""]
    if results is None:
        lines += [
            PENDING_LINE,
            "",
            "The minimum detectable effect (at 100 and at 253 tasks per arm, one trial per task), "
            "the ship-target verdict, the false-alarm rate under the null per cluster stratum, "
            "the abstention rate, and the ICC / zero-variance share were all calibrated on a "
            "corpus collected with one fixed sampler seed for every repeat trial. They are being "
            "re-measured with per-trial seeds (`scripts/recalibration_analyze.py`, output "
            f"`{source}`). Until that file exists this block shows no value, and the earlier "
            'framing that "repeat trials carry no information" is withdrawn.',
        ]
    else:
        validate(results)
        used = results["tool_sets_used"]
        dropped = results["tool_sets_dropped_partial_or_incomplete"]
        lines += [
            "**Re-measured with per-trial seeds** (replaces the fixed-seed figures; those are "
            "retired).",
            "",
            f"- Source: `{source}`",
            f"- Tool sets in the new data: {len(used)} ({', '.join(f'`{t}`' for t in used)}); "
            f"trials used: {results['n_new_rows_used']}; dropped as partial/incomplete: "
            f"{', '.join(dropped) if dropped else 'none'}.",
            "- 'Old, same subset' restricts the original fixed-seed corpus to those tool sets, so "
            "the paired comparison is like-for-like; 'old, all' is the original 44 tool sets.",
            "- CIs are 95%, cluster bootstrap over tool sets (variance table) and Wilson (rates). "
            "With few tool sets the intervals are degenerate or optimistic; read n first.",
            "",
            *_variance_table(results),
            "",
            *_diagnosis(results, extras or {}),
            "",
            *_mde_table(results),
            "",
            *_null_table(results),
            "",
            f"Null-comparison caveat: {results.get('null', {}).get('caveat', 'n/a')}",
            "",
            "Input hashes (sha256): "
            + "; ".join(
                f"{k} `{v.get('sha256', 'n/a')[:12]}`"
                for k, v in results["inputs"].items()
                if isinstance(v, dict)
            ),
        ]
    lines += ["", f"{SHA_PREFIX}`{sha}`", "", END]
    return "\n".join(lines)


_SHA_LINE = re.compile(rf"^{re.escape(SHA_PREFIX)}.*$", re.MULTILINE)


def _mask_sha(text: str) -> str:
    return _SHA_LINE.sub(f"{SHA_PREFIX}<sha>", text)


def find_block(readme: str) -> tuple[int, int]:
    """Return (start, end) offsets of the marker block; error unless exactly one pair exists."""
    if readme.count(BEGIN) != 1 or readme.count(END) != 1:
        raise RenderError(
            f"README must contain exactly one {BEGIN!r} and one {END!r} marker "
            f"(found {readme.count(BEGIN)} / {readme.count(END)})"
        )
    start, end = readme.index(BEGIN), readme.index(END) + len(END)
    if end <= start:
        raise RenderError("README markers are in the wrong order")
    return start, end


def load_results(path: Path) -> dict[str, Any] | None:
    """Load results.json; ``None`` if absent. Unreadable/invalid content is an error."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RenderError(f"cannot read results file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RenderError(f"results file {path} is not a JSON object")
    return data


def _load_extras(results_path: Path) -> dict[str, Any]:
    """Sibling audit fixtures next to results.json; absent files are simply omitted."""
    extras: dict[str, Any] = {}
    for key, name in (
        ("output_diversity", "output_diversity.json"),
        ("zero_variance_audit", "zero_variance_audit.json"),
    ):
        path = results_path.parent / name
        if path.exists():
            try:
                extras[key] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RenderError(f"cannot read {path}: {exc}") from exc
    return extras


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", default=DEFAULT_RESULTS, help="path to results.json")
    ap.add_argument("--readme", default=DEFAULT_README, help="README to update")
    ap.add_argument("--check", action="store_true", help="exit 1 if the block is stale")
    ap.add_argument("--sha", default=None, help="override the commit SHA (tests)")
    args = ap.parse_args(argv)

    readme_path = Path(args.readme)
    results_path = Path(args.results)
    if not readme_path.is_absolute():
        readme_path = ROOT / readme_path
    if not results_path.is_absolute():
        results_path = ROOT / results_path
    try:
        readme = readme_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        start, end = find_block(readme)
        results = load_results(results_path)
        rendered = render_block(
            results, args.sha or git_short_sha(), args.results, _load_extras(results_path)
        )
    except (OSError, RenderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    current = readme[start:end]
    if args.check:
        if _mask_sha(current) == _mask_sha(rendered):
            print("recalibration-metrics block is up to date")
            return 0
        print(
            "STALE: README recalibration-metrics block differs from "
            f"{'results.json' if results else 'the pending state'}; "
            "run python scripts/render_readme_metrics.py",
            file=sys.stderr,
        )
        return 1
    readme_path.write_text(readme[:start] + rendered + readme[end:], encoding="utf-8", newline="\n")
    print(f"updated {readme_path.name} ({'results' if results else 'pending'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

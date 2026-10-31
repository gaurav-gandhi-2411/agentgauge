"""Zero-LLM, offline POST-HOC study of the opt-in `agentgauge lint --tasks` task-specification check.

Two questions, answered with the rule's own function (`agentgauge.task_spec`):

(a) Validation against a noisy proxy label: whether open labellers disagreed about a task's
    required arguments (`disputed`, positive) or agreed (`control`, negative), on privately held
    R1 items run against privately held catalogs.
(b) Prevalence of each finding on the repo's own committed task corpora.

Public-repo rules: the output is AGGREGATE COUNTS ONLY. No task text, server id, tool name,
schema or per-item row is ever written. As a last line of defence the writer refuses to emit
text that contains any server id, catalog hash, or gold-tool name.

No network, no model call. Input paths are CLI arguments; the defaults point at the private data
layout used for the original study and are only defaults. The `votes` field is never read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agentgauge.constraints import BlindTask  # noqa: E402
from agentgauge.linter import Severity  # noqa: E402
from agentgauge.task_spec import (  # noqa: E402
    ALL_FINDING_CHECKS,
    CHECK_DESC_DUP,
    CHECK_NAME_DUP,
    check_task_specification,
)

Z95 = 1.959963984540054  # two-sided 95 % normal quantile

# The commit that fixed every threshold, recorded before the first validation run.
RULE_COMMIT_INITIAL = "849e9c482f60ffcddc050202d91381c3ef01362c"

_DEFAULT_ITEMS = Path.home() / "ml-projects" / "agentgauge-r1" / "data" / "f" / "items_v2.json"
_DEFAULT_CATALOGS = Path.home() / "agentgauge-r1-data" / "f_catalogs"

NEAR_DUP_EITHER = "near_duplicate_name_or_description"
ANY = "any_finding"
PREDICATES: tuple[str, ...] = (*ALL_FINDING_CHECKS, NEAR_DUP_EITHER, ANY)


# ── pure functions ──────────────────────────────────────────────────────────────────────────


def wilson_ci(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion k/n; None when n == 0 (undefined)."""
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def confusion_counts(predicted: Sequence[bool], actual: Sequence[bool]) -> dict[str, int]:
    """TP/FP/FN/TN with `actual` True = positive (labellers disagreed)."""
    if len(predicted) != len(actual):
        raise ValueError("predicted and actual must have the same length")
    pairs = list(zip(predicted, actual, strict=True))
    return {
        "tp": sum(p and a for p, a in pairs),
        "fp": sum(p and not a for p, a in pairs),
        "fn": sum((not p) and a for p, a in pairs),
        "tn": sum((not p) and (not a) for p, a in pairs),
    }


def _ratio(k: int, n: int) -> dict[str, Any]:
    ci = wilson_ci(k, n)
    return {"k": k, "n": n, "value": (k / n) if n else None, "ci95": list(ci) if ci else None}


def classification_metrics(c: dict[str, int]) -> dict[str, Any]:
    """Precision, recall, specificity, each with a Wilson 95 % CI (None when undefined)."""
    return {
        **c,
        "precision": _ratio(c["tp"], c["tp"] + c["fp"]),
        "recall": _ratio(c["tp"], c["tp"] + c["fn"]),
        "specificity": _ratio(c["tn"], c["tn"] + c["fp"]),
    }


def predicates_for(checks: set[str]) -> dict[str, bool]:
    """Per-finding booleans plus the union predicates, from the set of fired check names."""
    out = {c: c in checks for c in ALL_FINDING_CHECKS}
    out[NEAR_DUP_EITHER] = out[CHECK_NAME_DUP] or out[CHECK_DESC_DUP]
    out[ANY] = any(out[c] for c in ALL_FINDING_CHECKS)
    return out


def fired_checks(task: BlindTask, tools: list[Any]) -> set[str]:
    """ADVISORY check names that fire for one task (INFO notes are not findings)."""
    return {
        v.check for v in check_task_specification(task, tools) if v.severity == Severity.ADVISORY
    }


def tools_from_catalog(raw_tools: Sequence[dict[str, Any]]) -> list[Any]:
    """Catalog JSON tool dicts -> objects shaped like `mcp.types.Tool`."""
    return [
        SimpleNamespace(
            name=t["name"], description=t.get("description"), inputSchema=t.get("input_schema")
        )
        for t in raw_tools
    ]


def metrics_table(rows: Sequence[tuple[dict[str, bool], bool]]) -> dict[str, Any]:
    """Confusion + metrics for every predicate over (predicates, is_positive) rows."""
    actual = [a for _, a in rows]
    return {
        name: classification_metrics(confusion_counts([p[name] for p, _ in rows], actual))
        for name in PREDICATES
    }


def recall_by_group(
    rows: Sequence[tuple[dict[str, bool], str]],
) -> dict[str, dict[str, Any]]:
    """Recall of every predicate within each group, over positive items only."""
    groups: dict[str, list[dict[str, bool]]] = defaultdict(list)
    for preds, key in rows:
        groups[key].append(preds)
    return {
        key: {
            "n": len(ps),
            **{name: _ratio(sum(p[name] for p in ps), len(ps)) for name in PREDICATES},
        }
        for key, ps in sorted(groups.items())
    }


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_lf(path: Path) -> str:
    """sha256 with CRLF folded to LF, so it matches the committed blob on any checkout."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed git argv, no shell
        ["git", *args], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def load_catalogs(directory: Path) -> dict[str, dict[str, Any]]:
    """catalog sha256 (as recorded inside each file) -> catalog document."""
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(directory.glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        out[doc["sha256"]] = doc
    return out


def leak_tokens(items: Sequence[dict[str, Any]], catalogs: dict[str, dict[str, Any]]) -> set[str]:
    """Strings that must never appear in the written output."""
    toks = {i["server_id"] for i in items} | {i["gold_tool"] for i in items} | set(catalogs)
    for doc in catalogs.values():
        toks.add(doc["server_id"])
        # Full tool-name inventory, minus bare lower-case words that collide with report prose.
        toks |= {t["name"] for t in doc["tools"] if re.search(r"[_\-./A-Z0-9]", t["name"])}
    return {t for t in toks if t}


def find_leaks(blob: str, tokens: set[str]) -> int:
    """Number of forbidden tokens present in `blob` (word-bounded); never returns the tokens."""
    return sum(
        1 for t in tokens if re.search(rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])", blob)
    )


# ── validation on private items ─────────────────────────────────────────────────────────────


def validate(items: list[dict[str, Any]], catalogs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Run the check over every item and aggregate. Task text is read but never retained."""
    tool_cache: dict[str, list[Any]] = {}
    scored: list[dict[str, Any]] = []
    for it in items:
        sha = it["catalog_sha256"]
        if sha not in catalogs:
            raise KeyError("an item's catalog hash has no catalog file; refusing to guess")
        tools = tool_cache.setdefault(sha, tools_from_catalog(catalogs[sha]["tools"]))
        preds = predicates_for(fired_checks(BlindTask(it["gold_tool"], it["task_text"]), tools))
        scored.append(
            {
                "preds": preds,
                "pos": it["set"] == "disputed",
                "cause": it.get("primary_cause") or "none",
                "pilot": it["pilot"],
                "n_req": len(it["required_args"]),
                "flag": bool(it["near_duplicate_tool"]),
                "cos": float(it["max_cosine_to_other_tool"]),
            }
        )
    for s in scored:
        if s["pos"] and s["n_req"] == 0:
            raise ValueError("a disputed item with no required args contradicts the label")

    def table(sel: list[dict[str, Any]]) -> dict[str, Any]:
        return metrics_table([(s["preds"], s["pos"]) for s in sel])

    pos = [s for s in scored if s["pos"]]
    has_req = [s for s in scored if s["n_req"] >= 1]
    # The labeller-flag baselines are what a trivial predictor achieves on the same labels.
    baseline_req = classification_metrics(
        confusion_counts([s["n_req"] >= 1 for s in scored], [s["pos"] for s in scored])
    )
    baseline_flag = classification_metrics(
        confusion_counts([s["flag"] for s in scored], [s["pos"] for s in scored])
    )
    return {
        "n_items": len(scored),
        "n_positive_disputed": len(pos),
        "n_negative_control": len(scored) - len(pos),
        "n_controls_with_zero_required_args": sum(
            1 for s in scored if not s["pos"] and s["n_req"] == 0
        ),
        "overall": table(scored),
        "restricted_to_items_with_ge1_required_arg": {
            "n_items": len(has_req),
            "n_positive": sum(s["pos"] for s in has_req),
            "n_negative": sum(not s["pos"] for s in has_req),
            "metrics": table(has_req),
        },
        "recall_by_primary_cause": recall_by_group([(s["preds"], s["cause"]) for s in pos]),
        "recall_by_pilot": recall_by_group([(s["preds"], s["pilot"]) for s in pos]),
        "recall_by_n_required_args": recall_by_group(
            [(s["preds"], str(min(s["n_req"], 3)) + ("+" if s["n_req"] >= 3 else "")) for s in pos]
        ),
        "recall_by_near_duplicate_flag": recall_by_group(
            [(s["preds"], "flag_true" if s["flag"] else "flag_false") for s in pos]
        ),
        "baseline_predict_has_required_arg": baseline_req,
        "baseline_predict_near_duplicate_tool_flag": baseline_flag,
        "near_duplicate_flag_vs_cosine": {
            "flag_true_min_max_cosine": min(s["cos"] for s in scored if s["flag"]),
            "flag_false_max_max_cosine": max(s["cos"] for s in scored if not s["flag"]),
        },
    }


# ── prevalence on committed corpora ─────────────────────────────────────────────────────────


def prevalence(tasks_and_tools: Sequence[tuple[BlindTask, list[Any]]]) -> dict[str, Any]:
    """Share of tasks on which each finding fires."""
    n = len(tasks_and_tools)
    rows = [predicates_for(fired_checks(t, tools)) for t, tools in tasks_and_tools]
    return {
        "n_tasks": n,
        **{name: _ratio(sum(r[name] for r in rows), n) for name in PREDICATES},
    }


def committed_corpora() -> dict[str, Any]:
    """Prevalence over the same corpora scripts/constraint_coverage_corpora.py covers."""
    import asyncio

    import constraint_coverage_corpora as ccc  # sibling script; sys.path[0] is scripts/

    out: dict[str, Any] = {}
    demo = _ROOT / "agentgauge" / "demo" / "tasks.json"
    if demo.exists():
        from agentgauge.demo import before_server

        tools = [
            SimpleNamespace(
                name=t["name"], description=t.get("description"), inputSchema=t["inputSchema"]
            )
            for t in before_server.TOOLS
        ]
        tasks = [BlindTask.from_dict(d) for d in json.loads(demo.read_text(encoding="utf-8"))]
        out["bundled_demo"] = prevalence([(t, tools) for t in tasks])

    mod = ccc._load_module("v2_5_adl", _ROOT / "scripts" / "v2_5_argument_degradation_live.py")
    pairs: list[tuple[BlindTask, list[Any]]] = []
    for _name, _bad, fixed, tasks_module, attr in mod.FIXTURES:
        tools = asyncio.run(ccc._introspect(fixed))
        pairs += [(t, tools) for t in mod._load_fixture_tasks(tasks_module, attr)]
    out["argument_degradation_253"] = prevalence(pairs)

    from evals.fixtures.predictive_validity.blind_tasks import BLIND_TASKS
    from evals.fixtures.predictive_validity.manifest import MANIFEST

    cache: dict[str, list[Any]] = {}
    pv: list[tuple[BlindTask, list[Any]]] = []
    for entry in MANIFEST:
        if entry.server_path not in cache:
            cache[entry.server_path] = asyncio.run(ccc._introspect(entry.server_path))
        keep = set(entry.tool_name_filter) if entry.tool_name_filter is not None else None
        tools = [t for t in cache[entry.server_path] if keep is None or t.name in keep]
        pv += [(BlindTask(t.tool_name, t.description), tools) for t in BLIND_TASKS[entry.name]]
    out["predictive_validity_44_tool_sets"] = prevalence(pv)
    return out


# ── rendering ───────────────────────────────────────────────────────────────────────────────

CAVEATS: tuple[str, ...] = (
    "POST-HOC and IN-SAMPLE: the rules were designed after seeing the A6 cause taxonomy "
    "(wrapper object, free-text required argument, near-duplicate tools, other) and are scored "
    "on the same items. These numbers are not out-of-sample performance.",
    "The label is open-labeller DISAGREEMENT on required arguments: a noisy proxy for "
    "underspecification, not ground truth. A disputed item can be well specified (a labeller "
    "error) and an agreed item can be underspecified (shared bias).",
    "The control set is stratum-matched, not a random sample, and the 50/50 class balance is by "
    "construction. Precision does not transfer to a real prevalence of underspecified tasks; "
    "recall and specificity are the transferable quantities.",
    "Structural confound: every disputed item has at least one required argument (disagreement on "
    "required arguments needs one), while a share of controls has none. Argument-based findings "
    "cannot fire on those controls, which inflates specificity and precision. The "
    "`restricted_to_items_with_ge1_required_arg` table removes this confound and is the one to read.",
    "Possible circularity: the `near_duplicate_tool` field is a boolean that matches a threshold "
    "of about 0.70 on `max_cosine_to_other_tool`, a cosine similarity between the gold tool and "
    "the most similar other tool in the same catalog; the `primary_cause` and `all_causes` "
    "fields are present for disputed items only. The tool-pair near-duplicate findings here use "
    "name edit distance and description token overlap on the same catalogs, so the near-duplicate "
    "result is not independent of how that field was derived. How `primary_cause` was assigned "
    "was not inspected beyond the field values.",
    "No launch claim: nothing here gates, scores or changes a published number. The check is "
    "opt-in, ADVISORY only.",
)


def _fmt(r: dict[str, Any]) -> str:
    if r["value"] is None:
        return "n/a"
    lo, hi = r["ci95"]
    return f"{r['value']:.3f} [{lo:.3f}, {hi:.3f}] ({r['k']}/{r['n']})"


def _confusion_rows(table: dict[str, Any]) -> list[str]:
    lines = [
        "| finding | TP | FP | FN | TN | precision | recall | specificity |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name in PREDICATES:
        m = table[name]
        lines.append(
            f"| {name} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | "
            f"{_fmt(m['precision'])} | {_fmt(m['recall'])} | {_fmt(m['specificity'])} |"
        )
    return lines


def _group_rows(groups: dict[str, dict[str, Any]], title: str) -> list[str]:
    header = "| " + title + " | n | " + " | ".join(PREDICATES) + " |"
    lines = [header, "|" + "---|" * (len(PREDICATES) + 2)]
    for key, g in groups.items():
        cells = " | ".join(_fmt(g[p]) for p in PREDICATES)
        lines.append(f"| {key} | {g['n']} | {cells} |")
    return lines


def render_markdown(res: dict[str, Any]) -> str:
    """Human-readable report; caveats first."""
    v, p = res["validation"], res["provenance"]
    out = ["# Task-specification check: post-hoc validation", ""]
    out += ["**Read these caveats first.**", ""]
    out += [f"{i}. {c}" for i, c in enumerate(CAVEATS, 1)]
    out += [
        "",
        res["statement"],
        "",
        f"- rule_commit (thresholds fixed): `{p['rule_commit']}`",
        f"- rule file sha256 at run: `{p['rule_file_sha256']}`",
        f"- head at run: `{p['head_at_run']}` (working tree dirty: {p['working_tree_dirty']})",
        f"- post-validation rule changes: {res['post_validation_changes'] or 'none'}",
        f"- items: {v['n_items']} ({v['n_positive_disputed']} disputed, "
        f"{v['n_negative_control']} control; {v['n_controls_with_zero_required_args']} controls "
        "have zero required arguments)",
        "",
        "## Validation: all items",
        "",
        *_confusion_rows(v["overall"]),
        "",
        "## Validation: items with at least one required argument (confound removed)",
        "",
        f"{v['restricted_to_items_with_ge1_required_arg']['n_positive']} positive, "
        f"{v['restricted_to_items_with_ge1_required_arg']['n_negative']} negative.",
        "",
        *_confusion_rows(v["restricted_to_items_with_ge1_required_arg"]["metrics"]),
        "",
        "## Recall within disputed items, by `primary_cause`",
        "",
        *_group_rows(v["recall_by_primary_cause"], "primary_cause"),
        "",
        "## Recall within disputed items, by pilot",
        "",
        *_group_rows(v["recall_by_pilot"], "pilot"),
        "",
        "## Recall within disputed items, by number of required arguments",
        "",
        *_group_rows(v["recall_by_n_required_args"], "n required"),
        "",
        "## Recall within disputed items, by the `near_duplicate_tool` field",
        "",
        *_group_rows(v["recall_by_near_duplicate_flag"], "near_duplicate_tool"),
        "",
        "## Trivial baselines on the same labels",
        "",
        "| predictor | TP | FP | FN | TN | precision | recall | specificity |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for label, key in (
        ("has at least one required argument", "baseline_predict_has_required_arg"),
        ("`near_duplicate_tool` field", "baseline_predict_near_duplicate_tool_flag"),
    ):
        m = v[key]
        out.append(
            f"| {label} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | "
            f"{_fmt(m['precision'])} | {_fmt(m['recall'])} | {_fmt(m['specificity'])} |"
        )
    c = v["near_duplicate_flag_vs_cosine"]
    out += [
        "",
        f"`near_duplicate_tool` field vs `max_cosine_to_other_tool`: lowest cosine with flag true "
        f"{c['flag_true_min_max_cosine']:.4f}, highest with flag false "
        f"{c['flag_false_max_max_cosine']:.4f}.",
        "",
        "## Prevalence on the repo's committed task corpora",
        "",
        "Share of tasks on which each finding fires (no label; nothing here says a flagged task "
        "is wrong).",
        "",
        "| corpus | n | " + " | ".join(PREDICATES) + " |",
        "|" + "---|" * (len(PREDICATES) + 2),
    ]
    for name, row in res["prevalence_committed_corpora"].items():
        out.append(
            f"| {name} | {row['n_tasks']} | " + " | ".join(_fmt(row[k]) for k in PREDICATES) + " |"
        )
    out.append("")
    return "\n".join(out)


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the study and return the full aggregate result dict."""
    items_path, catalogs_dir = Path(args.items), Path(args.catalogs)
    doc = json.loads(items_path.read_text(encoding="utf-8"))
    items = doc["items"]
    catalogs = load_catalogs(catalogs_dir)
    rule_file = _ROOT / "agentgauge" / "task_spec.py"
    result: dict[str, Any] = {
        "statement": "Zero-LLM, aggregate-only: no model or network call; counts only.",
        "caveats": list(CAVEATS),
        "provenance": {
            "date": datetime.now(UTC).date().isoformat(),
            "rule_commit": RULE_COMMIT_INITIAL,
            "rule_file_last_commit": _git(
                "log", "-1", "--format=%H", "--", "agentgauge/task_spec.py"
            ),
            "rule_file_sha256": sha256_lf(rule_file),
            "head_at_run": _git("rev-parse", "HEAD"),
            "working_tree_dirty": bool(_git("status", "--short", "--", "agentgauge")),
            "script_sha256": sha256_lf(Path(__file__)),
            "items_file_sha256": sha256_file(items_path),
            "catalog_files": {
                "count": len(catalogs),
                "combined_sha256": hashlib.sha256("".join(sorted(catalogs)).encode()).hexdigest(),
            },
        },
        "post_validation_changes": [],
        "validation": validate(items, catalogs),
        "prevalence_committed_corpora": committed_corpora(),
    }
    # Fail closed on the aggregate-only promise: no identifier may reach the output.
    blob = json.dumps(result) + render_markdown(result)
    leaked = find_leaks(blob, leak_tokens(items, catalogs) - set(catalogs))
    if leaked:
        raise RuntimeError(f"{leaked} private identifier(s) would be written; refusing")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    ap.add_argument("--items", default=str(_DEFAULT_ITEMS), help="private R1 items_v2.json")
    ap.add_argument("--catalogs", default=str(_DEFAULT_CATALOGS), help="private catalogs dir")
    ap.add_argument("--out-md", default=str(_ROOT / "reports" / "task_specification_validation.md"))
    ap.add_argument(
        "--out-json", default=str(_ROOT / "reports" / "task_specification_validation.json")
    )
    args = ap.parse_args(argv)
    result = run(args)
    Path(args.out_json).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    Path(args.out_md).write_text(render_markdown(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

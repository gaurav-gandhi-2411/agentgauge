"""Zero-LLM, offline study of the opt-in `agentgauge lint --provider-compat` rule family.

Two questions, both answered with the rule's own functions (`agentgauge.provider_compat`):

(a) Validation against observed accept/reject outcomes of real MCP catalogs sent to a hosted
    function-calling endpoint (primary: Vertex probe; secondary, kept separate: Gemini API
    preflight).
(b) Prevalence of each finding on locally held official-registry + Smithery catalogs that carry
    full tool input schemas (Glama is never read).

Public-repo rules: the output is AGGREGATE COUNTS ONLY. No tool name, description, schema, server
identifier or per-server row is ever written. Catalog files are named after server identifiers, so
their sha256 are published as an unlabelled sorted list, never next to a file name. As a last
line of defence the writer refuses to emit text that contains any catalog identifier.

No network, no model call. Catalog paths are CLI arguments; the defaults point at the private
data layout used for the original study and are only defaults.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agentgauge.linter import Severity  # noqa: E402
from agentgauge.provider_compat import lint_provider_compat  # noqa: E402

Z95 = 1.959963984540054  # two-sided 95 % normal quantile

# Check name -> tier. ADVISORY-severity checks mirror a documented limit ("violation");
# INFO-severity checks are advisories that make no pass/fail claim.
VIOLATION_CHECKS: tuple[str, ...] = (
    "provider_compat_tool_name",
    "provider_compat_schema_depth",
    "provider_compat_ref",
)
ADVISORY_CHECKS: tuple[str, ...] = ("provider_compat_schema_size", "provider_compat_tool_count")
ALL_CHECKS: tuple[str, ...] = VIOLATION_CHECKS + ADVISORY_CHECKS
PREDICATES: tuple[str, ...] = (*ALL_CHECKS, "any_violation", "any_finding")

# R1 size strata by tool count (agentgauge-r1 src/agentgauge_r1/sampling/strata.py: S_MAX, M_MAX,
# L_MAX = 5, 15, 40; MIN_TOOLS = 3). The R1 token-cap rule (>20K tokens -> XL) is NOT applied here.
MIN_TOOLS = 3
S_MAX, M_MAX, L_MAX = 5, 15, 40
STRATA: tuple[str, ...] = ("S", "M", "L", "XL")
BELOW_S = "below_S(1-2 tools)"

_DEFAULT_DATA = Path.home() / "agentgauge-r1-data"
_DEFAULT_R1 = Path.home() / "ml-projects" / "agentgauge-r1"


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
    """TP/FP/FN/TN with `actual` True = positive (rejected by the provider)."""
    if len(predicted) != len(actual):
        raise ValueError("predicted and actual must have the same length")
    tp = sum(p and a for p, a in zip(predicted, actual, strict=True))
    fp = sum(p and not a for p, a in zip(predicted, actual, strict=True))
    fn = sum((not p) and a for p, a in zip(predicted, actual, strict=True))
    tn = sum((not p) and (not a) for p, a in zip(predicted, actual, strict=True))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _ratio(k: int, n: int) -> dict[str, Any]:
    """k/n with Wilson CI; value and CI are None (undefined) when n == 0."""
    ci = wilson_ci(k, n)
    return {
        "k": k,
        "n": n,
        "value": (k / n) if n else None,
        "ci95": list(ci) if ci else None,
    }


def classification_metrics(c: dict[str, int]) -> dict[str, Any]:
    """Precision, recall, specificity from a confusion dict, each with a Wilson 95 % CI.

    Precision is undefined (None) when the predicate flags nothing (tp + fp == 0); recall is
    undefined when there are no positives; specificity when there are no negatives.
    """
    return {
        **c,
        "precision": _ratio(c["tp"], c["tp"] + c["fp"]),
        "recall": _ratio(c["tp"], c["tp"] + c["fn"]),
        "specificity": _ratio(c["tn"], c["tn"] + c["fp"]),
    }


def stratum_of(n_tools: int) -> str:
    """R1 stratum by tool count; catalogs with fewer than MIN_TOOLS tools are BELOW_S."""
    if n_tools < MIN_TOOLS:
        return BELOW_S
    if n_tools <= S_MAX:
        return "S"
    if n_tools <= M_MAX:
        return "M"
    if n_tools <= L_MAX:
        return "L"
    return "XL"


def predicates_from_fired(fired: Iterable[str]) -> dict[str, bool]:
    """Map the set of fired check names to the study's per-rule and aggregate predicates."""
    f = set(fired)
    out = {name: name in f for name in ALL_CHECKS}
    out["any_violation"] = any(out[c] for c in VIOLATION_CHECKS)
    out["any_finding"] = any(out[c] for c in ALL_CHECKS)
    return out


def lint_catalog(tools: Sequence[dict[str, Any]]) -> dict[str, bool]:
    """Run the provider-compat rule family over raw tool dicts; return the predicates.

    Accepts both `input_schema` (private catalog layout) and `inputSchema` (MCP / Smithery).
    Raises ValueError for a tool without a string name (fail closed, never skipped silently).
    """
    objs = []
    for t in tools:
        if not isinstance(t, dict) or not isinstance(t.get("name"), str):
            raise ValueError("tool without a string name")
        schema = t.get("inputSchema", t.get("input_schema"))
        objs.append(
            SimpleNamespace(name=t["name"], inputSchema=schema if isinstance(schema, dict) else {})
        )
    fired = {v.check for v in lint_provider_compat(objs) if isinstance(v.severity, Severity)}
    return predicates_from_fired(fired)


def prevalence_table(rows: Sequence[tuple[str, dict[str, bool]]]) -> dict[str, Any]:
    """Share of catalogs tripping each predicate, overall and per stratum, with Wilson CIs."""
    by_stratum: dict[str, list[dict[str, bool]]] = defaultdict(list)
    for stratum, preds in rows:
        by_stratum[stratum].append(preds)
    groups: dict[str, list[dict[str, bool]]] = {"ALL": [p for _, p in rows]}
    for s in (BELOW_S, *STRATA):
        if s in by_stratum:
            groups[s] = by_stratum[s]
    return {
        g: {
            "n": len(ps),
            **{name: _ratio(sum(p[name] for p in ps), len(ps)) for name in PREDICATES},
        }
        for g, ps in groups.items()
    }


# ── data loading ────────────────────────────────────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_lf(path: Path) -> str:
    """Hex sha256 of a text file with CRLF folded to LF.

    Matches the committed git blob regardless of the checkout's autocrlf setting, so the
    recorded script hash can be checked with `git show HEAD:<path> | sha256sum`.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file into a list of dicts."""
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_catalogs(directory: Path) -> dict[str, list[dict[str, Any]]]:
    """server_id -> raw tool list, from every *.json catalog file in a directory."""
    out: dict[str, list[dict[str, Any]]] = {}
    for p in sorted(directory.glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        out[doc["server_id"]] = doc["tools"]
    return out


def vertex_labels(probe_rows: Sequence[dict[str, Any]]) -> tuple[dict[str, bool], dict[str, Any]]:
    """Per-catalog label (True = rejected by Flash and/or Pro with HTTP 400) plus call counts.

    Any status other than `ok` / `HTTP_400` raises (fail closed: an unknown outcome is not a
    negative).
    """
    rejected: dict[str, bool] = {}
    calls: Counter[str] = Counter()
    for r in probe_rows:
        status = r["status"]
        if status not in ("ok", "HTTP_400"):
            raise ValueError(f"unexpected probe status {status!r}")
        calls[f"{r['labeller']}:{status}"] += 1
        rejected[r["server_id"]] = rejected.get(r["server_id"], False) or status == "HTTP_400"
    meta = {
        "n_calls": len(probe_rows),
        "n_catalogs": len(rejected),
        "calls_by_labeller_status": dict(sorted(calls.items())),
        "catalogs_rejected_any": sum(rejected.values()),
        "catalogs_rejected_by_flash": len(
            {r["server_id"] for r in probe_rows if r["labeller"] == "flash" and r["status"] != "ok"}
        ),
        "catalogs_also_probed_with_pro": len(
            {r["server_id"] for r in probe_rows if r["labeller"] == "pro"}
        ),
        "catalogs_rejected_by_pro": len(
            {r["server_id"] for r in probe_rows if r["labeller"] == "pro" and r["status"] != "ok"}
        ),
    }
    return rejected, meta


def validation_block(
    labels: dict[str, bool], catalogs: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Confusion matrices and metrics per predicate for the catalogs that have a label."""
    ids = sorted(i for i in labels if i in catalogs)
    if len(ids) != len(labels):
        raise ValueError("a labelled catalog is missing from the catalog directory")
    preds = {i: lint_catalog(catalogs[i]) for i in ids}
    actual = [labels[i] for i in ids]
    return {
        "n": len(ids),
        "n_positive": sum(actual),
        "n_negative": len(actual) - sum(actual),
        "predicates": {
            name: classification_metrics(confusion_counts([preds[i][name] for i in ids], actual))
            for name in PREDICATES
        },
    }


def smithery_catalogs(
    frame_path: Path, details_path: Path
) -> tuple[list[tuple[int, list[dict[str, Any]]]], dict[str, Any]]:
    """Deduplicated lintable Smithery catalogs and the accounting of everything excluded.

    Unit of deduplication = one entry of the R1 sampling frame (official U Smithery, deduped by
    normalised repo URL). When several fetched Smithery servers share an entry, the one with the
    most tools wins (ties: lexicographically smallest qualifiedName). The official registry
    carries no tool schemas, so an official-only entry can never be linted.
    """
    frame = read_jsonl(frame_path)
    entry_of_smithery: dict[str, int] = {}
    sources: list[tuple[str, ...]] = []
    n_smithery_members = 0
    for idx, entry in enumerate(frame):
        sources.append(tuple(sorted(entry["sources"])))
        for m in entry["members"]:
            if m["source"] == "smithery":
                n_smithery_members += 1
                entry_of_smithery[m["id"]] = idx
    details = read_jsonl(details_path)
    http = Counter(str(d["status"]) for d in details)
    best: dict[int, tuple[int, str, list[dict[str, Any]]]] = {}
    fetched_ok = no_tools = unmapped = 0
    for d in details:
        if d["status"] != 200:
            continue
        fetched_ok += 1
        tools = (d.get("data") or {}).get("tools")
        if not isinstance(tools, list) or not tools:
            no_tools += 1
            continue
        qn = d["qualifiedName"]
        if qn not in entry_of_smithery:
            unmapped += 1
            continue
        idx = entry_of_smithery[qn]
        cur = best.get(idx)
        if cur is None or (-len(tools), qn) < (-cur[0], cur[1]):
            best[idx] = (len(tools), qn, tools)
    with_tools = sum(1 for _ in best)
    lintable = [(idx, v[2]) for idx, v in sorted(best.items())]
    src_counts = Counter("+".join(sources[idx]) for idx, _ in lintable)
    frame_src = Counter("+".join(s) for s in sources)
    acct = {
        "frame_entries_total": len(frame),
        "frame_entries_by_source": dict(sorted(frame_src.items())),
        "smithery_frame_members": n_smithery_members,
        "smithery_detail_records": len(details),
        "smithery_detail_http_status": dict(sorted(http.items())),
        "smithery_detail_http200": fetched_ok,
        "smithery_http200_with_zero_tools": no_tools,
        "smithery_http200_not_in_frame": unmapped,
        "smithery_servers_with_tools": fetched_ok - no_tools - unmapped,
        "frame_entries_after_dedup_with_tool_schemas": with_tools,
        "duplicates_collapsed_by_frame_entry": fetched_ok - no_tools - unmapped - with_tools,
        "no_schema_available_excluded": len(frame) - with_tools,
        "lintable_by_source": dict(sorted(src_counts.items())),
    }
    return lintable, acct


# ── provenance & output ─────────────────────────────────────────────────────────────────────


def _git(*args: str) -> str:
    """Run git in the repo root and return stripped stdout."""
    r = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *args], cwd=_ROOT, capture_output=True, text=True, check=True
    )
    return r.stdout.strip()


def _fmt(r: dict[str, Any]) -> str:
    """Render a ratio dict as 'k/n = v [lo, hi]' or 'undefined (k/n)'."""
    if r["value"] is None:
        return f"undefined ({r['k']}/{r['n']})"
    lo, hi = r["ci95"]
    return f"{r['k']}/{r['n']} = {r['value']:.3f} [{lo:.3f}, {hi:.3f}]"


def _matrix_rows(block: dict[str, Any]) -> list[str]:
    """Markdown table rows (header included) for one validation block."""
    lines = [
        "| Predicate | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name in PREDICATES:
        m = block["predicates"][name]
        lines.append(
            f"| `{name}` | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | "
            f"{_fmt(m['precision'])} | {_fmt(m['recall'])} | {_fmt(m['specificity'])} |"
        )
    return lines


def _prev_rows(table: dict[str, Any]) -> list[str]:
    """Markdown rows of the prevalence table."""
    lines = ["| Stratum | n | " + " | ".join(f"`{p}`" for p in PREDICATES) + " |"]
    lines.append("|---|---|" + "---|" * len(PREDICATES))
    for g, row in table.items():
        lines.append(f"| {g} | {row['n']} | " + " | ".join(_fmt(row[p]) for p in PREDICATES) + " |")
    return lines


GATE_PRECISION = 0.9


def launch_gate_sentence(p_viol: dict[str, Any], p_any: dict[str, Any]) -> str:
    """One plain-words verdict on the launch-claim gate, computed from the precision ratios.

    The gate is met only when any-violation precision is defined and its Wilson 95 % lower bound
    is >= GATE_PRECISION (the conservative reading: a point value alone cannot carry the claim
    at this n). Undefined or unmet precision means NOT met.
    """
    lo = p_viol["ci95"][0] if p_viol["ci95"] else None
    met = lo is not None and lo >= GATE_PRECISION
    if p_viol["value"] is None:
        viol = "any-violation precision is undefined (the predicate flags nothing)"
    else:
        viol = (
            f"any-violation precision is {p_viol['k']}/{p_viol['n']} with Wilson lower bound "
            f"{lo:.3f}"
        )
    anyf = (
        "any-finding precision is undefined"
        if p_any["value"] is None
        else f"any-finding precision {p_any['value']:.3f}"
    )
    return (
        f"Launch-claim gate (precision >= {GATE_PRECISION}, judged on the Wilson lower bound of "
        f"any-violation precision): **{'met' if met else 'NOT met'}**. {viol[0].upper()}{viol[1:]}; "
        f"{anyf}."
    )


def render_markdown(res: dict[str, Any]) -> str:
    """Render the full aggregate-only report."""
    v, s, pv = res["validation_vertex"], res["validation_gemini_api_secondary"], res["prevalence"]
    vm = v["predicates"]
    prov, pa = res["provenance"], res["prevalence_accounting"]
    p_viol, p_any = vm["any_violation"]["precision"], vm["any_finding"]["precision"]
    gate_sentence = launch_gate_sentence(p_viol, p_any)
    gate_lines = []
    for label, pr in (("any violation", p_viol), ("any finding", p_any)):
        if pr["value"] is None:
            gate_lines.append(f"- `{label}`: precision undefined (the predicate flags nothing).")
        else:
            gate_lines.append(
                f"- `{label}`: point precision {pr['value']:.3f}, Wilson lower bound "
                f"{pr['ci95'][0]:.3f}; point >= 0.9: **{pr['value'] >= 0.9}**; lower bound "
                f">= 0.9: **{pr['ci95'][0] >= 0.9}**."
            )
    src = res["vertex_probe_meta"]
    lines = [
        "# Provider-compat lint rule: validation and prevalence",
        "",
        "Zero-LLM, aggregate-only: no model or network call was made, and this report contains "
        "counts only (no tool names, descriptions, schemas, server identifiers or per-server "
        "rows). Reproduce with `scripts/provider_compat_study.py` (see provenance).",
        "",
        "## Provenance",
        "",
        f"- Date: {prov['date']}",
        f"- Rule code: `agentgauge/provider_compat.py` last changed in commit "
        f"`{prov['rule_commit']}`; file sha256 `{prov['rule_file_sha256']}`; study run at HEAD "
        f"`{prov['head_at_run']}` (working tree dirty: {prov['working_tree_dirty']}).",
        f"- Study script sha256: `{prov['script_sha256']}`",
        "- Input file sha256 (private data; hashes only):",
    ]
    for k, h in prov["input_files_sha256"].items():
        lines.append(f"  - {k}: `{h}`")
    lines += [
        f"  - catalog files ({prov['catalog_files']['count']} files, hashes sorted, "
        "file names withheld because they are server identifiers):",
        *[f"    - `{h}`" for h in prov["catalog_files"]["sha256_sorted"]],
        "",
        "## Read this first: in-sample, wide intervals, low recall is expected",
        "",
        "- **In-sample.** The rule family was designed AFTER the 5 Vertex rejections analysed "
        "in (a) were seen; those same catalogs are the validation set. This is a descriptive "
        "check of the rule on the data that motivated it, not an out-of-sample estimate.",
        f"- **Not a random sample.** The held Smithery set is {pa['smithery_detail_records']:,} of "
        f"the {pa['smithery_frame_members']:,} Smithery frame members: the first listed "
        "(github-homepage servers first, then by use count). It is not a random sample, so "
        "prevalence in section (b) describes only this held set, not the ecosystem.",
        f"- **Wide intervals.** n = {v['n']} with {v['n_positive']} positives. Wilson 95 % "
        "intervals are reported and are wide; no claim should rest on a point value alone.",
        f"- {gate_sentence}",
        "- **Low recall is legitimate.** The private diagnostic (DECISIONS 36) found the "
        "rejections consistent with an AGGREGATE schema-complexity limit, not any single "
        "documented keyword. The rule deliberately implements only DOCUMENTED limits, plus two "
        "advisories that make no pass/fail claim; it is not a rejection predictor.",
        "",
        "## (a) Validation against observed accept/reject outcomes",
        "",
        '### What the "29" is',
        "",
        f"The Vertex schema probe made **{src['n_calls']} calls over {src['n_catalogs']} "
        f"catalogs**: {src['calls_by_labeller_status']}. Flash was called on every catalog "
        f"({src['catalogs_rejected_by_flash']} rejected with HTTP 400, "
        f"{src['n_catalogs'] - src['catalogs_rejected_by_flash']} accepted); Pro was called on "
        f"{src['catalogs_also_probed_with_pro']} of them ({src['catalogs_rejected_by_pro']} "
        f"rejected). So n = {v['n']} catalogs, not 29: 29 is the call count. Positive = rejected "
        f"by Flash and/or Pro ({v['n_positive']}); negative = accepted by everything it was sent "
        f"to ({v['n_negative']}). A second probe ({res['vertex_probe_after_strip']['n_calls']} "
        "calls) re-probed the same catalogs after the uniform, pre-registered stripping of "
        f"validation keywords; it accepted {res['vertex_probe_after_strip']['n_ok']} of them.",
        "",
        "### Definitions",
        "",
        "- Predicted positive = the rule (or rule set) fires on the catalog at least once, "
        "linting the catalog as stored (no `$ref` dereferencing, no keyword stripping).",
        "- Limit violations (`any_violation`) = the three ADVISORY-severity checks that mirror a "
        "documented limit: tool name, schema depth, `$ref`. Advisories = the two INFO-severity "
        "notes: `provider_compat_schema_size` (any validation-only keyword present) and "
        "`provider_compat_tool_count` (> 20 tools). `any_finding` = violations or advisories.",
        "- Precision = TP/(TP+FP), recall = TP/(TP+FN), specificity = TN/(TN+FP), each with a "
        "Wilson 95 % CI. When a predicate flags nothing, precision is **undefined** (reported "
        "as `undefined`), not 0 or 1.",
        "",
        "### Vertex (primary)",
        "",
        *_matrix_rows(v),
        "",
        "Precision gate (launch claim needs precision >= 0.9):",
        "",
        *gate_lines,
        "",
        gate_sentence,
        "",
        "### Gemini API free-tier preflight (secondary; different endpoint)",
        "",
        f"Separate validation set: the pilot's Gemini API preflight (not Vertex) over {s['n']} "
        f"catalogs: {s['n_positive']} rejected even after lossless translation, {s['n_negative']} "
        "accepted untranslated. These catalogs are a subset of the 24 above, and "
        f"{res['secondary_overlap']['rejected_in_both']} of the {s['n_positive']} rejected ones "
        "are also Vertex rejections, so this set is NOT independent of the primary one and adds "
        "no out-of-sample evidence; it only shows the outcome on a second endpoint. It is NOT "
        "pooled with the Vertex table.",
        "",
        *_matrix_rows(s),
        "",
        "## (b) Prevalence on locally held official-registry + Smithery catalogs (no Glama)",
        "",
        f"Frame entries: {pa['frame_entries_total']} (by source: {pa['frame_entries_by_source']}"
        "). The official registry carries no tool schemas, so only Smithery detail records can be "
        f"linted. Smithery detail records: {pa['smithery_detail_records']} (HTTP "
        f"{pa['smithery_detail_http_status']}); HTTP 200 with zero tools: "
        f"{pa['smithery_http200_with_zero_tools']}; servers with tool schemas: "
        f"{pa['smithery_servers_with_tools']}; after frame-entry dedup (rule below): "
        f"**{pa['frame_entries_after_dedup_with_tool_schemas']}** "
        f"({pa['duplicates_collapsed_by_frame_entry']} collapsed). "
        f"**No schema available, excluded from the denominator: {pa['no_schema_available_excluded']}** "
        f"of {pa['frame_entries_total']}. Malformed catalogs skipped: {pa['malformed_skipped']}. "
        f"Lintable source mix (counts): {pa['lintable_by_source']}.",
        "",
        "- Dedup rule: the unit is a frame entry (official U Smithery, deduplicated by normalised "
        "repo URL in the private snapshot). If several fetched Smithery servers share one entry, "
        "the one with the most tools is kept (ties: smallest qualified name).",
        "- Strata by tool count, from agentgauge-r1 `src/agentgauge_r1/sampling/strata.py` "
        f"(`S_MAX, M_MAX, L_MAX = {S_MAX}, {M_MAX}, {L_MAX}`, `MIN_TOOLS = {MIN_TOOLS}`): S 3-5, "
        "M 6-15, L 16-40, XL >= 41; catalogs with 1-2 tools are outside R1's strata and shown "
        'separately. R1\'s additional "> 20K tokens -> XL" rule is not applied (tool count only).',
        "- The Smithery set is the first 3,327 listed servers (github-homepage first, then by "
        "use count), not a random sample of the registry: prevalence describes this held set, "
        "not the ecosystem.",
        "",
        *_prev_rows(pv),
        "",
        "## Caveats",
        "",
        "- Validation labels come from one provider/model family probed on one date; a rejection "
        "is a property of that endpoint at that time.",
        "- The `provider_compat_schema_size` advisory fires whenever any validation-only keyword "
        "is present, so it is expected to have low precision as a rejection predictor; it is an "
        "information note, not a prediction.",
        "- Prevalence says how often a finding appears, not how often a provider rejects.",
        "",
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the study and return the full aggregate result dict."""
    data, r1 = Path(args.data_dir), Path(args.r1_dir)
    catalogs_dir = data / "f_catalogs"
    probe = data / "f_runs" / "f1_schema_probe.jsonl"
    probe_after = data / "f_runs" / "f1_schema_probe_wire1.jsonl"
    preflight = r1 / "data" / "pilot_a5" / "preflight.json"
    frame = r1 / "data" / "snapshots" / "2026-10-12b" / "frame_official_smithery.jsonl"
    details = r1 / "data" / "snapshots" / "2026-10-12" / "smithery_details.jsonl"
    for p in (probe, probe_after, preflight, frame, details):
        if "glama" in p.name.lower():
            raise ValueError("Glama inputs are forbidden")

    catalogs = load_catalogs(catalogs_dir)
    labels, probe_meta = vertex_labels(read_jsonl(probe))
    after = read_jsonl(probe_after)
    pre = json.loads(preflight.read_text(encoding="utf-8"))
    sec_labels: dict[str, bool] = {}
    for sid, rec in pre.items():
        if rec["status"] == "excluded_lossy":
            sec_labels[sid] = True
        elif rec["status"] == "accepted_untranslated":
            sec_labels[sid] = False
        else:
            raise ValueError(f"unexpected preflight status {rec['status']!r}")

    lintable, acct = smithery_catalogs(frame, details)
    rows: list[tuple[str, dict[str, bool]]] = []
    malformed = 0
    for _, tools in lintable:
        try:
            rows.append((stratum_of(len(tools)), lint_catalog(tools)))
        except ValueError:
            malformed += 1
    acct["malformed_skipped"] = malformed

    rule_file = _ROOT / "agentgauge" / "provider_compat.py"
    cat_hashes = sorted(sha256_file(p) for p in catalogs_dir.glob("*.json"))
    result: dict[str, Any] = {
        "statement": "Zero-LLM, aggregate-only: no model or network call; counts only.",
        "provenance": {
            "date": datetime.now(UTC).date().isoformat(),
            "rule_commit": _git("log", "-1", "--format=%H", "--", "agentgauge/provider_compat.py"),
            "rule_file_sha256": sha256_file(rule_file),
            "head_at_run": _git("rev-parse", "HEAD"),
            "working_tree_dirty": bool(_git("status", "--short", "--", "agentgauge")),
            "script_sha256": sha256_lf(Path(__file__)),
            "input_files_sha256": {
                "vertex_probe (f1_schema_probe.jsonl)": sha256_file(probe),
                "vertex_probe_after_strip (f1_schema_probe_wire1.jsonl)": sha256_file(probe_after),
                "gemini_api_preflight (pilot_a5/preflight.json)": sha256_file(preflight),
                "frame (frame_official_smithery.jsonl)": sha256_file(frame),
                "smithery_details (smithery_details.jsonl)": sha256_file(details),
            },
            "catalog_files": {"count": len(cat_hashes), "sha256_sorted": cat_hashes},
        },
        "vertex_probe_meta": probe_meta,
        "vertex_probe_after_strip": {
            "n_calls": len(after),
            "n_ok": sum(r["status"] == "ok" for r in after),
        },
        "validation_vertex": validation_block(labels, catalogs),
        "validation_gemini_api_secondary": validation_block(sec_labels, catalogs),
        "secondary_overlap": {
            "rejected_in_both": sum(1 for i, y in sec_labels.items() if y and labels.get(i))
        },
        "prevalence_accounting": acct,
        "prevalence": prevalence_table(rows),
    }
    # Fail closed on the aggregate-only promise: no catalog identifier may reach the output.
    blob = json.dumps(result) + render_markdown(result)
    leaked = [i for i in catalogs if i in blob or i[:8] in blob]
    if leaked:
        raise RuntimeError(f"{len(leaked)} catalog identifier(s) would be written; refusing")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    ap.add_argument("--data-dir", default=str(_DEFAULT_DATA), help="private R1 data root")
    ap.add_argument("--r1-dir", default=str(_DEFAULT_R1), help="private R1 repo root (read-only)")
    ap.add_argument("--out-md", default=str(_ROOT / "reports" / "provider_compat_validation.md"))
    ap.add_argument(
        "--out-json", default=str(_ROOT / "reports" / "provider_compat_validation.json")
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

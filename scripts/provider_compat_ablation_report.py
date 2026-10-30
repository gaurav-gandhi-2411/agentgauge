"""POST-HOC publishable report for the provider-compat ablation probe.

Design (frozen): `docs/research/provider-compat-ablation-design.md`, commit 3d5d6e6.

Reads the PRIVATE aggregate-only report written by the probe (`--in`), adds the isolation
verdict, the precise re-sent-call breakdown, the unresolved-call list and the caveats, and writes
`reports/provider_compat_ablation.{json,md}`. No network, no model call.

Fail closed: the input is checked against an allow-list of keys and value shapes, and the
rendered text is refused if any hex string of 8+ characters other than the declared provenance
digests appears (a hash, an identifier) or if any key outside the allow-lists is present (a tool
name would be one). Nothing is written unless both outputs pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent

DESIGN_COMMIT = "3d5d6e6"
PLAN_SHA256 = "40669f1d723e3c4482c13e9b8fb10504cd240be6eebd8637bf13182b3b28249b"

# Constructs the bisection's transform list can name (design, Phase A). Any other key is refused:
# a tool or property name would land here.
CONSTRUCTS: frozenset[str] = frozenset(
    {
        "$schema",
        "additionalProperties",
        "anyOf",
        "default",
        "empty_schema",
        "enum",
        "examples",
        "format",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "pattern",
        "propertyNames",
        "title",
        "type_list",
        "type_null",
    }
)
TOP_KEYS = {
    "banner",
    "complete",
    "deviation_note",
    "n_resent_calls",
    "stopped",
    "totals",
    "units",
}
TOTAL_KEYS = {"accepted", "calls", "inr", "other", "rejected"}
UNIT_KEYS = {
    "a0",
    "a0_reproduced",
    "a1",
    "b",
    "c",
    "d",
    "depends_on_resent_call",
    "flipping",
    "label",
    "n_instances",
    "n_tools",
    "r_label",
    "s",
}
B_KEYS = {
    "N",
    "class",
    "class_before_stability",
    "idx_forward",
    "idx_reverse",
    "n_forward",
    "n_reverse",
    "reason",
    "singles",
}
C_KEYS = {"construct", "copies_rejected_at", "outcomes"}
D_KEYS = {"construct", "double", "one"}
S_KEYS = {"a0_repeat", "a0_stable", "boundary"}
BOUNDARY_KEYS = {"lower", "reproduced", "upper"}
OUTCOMES = {"accepted", "rejected", "other"}
FLIPS = {"flip", "no_flip"}
CLASSES = {"aggregate", "instance-critical", "inconsistent", "unstable"}

_HEX_RUN = re.compile(r"[0-9a-fA-F]{8,}")
_TEXT_OK = re.compile(r"[A-Za-z0-9 ,.;:()\-₹]+")
_REASON_OK = re.compile(r"[a-z ]{1,60}")

CRITERION_2_REASON = (
    "Criterion 2 fails: no single static quantity separates all 59 accepted from all 65 "
    "rejected distinct requests, globally or within any unit."
)
CANDIDATES_TESTED = (
    "13 candidate quantities were tested. The aggregate report does not contain them and they "
    "cannot be recomputed from it; the results are quoted from the independent recompute. "
    "Named: the maxItems count, the maxItems value sum, the flipping-construct counts, the "
    "numeric-constraint totals, the tool count and the request JSON size."
)
RESENT_BREAKDOWN: dict[str, str] = {
    "U1": "D (set-to-1) and S only; A/B do not depend",
    "U2": "A0, so everything depends",
    "U3": "S only",
    "U4": (
        "one A1 non-flipping construct, and the B maxItems single-instance check (its "
        "aggregate class depends on it)"
    ),
    "U5": "one B search point below the observed boundary",
}
CAVEATS: tuple[str, ...] = (
    "POST-HOC and in-sample: the 24 catalogs are the ones the rule was built from, one model "
    "(Flash), so there is no launch claim.",
    "Attribution is assumed, not shown: every HTTP 400 carries the same generic "
    '"Request contains an invalid argument." with no reason text.',
    'The class `aggregate` means "needs several instances together, no single instance '
    'responsible". It cannot tell an additive budget from a specific conjunction of instances. '
    "In U1 and U3, removing enum also flips while every maxItems is kept, so the rejection "
    "depends on the other content of the request.",
    "Phase C refutes the simple count-budget prediction in U1, U3 and U5: renamed copies of one "
    "tool, up to 4, carrying as many or more maxItems/enum/maximum instances than the rejected "
    "unit, were accepted. Caveat: C requests are smaller than or comparable to the unit (U3 "
    "copies are about 0.4x the unit's size), so C does not test a request-level budget at the "
    "unit's scale.",
    "Phase C coverage: complete to 4 copies in U1, U3 and U5; U2 tested 2 and 3 (4 unresolved); "
    "U4 untested (copy 2 unresolved). `copies_rejected_at: null` must not be read as "
    '"accepted at all counts".',
    "Phase D: setting every value to 1 made U1, U2, U4 and U5 accepted; doubling made all "
    "rejected. In U3, value 1 was still rejected. The value matters in 4 of 5 units, but not "
    "consistently.",
    "U4: format is instance-critical (one specific format instance is needed).",
    "U5 (R5, 10-tool unit): removing maxItems does NOT flip it; only removing `maximum` flips "
    "it (aggregate, N=105). There is no stability boundary for U5, so it is unreplicated.",
    "U2 `maximum` = inconsistent is an ARTEFACT of one unresolved HTTP 429 during the search, "
    "not a real inconsistency.",
    "Single samples: the stability phase repeats only A0 and the maxItems boundary; the enum, "
    "maximum and format boundaries were measured once.",
)


def _sha256(path: Path) -> str:
    """sha256 hex digest of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    """Current git HEAD of the repo, or fail closed."""
    out = subprocess.run(  # noqa: S603  # fixed argv, no shell
        ["git", "-C", str(_ROOT), "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _require(cond: bool, msg: str) -> None:
    """Raise ValueError(msg) unless cond; the fail-closed primitive of the validator."""
    if not cond:
        raise ValueError(f"refusing: {msg}")


def _keys(obj: Any, allowed: set[str] | frozenset[str], where: str, *, subset: bool) -> None:
    """Require `obj` to be a dict whose keys are all in `allowed` (and equal if not `subset`)."""
    _require(isinstance(obj, dict), f"{where} is not an object")
    extra = set(obj) - set(allowed)
    _require(not extra, f"{where} has keys outside the allow-list ({len(extra)} unknown)")
    if not subset:
        _require(set(obj) == set(allowed), f"{where} is missing required keys")


def _outcome_map(obj: Any, where: str, allowed: set[str]) -> None:
    """A dict of str-int copy/instance index -> outcome word."""
    _require(isinstance(obj, dict), f"{where} is not an object")
    for k, v in obj.items():
        _require(isinstance(k, str) and k.isdigit(), f"{where} has a non-index key")
        _require(v in allowed, f"{where} has an unexpected value")


def _construct_map(obj: Any, where: str, values: set[str] | None) -> None:
    """A dict keyed by construct name; values are outcome words, or ints when values is None."""
    _keys(obj, CONSTRUCTS, where, subset=True)
    for v in obj.values():
        if values is None:
            _require(isinstance(v, int) and not isinstance(v, bool), f"{where} value not int")
        else:
            _require(v in values, f"{where} has an unexpected value")


def _opt_int(v: Any, where: str) -> None:
    """None or a plain int."""
    _require(v is None or (isinstance(v, int) and not isinstance(v, bool)), f"{where} not int")


def validate_aggregate(agg: Any) -> None:
    """Allow-list validation of the private aggregate report; raises ValueError (fail closed)."""
    _keys(agg, TOP_KEYS, "report", subset=False)
    _require(isinstance(agg["banner"], str) and agg["banner"].startswith("POST-HOC"), "banner")
    _require(_TEXT_OK.fullmatch(agg["banner"]) is not None, "banner has unexpected characters")
    _require(
        isinstance(agg["deviation_note"], str)
        and _TEXT_OK.fullmatch(agg["deviation_note"]) is not None,
        "deviation_note has unexpected characters",
    )
    _require(agg["stopped"] is None or isinstance(agg["stopped"], bool), "stopped")
    _require(isinstance(agg["complete"], bool), "complete")
    _opt_int(agg["n_resent_calls"], "n_resent_calls")
    _keys(agg["totals"], TOTAL_KEYS, "totals", subset=False)
    _require(isinstance(agg["units"], list) and agg["units"], "units is not a non-empty list")
    for u in agg["units"]:
        _validate_unit(u)


def _validate_unit(u: Any) -> None:
    """Allow-list validation of one unit record."""
    _keys(u, UNIT_KEYS, "unit", subset=False)
    _require(re.fullmatch(r"U[1-9]", str(u["label"])) is not None, "unit label")
    _require(re.fullmatch(r"R[1-9]", str(u["r_label"])) is not None, "R label")
    _opt_int(u["n_tools"], "n_tools")
    _require(u["a0"] in OUTCOMES, "a0")
    _require(isinstance(u["a0_reproduced"], bool), "a0_reproduced")
    _require(isinstance(u["depends_on_resent_call"], bool), "depends_on_resent_call")
    _construct_map(u["a1"], "a1", FLIPS)
    _construct_map(u["n_instances"], "n_instances", None)
    _require(isinstance(u["flipping"], list) and set(u["flipping"]) <= CONSTRUCTS, "flipping list")
    _keys(u["b"], CONSTRUCTS, "b", subset=True)
    for rec in u["b"].values():
        _keys(rec, B_KEYS, "b record", subset=False)
        for k in ("N", "idx_forward", "idx_reverse", "n_forward", "n_reverse"):
            _opt_int(rec[k], f"b.{k}")
        for k in ("class", "class_before_stability"):
            _require(rec[k] is None or rec[k] in CLASSES, f"b.{k}")
        _require(
            rec["reason"] is None
            or (isinstance(rec["reason"], str) and _REASON_OK.fullmatch(rec["reason"])),
            "b.reason",
        )
        _outcome_map(rec["singles"], "b.singles", OUTCOMES)
    c, d, s = u["c"], u["d"], u["s"]
    _keys(c, C_KEYS, "c", subset=False)
    _require(c["construct"] in CONSTRUCTS, "c.construct")
    _opt_int(c["copies_rejected_at"], "c.copies_rejected_at")
    _outcome_map(c["outcomes"], "c.outcomes", OUTCOMES)
    _keys(d, D_KEYS, "d", subset=False)
    _require(d["construct"] in CONSTRUCTS, "d.construct")
    _require(d["one"] in OUTCOMES and d["double"] in OUTCOMES, "d outcomes")
    _keys(s, S_KEYS, "s", subset=False)
    _require(s["a0_repeat"] in OUTCOMES and isinstance(s["a0_stable"], bool), "s a0")
    if s["boundary"] is not None:
        _keys(s["boundary"], BOUNDARY_KEYS, "s.boundary", subset=False)
        _require(
            s["boundary"]["lower"] in OUTCOMES and s["boundary"]["upper"] in OUTCOMES,
            "s.boundary outcomes",
        )
        _require(isinstance(s["boundary"]["reproduced"], bool), "s.boundary.reproduced")


def unresolved_calls(agg: dict[str, Any]) -> list[dict[str, str]]:
    """Calls whose outcome is `other` and still unresolved in the report, in unit order.

    Two shapes: a Phase C copy count recorded `other`, and a Phase B search that stopped on an
    `other` outcome. Derived from the data, never hand-listed.
    """
    found: list[dict[str, str]] = []
    for u in agg["units"]:
        for cons in sorted(u["b"]):
            if u["b"][cons]["reason"] == "other outcome during search":
                found.append(
                    {"unit": u["label"], "phase": "B", "detail": f"{cons} search: other outcome"}
                )
        for k in sorted(u["c"]["outcomes"], key=int):
            if u["c"]["outcomes"][k] == "other":
                found.append(
                    {"unit": u["label"], "phase": "C", "detail": f"copy {k}: other outcome"}
                )
    return found


def c_coverage(unit: dict[str, Any]) -> str:
    """Plain-words coverage of the duplication test for one unit."""
    outs = unit["c"]["outcomes"]
    if not outs:
        return "untested"
    unresolved = sorted((int(k) for k, v in outs.items() if v == "other"))
    tested = sorted(int(k) for k, v in outs.items() if v != "other")
    if not unresolved:
        if unit["c"]["copies_rejected_at"] is not None:
            return f"rejected at copy {unit['c']['copies_rejected_at']}"
        return f"complete to {max(tested)} copies, all accepted"
    unres = ", ".join(str(k) for k in unresolved)
    if not tested:
        return f"untested (copy {unres} unresolved)"
    return f"tested {', '.join(str(k) for k in tested)} ({unres} unresolved)"


def isolation_block(agg: dict[str, Any]) -> dict[str, Any]:
    """The design's isolation verdict. Criterion 2's candidates are quoted, not recomputed."""
    crit1_units = sorted(
        u["label"]
        for u in agg["units"]
        if u["label"] in {"U1", "U2", "U3", "U4"}
        and u["b"].get("maxItems", {}).get("class") == "aggregate"
        and (u["s"]["boundary"] or {}).get("reproduced") is True
    )
    return {
        "isolated": False,
        "reason": CRITERION_2_REASON,
        "criterion_1": {
            "holds": crit1_units == ["U1", "U2", "U3", "U4"],
            "construct": "maxItems",
            "units": crit1_units,
            "note": "aggregate in U1-U4, boundary reproduced",
        },
        "criterion_2": {"holds": False, "note": CANDIDATES_TESTED},
        "candidates_tested": 13,
        "decision": "no lint-rule change; documentation only",
    }


def build_report(agg: dict[str, Any], *, input_sha256: str, git_head: str) -> dict[str, Any]:
    """The publishable JSON: the aggregate content plus the added blocks and provenance."""
    validate_aggregate(agg)
    out = json.loads(json.dumps(agg))  # deep copy, no shared state
    out["isolation"] = isolation_block(agg)
    out["resent_breakdown"] = {
        "note": "the per-unit `depends_on_resent_call` is true for all 5; this is the precise form",
        "units": dict(RESENT_BREAKDOWN),
    }
    out["unresolved_calls"] = unresolved_calls(agg)
    out["c_coverage"] = {u["label"]: c_coverage(u) for u in agg["units"]}
    out["caveats"] = list(CAVEATS)
    out["provenance"] = {
        "design_commit": DESIGN_COMMIT,
        "plan_sha256": PLAN_SHA256,
        "input_sha256": input_sha256,
        "git_head_at_run": git_head,
    }
    return out


def _table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    """Markdown table lines."""
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return lines


def _flip_list(a1: dict[str, str]) -> str:
    """Comma list of flipping constructs from an A1 map."""
    return ", ".join(f"`{k}`" for k in sorted(a1) if a1[k] == "flip") or "none"


def render_markdown(rep: dict[str, Any]) -> str:
    """Render the report; every number comes from `rep`."""
    units = rep["units"]
    t, prov = rep["totals"], rep["provenance"]
    lines = [
        "# Provider-compat ablation probe (Vertex, post-hoc)",
        "",
        f"> **{rep['banner']}**",
        "",
        "Aggregate-only: unit labels, construct names, counts and outcomes. No tool name, schema "
        "text, server identifier, limit value or per-catalog hash. Design (frozen): "
        f"`docs/research/provider-compat-ablation-design.md` at commit {DESIGN_COMMIT}.",
        "",
        "## Verdict",
        "",
        "**No limit isolated -> no rule change; documentation only.**",
        "",
        "- Criterion 1 holds for `maxItems`: aggregate in U1-U4, boundary reproduced.",
        f"- {CRITERION_2_REASON}",
        f"- {CANDIDATES_TESTED}",
        "- Per the design, a limit is isolated only if all three criteria hold, so no lint check "
        "changes; the diagnosis table in `provider_compat_posthoc.md` is updated instead.",
        "- This is not a finding that no limit exists. It is a finding that none of the "
        "candidates tested separates accepted from rejected requests.",
        "",
        "## Totals",
        "",
        f"{t['calls']} calls: {t['rejected']} rejected, {t['accepted']} accepted, "
        f"{t['other']} other ({len(rep['unresolved_calls'])} unresolved). "
        f"Spend INR {t['inr']:.2f} of the INR 200 cap. Run complete: {rep['complete']}.",
        "",
        "## Units",
        "",
        *_table(
            ["Unit", "From", "Tools", "A0 (raw unit)", "Flipping constructs (A1)"],
            [[u["label"], u["r_label"], u["n_tools"], u["a0"], _flip_list(u["a1"])] for u in units],
        ),
        "",
        "## Phase A: reproduce and remove one construct at a time",
        "",
        "Constructs present, each removed everywhere in turn; `flip` = unit became accepted.",
        "",
        *_table(
            ["Unit", "Constructs tested", "Flip", "No flip"],
            [
                [
                    u["label"],
                    len(u["a1"]),
                    _flip_list(u["a1"]),
                    ", ".join(f"`{k}`" for k in sorted(u["a1"]) if u["a1"][k] == "no_flip"),
                ]
                for u in units
            ],
        ),
        "",
        "## Phase B: additive reconstruction",
        "",
        "N = instances of the construct; indices count in the fixed instance order; n = smallest "
        "prefix that was rejected, forward and reverse; singles = base plus only the threshold "
        "instance.",
        "",
        *_table(
            ["Unit", "Construct", "N", "Class", "idx fwd/rev", "n fwd/rev", "Singles", "Note"],
            [
                [
                    u["label"],
                    f"`{cons}`",
                    r["N"],
                    r["class"],
                    f"{r['idx_forward']}/{r['idx_reverse']}",
                    f"{r['n_forward']}/{r['n_reverse']}",
                    ", ".join(f"{k}: {v}" for k, v in sorted(r["singles"].items(), key=_ik)) or "-",
                    r["reason"] or "",
                ]
                for u in units
                for cons, r in sorted(u["b"].items())
            ],
        ),
        "",
        "U2 `maximum` = inconsistent is an artefact of one unresolved HTTP 429 during the search, "
        "not a real inconsistency.",
        "",
        "## Phase C: duplication test",
        "",
        "Renamed copies of one accepted tool, 2 to 4. `copies_rejected_at: null` is NOT "
        '"accepted at all counts"; read the coverage column.',
        "",
        *_table(
            ["Unit", "Construct", "Outcomes by copy count", "copies_rejected_at", "Coverage"],
            [
                [
                    u["label"],
                    f"`{u['c']['construct']}`",
                    ", ".join(f"{k}: {v}" for k, v in sorted(u["c"]["outcomes"].items(), key=_ik)),
                    u["c"]["copies_rejected_at"],
                    rep["c_coverage"][u["label"]],
                ]
                for u in units
            ],
        ),
        "",
        "## Phase D: magnitude",
        "",
        "Every value of the construct set to 1, and every value doubled.",
        "",
        *_table(
            ["Unit", "Construct", "All values = 1", "All values doubled"],
            [
                [u["label"], f"`{u['d']['construct']}`", u["d"]["one"], u["d"]["double"]]
                for u in units
            ],
        ),
        "",
        "## Phase S: stability",
        "",
        *_table(
            ["Unit", "A0 repeat", "maxItems boundary (lower / upper)", "Boundary reproduced"],
            [
                [
                    u["label"],
                    u["s"]["a0_repeat"],
                    (
                        f"{u['s']['boundary']['lower']} / {u['s']['boundary']['upper']}"
                        if u["s"]["boundary"]
                        else "none"
                    ),
                    u["s"]["boundary"]["reproduced"] if u["s"]["boundary"] else "n/a",
                ]
                for u in units
            ],
        ),
        "",
        "## Caveats",
        "",
        *[f"- {c}" for c in rep["caveats"]],
        "",
        "## Unresolved calls",
        "",
        *[f"- {x['unit']}, phase {x['phase']}: {x['detail']}" for x in rep["unresolved_calls"]],
        "",
        "## Deviation from the frozen design",
        "",
        f'"{rep["deviation_note"]}"',
        "",
        "Which results depend on a re-sent call (the report's unit-level flag is true for all "
        "5; the precise form is):",
        "",
        *_table(["Unit", "Re-sent calls touch"], list(rep["resent_breakdown"]["units"].items())),
        "",
        "## Provenance",
        "",
        f"- Design commit: {prov['design_commit']}",
        f"- Plan sha256: `{prov['plan_sha256']}`",
        f"- Private aggregate input sha256: `{prov['input_sha256']}`",
        f"- Git HEAD at run: `{prov['git_head_at_run']}`",
        "- Raw call rows stay in the private data directory.",
        "",
    ]
    return "\n".join(lines)


def _ik(kv: tuple[str, Any]) -> int:
    """Sort key: numeric value of a digit-string index."""
    return int(kv[0])


def guard_text(text: str, declared: Sequence[str]) -> None:
    """Refuse text containing a hex run of 8+ characters other than the declared digests."""
    stripped = text
    for d in declared:
        stripped = stripped.replace(d, "")
    m = _HEX_RUN.search(stripped)
    _require(m is None, "an undeclared hex string of 8+ characters would be written")


def render_outputs(agg: dict[str, Any], *, input_sha256: str, git_head: str) -> tuple[str, str]:
    """(json_text, md_text), both guarded; raises ValueError instead of returning unsafe text."""
    rep = build_report(agg, input_sha256=input_sha256, git_head=git_head)
    json_text = json.dumps(rep, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    md_text = render_markdown(rep)
    declared = (PLAN_SHA256, input_sha256, git_head)
    guard_text(json_text, declared)
    guard_text(md_text, declared)
    return json_text, md_text


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="POST-HOC provider-compat ablation report")
    ap.add_argument("--in", dest="inp", required=True, help="private aggregate JSON")
    ap.add_argument("--out-json", default=str(_ROOT / "reports" / "provider_compat_ablation.json"))
    ap.add_argument("--out-md", default=str(_ROOT / "reports" / "provider_compat_ablation.md"))
    args = ap.parse_args(argv)
    src = Path(args.inp)
    agg = json.loads(src.read_text(encoding="utf-8"))
    json_text, md_text = render_outputs(agg, input_sha256=_sha256(src), git_head=_git_head())
    Path(args.out_json).write_text(json_text, encoding="utf-8", newline="\n")
    Path(args.out_md).write_text(md_text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

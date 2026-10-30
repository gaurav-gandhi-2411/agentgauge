"""POST-HOC re-measurement of the provider-compat lint rule after two documented-limit changes.

POST-HOC: the rule changed after seeing these outcomes; in-sample; not a validation.

Same data as `scripts/provider_compat_study.py` (24 catalogs, 29 Vertex probe calls, the held
Smithery set), outcomes fixed. Stage 0 = the rule's original five checks; stage 1 adds
`provider_compat_array_length`; stage 2 adds `provider_compat_unsupported_attribute`. The original study script and report are NOT touched: this
script imports the study's pure functions, and its "before" numbers are asserted equal to the
committed original report (`reports/provider_compat_validation.json`) so a silent drift in the
old checks would fail the run.

No network, no model call. Output is AGGREGATE ONLY: no tool name, description, schema, server
identifier or per-server row. The five rejected catalogs appear as R1-R5, arbitrary labels
whose mapping is not written anywhere. The per-miss diagnosis
(`DIAGNOSIS_MD`) is hand-written from the private bisection log and catalogs, at construct level.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agentgauge.linter import Severity  # noqa: E402
from agentgauge.provider_compat import (  # noqa: E402
    lint_provider_compat,
    measure_unsupported_attributes,
)

_spec = importlib.util.spec_from_file_location(
    "provider_compat_study", _ROOT / "scripts" / "provider_compat_study.py"
)
assert _spec and _spec.loader
study = importlib.util.module_from_spec(_spec)
sys.modules["provider_compat_study"] = study
_spec.loader.exec_module(study)

BANNER = "POST-HOC: rule changed after seeing these outcomes; in-sample; not a validation"
NEW_CHECK = "provider_compat_array_length"
UNSUPPORTED_CHECK = "provider_compat_unsupported_attribute"
NEW_CHECKS: tuple[str, ...] = (NEW_CHECK, UNSUPPORTED_CHECK)
# Keywords whose single-keyword removal flipped a rejected unit in the (private) bisection. This
# predicate is SELECTED POST HOC from those outcomes: it is not a check and is reported only as
# an upper-bound illustration, never as evidence for the check itself.
SELECTED_KEYWORDS: tuple[str, ...] = ("maxItems", "oneOf", "maximum")
SELECTED = "posthoc_selected_keywords_present[maxItems,oneOf,maximum]"
PREDICATES_BEFORE: tuple[str, ...] = study.PREDICATES
PREDICATES_AFTER: tuple[str, ...] = (
    *study.ALL_CHECKS,
    *NEW_CHECKS,
    "any_violation",
    "any_finding",
    SELECTED,
)
RARE_KEYWORD_MIN_CATALOGS = 10  # keywords used by fewer catalogs are not listed (fingerprint risk)
LABEL_PRESENT = (
    "documented contributor (maxItems) present; magnitude not covered by any documented number"
)


def _as_objs(tools: Sequence[dict[str, Any]]) -> list[SimpleNamespace]:
    """Raw tool dicts -> objects with `.name`/`.inputSchema` (fail closed on a nameless tool)."""
    objs = []
    for t in tools:
        if not isinstance(t, dict) or not isinstance(t.get("name"), str):
            raise ValueError("tool without a string name")
        schema = t.get("inputSchema", t.get("input_schema"))
        objs.append(
            SimpleNamespace(name=t["name"], inputSchema=schema if isinstance(schema, dict) else {})
        )
    return objs


def profile(tools: Sequence[dict[str, Any]]) -> tuple[set[str], dict[str, int]]:
    """(checks that fire, per-keyword unsupported-attribute counts) for a raw tool list.

    The returned `fired` set also carries the post-hoc `SELECTED` pseudo-name when any of
    `SELECTED_KEYWORDS` is present, so the predicate machinery treats it like a check.
    """
    objs = _as_objs(tools)
    fired = {v.check for v in lint_provider_compat(objs) if isinstance(v.severity, Severity)}
    counts = measure_unsupported_attributes(objs)
    if any(k in counts for k in SELECTED_KEYWORDS):
        fired.add(SELECTED)
    return fired, counts


def fired_checks(tools: Sequence[dict[str, Any]]) -> set[str]:
    """Names of every provider-compat check that fires on a raw tool list (fail closed)."""
    return profile(tools)[0]


def predicates(fired: set[str], *, stage: int) -> dict[str, bool]:
    """Per-check and aggregate predicates at stage 0 (original), 1 (+array), 2 (+unsupported).

    `any_finding` is the OR of the checks present at that stage; the post-hoc selected-keyword
    predicate appears only at stage 2 and is never part of `any_finding`.
    """
    if stage not in (0, 1, 2):
        raise ValueError(f"stage must be 0, 1 or 2, got {stage}")
    checks = (*study.ALL_CHECKS, *NEW_CHECKS[:stage])
    out = {c: c in fired for c in checks}
    out["any_violation"] = any(out[c] for c in study.VIOLATION_CHECKS)
    out["any_finding"] = any(out[c] for c in checks)
    if stage == 2:
        out[SELECTED] = SELECTED in fired
    return out


def validation(
    labels: dict[str, bool], fired: dict[str, set[str]], *, stage: int
) -> dict[str, Any]:
    """Confusion matrices and metrics per predicate for the labelled catalogs."""
    ids = sorted(labels)
    actual = [labels[i] for i in ids]
    preds = {i: predicates(fired[i], stage=stage) for i in ids}
    names = tuple(predicates(set(), stage=stage))
    return {
        "n": len(ids),
        "n_positive": sum(actual),
        "n_negative": len(actual) - sum(actual),
        "predicates": {
            n: study.classification_metrics(
                study.confusion_counts([preds[i][n] for i in ids], actual)
            )
            for n in names
        },
    }


def prevalence(rows: Sequence[tuple[str, set[str]]], *, stage: int) -> dict[str, Any]:
    """Share of catalogs tripping each predicate, overall and per R1 stratum."""
    names = tuple(predicates(set(), stage=stage))
    groups: dict[str, list[dict[str, bool]]] = {"ALL": []}
    for stratum, fired in rows:
        p = predicates(fired, stage=stage)
        groups["ALL"].append(p)
        groups.setdefault(stratum, []).append(p)
    order = ["ALL", study.BELOW_S, *study.STRATA]
    return {
        g: {
            "n": len(groups[g]),
            **{n: study._ratio(sum(p[n] for p in groups[g]), len(groups[g])) for n in names},
        }
        for g in order
        if g in groups
    }


def _delta_rows(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Markdown rows: prevalence before -> after for the predicates that exist in both/after."""
    cols = [NEW_CHECK, UNSUPPORTED_CHECK, "any_violation", "any_finding", SELECTED]
    lines = [
        "| Stratum | n | " + " | ".join(f"`{c}` before -> after" for c in cols) + " |",
        "|---|---|" + "---|" * len(cols),
    ]
    for g, row in after.items():
        cells = []
        for c in cols:
            b = before[g].get(c)
            cells.append(f"{study._fmt(b) if b else 'n/a (new)'} -> {study._fmt(row[c])}")
        lines.append(f"| {g} | {row['n']} | " + " | ".join(cells) + " |")
    return lines


DIAGNOSIS_MD = """\
## Per-miss diagnosis (construct level)

Source: the existing Vertex probe and bisection logs only (private; no new call of any kind was
made). The five rejected catalogs are R1-R5, arbitrary labels; the mapping is deliberately not
recorded, and this table is kept at construct level, without per-catalog counts, tool counts or
limit values, so a row cannot be matched to a server. R1 is the one the `$ref` check caught;
R2-R5 are the four misses. The bisection log stores only accept/reject per tool subset and per
single-keyword removal, so a construct can be pinned only where such a removal was run.

**Reading guide.** "Unit" = the smallest tool subset the bisection could still show rejected.
"Flips" = removal of that single keyword (everywhere in the unit) made the unit accepted;
"does not flip" = removal left it rejected. The probe's HTTP 400 body is the opaque
"Request contains an invalid argument." with no reason text, so identifying the cause with the
documented "too many states" wording is an inference, not an observation.

| Label | Smallest unit established | Single-keyword removals that flip it | Constructs present in the unit | Class |
|---|---|---|---|---|
| R1 (caught by `$ref`) | one tool | `maxItems` only; other single removals tried did not flip it. Removing or inlining `$ref` was never run. | arrays with `maxItems`; local `$ref` that are not direct children of `$defs`; `anyOf` | `$ref` check is DOCUMENTED, but its TP is **not shown causal**: the only keyword that flips it is `maxItems` |
| R2 (miss) | one tool | `maxItems` or `oneOf`; other single removals tried did not flip it | many properties, moderate nesting, many arrays with `maxItems` (all with small limits), most of them nested inside an array and under a `oneOf` branch | LABEL_PRESENT_PLACEHOLDER |
| R3 (miss) | a pair of tools, each accepted alone; no keyword-removal run | none run | per tool: moderate nesting, an array with `maxItems` whose items contain another array, several enums, an `anyOf`; the two tools are near-identical in shape and are the only tools in their catalog with `maxItems` | UNDETERMINED from existing logs (which construct); the only documented contributor present is `maxItems` on nested arrays |
| R4 (miss) | at least four independent rejected units: two single tools and two multi-tool groups whose halves are each accepted | single tool A: `maxItems` or `oneOf`; single tool B: `maxItems` or `maximum`; other single removals tried did not flip either | each single tool has an array with `maxItems` (A also has one `oneOf`; B also has paired `minimum`/`maximum` and `pattern`); both groups carry `maxItems` across several tools | the two single-tool units: LABEL_PRESENT_PLACEHOLDER; the two group-only units: UNDETERMINED |
| R5 (miss) | a 3-tool group; its 1-tool and 2-tool parts are each accepted; no keyword-removal run | none run | arrays with `maxItems` in two of the three tools; the largest tool also has paired `minimum`/`maximum`, string length limits, `pattern`/`format` | UNDETERMINED from existing logs |

### What the evidence supports, and how strongly

1. **Every rejected catalog contains `maxItems`; most accepted ones do not.** 5 of 5 rejected
   catalogs carry at least one array with `maxItems`; 17 of 19 accepted catalogs carry none (the
   other 2 carry some and were accepted). This is a descriptive in-sample contingency, not a test.
2. **Where a removal was run, `maxItems` always flips.** Of the 4 single-tool units with
   keyword-removal runs (R1, R2, R4 x2), removing `maxItems` alone made all 4 accepted; no other
   single keyword flips more than 2 of them (`oneOf` flips 2, `maximum` flips 1). High
   confidence for "an array length limit participates" in those 4 units; it does NOT show that
   `maxItems` alone suffices (the units are also accepted after one other removal in 3 of 4
   cases, so a second construct is needed there too).
3. **Size of the limit is not the whole story.** R2's array limits are all small yet the unit
   is rejected, so "large `maxItems`" in the docs' wording does not describe R2; the number of
   limited arrays and their nesting fit better. Not established. This is why the R2 and R4
   single-tool rows carry the label "documented contributor (maxItems) present; magnitude not
   covered by any documented number" rather than a bare DOCUMENTED.
4. **Aggregation across tools.** R3, R5 and two R4 units are rejected only as a group while every
   smaller part is accepted. That is consistent with an additive budget over the whole
   function-declaration set, which no page checked states (UNDOCUMENTED, below).
5. **R1's `$ref` TP is weaker than it looks.** The `$ref` check fired on R1 and R1 was
   rejected, but the bisection shows R1's rejection flips on removing `maxItems` and was never
   tested for `$ref` removal. The single TP of `provider_compat_ref` is therefore compatible with
   coincidence.

### Documentation search (fetched 2026-10-30; page "Last updated" in brackets)

Pages checked for a documented limit that covers the misses:

- Vertex function calling, <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling> (redirects to `.../gemini-enterprise-agent-platform/models/tools/function-calling/`) [2026-10-28]
- Vertex function-calling model reference, <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/function-calling> [2026-10-28]
- Vertex structured output, <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output> (redirects to `.../gemini-enterprise-agent-platform/models/capabilities/control-generated-output`) [2026-10-28]
- Gemini API function calling, <https://ai.google.dev/gemini-api/docs/function-calling> [2026-09-23]
- Gemini API structured output, <https://ai.google.dev/gemini-api/docs/structured-output> [2026-10-21]
- Searched with no relevant hit: Vertex quotas page, Vertex `Schema` REST reference, Gemini API troubleshooting page (no schema-complexity, `maxItems` or function-declaration size text).

**DOCUMENTED (qualitative, no number, sibling feature).** Two pages name array length limits as
a cause of schema-complexity rejection. Both are about structured-output response schemas, not
function declarations:

- Gemini API structured output: "Schema complexity: Very large or deeply nested schemas may be rejected with a 400 INVALID_ARGUMENT error that says the schema produces a constraint with too many states or too much branching for serving. Common causes are large maxItems limits (especially on nested arrays), very long property or enum names, enums with many values, long runs of optional properties, anyOf with many alternatives, and numeric minimum/maximum bounds. To fix it, lower or remove nested array limits, shorten names, or intersperse required properties among optional ones." (<https://ai.google.dev/gemini-api/docs/structured-output>, section Limitations)
- Vertex structured output: "A complex schema can result in an InvalidArgument: 400 error. Complexity might come from long property names, long array length limits, enums with many values, objects with lots of optional properties, or a combination of these factors." and the fixes "Flatten nested arrays." and "Reduce the number of properties with constraints, such as numbers with minimum and maximum limits." (<https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output>, section Considerations)
- Function-calling pages: the Gemini API page says only "Only a subset of the OpenAPI schema is supported. For any mode, the API may reject very large or deeply nested schemas." and gives NO attribute list. The Vertex page says "We support the following attributes: type, nullable, required, format, description, properties, items, enum, anyOf, $ref, and $defs. Remaining attributes are not supported." That list is checked by `provider_compat_unsupported_attribute` (section below). `maxItems`, `minimum`, `maximum`, `oneOf`, `const` are not in it, yet 11 accepted catalogs carry validation-only keywords (the schema-size note fires on 16 of the 24) and removing `maxItems` flips rejections, so on this endpoint they are evidently processed rather than ignored; the pages do not say so.

**UNDOCUMENTED (searched; nothing found on any page above):** (a) any numeric threshold for
"large" / "long" / "many" in the complexity wording; (b) that the complexity budget is
aggregated across all function declarations in a request (R3, R5, two R4 units); (c) that the
structured-output complexity rule applies to function declarations in mode ANY at all (the
function-calling pages state only the generic "very large or deeply nested" sentence).

**Documented limits found that are unrelated to these misses and NOT added:** at most 128
function declarations per request (model reference page: "The maximum number of function
declarations that can be provided with the request is 128.") and self-reference through `$defs`
limited to two levels ("Recursion depth in defs (self-reference) is limited to two."). Out of
scope for a miss diagnosis; candidates for a separate change.

### What changed in the rule, and why only these

Added two INFO checks, opt-in under `--provider-compat`, both by presence only.
`provider_compat_array_length` fires when any array declares `maxItems`: the one documented,
structurally checkable contributor that the bisection also implicates. The docs give no number,
so no threshold is encoded and the finding says it makes no claim of rejection.
`provider_compat_unsupported_attribute` fires when a schema node carries a keyword outside the
Vertex-documented supported-attribute list; it quotes the sentence and URL, says unsupported
attributes may be ignored rather than rejected, and encodes no threshold. Not encoded,
deliberately: size cut-offs for `maxItems`, nesting-depth cut-offs, per-catalog count budgets
(all inferred from this sample, none documented), and the other qualitative contributors (long
names, many enum values, optional-property runs, `anyOf` breadth, numeric bounds), which have no
checkable definition without inventing a threshold. **Selection caveat:** `maxItems` was chosen
from the documented contributors because the bisection implicated it; the post-hoc numbers below
are therefore optimistic for it by construction.
"""

DIAGNOSIS_MD = DIAGNOSIS_MD.replace("LABEL_PRESENT_PLACEHOLDER", LABEL_PRESENT)


def render_markdown(res: dict[str, Any]) -> str:
    """Render the aggregate-only post-hoc report."""
    vb, va = res["vertex_before"], res["vertex_after"]
    v1 = res["vertex_stage1"]
    sb, sa = res["secondary_before"], res["secondary_after"]
    prov, pa = res["provenance"], res["prevalence_accounting"]
    lines = [
        "# Provider-compat lint rule: post-hoc re-measurement after two documented-limit notes",
        "",
        f"> **{BANNER}.**",
        "",
        "The rule gained two INFO checks (`provider_compat_array_length`, "
        "`provider_compat_unsupported_attribute`) AFTER the 5 Vertex "
        "rejections below were seen and diagnosed. The same 24 catalogs and 29 probe calls "
        "(outcomes fixed) are re-scored. These numbers cannot support a validation claim. The "
        "original report, `provider_compat_validation.md`, is unchanged.",
        "",
        "Zero-LLM, aggregate-only: no model or network call was made, and this report contains "
        "counts and construct-level descriptions only (no tool names, descriptions, schemas, "
        "server identifiers or per-server rows).",
        "",
        "## Provenance",
        "",
        f"- Date: {prov['date']}",
        f"- Rule file sha256 `{prov['rule_file_sha256']}`; run at HEAD `{prov['head_at_run']}` "
        f"(`agentgauge/` tree dirty: {prov['agentgauge_tree_dirty']}).",
        f"- Script sha256 (LF-normalised): `{prov['script_sha256']}`",
        f"- Original report reproduced exactly by the unchanged checks: "
        f"**{prov['before_reproduces_original_report']}** (validation and prevalence blocks "
        "compared with `provider_compat_validation.json`).",
        "- Input files: same private files and hashes as the original report "
        "(`provider_compat_validation.md`, Provenance).",
        "",
        "## Headline",
        "",
        "- **Selection bias (array-length note).** `maxItems` was picked from the documented "
        "contributors because the bisection had already implicated it, so its precision "
        f"({study._fmt(va['predicates'][NEW_CHECK]['precision'])}) is selection-biased by "
        "construction; it cannot be read as validation.",
        "- **No added coverage.** any_finding is unchanged by the array-length note "
        f"({_cm(vb, 'any_finding')} -> {_cm(v1, 'any_finding')}): it adds nothing beyond "
        "`provider_compat_schema_size`, which already fires on every rejected catalog and on "
        "every catalog with `maxItems`. The unsupported-attribute check changes any_finding "
        f"to {_cm(va, 'any_finding')}: no new true positive, only added false positives.",
        f"- Vertex, any-violation (the gate predicate): unchanged, recall "
        f"{study._fmt(va['predicates']['any_violation']['recall'])}, precision "
        f"{study._fmt(va['predicates']['any_violation']['precision'])}. Both new checks are "
        "INFO tier, so they cannot change it. The launch-claim gate is therefore **still NOT "
        "met**.",
        f"- Vertex, array-length note alone: {_cm(va, NEW_CHECK)}; precision "
        f"{study._fmt(va['predicates'][NEW_CHECK]['precision'])}, recall "
        f"{study._fmt(va['predicates'][NEW_CHECK]['recall'])}, specificity "
        f"{study._fmt(va['predicates'][NEW_CHECK]['specificity'])}.",
        f"- Vertex, unsupported-attribute check alone (documented list, no selection from "
        f"outcomes): {_cm(va, UNSUPPORTED_CHECK)}; precision "
        f"{study._fmt(va['predicates'][UNSUPPORTED_CHECK]['precision'])}, recall "
        f"{study._fmt(va['predicates'][UNSUPPORTED_CHECK]['recall'])}, specificity "
        f"{study._fmt(va['predicates'][UNSUPPORTED_CHECK]['specificity'])}. The rule was still "
        "changed after the outcomes were seen, so this is in-sample too.",
        "- No documented limit explains R2-R5 as a violation. The docs name the contributor "
        "qualitatively and publish no threshold, so none could be encoded as a violation-tier "
        "check. Recall of any-violation therefore stays 1/5.",
        "",
        DIAGNOSIS_MD,
        "## Before / after: Vertex (primary), 24 catalogs",
        "",
        f"POST-HOC. n = {va['n']} ({va['n_positive']} rejected, {va['n_negative']} accepted).",
        "",
        "### Before (rule as originally validated)",
        "",
        *study._matrix_rows(vb),
        "",
        "### After (original checks + both new INFO checks)",
        "",
        *_matrix_rows_for(va, PREDICATES_AFTER),
        "",
        "### any_finding by stage (Vertex)",
        "",
        "| Stage | any_finding | Precision [95% CI] | Recall [95% CI] | Specificity |",
        "|---|---|---|---|---|",
        *_stage_rows(vb, v1, va),
        "",
        "### The selected-keyword predicate (POST-HOC SELECTED, illustration only)",
        "",
        f"`{SELECTED}` fires when any of `maxItems`, `oneOf`, `maximum` is present. These "
        "three keywords were selected AFTER seeing which single-keyword removals flipped a "
        "rejection in the bisection, so this row is the optimistic ceiling of the idea, not "
        "an estimate of anything. It is not a check and is not in the rule. "
        f"Vertex: {_cm(va, SELECTED)}; precision "
        f"{study._fmt(va['predicates'][SELECTED]['precision'])}, recall "
        f"{study._fmt(va['predicates'][SELECTED]['recall'])}, specificity "
        f"{study._fmt(va['predicates'][SELECTED]['specificity'])}.",
        "",
        "## Before / after: Gemini API preflight (secondary; not independent of Vertex)",
        "",
        f"POST-HOC. n = {sa['n']} ({sa['n_positive']} rejected, {sa['n_negative']} accepted); a "
        "subset of the 24 catalogs on a different endpoint, not pooled with the table above.",
        "",
        "### Before",
        "",
        *study._matrix_rows(sb),
        "",
        "### After",
        "",
        *_matrix_rows_for(sa, PREDICATES_AFTER),
        "",
        "## Prevalence on the held Smithery set, before -> after",
        "",
        f"Same {pa['frame_entries_after_dedup_with_tool_schemas']} lintable catalogs as the "
        "original report (the first-listed Smithery servers, not a random sample; prevalence "
        "describes this held set only). Only the new predicates, the two aggregates that "
        "could move and the post-hoc selected-keyword predicate are shown; every other column is unchanged.",
        "",
        *_delta_rows(res["prevalence_before"], res["prevalence_after"]),
        "",
        "### Unsupported-attribute keywords on the held Smithery set",
        "",
        f"Catalogs using each keyword outside the documented list (keywords used by fewer "
        f"than {RARE_KEYWORD_MIN_CATALOGS} catalogs are not listed). Keywords are counted from "
        "schema nodes only, never property names.",
        "",
        "| Keyword | Catalogs using it |",
        "|---|---|",
        *[f"| `{k}` | {study._fmt(r)} |" for k, r in res["unsupported_keyword_prevalence"].items()],
        "",
        "## Caveats",
        "",
        "- POST-HOC and in-sample: the rule was changed after these outcomes were seen. The "
        "post-hoc precision of the array-length check is optimistic by construction.",
        "- n = 24 catalogs with 5 positives; intervals are Wilson 95 % and wide.",
        "- The probe's rejection bodies carry no reason text; the link to the documented "
        "'too many states' failure is an inference.",
        "- Prevalence says how often a note appears, not how often a provider rejects.",
        "",
    ]
    return "\n".join(lines)


def _cm(block: dict[str, Any], name: str) -> str:
    """'TP/FP/FN/TN' string for a predicate."""
    m = block["predicates"][name]
    return f"TP {m['tp']} / FP {m['fp']} / FN {m['fn']} / TN {m['tn']}"


def _stage_rows(v0: dict[str, Any], v1: dict[str, Any], v2: dict[str, Any]) -> list[str]:
    """Rows showing any_finding at stages 0 (original), 1 (+array), 2 (+unsupported)."""
    rows = []
    for label, blk in (
        ("0: original five checks", v0),
        ("1: + array-length note", v1),
        ("2: + unsupported-attribute note", v2),
    ):
        m = blk["predicates"]["any_finding"]
        rows.append(
            f"| {label} | TP {m['tp']} / FP {m['fp']} / FN {m['fn']} / TN {m['tn']} | "
            f"{study._fmt(m['precision'])} | {study._fmt(m['recall'])} | "
            f"{study._fmt(m['specificity'])} |"
        )
    return rows


def _matrix_rows_for(block: dict[str, Any], names: Sequence[str]) -> list[str]:
    """Like study._matrix_rows but for an explicit predicate list."""
    lines = [
        "| Predicate | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for n in names:
        m = block["predicates"][n]
        lines.append(
            f"| `{n}` | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | "
            f"{study._fmt(m['precision'])} | {study._fmt(m['recall'])} | "
            f"{study._fmt(m['specificity'])} |"
        )
    return lines


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the post-hoc re-measurement and return the aggregate result dict."""
    data, r1 = Path(args.data_dir), Path(args.r1_dir)
    catalogs = study.load_catalogs(data / "f_catalogs")
    probe = data / "f_runs" / "f1_schema_probe.jsonl"
    labels, _ = study.vertex_labels(study.read_jsonl(probe))
    pre = json.loads((r1 / "data" / "pilot_a5" / "preflight.json").read_text(encoding="utf-8"))
    sec: dict[str, bool] = {}
    for sid, rec in pre.items():
        if rec["status"] == "excluded_lossy":
            sec[sid] = True
        elif rec["status"] == "accepted_untranslated":
            sec[sid] = False
        else:
            raise ValueError(f"unexpected preflight status {rec['status']!r}")
    if any(i not in catalogs for i in (*labels, *sec)):
        raise ValueError("a labelled catalog is missing from the catalog directory")
    fired = {i: fired_checks(t) for i, t in catalogs.items()}

    frame = r1 / "data" / "snapshots" / "2026-10-12b" / "frame_official_smithery.jsonl"
    details = r1 / "data" / "snapshots" / "2026-10-12" / "smithery_details.jsonl"
    lintable, acct = study.smithery_catalogs(frame, details)
    rows: list[tuple[str, set[str]]] = []
    kw_catalogs: Counter[str] = Counter()
    malformed = 0
    for _, tools in lintable:
        try:
            f, counts = profile(tools)
        except ValueError:
            malformed += 1
            continue
        rows.append((study.stratum_of(len(tools)), f))
        kw_catalogs.update(counts.keys())
    n_rows = len(rows)
    kw_prev = {
        k: study._ratio(c, n_rows)
        for k, c in sorted(kw_catalogs.items(), key=lambda kv: (-kv[1], kv[0]))
        if c >= RARE_KEYWORD_MIN_CATALOGS
    }
    acct["malformed_skipped"] = malformed

    res: dict[str, Any] = {
        "label": BANNER,
        "vertex_before": validation(labels, fired, stage=0),
        "vertex_stage1": validation(labels, fired, stage=1),
        "vertex_after": validation(labels, fired, stage=2),
        "secondary_before": validation(sec, fired, stage=0),
        "secondary_after": validation(sec, fired, stage=2),
        "prevalence_accounting": acct,
        "prevalence_before": prevalence(rows, stage=0),
        "prevalence_stage1": prevalence(rows, stage=1),
        "prevalence_after": prevalence(rows, stage=2),
        "unsupported_keyword_prevalence": kw_prev,
    }
    original = json.loads(
        (_ROOT / "reports" / "provider_compat_validation.json").read_text(encoding="utf-8")
    )
    same = (
        res["vertex_before"] == original["validation_vertex"]
        and res["secondary_before"] == original["validation_gemini_api_secondary"]
        and res["prevalence_before"] == original["prevalence"]
    )
    cat_hashes = sorted(study.sha256_file(p) for p in (data / "f_catalogs").glob("*.json"))
    # One combined digest, not the per-file list: the list is published in the original report,
    # and repeating 24 per-catalog hashes here adds fingerprints without adding provenance.
    combined = hashlib.sha256("\n".join(cat_hashes).encode()).hexdigest()
    res["provenance"] = {
        "date": datetime.now(UTC).date().isoformat(),
        "rule_file_sha256": study.sha256_file(_ROOT / "agentgauge" / "provider_compat.py"),
        "head_at_run": study._git("rev-parse", "HEAD"),
        "agentgauge_tree_dirty": bool(study._git("status", "--short", "--", "agentgauge")),
        "script_sha256": study.sha256_lf(Path(__file__)),
        "before_reproduces_original_report": same,
        "catalog_files_count": len(cat_hashes),
        "catalog_files_combined_sha256": combined,
    }
    if not same:
        raise RuntimeError("'before' numbers do not reproduce the original report; refusing")
    blob = json.dumps(res) + render_markdown(res)
    leaked = [i for i in catalogs if i in blob or i[:8] in blob]
    if leaked:
        raise RuntimeError(f"{len(leaked)} catalog identifier(s) would be written; refusing")
    return res


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="POST-HOC provider-compat re-measurement")
    ap.add_argument("--data-dir", default=str(study._DEFAULT_DATA), help="private R1 data root")
    ap.add_argument("--r1-dir", default=str(study._DEFAULT_R1), help="private R1 repo (read-only)")
    ap.add_argument("--out-md", default=str(_ROOT / "reports" / "provider_compat_posthoc.md"))
    ap.add_argument("--out-json", default=str(_ROOT / "reports" / "provider_compat_posthoc.json"))
    args = ap.parse_args(argv)
    res = run(args)
    Path(args.out_json).write_text(
        json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    Path(args.out_md).write_text(render_markdown(res), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

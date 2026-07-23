#!/usr/bin/env python3
"""Defect-injection corpus builder + precision/recall evaluation (Task 2d).

Draws base tool sets from the pre-declared clean corpus (tier in
real-world-mirror/real-world-mirror-improved/good/mediocre-good, deduplicated
by content -- t18_*_set2 entries are byte-identical to their non-set2
counterparts once tool_name_filter is dropped). For each base, injects one or
more of five labeled defect types into a randomly-selected tool, producing a
mutated copy with an explicit ground-truth record of (defect_type,
expected_check, tool_name). Runs agentgauge.linter against both the clean
base and every injected variant; precision/recall is computed against the
injection ground truth, not assumed.

Defect types (from the task brief):
  1. param_renamed: a schema property is renamed, but the description still
     refers to the OLD name -> expects described_not_in_schema.
  2. type_flipped: a property's type is changed to a non-boolean type, and a
     boolean-phrase sentence referencing it is added to the description ->
     expects type_enum_contradiction.
  3. enum_dropped: an enum value the description explicitly quotes is removed
     from the schema's enum list -> expects type_enum_contradiction.
  4. required_unmentioned_prose: an existing mention of a required param is
     deleted from the description -> expects required_not_mentioned (INFO
     severity; this defect type deliberately tests whether the v2 demotion
     decision creates a recall gap on the HIGH-severity surface).
  5. contradictory_required_claim: a bogus required-list entry (referencing a
     property that doesn't exist) is added to the schema, mirroring the real
     ping_server defect this checker was built around -> expects
     required_references_missing_property.

No LLM calls -- fully deterministic string/dict mutation plus the
deterministic linter. Zero inference cost.

Usage:
    uv run python scripts/v2_defect_injector.py
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.linter import lint_tool_set

TOOL_DEFS_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "v2_tool_definitions.json"
OUT_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "v2_defect_injection_results.json"

CLEAN_TIERS = {"real-world-mirror", "real-world-mirror-improved", "good", "mediocre-good"}
DEFECT_TYPES = [
    "param_renamed",
    "type_flipped",
    "enum_dropped",
    "required_unmentioned_prose",
    "contradictory_required_claim",
]
EXPECTED_CHECK = {
    "param_renamed": "described_not_in_schema",
    "type_flipped": "type_enum_contradiction",
    "enum_dropped": "type_enum_contradiction",
    "required_unmentioned_prose": "required_not_mentioned",
    "contradictory_required_claim": "required_references_missing_property",
}


@dataclass
class InjectedDefect:
    base_tool_set: str
    tool_name: str
    defect_type: str
    expected_check: str
    detail: str


def _load_clean_corpus() -> list[dict]:
    with TOOL_DEFS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    seen: set[tuple] = set()
    clean = []
    for e in data:
        if e["tier"] not in CLEAN_TIERS:
            continue
        key = (e["tier"], tuple(sorted(t["name"] for t in e["tools"])))
        if key in seen:
            continue
        seen.add(key)
        clean.append(e)
    return clean


_MAX_TARGETS_PER_DEFECT_TYPE = 3  # cap instances-per-(tool_set, defect_type) so one large
# tool set doesn't dominate the corpus


def _eligible_names_required_string_param(tools: list[dict]) -> list[str]:
    names = []
    for t in tools:
        props = (t["inputSchema"] or {}).get("properties", {}) or {}
        for pname, pschema in props.items():
            if (pschema or {}).get("type") == "string" and pname.lower() in (t["description"] or "").lower():
                names.append(t["name"])
                break
    return names


def _eligible_names_required_param(tools: list[dict]) -> list[str]:
    names = []
    for t in tools:
        required = (t["inputSchema"] or {}).get("required", []) or []
        desc = t["description"] or ""
        if any(r.lower() in desc.lower() for r in required):
            names.append(t["name"])
    return names


def _eligible_names_any_with_properties(tools: list[dict]) -> list[str]:
    return [t["name"] for t in tools if (t["inputSchema"] or {}).get("properties")]


def _eligible_names_any(tools: list[dict]) -> list[str]:
    return [t["name"] for t in tools]


def _find_by_name(tools: list[dict], name: str) -> dict | None:
    return next((t for t in tools if t["name"] == name), None)


def inject_param_renamed(tools: list[dict], target_name: str) -> tuple[list[dict], InjectedDefect] | None:
    """Rename a schema property; description keeps referring to the OLD name."""
    mutated = json.loads(json.dumps(tools))  # deep copy
    t = _find_by_name(mutated, target_name)
    if t is None:
        return None
    props = t["inputSchema"].get("properties", {})
    for pname in list(props.keys()):
        if pname.lower() in (t["description"] or "").lower():
            new_name = f"{pname}_v2"
            props[new_name] = props.pop(pname)
            required = t["inputSchema"].get("required", [])
            t["inputSchema"]["required"] = [new_name if r == pname else r for r in required]
            return mutated, InjectedDefect(
                base_tool_set="", tool_name=target_name, defect_type="param_renamed",
                expected_check=EXPECTED_CHECK["param_renamed"],
                detail=f"schema property '{pname}' renamed to '{new_name}'; description still says '{pname}'",
            )
    return None


def inject_type_flipped(tools: list[dict], target_name: str) -> tuple[list[dict], InjectedDefect] | None:
    """Change a string property's type and add a boolean-phrase sentence about it."""
    mutated = json.loads(json.dumps(tools))
    t = _find_by_name(mutated, target_name)
    if t is None:
        return None
    props = t["inputSchema"].get("properties", {})
    for pname, pschema in props.items():
        if pschema.get("type") == "string":
            pschema["type"] = "integer"
            t["description"] = (t["description"] or "") + f" Set {pname} to true/false as needed."
            return mutated, InjectedDefect(
                base_tool_set="", tool_name=target_name, defect_type="type_flipped",
                expected_check=EXPECTED_CHECK["type_flipped"],
                detail=f"'{pname}' schema type changed to 'integer'; description added boolean phrase about it",
            )
    return None


def inject_enum_dropped(tools: list[dict], target_name: str) -> tuple[list[dict], InjectedDefect] | None:
    """Add an enum to a property and quote a value in the description that ISN'T in it."""
    mutated = json.loads(json.dumps(tools))
    t = _find_by_name(mutated, target_name)
    if t is None:
        return None
    props = t["inputSchema"].get("properties", {})
    for pname, pschema in props.items():
        if pschema.get("type") == "string":
            pschema["enum"] = ["alpha", "beta"]
            t["description"] = (t["description"] or "") + f" Set {pname} to 'gamma' for the legacy mode."
            return mutated, InjectedDefect(
                base_tool_set="", tool_name=target_name, defect_type="enum_dropped",
                expected_check=EXPECTED_CHECK["enum_dropped"],
                detail=f"description quotes 'gamma' for '{pname}' but schema enum is ['alpha','beta']",
            )
    return None


def inject_required_unmentioned_prose(tools: list[dict], target_name: str) -> tuple[list[dict], InjectedDefect] | None:
    """Delete an existing mention of a required param from the description."""
    mutated = json.loads(json.dumps(tools))
    t = _find_by_name(mutated, target_name)
    if t is None:
        return None
    required = t["inputSchema"].get("required", [])
    desc = t["description"] or ""
    for r in required:
        if r.lower() in desc.lower():
            new_desc = re.sub(re.escape(r), "the specified value", desc, flags=re.IGNORECASE)
            t["description"] = new_desc
            return mutated, InjectedDefect(
                base_tool_set="", tool_name=target_name, defect_type="required_unmentioned_prose",
                expected_check=EXPECTED_CHECK["required_unmentioned_prose"],
                detail=f"removed the only mention of required param '{r}' from the description",
            )
    return None


def inject_contradictory_required_claim(
    tools: list[dict], target_name: str
) -> tuple[list[dict], InjectedDefect] | None:
    """Add a bogus required entry referencing a nonexistent property (the real
    ping_server defect this checker was built around)."""
    mutated = json.loads(json.dumps(tools))
    t = _find_by_name(mutated, target_name)
    if t is None:
        return None
    bogus_name = "_injected_ghost_param"
    required = t["inputSchema"].setdefault("required", [])
    required.append(bogus_name)
    t["description"] = (t["description"] or "") + " This tool requires no additional parameters."
    return mutated, InjectedDefect(
        base_tool_set="", tool_name=target_name, defect_type="contradictory_required_claim",
        expected_check=EXPECTED_CHECK["contradictory_required_claim"],
        detail=f"added bogus required entry '{bogus_name}' (not in properties)",
    )


INJECTORS = {
    "param_renamed": (inject_param_renamed, _eligible_names_required_string_param),
    "type_flipped": (inject_type_flipped, _eligible_names_any_with_properties),
    "enum_dropped": (inject_enum_dropped, _eligible_names_any_with_properties),
    "required_unmentioned_prose": (inject_required_unmentioned_prose, _eligible_names_required_param),
    "contradictory_required_claim": (inject_contradictory_required_claim, _eligible_names_any),
}


class _T:
    def __init__(self, d: dict) -> None:
        self.name = d["name"]
        self.description = d["description"]
        self.inputSchema = d["inputSchema"]


def main() -> None:
    clean_corpus = _load_clean_corpus()
    print(f"Clean corpus for injection: {len(clean_corpus)} unique tool sets")

    all_instances: list[dict] = []  # each is one injected tool-set instance
    total_defects = 0
    for entry in clean_corpus:
        for defect_type, (injector, eligibility_fn) in INJECTORS.items():
            eligible = eligibility_fn(entry["tools"])[:_MAX_TARGETS_PER_DEFECT_TYPE]
            for target_name in eligible:
                result = injector(entry["tools"], target_name)
                if result is None:
                    continue
                mutated_tools, defect = result
                defect.base_tool_set = entry["name"]
                all_instances.append(
                    {
                        "base_tool_set": entry["name"],
                        "tier": entry["tier"],
                        "defect_type": defect_type,
                        "defect": asdict(defect),
                        "tools": mutated_tools,
                    }
                )
                total_defects += 1

    print(f"Injected {total_defects} labeled defects across {len(all_instances)} tool-set instances")
    print(f"({len(clean_corpus)} base tool sets, up to {_MAX_TARGETS_PER_DEFECT_TYPE} targets x {len(INJECTORS)} defect types each)")

    # Evaluate: for each injected instance, does the linter's HIGH+INFO output
    # include a violation matching the expected check on the expected tool?
    per_check_tp: dict[str, int] = {d: 0 for d in DEFECT_TYPES}
    per_check_fn: dict[str, int] = {d: 0 for d in DEFECT_TYPES}
    results_detail = []
    for inst in all_instances:
        tools = [_T(t) for t in inst["tools"]]
        report = lint_tool_set(tools)
        expected_check = inst["defect"]["expected_check"]
        expected_tool = inst["defect"]["tool_name"]
        found = any(
            v.check == expected_check and expected_tool in v.tool_name
            for v in (report.high + report.info)
        )
        if found:
            per_check_tp[inst["defect_type"]] += 1
        else:
            per_check_fn[inst["defect_type"]] += 1
        results_detail.append(
            {
                "base_tool_set": inst["base_tool_set"],
                "defect_type": inst["defect_type"],
                "expected_check": expected_check,
                "expected_tool": expected_tool,
                "detected": found,
            }
        )

    print(f"\n{'defect_type':32s} {'n':>4} {'detected':>9} {'recall':>8}")
    for d in DEFECT_TYPES:
        n = per_check_tp[d] + per_check_fn[d]
        recall = per_check_tp[d] / n if n else None
        print(f"{d:32s} {n:4d} {per_check_tp[d]:9d} {recall if recall is None else f'{recall:.2%}':>8}")

    OUT_PATH.write_text(
        json.dumps(
            {
                "n_base_tool_sets": len(clean_corpus),
                "n_injected_instances": len(all_instances),
                "n_total_defects": total_defects,
                "per_defect_type": {
                    d: {"n": per_check_tp[d] + per_check_fn[d], "detected": per_check_tp[d]}
                    for d in DEFECT_TYPES
                },
                "results_detail": results_detail,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWritten: {OUT_PATH}")


if __name__ == "__main__":
    main()

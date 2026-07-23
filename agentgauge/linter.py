"""Deterministic schema-consistency + name-collision linter (AgentGauge v2).

Replaces v1's LLM-judged 8-axis correlational scorer. Per `reports/v2_axis_triage.md`,
none of v1's 8 axes survived a length-controlled re-test against real task success —
this module ships only checks whose task is genuine defect *detection*
(precision/recall/false-alarm rate against labeled ground truth), never a
correlational score.

Checks, each independently toggleable and each with an explicit severity:

  HIGH severity (on by default):
    (a) described_not_in_schema: identifier-like tokens in the top-level tool
        description that don't match any schema property, EXCLUDING tokens that
        only appear in a documented Returns/Output section (v1 false-positived on
        exactly this: a docstring's own return-value field names, e.g.
        `unknown_sections`, mistaken for missing input parameters).
    (c) type_enum_contradiction: boolean-PHRASE description language
        ("true/false", "yes/no", "boolean") near a non-boolean-typed property, or
        a quoted description value absent from that property's schema `enum`. v1
        fired on the bare word "no" anywhere in the description (e.g. "no
        pagination"); v2 requires an explicit boolean phrase, not a single common
        negation word, and requires it within a bounded token window of the
        parameter's own mention (not anywhere in the whole description).
    (e) required_references_missing_property: schema-internal -- a name in
        `required` that isn't a key in `properties` at all. Fully deterministic,
        no NLP judgment, unaffected by anything above.
    (f) name_collision: near-duplicate tool names within one tool set (normalized
        Levenshtein similarity >= the threshold shared with agentgauge.scorer).
        Extracted from v1's `discoverability` axis per v2_axis_triage.md -- this
        was never itself a correlational judgment, just misfiled as 60% of one.

  INFO severity (off by default -- opt in explicitly):
    (b) required_not_mentioned: a schema-required property name that never
        appears in the description text. Demoted per `reports/
        predictive_validity_study.md`'s tier-stratified finding: this check fires
        at nearly the same rate on real-world professional API docs (1.42/tool)
        as on deliberately-bad synthetic fixtures (1.37/tool) -- individually
        accurate, but it does not discriminate documented-badly from
        documented-fine, so it is not a HIGH-severity defect signal.

  Not implemented in this module (LLM-judged, requires live inference; see
  `check_d_semantic_llm` in the archived `scripts/schema_consistency_checker.py`
  for the pre-v2 version, kept structurally separate so its own precision/recall
  can be measured independently when GPU is available):
    (d) semantic_contradiction -- does a parameter description's stated meaning
        match what its name/schema constraints imply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agentgauge.scorer import _COLLISION_THRESHOLD, _levenshtein

_BOOLEAN_PHRASE_RE = re.compile(
    r"\btrue\s*(?:/|or)\s*false\b|\byes\s*(?:/|or)\s*no\b|\bboolean\b|\btrue\b.{0,20}\bfalse\b",
    re.IGNORECASE,
)
_IDENTIFIER_RE = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]*)`|\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")
_RETURN_SECTION_RE = re.compile(
    r"\n\s*(returns?|output)\s*:", re.IGNORECASE
)


class Severity(StrEnum):
    HIGH = "high"
    INFO = "info"


@dataclass
class Violation:
    check: str
    severity: Severity
    tool_name: str
    detail: str


@dataclass
class ToolLintResult:
    """Lint result for one tool, split by severity so callers can filter cheaply."""

    tool_name: str
    high: list[Violation] = field(default_factory=list)
    info: list[Violation] = field(default_factory=list)

    @property
    def all(self) -> list[Violation]:
        return self.high + self.info


def _input_section(description: str) -> str:
    """Strip any Returns:/Output: section (and everything after it) before
    scanning for parameter mentions -- v1's (a) check false-positived by treating
    documented return-value field names as missing input parameters."""
    m = _RETURN_SECTION_RE.search(description or "")
    return description[: m.start()] if m else (description or "")


def _extract_identifiers(text: str) -> set[str]:
    found = set()
    for m in _IDENTIFIER_RE.finditer(text or ""):
        tok = m.group(1) or m.group(2)
        if tok:
            found.add(tok.lower())
    return found


def _check_described_not_in_schema(tool_name: str, description: str, props: dict) -> list[Violation]:
    input_text = _input_section(description)
    mentioned = _extract_identifiers(input_text)
    prop_names_lower = {p.lower() for p in props}
    violations = []
    for tok in sorted(mentioned):
        if tok not in prop_names_lower and tok != tool_name.lower():
            violations.append(
                Violation(
                    check="described_not_in_schema",
                    severity=Severity.HIGH,
                    tool_name=tool_name,
                    detail=f"description mentions '{tok}' as if it were a parameter, but it is not in the schema",
                )
            )
    return violations


def _check_type_enum_contradiction(tool_name: str, description: str, props: dict) -> list[Violation]:
    desc = description or ""
    violations = []
    # Same-sentence co-occurrence, not a raw character window: "nearby" only
    # means anything if the boolean phrase and the parameter mention are part
    # of the same clause, not just close together in a short multi-sentence
    # description (a fixed character window is too loose for that -- see
    # tests/test_linter.py's TestNegationRegressionBug for the exact case this
    # fixes).
    sentences = re.split(r"(?<=[.!?])\s+", desc)
    for sentence in sentences:
        m = _BOOLEAN_PHRASE_RE.search(sentence)
        if m is None:
            continue
        sentence_lower = sentence.lower()
        for pname, pschema in props.items():
            ptype = (pschema or {}).get("type", "")
            if pname.lower() in sentence_lower and ptype not in ("boolean", ""):
                violations.append(
                    Violation(
                        check="type_enum_contradiction",
                        severity=Severity.HIGH,
                        tool_name=tool_name,
                        detail=(
                            f"description uses boolean phrase {m.group(0)!r} near '{pname}' "
                            f"but its schema type is {ptype!r}"
                        ),
                    )
                )
    for pname, pschema in props.items():
        penum = (pschema or {}).get("enum")
        if not penum:
            continue
        enum_lower = {str(v).lower() for v in penum}
        prop_names_lower = {p.lower() for p in props}
        if pname.lower() in desc.lower():
            quoted = re.findall(r"['\"`]([a-zA-Z0-9_\-]+)['\"`]", desc)
            for q in quoted:
                if q.lower() not in enum_lower and q.lower() not in prop_names_lower:
                    violations.append(
                        Violation(
                            check="type_enum_contradiction",
                            severity=Severity.HIGH,
                            tool_name=tool_name,
                            detail=f"description quotes '{q}' near param '{pname}' but schema enum is {penum}",
                        )
                    )
    return violations


def _check_required_missing_property(tool_name: str, required: list, props: dict) -> list[Violation]:
    return [
        Violation(
            check="required_references_missing_property",
            severity=Severity.HIGH,
            tool_name=tool_name,
            detail=f"'{r}' is in the schema's required list but is not a key in properties",
        )
        for r in required
        if r not in props
    ]


def _check_required_not_mentioned(tool_name: str, description: str, required: list) -> list[Violation]:
    desc_lower = (description or "").lower()
    return [
        Violation(
            check="required_not_mentioned",
            severity=Severity.INFO,
            tool_name=tool_name,
            detail=f"required param '{r}' is never named in the description text",
        )
        for r in required
        if r.lower() not in desc_lower
    ]


def lint_tool(tool_name: str, description: str, schema: dict[str, Any]) -> ToolLintResult:
    """Run every per-tool check. Pure function, no I/O, no LLM calls."""
    props: dict[str, Any] = (schema or {}).get("properties", {}) or {}
    required: list[str] = (schema or {}).get("required", []) or []

    result = ToolLintResult(tool_name=tool_name)
    result.high.extend(_check_described_not_in_schema(tool_name, description, props))
    result.high.extend(_check_type_enum_contradiction(tool_name, description, props))
    result.high.extend(_check_required_missing_property(tool_name, required, props))
    result.info.extend(_check_required_not_mentioned(tool_name, description, required))
    return result


def check_name_collisions(tool_names: list[str]) -> list[Violation]:
    """Near-duplicate tool names within one tool set (HIGH severity).

    Extracted from v1's discoverability axis's deterministic heuristic sub-score
    (agentgauge.scorer._heuristic_subscore) -- this was never itself a
    correlational judgment, so it survives the v2 axis triage unchanged in logic,
    only relocated. Reuses the same threshold/edit-distance function for
    consistency with any pre-existing calibration.
    """
    violations = []
    for i in range(len(tool_names)):
        for j in range(i + 1, len(tool_names)):
            a, b = tool_names[i].lower(), tool_names[j].lower()
            max_len = max(len(a), len(b), 1)
            sim = 1.0 - _levenshtein(a, b) / max_len
            if sim >= _COLLISION_THRESHOLD:
                violations.append(
                    Violation(
                        check="name_collision",
                        severity=Severity.HIGH,
                        tool_name=f"{tool_names[i]}/{tool_names[j]}",
                        detail=f"'{tool_names[i]}' and '{tool_names[j]}' are near-duplicate names (similarity={sim:.2f})",
                    )
                )
    return violations


@dataclass
class LintReport:
    """Lint result for a full tool set (one MCP server / manifest entry)."""

    tool_results: list[ToolLintResult]
    collision_violations: list[Violation]

    @property
    def high(self) -> list[Violation]:
        return [v for r in self.tool_results for v in r.high] + self.collision_violations

    @property
    def info(self) -> list[Violation]:
        return [v for r in self.tool_results for v in r.info]

    @property
    def n_high(self) -> int:
        return len(self.high)

    @property
    def n_info(self) -> int:
        return len(self.info)

    @property
    def flagged(self) -> bool:
        """A tool set is 'flagged' if it has any HIGH-severity violation.
        INFO-severity violations never flag a tool set by design (they are
        off-by-default hints, not defect signals)."""
        return self.n_high > 0


def lint_tool_set(tools: list[Any]) -> LintReport:
    """Lint a full tool set. `tools` is any sequence of objects with
    `.name`, `.description`, `.inputSchema` attributes (matches `mcp.types.Tool`)."""
    tool_results = [lint_tool(t.name, t.description or "", t.inputSchema or {}) for t in tools]
    collisions = check_name_collisions([t.name for t in tools])
    return LintReport(tool_results=tool_results, collision_violations=collisions)

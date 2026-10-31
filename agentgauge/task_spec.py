"""Zero-LLM, offline check for underspecified tasks in a tasks file (opt-in, ADVISORY only).

`agentgauge lint <target> --tasks FILE` runs this over each task against the introspected
catalog. It asks, deterministically and without any model, whether the task text gives an agent
(and a scorer comparing the agent's call with the expected call) enough to fix the call. A task
that does not is one where two honest agents can legitimately build different arguments, so the
measured "wrong call" is partly an ambiguity of the task, not of the server.

Checks (every finding is ADVISORY; none changes a score or an exit code):

  task_spec_unstated_required_arg
      The target tool has more value-needing required parameters than the task states values.
      A "value-needing" parameter is a required, non-boolean, non-wrapper parameter. A "stated
      value" is a quoted string, a token containing a digit, a URL / e-mail / path-like token,
      or a capitalised word run that is not sentence-initial. An enum parameter is satisfied
      only when one of its enum values occurs in the text. A heuristic, not a parser: lower-case
      values ("the react repo") are invisible to it, so it over-flags.
  task_spec_free_text_required_arg
      The target tool has a required free-text string parameter (type string, no enum / const /
      format / pattern) and the task text contains no quoted string, so the value's boundaries
      are not marked.
  task_spec_wrapper_object_arg
      The target tool has a required wrapper parameter (type object, or array of objects) and
      the task text does not name every inner required field, or the wrapper declares no
      properties at all (nothing in the task can be matched to it).
  task_spec_near_duplicate_name
      Another tool in the same catalog has a name whose similarity to the target is at least
      `agentgauge.scorer._COLLISION_THRESHOLD` (the threshold `check_name_collisions` uses).
  task_spec_near_duplicate_description
      Another tool's description has token-set Jaccard overlap with the target's of at least
      `DESCRIPTION_OVERLAP_THRESHOLD` (0.5), both descriptions having at least
      `_MIN_DESCRIPTION_TOKENS` content tokens. Thresholds are fixed constants; if one is
      changed after a validation run, the change must be disclosed with before/after numbers
      (see reports/task_specification_validation.md).

Everything here is a heuristic over text and JSON-schema shape. It is a hint for the task author,
not evidence that a task is wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agentgauge.audit import _QUOTED, _required_params, _task_literals
from agentgauge.constraints import BlindTask
from agentgauge.linter import Severity, Violation, check_name_collisions

CHECK_UNSTATED = "task_spec_unstated_required_arg"
CHECK_FREE_TEXT = "task_spec_free_text_required_arg"
CHECK_WRAPPER = "task_spec_wrapper_object_arg"
CHECK_NAME_DUP = "task_spec_near_duplicate_name"
CHECK_DESC_DUP = "task_spec_near_duplicate_description"
CHECK_UNKNOWN_TOOL = "task_spec_unknown_target_tool"

ALL_FINDING_CHECKS: tuple[str, ...] = (
    CHECK_UNSTATED,
    CHECK_FREE_TEXT,
    CHECK_WRAPPER,
    CHECK_NAME_DUP,
    CHECK_DESC_DUP,
)

# Fixed before any validation run (see module docstring).
DESCRIPTION_OVERLAP_THRESHOLD = 0.5
_MIN_DESCRIPTION_TOKENS = 4  # below this, Jaccard on a handful of words is noise

_URLISH = re.compile(r"https?://\S+|\S+@\S+\.\S+|(?:[\w.~-]*/)+[\w.~-]+")
_CAP_WORD = re.compile(r"[A-Z][\w'-]*")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9']*")
_CONTENT_TOKEN = re.compile(r"[a-z]{3,}")
_SPLIT_NAME = re.compile(r"[_\-\s]+|(?<=[a-z0-9])(?=[A-Z])")
# Function words only; kept tiny on purpose (a longer list is a tunable we have no evidence for).
_STOPWORDS = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "are",
        "was",
        "were",
        "not",
        "you",
        "your",
        "use",
        "used",
        "using",
        "can",
        "will",
        "any",
        "all",
        "has",
        "have",
        "its",
        "their",
        "than",
        "then",
        "when",
        "which",
        "who",
        "whom",
        "what",
        "where",
        "how",
        "also",
        "but",
    ]
)


def _schema_types(schema: Any) -> set[str]:
    """Declared JSON-schema type(s), looking through anyOf / oneOf / allOf one level."""
    if not isinstance(schema, dict):
        return set()
    types: set[str] = set()
    t = schema.get("type")
    if isinstance(t, str):
        types.add(t)
    elif isinstance(t, list):
        types.update(x for x in t if isinstance(x, str))
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(key) or []:
            types |= _schema_types(sub)
    return types


def _enum_values(schema: Any) -> list[str]:
    if not isinstance(schema, dict):
        return []
    if "const" in schema:
        return [str(schema["const"])]
    enum = schema.get("enum")
    return [str(v) for v in enum] if isinstance(enum, list) else []


def _object_schema(schema: Any) -> dict[str, Any] | None:
    """The object schema behind a wrapper parameter: itself, or an array's item schema."""
    if not isinstance(schema, dict):
        return None
    types = _schema_types(schema)
    if "array" in types:
        items = schema.get("items")
        if isinstance(items, dict) and "object" in _schema_types(items):
            return items
        return None
    if "object" in types:
        return schema
    return None


def _is_free_text_string(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    return (
        "string" in _schema_types(schema)
        and not _enum_values(schema)
        and "format" not in schema
        and "pattern" not in schema
    )


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def stated_value_spans(text: str) -> list[str]:
    """Distinct value-like spans in task text: quoted strings, digit tokens, URL / e-mail /
    path tokens, and capitalised word runs that are not sentence-initial. Spans contained in a
    longer span are dropped, so one value is counted once."""
    spans: list[str] = list(_task_literals(text))
    spans += [m.group(0).rstrip(".,;:)") for m in _URLISH.finditer(_QUOTED.sub(" ", text))]
    stripped = _QUOTED.sub(" ", text)
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", stripped):
        run: list[str] = []
        first = True
        for tok in sentence.split():
            clean = tok.strip('.,;:!?()[]{}"')
            if _CAP_WORD.fullmatch(clean) and not first:
                run.append(clean)
            else:
                if run:
                    spans.append(" ".join(run))
                run = []
            first = False
        if run:
            spans.append(" ".join(run))
    lowered: dict[str, str] = {}
    for s in spans:
        s = s.strip()
        if s:
            lowered.setdefault(s.lower(), s)
    keys = list(lowered)
    return [lowered[k] for k in keys if not any(k != o and k in o for o in keys)]


def _enum_value_in_text(values: list[str], text_low: str) -> bool:
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(v.lower())}(?![a-z0-9])", text_low) for v in values
    )


def _field_named_in_text(name: str, words: set[str]) -> bool:
    """True when every part of an inner field name (snake / camel split, plural stripped)
    occurs among the task's words."""
    parts = [p.lower() for p in _SPLIT_NAME.split(name) if p]
    if not parts:
        return False
    return all(p in words or p.rstrip("s") in words or f"{p}s" in words for p in parts)


@dataclass
class _ParamAnalysis:
    needs_slot: list[str] = field(default_factory=list)
    unmet_enum: list[str] = field(default_factory=list)
    free_text: list[str] = field(default_factory=list)
    wrapper_gaps: list[str] = field(default_factory=list)


def _analyse_params(tool: Any, text: str) -> _ParamAnalysis:
    schema = getattr(tool, "inputSchema", None) or {}
    props = schema.get("properties") or {}
    low = text.lower()
    words = _words(text)
    out = _ParamAnalysis()
    for name in _required_params(tool):
        p = props.get(name, {})
        wrapper = _object_schema(p)
        enum = _enum_values(p)
        if wrapper is not None:
            inner_props = wrapper.get("properties") or {}
            inner_req = [str(x) for x in wrapper.get("required") or []]
            if not inner_props or any(not _field_named_in_text(f, words) for f in inner_req):
                out.wrapper_gaps.append(name)
        elif enum:
            if len(enum) > 1 and not _enum_value_in_text(enum, low):
                out.unmet_enum.append(name)
        elif "boolean" in _schema_types(p):
            continue
        else:
            out.needs_slot.append(name)
            if _is_free_text_string(p):
                out.free_text.append(name)
    return out


def _description_tokens(description: str) -> frozenset[str]:
    return frozenset(t for t in _CONTENT_TOKEN.findall(description.lower()) if t not in _STOPWORDS)


def _name_duplicates(target: str, others: list[str]) -> list[str]:
    return [o for o in others if check_name_collisions([target, o])]


def _description_duplicates(target_desc: str, others: dict[str, str]) -> list[str]:
    a = _description_tokens(target_desc)
    if len(a) < _MIN_DESCRIPTION_TOKENS:
        return []
    found = []
    for name, desc in others.items():
        b = _description_tokens(desc)
        if len(b) >= _MIN_DESCRIPTION_TOKENS and len(a & b) / len(a | b) >= (
            DESCRIPTION_OVERLAP_THRESHOLD
        ):
            found.append(name)
    return found


def check_task_specification(task: BlindTask, tools: list[Any]) -> list[Violation]:
    """ADVISORY findings for one task against the catalog `tools` (objects with `.name`,
    `.description`, `.inputSchema`). Pure and deterministic; never raises on odd schemas."""
    target = next((t for t in tools if getattr(t, "name", None) == task.tool_name), None)
    if target is None:
        return [
            Violation(
                CHECK_UNKNOWN_TOOL,
                Severity.INFO,
                task.tool_name,
                "task's tool_name is not in the catalog; specification not checked",
            )
        ]
    name = task.tool_name
    a = _analyse_params(target, task.description)
    out: list[Violation] = []

    def add(check: str, detail: str) -> None:
        out.append(Violation(check, Severity.ADVISORY, name, detail))

    n_spans = len(stated_value_spans(task.description))
    short = (len(a.needs_slot) - n_spans) + len(a.unmet_enum)
    if len(a.needs_slot) > n_spans or a.unmet_enum:
        add(
            CHECK_UNSTATED,
            f"{len(a.needs_slot)} required parameter(s) need a value and the task states "
            f"{n_spans} value-like span(s); {max(short, 1)} value(s) may be unstated "
            f"(heuristic; params: {', '.join(a.needs_slot + a.unmet_enum)})",
        )
    if a.free_text and not _QUOTED.search(task.description):
        add(
            CHECK_FREE_TEXT,
            f"required free-text parameter(s) {', '.join(a.free_text)} and no quoted value in "
            "the task, so the exact string is left to the agent",
        )
    if a.wrapper_gaps:
        add(
            CHECK_WRAPPER,
            f"required wrapper parameter(s) {', '.join(a.wrapper_gaps)}: the task does not name "
            "every inner required field (or the wrapper declares no properties)",
        )
    others = [t for t in tools if getattr(t, "name", None) not in (None, name)]
    names = _name_duplicates(name, [t.name for t in others])
    if names:
        add(CHECK_NAME_DUP, f"near-duplicate tool name(s) in the catalog: {', '.join(names)}")
    descs = _description_duplicates(
        getattr(target, "description", None) or "",
        {t.name: getattr(t, "description", None) or "" for t in others},
    )
    if descs:
        add(
            CHECK_DESC_DUP,
            f"description overlap >= {DESCRIPTION_OVERLAP_THRESHOLD} with: {', '.join(descs)}",
        )
    return out


@dataclass
class TaskSpecReport:
    """Findings for a whole tasks file, as (task index, violations) pairs. ADVISORY / INFO only,
    so it never flags a run or changes an exit code."""

    n_tasks: int
    by_task: list[tuple[int, list[Violation]]] = field(default_factory=list)

    @property
    def findings(self) -> list[Violation]:
        return [v for _, vs in self.by_task for v in vs]

    @property
    def n_advisory(self) -> int:
        return sum(1 for v in self.findings if v.severity == Severity.ADVISORY)

    @property
    def n_tasks_flagged(self) -> int:
        return sum(1 for _, vs in self.by_task if any(v.severity == Severity.ADVISORY for v in vs))


def check_task_file(tasks: list[BlindTask], tools: list[Any]) -> TaskSpecReport:
    """Run `check_task_specification` over every task."""
    report = TaskSpecReport(n_tasks=len(tasks))
    for i, task in enumerate(tasks):
        found = check_task_specification(task, tools)
        if found:
            report.by_task.append((i, found))
    return report

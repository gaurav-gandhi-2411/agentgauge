"""Deterministic schema-consistency + name-collision linter (AgentGauge v2).

Replaces v1's LLM-judged 8-axis correlational scorer. Per `reports/v2_axis_triage.md`,
none of v1's 8 axes survived a length-controlled re-test against real task success —
this module ships only checks whose task is genuine defect *detection*
(precision/recall/false-alarm rate against labeled ground truth), never a
correlational score.

Checks, each independently toggleable and each with an explicit severity tier
(v2.1, Task 5: restructured from a single HIGH tier into BLOCKING/ADVISORY,
after measuring that a naive "any HIGH flag blocks the PR" gate would reject
66.67% of genuinely clean tool sets -- see `reports/v2_1_severity_gate.md`):

  BLOCKING severity (fails CI; 0% measured false alarms on the clean corpus,
  100% measured recall on their targeted defect type):
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

  ADVISORY severity (surfaced, does not fail CI; each carries measured,
  documented, only-partially-fixable false-alarm noise):
    (a) described_not_in_schema: identifier-like tokens in the top-level tool
        description that don't match any schema property, EXCLUDING tokens that
        only appear in a documented Returns/Output section (v1 false-positived on
        exactly this: a docstring's own return-value field names, e.g.
        `unknown_sections`, mistaken for missing input parameters).
    (f) name_collision: near-duplicate tool names within one tool set (normalized
        Levenshtein similarity >= the threshold shared with agentgauge.scorer).
        Extracted from v1's `discoverability` axis per v2_axis_triage.md -- this
        was never itself a correlational judgment, just misfiled as 60% of one.
    (g) param_possibly_renamed (v2.1, Task 4): the INVERSE direction of (a).
        For each schema property NOT mentioned verbatim in the description,
        search the description's tokens for a near-miss sharing a common
        prefix (Levenshtein distance <=2 after folding case/underscore/
        camelCase differences, excluding common id/unit-suffix abbreviations
        like `_id`/`_cs` that are routine shorthand, not renames). A near-miss
        token where the exact name is absent is high-precision evidence the
        description was written for an old parameter name since renamed in
        the schema. Fixes the 22.9%-recall gap (a) left on `param_renamed`
        defects -- (a) can only ever flag identifiers that ARE in the
        description but AREN'T in the schema; it structurally cannot notice a
        schema property that silently has no description coverage at all,
        which is exactly what a rename produces from the new name's
        perspective. See `reports/v2_1_linter_recall_fix.md`.

  INFO severity (off by default -- opt in explicitly):
    (b) required_not_mentioned: a schema-required property name that never
        appears in the description text. Demoted per `reports/
        predictive_validity_study.md`'s tier-stratified finding: this check fires
        at nearly the same rate on real-world professional API docs (1.42/tool)
        as on deliberately-bad synthetic fixtures (1.37/tool) -- individually
        accurate, but it does not discriminate documented-badly from
        documented-fine, so it is not a BLOCKING-severity defect signal.

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

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")
_RENAME_MIN_NORMALIZED_LEN = 4  # below this, edit-distance<=2 is too loose (matches common words)
_RENAME_MAX_EDIT_DISTANCE = 2
# Common identifier suffixes that are routinely dropped in natural-language prose
# without indicating a rename at all ("customer_id" -> "the customer", "delay_cs"
# -> "the delay"). Found empirically: the "id" pattern alone was ~79% of this
# check's clean-corpus false positives (order_id/invoice_id/customer_id/
# ticket_id/account_id -> their bare noun) before this exclusion was added; "cs"/
# "ds" (centi-/deci-second units) were a smaller residual of the same shape --
# see reports/v2_1_linter_recall_fix.md. Not exhaustive: other unit/unit-code
# suffixes in other domains may need adding if they surface as false positives.
_COMMON_ID_SUFFIXES = ("id", "key", "code", "no", "num", "ref", "type", "cs", "ds", "ms")

_BOOLEAN_PHRASE_RE = re.compile(
    r"\btrue\s*(?:/|or)\s*false\b|\byes\s*(?:/|or)\s*no\b|\bboolean\b|\btrue\b.{0,20}\bfalse\b",
    re.IGNORECASE,
)
_IDENTIFIER_RE = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]*)`|\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")
_RETURN_SECTION_RE = re.compile(r"\n\s*(returns?|output)\s*:", re.IGNORECASE)
_RETURN_SENTENCE_RE = re.compile(r"^\s*returns?\b", re.IGNORECASE)
_EXAMPLES_SECTION_RE = re.compile(r"\n\s*examples?\s*:", re.IGNORECASE)


class Severity(StrEnum):
    """v2.1, Task 5: BLOCKING/ADVISORY split replaces v2's single HIGH tier,
    after measuring that a naive "any HIGH flag blocks the PR" gate rejected
    66.67% of genuinely clean tool sets (`reports/v2_linter_evaluation.md`
    §2c). Only BLOCKING checks (measured 0% false alarms) fail CI."""

    BLOCKING = "blocking"
    ADVISORY = "advisory"
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
    blocking: list[Violation] = field(default_factory=list)
    advisory: list[Violation] = field(default_factory=list)
    info: list[Violation] = field(default_factory=list)

    @property
    def all(self) -> list[Violation]:
        return self.blocking + self.advisory + self.info


def _input_section(description: str) -> str:
    """Return only the input-relevant text, with output-describing text removed
    before scanning for parameter mentions.

    Three independently-found false-positive patterns are handled:
    1. A formal `Returns:`/`Output:` section header (everything after it is
       dropped) -- v1's original bug.
    2. A single SENTENCE whose main verb is "Returns"/"Return", even mid-
       paragraph with no section header (e.g. "Returns the order with discount
       and tax calculations applied: subtotal, discount_amount, ...") -- found
       during v2 clean-corpus measurement on p2a_arm_oracle's real-world-style
       prose, where professional descriptions routinely describe output shape
       inline rather than under a formal heading.
    3. An `Examples:` section (everything after it dropped) -- illustrative
       example values (e.g. an example URI `core://my_user/survival_state`)
       contain snake_case-looking substrings that are not parameter references
       at all. Found on exp1_dataojitori_nocturne_memory_mirror.
    """
    desc = description or ""
    for section_re in (_RETURN_SECTION_RE, _EXAMPLES_SECTION_RE):
        m = section_re.search(desc)
        if m:
            desc = desc[: m.start()]
    sentences = re.split(r"(?<=[.!?])\s+", desc)
    kept = [s for s in sentences if not _RETURN_SENTENCE_RE.match(s)]
    return " ".join(kept)


def _extract_identifiers(text: str) -> set[str]:
    found = set()
    for m in _IDENTIFIER_RE.finditer(text or ""):
        tok = m.group(1) or m.group(2)
        if tok:
            found.add(tok.lower())
    return found


def _check_described_not_in_schema(
    tool_name: str, description: str, props: dict, sibling_tool_names: frozenset[str] = frozenset()
) -> list[Violation]:
    """(a) description mentions an identifier absent from the schema.

    Excludes: the tool's own name (self-reference in prose); any SIBLING tool's
    name in the same tool set (workflow guidance like "use `watch_topic` before
    calling this" references another TOOL, not a parameter -- found as a
    concrete false positive on exp1_blazickjp_arxiv_mcp_server_mirror's
    `check_alerts`/`get_abstract`/etc. tools during v2 clean-corpus measurement,
    fixed here rather than shipped).
    """
    input_text = _input_section(description)
    mentioned = _extract_identifiers(input_text)
    prop_names_lower = {p.lower() for p in props}
    sibling_names_lower = {n.lower() for n in sibling_tool_names}
    violations = []
    for tok in sorted(mentioned):
        if tok in prop_names_lower or tok == tool_name.lower() or tok in sibling_names_lower:
            continue
        violations.append(
            Violation(
                check="described_not_in_schema",
                severity=Severity.ADVISORY,
                tool_name=tool_name,
                detail=f"description mentions '{tok}' as if it were a parameter, but it is not in the schema",
            )
        )
    return violations


def _check_type_enum_contradiction(
    tool_name: str, description: str, props: dict
) -> list[Violation]:
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
                        severity=Severity.BLOCKING,
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
                            severity=Severity.BLOCKING,
                            tool_name=tool_name,
                            detail=f"description quotes '{q}' near param '{pname}' but schema enum is {penum}",
                        )
                    )
    return violations


def _check_required_missing_property(
    tool_name: str, required: list, props: dict
) -> list[Violation]:
    return [
        Violation(
            check="required_references_missing_property",
            severity=Severity.BLOCKING,
            tool_name=tool_name,
            detail=f"'{r}' is in the schema's required list but is not a key in properties",
        )
        for r in required
        if r not in props
    ]


def _normalize_identifier(token: str) -> str:
    """Fold case/underscore/camelCase differences so 'user_id', 'userId', and
    'UserID' all normalize to the same form: split camelCase boundaries,
    lowercase, strip separators."""
    split = _CAMEL_BOUNDARY_RE.sub("_", token)
    return split.lower().replace("_", "").replace("-", "")


def _is_common_id_suffix_abbreviation(norm_pname: str, norm_tok: str) -> bool:
    """True if norm_pname is exactly norm_tok plus one of the common
    identifier suffixes (id/key/code/no/num/ref/type) -- e.g. 'customerid'
    (customer_id) vs 'customer'. This is routine technical-writing shorthand
    ("the customer" for a customer_id parameter), not a rename signal, and
    was ~79% of this check's clean-corpus false positives before this
    exclusion existed."""
    if not norm_pname.startswith(norm_tok):
        return False
    return norm_pname[len(norm_tok) :] in _COMMON_ID_SUFFIXES


def _shares_prefix(norm_pname: str, norm_tok: str) -> bool:
    """True if one normalized form is a prefix of the other. A genuine rename
    (typo, version suffix like '_v2', or an id-style suffix) always shares a
    common prefix with the original name by construction; an unrelated
    English word that merely happens to be edit-distance-close (e.g.
    'page'/'name', 'query'/'queue', 'limit'/'List') essentially never does.
    This single structural check was the fix that separated genuine renames
    from coincidental short-word collisions -- see
    reports/v2_1_linter_recall_fix.md for the measured before/after."""
    return norm_pname.startswith(norm_tok) or norm_tok.startswith(norm_pname)


def _check_param_possibly_renamed(tool_name: str, description: str, props: dict) -> list[Violation]:
    """(g) Task 4 (v2.1): inverse of (a). For each schema property not
    mentioned verbatim in the description, look for a near-miss token among
    the description's words -- high-precision evidence of a stale rename,
    not a generic "this parameter went undocumented" signal (that is check
    (b), INFO-severity, which fires on ANY undocumented required param
    whether or not a near-miss exists). Two precision guards, both found
    necessary empirically (reports/v2_1_linter_recall_fix.md):
    - A near-miss must share a prefix with the property name (`_shares_prefix`)
      -- excludes coincidental edit-distance-2 collisions between unrelated
      English words that share no common root.
    - Common identifier-suffix abbreviations (`_id`, `_key`, etc.) are
      excluded outright even though they share a prefix -- routine
      documentation shorthand, not a rename.
    """
    desc = description or ""
    desc_lower = desc.lower()
    candidate_tokens = {m.group(0) for m in _WORD_TOKEN_RE.finditer(desc)}
    violations = []
    for pname in props:
        if pname.lower() in desc_lower:
            continue
        norm_pname = _normalize_identifier(pname)
        if len(norm_pname) < _RENAME_MIN_NORMALIZED_LEN:
            continue
        best_token: str | None = None
        best_dist: int | None = None
        for tok in candidate_tokens:
            norm_tok = _normalize_identifier(tok)
            if len(norm_tok) < _RENAME_MIN_NORMALIZED_LEN:
                continue
            if not _shares_prefix(norm_pname, norm_tok):
                continue
            if _is_common_id_suffix_abbreviation(norm_pname, norm_tok):
                continue
            dist = _levenshtein(norm_tok, norm_pname)
            if dist <= _RENAME_MAX_EDIT_DISTANCE and (best_dist is None or dist < best_dist):
                best_token, best_dist = tok, dist
        if best_token is not None:
            violations.append(
                Violation(
                    check="param_possibly_renamed",
                    severity=Severity.ADVISORY,
                    tool_name=tool_name,
                    detail=(
                        f"schema property '{pname}' is not named in the description, but "
                        f"'{best_token}' is (edit distance {best_dist} after case/underscore/"
                        f"camelCase normalization) -- possible stale rename"
                    ),
                )
            )
    return violations


def _check_required_not_mentioned(
    tool_name: str, description: str, required: list
) -> list[Violation]:
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


def lint_tool(
    tool_name: str,
    description: str,
    schema: dict[str, Any],
    sibling_tool_names: frozenset[str] = frozenset(),
) -> ToolLintResult:
    """Run every per-tool check. Pure function, no I/O, no LLM calls.

    `sibling_tool_names`: names of OTHER tools in the same tool set, so
    check (a) can exclude cross-tool workflow references (e.g. "call
    `other_tool` first") from being mistaken for missing parameters. Empty by
    default for single-tool testing; `lint_tool_set` always populates it.
    """
    props: dict[str, Any] = (schema or {}).get("properties", {}) or {}
    required: list[str] = (schema or {}).get("required", []) or []

    result = ToolLintResult(tool_name=tool_name)
    all_violations = (
        _check_described_not_in_schema(tool_name, description, props, sibling_tool_names)
        + _check_type_enum_contradiction(tool_name, description, props)
        + _check_required_missing_property(tool_name, required, props)
        + _check_param_possibly_renamed(tool_name, description, props)
        + _check_required_not_mentioned(tool_name, description, required)
    )
    for v in all_violations:
        if v.severity == Severity.BLOCKING:
            result.blocking.append(v)
        elif v.severity == Severity.ADVISORY:
            result.advisory.append(v)
        else:
            result.info.append(v)
    return result


def check_name_collisions(tool_names: list[str]) -> list[Violation]:
    """Near-duplicate tool names within one tool set (ADVISORY severity).

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
                        severity=Severity.ADVISORY,
                        tool_name=f"{tool_names[i]}/{tool_names[j]}",
                        detail=f"'{tool_names[i]}' and '{tool_names[j]}' are near-duplicate names (similarity={sim:.2f})",
                    )
                )
    return violations


@dataclass
class LintReport:
    """Lint result for a full tool set (one MCP server / manifest entry).
    `collision_violations` (name_collision, ADVISORY) are reported separately
    from per-tool results since they are pairwise, not per-tool."""

    tool_results: list[ToolLintResult]
    collision_violations: list[Violation]

    @property
    def blocking(self) -> list[Violation]:
        return [v for r in self.tool_results for v in r.blocking]

    @property
    def advisory(self) -> list[Violation]:
        return [v for r in self.tool_results for v in r.advisory] + self.collision_violations

    @property
    def info(self) -> list[Violation]:
        return [v for r in self.tool_results for v in r.info]

    @property
    def n_blocking(self) -> int:
        return len(self.blocking)

    @property
    def n_advisory(self) -> int:
        return len(self.advisory)

    @property
    def n_info(self) -> int:
        return len(self.info)

    @property
    def flagged(self) -> bool:
        """A tool set is 'flagged' (fails CI) if it has any BLOCKING-severity
        violation. ADVISORY and INFO never flag a tool set by design (v2.1,
        Task 5) -- ADVISORY findings are still surfaced to the user, just not
        gated on, since both carry measured, only-partially-fixable noise
        (`reports/v2_1_severity_gate.md`)."""
        return self.n_blocking > 0


def lint_tool_set(tools: list[Any]) -> LintReport:
    """Lint a full tool set. `tools` is any sequence of objects with
    `.name`, `.description`, `.inputSchema` attributes (matches `mcp.types.Tool`)."""
    all_names = frozenset(t.name for t in tools)
    tool_results = [
        lint_tool(t.name, t.description or "", t.inputSchema or {}, all_names - {t.name})
        for t in tools
    ]
    collisions = check_name_collisions([t.name for t in tools])
    return LintReport(tool_results=tool_results, collision_violations=collisions)

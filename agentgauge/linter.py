"""Deterministic schema-consistency + name-collision linter (AgentGauge v2).

Replaces v1's LLM-judged 8-axis correlational scorer. Per `reports/v2_axis_triage.md`,
none of v1's 8 axes survived a length-controlled re-test against real task success —
this module ships only checks whose task is genuine defect *detection*
(precision/recall/false-alarm rate against labeled ground truth), never a
correlational score.

Checks, each independently toggleable and each with an explicit severity tier
(v2.1, Task 5: restructured from a single HIGH tier into BLOCKING/ADVISORY on
false-alarm-rate grounds -- see `reports/v2_1_severity_gate.md`; v2.3, Task 2:
RE-tiered by measured causal impact x precision, after live agent runs found
false-alarm rate alone was a poor proxy for real-world severity -- one
BLOCKING check turned out to cause zero measured task-success drop in 3 model
families, while the largest measured drop was on an ADVISORY check. See
`reports/v2_3_task2_retiering.md`):

  BLOCKING severity (fails CI; 0% measured false alarms on the clean corpus,
  100% measured recall, AND a measured task-success drop with CI excluding
  zero in at least 2 of 3 tested model families):
    (c) type_enum_contradiction: boolean-PHRASE description language
        ("true/false", "yes/no", "boolean") near a non-boolean-typed property, or
        a quoted description value absent from that property's schema `enum`. v1
        fired on the bare word "no" anywhere in the description (e.g. "no
        pagination"); v2 requires an explicit boolean phrase, not a single common
        negation word, and requires it within a bounded token window of the
        parameter's own mention (not anywhere in the whole description). Causal
        effect: -13.3 to -40.0pp task success across gemma2:9b/llama3.1:8b/
        qwen2.5:7b (`reports/v2_2_task_b_causal_chain_multimodel.md`).

  ADVISORY severity (surfaced, does not fail CI; each carries measured,
  documented, only-partially-fixable false-alarm noise):
    (a) described_not_in_schema: identifier-like tokens in the top-level tool
        description that don't match any schema property, EXCLUDING tokens that
        only appear in a documented Returns/Output section (v1 false-positived on
        exactly this: a docstring's own return-value field names, e.g.
        `unknown_sections`, mistaken for missing input parameters), "(e.g., ...)"
        example asides, property-value-list parentheticals, explicit
        negations, and enumerated value lists (v2.3, Task 2c precision pass --
        28.57%->23.81% per-tool-set false alarm, still short of the <10%
        BLOCKING bar; kept ADVISORY). Causal effect on its targeted defect
        (`param_renamed`): corrected to near-zero in all 3 models after fixing
        a scoring artifact that had inflated it to -76.7/-80.0pp (`reports/
        v2_3_task1_advisory_audit.md`) -- impact no longer supports promotion
        either.
    (f) name_collision: near-duplicate tool names within one tool set (normalized
        Levenshtein similarity >= the threshold shared with agentgauge.scorer).
        Extracted from v1's `discoverability` axis per v2_axis_triage.md -- this
        was never itself a correlational judgment, just misfiled as 60% of one.
        47.62% per-tool-set false alarm; 86% of clean-corpus violations are a
        documented-irreducible verb-differentiated class (attach/detach,
        put/get, create/delete, etc.) a deterministic Levenshtein heuristic
        cannot resolve without semantic understanding (v2.3, Task 2d). Causal
        impact not measured (no defect-injection instance targets this check).
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
    (e) required_references_missing_property (v2.3, Task 2b): DEMOTED from
        BLOCKING. Still 0% false alarms and 100% recall on its targeted
        defect, but causally measured to have ZERO effect on real task
        success in all 3 tested model families (a bogus required entry
        referencing a nonexistent property gives the agent no real parameter
        to act on either way, so real argument construction is unaffected).
        A BLOCKING gate for a defect class with no measured behavioral impact
        is dead weight -- kept as an INFO-severity signal (still perfect
        precision, so worth surfacing) rather than removed outright. See
        `reports/v2_3_task2_retiering.md`.

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
# v2.3, Task 2c: a sentence mentioning "returns"/"returning" ANYWHERE (not
# just sentence-initial, e.g. "...and returns a status dict with `delivered`
# set to True") is describing output, not input -- dispatch_sms/stage_invoice's
# real clean-corpus false positives. Widening from sentence-initial-only risks
# little: a real missing-parameter mention that happens to share a sentence
# with the word "returns" is not a pattern seen anywhere in the defect-
# injection recall corpus.
_RETURN_ANYWHERE_RE = re.compile(r"\breturns?\b|\breturning\b", re.IGNORECASE)
# A comma-separated run of 3+ short lowercase/snake_case tokens is an
# enumerated VALUE LIST ("Available sections: experience, education,
# interests, ...", job_type's "full_time, part_time, ..."), not 3+
# simultaneously-undocumented parameters -- no real clean-corpus tool
# documents that many distinct missing params in one comma list.
_ENUM_LIST_RE = re.compile(
    r"(?::\s*)?\b([a-z][a-z0-9_]*(?:\s*,\s*[a-z][a-z0-9_]*){2,})\b", re.IGNORECASE
)
_EXAMPLES_SECTION_RE = re.compile(r"\n\s*examples?\s*:", re.IGNORECASE)
# v2.3, Task 2c: two more clean-corpus false-positive categories found by hand
# inspection of described_not_in_schema's 29 residual flags (reports/
# v2_linter_evaluation.md), root-caused precisely rather than patched blind:
# 1. "(e.g., ...)" parenthetical asides give an illustrative example VALUE
#    (a URI, a metric name), not a parameter reference -- e.g. "Compute a named
#    business metric (e.g., churn_rate, MRR)" or "uri: ... (e.g., "core://x/y")".
_EG_PAREN_RE = re.compile(r"\(\s*e\.g\.,?[^)]*\)", re.IGNORECASE)
# 2. A parenthetical directly following "<schema_property>: ...(" lists ENUM-
#    style VALUES for that property (comma-separated short tokens), not
#    separate parameters -- e.g. "date_posted: Filter by posting date
#    (past_hour, past_24_hours, past_week, past_month)". Matched per-property
#    below since the property name must be a real schema key, not any word.
_PROP_VALUE_PAREN_TEMPLATE = r"\b{prop}\s*:[^().]*\(([^)]*)\)"
# 3. "NOT the internal `account_id`" -- an explicit disambiguating negation,
#    never a parameter claim (find_account's real clean-corpus case).
_NOT_NEGATION_RE = re.compile(r"\bnot\b[^.]*", re.IGNORECASE)


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
    2. Any SENTENCE mentioning "returns"/"return"/"returning", even mid-
       paragraph with no section header and not sentence-initial (e.g.
       "Returns the order with discount and tax calculations applied:
       subtotal, discount_amount, ..." or "...and returns a status dict with
       `delivered` set to True") -- found during v2/v2.3 clean-corpus
       measurement, where professional descriptions routinely describe output
       shape inline rather than under a formal heading.
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
    kept = [s for s in sentences if not _RETURN_ANYWHERE_RE.search(s)]
    return " ".join(kept)


def _extract_identifiers(text: str) -> set[str]:
    found = set()
    for m in _IDENTIFIER_RE.finditer(text or ""):
        tok = m.group(1) or m.group(2)
        if tok:
            found.add(tok.lower())
    return found


def _strip_value_hint_parens(text: str, props: dict) -> str:
    """Remove parenthetical spans that give example/enum VALUES rather than
    naming a separate parameter (v2.3, Task 2c -- root-caused against real
    clean-corpus false positives, `reports/v2_linter_evaluation.md`):

    - "(e.g., ...)" asides: "Compute a metric (e.g., churn_rate, MRR)",
      'uri: ... (e.g., "core://agent/my_user")' -- the parenthetical is always
      an illustrative example, never a second parameter name.
    - A parenthetical directly after a REAL schema property's own "prop: ..."
      mention lists candidate values for that property, not other parameters --
      "date_posted: Filter by posting date (past_hour, past_24_hours, ...)".
      Only matched against actual schema property names, not any word, so this
      cannot suppress a genuine undocumented-parameter reference.
    """
    text = _EG_PAREN_RE.sub(" ", text)
    for prop in props:
        pattern = re.compile(rf"(\b{re.escape(prop)}\s*:[^().]*)\([^)]*\)", re.IGNORECASE)
        text = pattern.sub(r"\1", text)
    return text


def _negated_tokens(text: str) -> set[str]:
    """Identifiers named only to be explicitly ruled OUT ("NOT the internal
    `account_id`") -- a disambiguating negation, never a parameter claim
    (find_account's real clean-corpus false positive, v2.3 Task 2c). Scoped to
    a short window after "not" so it cannot suppress unrelated mentions later
    in a long sentence."""
    tokens: set[str] = set()
    for m in re.finditer(r"\bnot\b(.{0,40})", text, re.IGNORECASE):
        tokens |= _extract_identifiers(m.group(1))
    return tokens


def _enum_list_tokens(text: str) -> set[str]:
    """Identifiers appearing only inside a 3+-item comma-separated list
    ("Available sections: experience, education, ..., contact_info, posts")
    -- an enumerated VALUE list for an existing parameter, not 3+
    simultaneously-undocumented parameters (get_person_profile's real
    clean-corpus false positive, v2.3 Task 2c)."""
    tokens: set[str] = set()
    for m in _ENUM_LIST_RE.finditer(text):
        tokens |= _extract_identifiers(m.group(1))
    return tokens


def _check_described_not_in_schema(
    tool_name: str, description: str, props: dict, sibling_tool_names: frozenset[str] = frozenset()
) -> list[Violation]:
    """(a) description mentions an identifier absent from the schema.

    Excludes: the tool's own name (self-reference in prose); any SIBLING tool's
    name in the same tool set (workflow guidance like "use `watch_topic` before
    calling this" references another TOOL, not a parameter -- found as a
    concrete false positive on exp1_blazickjp_arxiv_mcp_server_mirror's
    `check_alerts`/`get_abstract`/etc. tools during v2 clean-corpus measurement,
    fixed here rather than shipped); "(e.g., ...)" example asides and
    property-value-list parentheticals (v2.3, Task 2c); tokens named only to
    be explicitly negated ("NOT the internal X"); tokens appearing only inside
    a 3+-item enumerated value list.
    """
    input_text = _input_section(description)
    input_text = _strip_value_hint_parens(input_text, props)
    mentioned = (
        _extract_identifiers(input_text)
        - _negated_tokens(input_text)
        - _enum_list_tokens(input_text)
    )
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
    """(e) v2.3, Task 2b: demoted BLOCKING -> INFO. Causally measured (`reports/
    v2_2_causal_chain.md`, `reports/v2_2_task_b_causal_chain_multimodel.md`)
    to have ZERO effect on real agent task success in all 3 tested model
    families -- an agent has no real parameter to act on for a bogus required
    entry either way, so its actual argument construction for parameters that
    DO exist is unaffected. A BLOCKING gate for a defect class with no
    measured behavioral impact is dead weight per the task brief's own
    framing; still perfect precision (0% false alarms) so it remains a
    reportable signal, just not one that should fail CI."""
    return [
        Violation(
            check="required_references_missing_property",
            severity=Severity.INFO,
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

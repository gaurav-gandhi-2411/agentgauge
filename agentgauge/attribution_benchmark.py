"""Injected-culprit benchmark generator for `agentgauge.attribution` (v0.5, Wave 1, Component 1.2).

Per `reports/v0_5_eval_doctrine.md` Component 1.2: localization accuracy must be measured against
KNOWN injected culprits, not assumed. This module builds benchmark cases by taking a real,
multi-tool catalog (`evals/fixtures/v2_tool_definitions.json`, the same corpus
`scripts/v2_defect_injector.py` already uses for defect-injection precision/recall measurement),
injecting the REAL, causally-validated `type_enum_contradiction` defect into exactly one
("changed") tool -- the true culprit -- and injecting benign, zero-effect textual changes into the
rest of the changed set (decoys).

**SYNTHETIC BENCHMARK CALIBRATED TO A REAL MEASURED EFFECT SIZE -- NOT A LIVE-MODEL MEASUREMENT.**
The injected culprit's effect magnitude is drawn from `type_enum_contradiction`'s measured
real-agent causal effect range (-13.3pp to -28.9pp task-success drop across 3 model families; see
`scripts/v2_defect_injector.py` and `reports/v2_2_task_b_causal_chain_multimodel.md`), but no live
LLM call is ever made here. `agentgauge.attribution_benchmark.make_probe_fn` builds a `ProbeFn`
(the interface `agentgauge.attribution`'s strategies consume) that feeds deterministic synthetic
`TrialOutcome` pairs -- constructed from this ground-truth model -- through the REAL
`agentgauge.harness.diff_server_level` paired + CUPED + cluster-bootstrap estimator, so every probe
genuinely reuses the harness's own estimator rather than a hand-rolled shortcut. This distinction
(MEASURED-synthetic-benchmark vs. NOT-MEASURED-against-a-real-agent) is restated in
`reports/v0_5_attribution_benchmark.md`.

**Mandatory benchmark-construction confound guard** (doctrine Component 1.2, "9th-artifact
watch"): the true culprit's position within the changed-tool list, and its textual-diff size
relative to the decoys, are BOTH randomized independently of ground truth -- see
`generate_benchmark`'s Fisher-Yates shuffles and `confound_guard_report` below. If either were fixed
(e.g. culprit always
at index 0, or culprit always the largest diff), a positional or diff-size shortcut would win by
construction rather than by real localization signal, and the benchmark would measure its own
generation process instead of attribution quality.

`agentgauge/` package code may not import from `scripts/` (see `agentgauge/harness.py`'s `_rank`
docstring for this repo's existing precedent for that import boundary) -- the defect-injection
mutation below mirrors `scripts/v2_defect_injector.py`'s `inject_type_flipped` exactly but is
reimplemented locally rather than imported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentgauge.attribution import ProbeFn, ProbeResult
from agentgauge.harness import (
    CALIBRATED_BASELINE_RATE,
    CALIBRATED_RESID_SD,
    TrialOutcome,
    _lcg_random,
    diff_server_level,
)
from agentgauge.scorer import _levenshtein

_TOOL_DEFS_PATH = (
    Path(__file__).resolve().parent.parent / "evals" / "fixtures" / "v2_tool_definitions.json"
)

# type_enum_contradiction's measured real-agent causal effect range (task-success DROP from
# injecting the defect), per scripts/v2_defect_injector.py / reports/
# v2_2_task_b_causal_chain_multimodel.md -- both endpoints negative pp.
CAUSAL_EFFECT_MIN_PP = -28.9
CAUSAL_EFFECT_MAX_PP = -13.3

_MIN_TOOLS_PER_CATALOG = 4  # need room for >=1 culprit + >=1 decoy, leaving some tools unchanged
_MIN_CHANGED = 2
_MAX_CHANGED = 6

# Benign decoy mutations at three deliberately different textual-diff-size tiers, so that across
# many benchmark cases some decoys have a LARGER diff than the true culprit's small, fixed-size
# defect-injection mutation -- required by the confound guard (baseline (i), "largest textual
# diff", must not win by construction). None of these carries any real causal effect.
_DECOY_TIER_SUFFIXES: dict[str, str] = {
    "small": " Note.",
    "medium": " This tool is part of the standard workflow for this service.",
    "large": (
        " This tool is part of the standard workflow for this service and is commonly used "
        "together with related operations exposed by this server; consult the documentation for "
        "the full set of supported parameters and their expected formats before calling it in an "
        "automated pipeline."
    ),
}
_DECOY_TIERS: list[str] = ["small", "medium", "large"]


def _stable_seed(base_seed: int, tokens: frozenset[str]) -> int:
    """Deterministic seed derived from a frozenset's contents. Never uses Python's built-in
    `hash()` on strings -- string hashing is randomized per-process by default (PYTHONHASHSEED),
    which would break this repo's determinism convention (seed=42 must reproduce identically
    across runs and machines)."""
    s = "|".join(sorted(tokens))
    acc = base_seed & 0xFFFFFFFF
    for ch in s:
        acc = (acc * 131 + ord(ch)) & 0xFFFFFFFF
    return acc


def _load_corpus() -> list[dict[str, Any]]:
    """Real multi-tool catalogs from the v2 corpus, deduplicated by (tier, tool-name-set) exactly
    as `scripts/v2_defect_injector.py._load_clean_corpus` does, filtered to catalogs with enough
    tools to select a multi-tool changed subset."""
    with _TOOL_DEFS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    seen: set[tuple[str, tuple[str, ...]]] = set()
    catalogs = []
    for entry in data:
        if len(entry["tools"]) < _MIN_TOOLS_PER_CATALOG:
            continue
        key = (entry["tier"], tuple(sorted(t["name"] for t in entry["tools"])))
        if key in seen:
            continue
        seen.add(key)
        catalogs.append(entry)
    return catalogs


def _eligible_culprits(tools: list[dict[str, Any]]) -> list[str]:
    """Tool names with at least one string-typed schema property -- the mutation target
    `_inject_type_enum_contradiction` needs (mirrors `scripts/v2_defect_injector.py`'s
    `inject_type_flipped` eligibility rule)."""
    names = []
    for t in tools:
        props = (t.get("inputSchema") or {}).get("properties", {}) or {}
        if any((p or {}).get("type") == "string" for p in props.values()):
            names.append(t["name"])
    return names


def _inject_type_enum_contradiction(tool: dict[str, Any]) -> dict[str, Any] | None:
    """Mirrors `scripts/v2_defect_injector.py`'s `inject_type_flipped` mutation exactly: flip a
    string schema property's type to `integer` and append a boolean-phrase sentence about it --
    triggers the BLOCKING-severity `type_enum_contradiction` lint check, the only check in this
    repo's linter with a measured causal task-success effect. Returns None if no string property
    exists to mutate (caller must pre-filter with `_eligible_culprits`)."""
    mutated = json.loads(json.dumps(tool))
    props = (mutated.get("inputSchema") or {}).get("properties", {}) or {}
    for pname, pschema in props.items():
        if (pschema or {}).get("type") == "string":
            pschema["type"] = "integer"
            mutated["description"] = (mutated.get("description") or "") + (
                f" Set {pname} to true/false as needed."
            )
            return mutated
    return None


def _inject_benign_decoy(tool: dict[str, Any], tier: str) -> dict[str, Any]:
    """Zero-causal-effect textual change at a given diff-size tier ('small'/'medium'/'large')."""
    mutated = json.loads(json.dumps(tool))
    mutated["description"] = (mutated.get("description") or "") + _DECOY_TIER_SUFFIXES[tier]
    return mutated


class ToolLike:
    """Minimal `.name`/`.description`/`.inputSchema` wrapper over a plain dict, matching the
    shape `agentgauge.linter.lint_tool_set` and `agentgauge.attribution.baseline_most_lint_violations`
    expect (mirrors `mcp.types.Tool`'s attribute surface, and `scripts/v2_defect_injector.py`'s
    private `_T` helper)."""

    def __init__(self, d: dict[str, Any]) -> None:
        self.name: str = d["name"]
        self.description: str = d.get("description") or ""
        self.inputSchema: dict[str, Any] = d.get("inputSchema") or {}


@dataclass
class BenchmarkCase:
    """One injected-culprit scenario. `all_tools_before`/`all_tools_after` are FULL catalogs (dicts
    with name/description/inputSchema) -- baseline (ii) needs the full catalog for sibling-aware
    linting, not just the changed subset."""

    case_id: str
    base_tool_set: str
    all_tools_before: list[dict[str, Any]]
    all_tools_after: list[dict[str, Any]]
    changed_tools: list[str]
    true_culprit: str
    true_effect_pp: float  # negative: task-success drop caused by the injected real defect
    diff_chars: dict[str, int] = field(default_factory=dict)  # per changed tool, before->after

    def before_description(self, tool_name: str) -> str:
        return next(t["description"] or "" for t in self.all_tools_before if t["name"] == tool_name)

    def after_description(self, tool_name: str) -> str:
        return next(t["description"] or "" for t in self.all_tools_after if t["name"] == tool_name)

    def tools_before_like(self) -> list[ToolLike]:
        return [ToolLike(t) for t in self.all_tools_before]

    def tools_after_like(self) -> list[ToolLike]:
        return [ToolLike(t) for t in self.all_tools_after]


def generate_benchmark(n_cases: int = 50, seed: int = 42) -> list[BenchmarkCase]:
    """Generate `n_cases` injected-culprit benchmark cases, cycling deterministically through the
    real multi-tool corpus. Each case's true culprit's index within `changed_tools`, and its
    decoys' diff-size tiers, are drawn independently via `_lcg` -- see module docstring's
    "confound guard" section. Cases where the sampled base catalog has no eligible culprit
    (no string-typed property anywhere) are skipped and re-drawn from the next corpus index."""
    corpus = _load_corpus()
    if not corpus:
        raise RuntimeError(f"No usable multi-tool catalogs found in {_TOOL_DEFS_PATH}")

    rng = _lcg_random(seed)
    cases: list[BenchmarkCase] = []
    attempt = 0
    while len(cases) < n_cases and attempt < n_cases * 20:
        attempt += 1
        entry = corpus[int(rng() * len(corpus)) % len(corpus)]
        tools = entry["tools"]
        eligible = _eligible_culprits(tools)
        if not eligible:
            continue

        max_changed = min(_MAX_CHANGED, len(tools))
        if max_changed < _MIN_CHANGED:
            continue
        n_changed = _MIN_CHANGED + int(rng() * (max_changed - _MIN_CHANGED + 1))
        n_changed = min(n_changed, max_changed)

        culprit_name = eligible[int(rng() * len(eligible)) % len(eligible)]
        other_names = [t["name"] for t in tools if t["name"] != culprit_name]
        # Deterministic shuffle-then-take for the decoy pool (Fisher-Yates via `rng`).
        pool = list(other_names)
        for i in range(len(pool) - 1, 0, -1):
            j = int(rng() * (i + 1))
            pool[i], pool[j] = pool[j], pool[i]
        decoy_names = pool[: n_changed - 1]

        changed = [culprit_name, *decoy_names]
        for i in range(len(changed) - 1, 0, -1):  # randomize the culprit's position too
            j = int(rng() * (i + 1))
            changed[i], changed[j] = changed[j], changed[i]

        true_effect_pp = CAUSAL_EFFECT_MIN_PP + rng() * (
            CAUSAL_EFFECT_MAX_PP - CAUSAL_EFFECT_MIN_PP
        )

        after_tools: list[dict[str, Any]] = []
        diff_chars: dict[str, int] = {}
        ok = True
        for t in tools:
            if t["name"] == culprit_name:
                mutated = _inject_type_enum_contradiction(t)
                if mutated is None:
                    ok = False
                    break
                after_tools.append(mutated)
                diff_chars[t["name"]] = _levenshtein(t["description"] or "", mutated["description"])
            elif t["name"] in decoy_names:
                tier = _DECOY_TIERS[int(rng() * len(_DECOY_TIERS)) % len(_DECOY_TIERS)]
                mutated = _inject_benign_decoy(t, tier)
                after_tools.append(mutated)
                diff_chars[t["name"]] = _levenshtein(t["description"] or "", mutated["description"])
            else:
                after_tools.append(json.loads(json.dumps(t)))
        if not ok:
            continue

        cases.append(
            BenchmarkCase(
                case_id=f"case_{len(cases):03d}",
                base_tool_set=entry["name"],
                all_tools_before=json.loads(json.dumps(tools)),
                all_tools_after=after_tools,
                changed_tools=changed,
                true_culprit=culprit_name,
                true_effect_pp=true_effect_pp,
                diff_chars=diff_chars,
            )
        )
    return cases


def make_probe_fn(
    case: BenchmarkCase, n_tasks: int = 24, n_resamples: int = 500, seed: int = 42
) -> ProbeFn:
    """Build a `ProbeFn` for one benchmark case. Every call feeds deterministic synthetic
    `TrialOutcome` pairs through the REAL `agentgauge.harness.diff_server_level` paired + CUPED +
    cluster-bootstrap estimator -- reusing the harness's own estimator, per the doctrine's
    instruction, rather than returning a hand-computed number directly.

    GROUND TRUTH MODEL (synthetic, deterministic, NOT a live measurement): reverting a subset S
    recovers `-case.true_effect_pp` percentage points of task success IF AND ONLY IF
    `case.true_culprit` is in S; every decoy tool has EXACTLY zero causal effect regardless of
    whether it is reverted. Each of `n_tasks` synthetic tasks' observed success rate is
    `CALIBRATED_BASELINE_RATE` (the real corpus-wide grand mean from `harness.py`, not invented)
    minus the active defect penalty, plus independent uniform noise scaled to
    `CALIBRATED_RESID_SD` (harness.py's measured within-task residual spread) -- so bootstrap CI
    width reflects the same measured variance structure the harness's real MDE table uses.
    `n_resamples=500` (vs. harness's own 2000 default) is a benchmarking-speed reduction only,
    documented here rather than silently applied; production callers of `diff_server_level` should
    use its own default.
    """
    magnitude_frac = -case.true_effect_pp / 100.0

    def probe(reverted: frozenset[str]) -> ProbeResult:
        rng = _lcg_random(_stable_seed(seed, reverted))
        defect_active_after = case.true_culprit not in reverted
        before_trials: list[TrialOutcome] = []
        after_trials: list[TrialOutcome] = []
        for i in range(n_tasks):
            task_name = f"t{i}"
            noise_before = (rng() - 0.5) * 2 * CALIBRATED_RESID_SD
            noise_after = (rng() - 0.5) * 2 * CALIBRATED_RESID_SD
            # "before" arm = current regressed state (nothing reverted): defect always active.
            rate_before = _clip01(CALIBRATED_BASELINE_RATE - magnitude_frac + noise_before)
            # "after" arm = state with `reverted` applied: defect active only if culprit not reverted.
            penalty_after = magnitude_frac if defect_active_after else 0.0
            rate_after = _clip01(CALIBRATED_BASELINE_RATE - penalty_after + noise_after)
            before_trials.append(TrialOutcome(task_name, task_name, rate_before))
            after_trials.append(TrialOutcome(task_name, task_name, rate_after))
        result = diff_server_level(
            before_trials,
            after_trials,
            n_resamples=n_resamples,
            seed=_stable_seed(seed, reverted),
        )
        return ProbeResult(result.delta, result.ci_lo, result.ci_hi)

    return probe


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


@dataclass
class ConfoundGuardReport:
    """Confirms the mandatory benchmark-construction guard (doctrine Component 1.2): the true
    culprit's position within `changed_tools` is not fixed, and decoy diff sizes are not
    systematically smaller than the true culprit's diff."""

    n_cases: int
    position_counts: dict[int, int]
    n_positions_observed: int
    n_cases_culprit_is_max_diff: int
    frac_cases_culprit_is_max_diff: float
    n_cases_a_decoy_exceeds_culprit_diff: int
    frac_cases_a_decoy_exceeds_culprit_diff: float


def confound_guard_report(cases: list[BenchmarkCase]) -> ConfoundGuardReport:
    """Compute the mandatory confound-guard statistics over a generated benchmark set."""
    position_counts: dict[int, int] = {}
    n_culprit_is_max = 0
    n_decoy_exceeds = 0
    for case in cases:
        pos = case.changed_tools.index(case.true_culprit)
        position_counts[pos] = position_counts.get(pos, 0) + 1
        culprit_diff = case.diff_chars.get(case.true_culprit, 0)
        decoy_diffs = [v for k, v in case.diff_chars.items() if k != case.true_culprit]
        if not decoy_diffs or culprit_diff >= max(decoy_diffs):
            n_culprit_is_max += 1
        if any(d > culprit_diff for d in decoy_diffs):
            n_decoy_exceeds += 1
    n = len(cases)
    return ConfoundGuardReport(
        n_cases=n,
        position_counts=position_counts,
        n_positions_observed=len(position_counts),
        n_cases_culprit_is_max_diff=n_culprit_is_max,
        frac_cases_culprit_is_max_diff=n_culprit_is_max / n if n else 0.0,
        n_cases_a_decoy_exceeds_culprit_diff=n_decoy_exceeds,
        frac_cases_a_decoy_exceeds_culprit_diff=n_decoy_exceeds / n if n else 0.0,
    )

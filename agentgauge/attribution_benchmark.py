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

**Measurement artifact #9 (diff-size confound, found and fixed this pass):** the ORIGINAL version
of this generator satisfied both of the guard's two edge-condition checks (culprit not always the
single max-diff tool; some decoy sometimes exceeds it) while still having a real, systematic
DISTRIBUTIONAL correlation between diff size and culprit status: the defect-injection sentence
(`_inject_type_enum_contradiction`) was a fixed-length ~32-47 char mutation, while 2 of the 3 decoy
tiers ("medium" ~65 chars, "large" ~230 chars) were unconditionally larger than that range by
construction. The culprit's diff-size RANK was skewed small (mean fractional rank ~0.66-0.73 on a
0=biggest/1=smallest scale, measured on n=50 and n=300 samples) not by chance but as a direct,
deterministic consequence of the tier-size choices -- this is why `baseline_largest_textual_diff`
scored 4% top-1 against a 26.7% random floor: the benchmark was actively pointing that heuristic at
the WRONG tool more often than chance would. FIX: the culprit's mutation now ALSO draws an
independent camouflage tier from the exact same `_DECOY_TIERS`/`_DECOY_TIER_SUFFIXES`
distribution decoys use, appended after the mandatory defect sentence (see
`_inject_type_enum_contradiction`'s `camouflage_suffix` parameter) -- so the culprit's total diff
length is drawn from a process independent of its role, not a structural giveaway. This camouflage
suffix is disclosed as exactly that: synthetic benchmark-construction plumbing bolted onto the
real, causally-validated defect sentence for decorrelation purposes, not itself part of the real
`type_enum_contradiction` defect. `tests/test_attribution_benchmark.py::TestConfoundGuard::
test_culprit_diff_size_distribution_not_correlated_with_role` is the standing distributional check
added for this artifact class; `agentgauge.audit.check_benchmark_construction_diffsize_bias` is the
standing, reusable audit function for the same class of bias in any future benchmark generator.

`agentgauge/` package code may not import from `scripts/` (see `agentgauge/harness.py`'s `_rank`
docstring for this repo's existing precedent for that import boundary) -- the defect-injection
mutation below mirrors `scripts/v2_defect_injector.py`'s `inject_type_flipped` exactly but is
reimplemented locally rather than imported.

**Measurement artifact #10 (probe-variance floor, found and fixed in the v0.5 Wave 1 MDE-discrepancy
investigation, see `reports/v0_5_mde_discrepancy.md`):** the ORIGINAL version of `make_probe_fn`/
`make_multi_probe_fn`'s ground-truth model added ONLY per-observation, i.i.d. noise scaled to
`CALIBRATED_RESID_SD` (0.1392) to each synthetic task's rate -- it never modeled the calibrated
BETWEEN-task variance component (`CALIBRATED_SIGMA_TASK` = 0.3588, correlated at `CALIBRATED_RHO` =
0.881 between the before/after arms of the same task) that `agentgauge.harness.simulate_task_level_pairs`
uses to produce this repo's own headline, validated MDE figures (server-level 5.37pp at n=253;
per-probe >=16.91pp at n=24, `reports/v0_5_effect_size_sensitivity.md` section 0). Since
`CALIBRATED_SIGMA_TASK` accounts for the majority of real measured variance (`reports/
v2_variance_structure.md`: 56.1% of total variance is between-task), omitting it made every probe's
synthetic ground truth dramatically LOWER-noise, and therefore higher-powered, than a real deployment
at the same `n_tasks` -- confirmed empirically (`reports/v0_5_mde_discrepancy.md`): detection power at
5-8pp effect and n_tasks=24 measured 72-97% under the pre-fix noise model vs. 10-28% once the
calibrated task-level variance component is included. FIX: both `probe()` closures below now draw a
correlated `task_effect`/`after_task_effect` pair per synthetic task (mirroring
`simulate_task_level_pairs` exactly, including its `_approx_standard_normal` noise draws in place of
the ad hoc uniform noise the original version used), so a benchmark probe's variance is no longer
structurally cleaner than what the harness's own calibration says a real probe would see.
`agentgauge.audit.check_probe_variance_calibration` is the standing check for this artifact class.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentgauge.attribution import ProbeFn, ProbeResult
from agentgauge.harness import (
    CALIBRATED_BASELINE_RATE,
    CALIBRATED_RESID_SD,
    CALIBRATED_RHO,
    CALIBRATED_SIGMA_TASK,
    TrialOutcome,
    _approx_standard_normal,
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

# Benign decoy mutations at three deliberately different textual-diff-size tiers. Both the true
# culprit and every decoy independently draw one of these three tiers (see `generate_benchmark`)
# -- required by the confound guard (baseline (i), "largest textual diff", must not win by
# construction, in EITHER direction). None of these tier suffixes carries any real causal effect.
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

# Measurement artifact #9 fix: the true culprit's mandatory defect sentence
# (`_inject_type_enum_contradiction`'s "Set {pname} to true/false as needed.") has a non-zero
# fixed floor length (~32-47 chars depending on property name) that a decoy's mutation, having no
# mandatory content, does not share. Appending the SAME independently-drawn tier suffix to both
# (see `generate_benchmark`) is necessary but not sufficient to decorrelate diff size from role --
# it leaves the culprit's total diff systematically ~35-40 chars ABOVE a decoy's, which reversed
# (not eliminated) the original bias when measured (Task 3a re-run showed mean fractional rank
# moving from ~0.66 to ~0.35 -- the mirror-image problem). FIX: give every decoy this same
# fixed-length, zero-causal-effect FLOOR sentence before its own tier suffix, so both culprit and
# decoy start from a comparable non-zero floor before the shared independently-drawn tier is
# layered on top -- this is what actually closes the gap (see `_inject_benign_decoy`). Length
# (38 chars) was chosen to sit inside the defect sentence's measured 32-47 char range, not fitted
# to make a specific reported number look good.
_DECOY_FLOOR_FILLER = " This value is supplied by the caller."


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


def _inject_type_enum_contradiction(
    tool: dict[str, Any], camouflage_suffix: str = ""
) -> dict[str, Any] | None:
    """Mirrors `scripts/v2_defect_injector.py`'s `inject_type_flipped` mutation exactly: flip a
    string schema property's type to `integer` and append a boolean-phrase sentence about it --
    triggers the BLOCKING-severity `type_enum_contradiction` lint check, the only check in this
    repo's linter with a measured causal task-success effect. Returns None if no string property
    exists to mutate (caller must pre-filter with `_eligible_culprits`).

    `camouflage_suffix`, if given, is appended AFTER the mandatory defect sentence. This is a
    SYNTHETIC diff-size camouflage layer, not part of the real defect -- see `generate_benchmark`'s
    docstring ("diff-size decorrelation") for why it exists and honest disclosure that it is
    benchmark-construction plumbing, not a property of the real `type_enum_contradiction` defect
    itself. The defect-triggering sentence (type flip + boolean phrase) is always present verbatim
    regardless of `camouflage_suffix`."""
    mutated = json.loads(json.dumps(tool))
    props = (mutated.get("inputSchema") or {}).get("properties", {}) or {}
    for pname, pschema in props.items():
        if (pschema or {}).get("type") == "string":
            pschema["type"] = "integer"
            mutated["description"] = (
                (mutated.get("description") or "")
                + f" Set {pname} to true/false as needed."
                + camouflage_suffix
            )
            return mutated
    return None


def _inject_benign_decoy(tool: dict[str, Any], tier: str) -> dict[str, Any]:
    """Zero-causal-effect textual change at a given diff-size tier ('small'/'medium'/'large').

    Prepends `_DECOY_FLOOR_FILLER` -- a fixed-length, zero-causal-effect sentence sized to match
    the true culprit's mandatory defect-sentence floor -- before the tier suffix (measurement
    artifact #9 fix; see `_DECOY_FLOOR_FILLER`'s docstring comment for why this floor is needed,
    not just the shared tier draw alone)."""
    mutated = json.loads(json.dumps(tool))
    mutated["description"] = (
        (mutated.get("description") or "") + _DECOY_FLOOR_FILLER + _DECOY_TIER_SUFFIXES[tier]
    )
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


def generate_benchmark(
    n_cases: int = 50,
    seed: int = 42,
    effect_min_pp: float = CAUSAL_EFFECT_MIN_PP,
    effect_max_pp: float = CAUSAL_EFFECT_MAX_PP,
    n_changed: int | None = None,
) -> list[BenchmarkCase]:
    """Generate `n_cases` injected-culprit benchmark cases, cycling deterministically through the
    real multi-tool corpus. Each case's true culprit's index within `changed_tools`, and its
    decoys' diff-size tiers, are drawn independently via `_lcg` -- see module docstring's
    "confound guard" section. Cases where the sampled base catalog has no eligible culprit
    (no string-typed property anywhere) are skipped and re-drawn from the next corpus index.

    `effect_min_pp`/`effect_max_pp` (v0.5 Wave 1, effect-size sensitivity study, see
    `reports/v0_5_effect_size_sensitivity.md`): the true culprit's injected effect magnitude is
    drawn uniformly from `[effect_min_pp, effect_max_pp]`, defaulting to the module's original
    fixed range (`CAUSAL_EFFECT_MIN_PP`/`CAUSAL_EFFECT_MAX_PP`, the measured real-agent causal
    range) so existing callers are behavior-preserving. Both follow this module's existing SIGNED
    `_pp` convention (negative = task-success drop; `effect_min_pp` is the more-negative, i.e.
    LARGER-magnitude, endpoint) -- NOT an absolute-magnitude convention. Passing a caller-specified
    band lets accuracy be measured as the true effect shrinks toward (or below) the harness's own
    measured minimum detectable effect, instead of only at the original benchmark's favorable,
    well-separated 13.3-28.9pp range.

    This parameter only changes which interval the SAME single per-case `rng()` draw is mapped
    into -- it consumes exactly one PRNG state transition regardless of the interval, identically
    to the original two-constant version. It therefore cannot, by construction, change which
    catalog/culprit/decoy-tier/position values any other part of this function draws for a given
    seed (those come from separate, sequentially-later `rng()` calls whose count and order do not
    depend on the value returned by the effect draw) -- see
    `reports/v0_5_effect_size_sensitivity.md` for the empirical confirmation of this argument
    across multiple bands with independent seeds.

    `n_changed` (v0.5 Wave 1, scale-curve study, see `reports/v0_5_scale_curve.md`): if `None`
    (default), the candidate-set size is drawn per-case in `[2, 6]` exactly as before -- fully
    behavior-preserving, byte-identical to every prior caller. If an `int`, EVERY generated case
    uses exactly that candidate-set size (a "pinned size" benchmark), and only catalogs with at
    least `n_changed` tools total are eligible (catalogs are filtered up front; a catalog with
    fewer tools than requested can never produce a case of that size and is skipped outright, not
    retried per-case). This is a separate code path from the default `n_changed=None` behavior --
    it consumes a different number/order of `rng()` calls (no per-case candidate-set-size draw),
    so it is not expected to reproduce the default path's case sequence at the same seed, and does
    not need to."""
    corpus = _load_corpus()
    if n_changed is not None:
        corpus = [e for e in corpus if len(e["tools"]) >= n_changed]
    if not corpus:
        raise RuntimeError(
            f"No usable multi-tool catalogs found in {_TOOL_DEFS_PATH}"
            + (f" with >= {n_changed} tools" if n_changed is not None else "")
        )

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

        if n_changed is not None:
            # Pinned-size path: catalogs too small to support `n_changed` were already filtered
            # out of `corpus` above, so `len(tools) >= n_changed` holds here unconditionally.
            n_changed_case = n_changed
        else:
            max_changed = min(_MAX_CHANGED, len(tools))
            if max_changed < _MIN_CHANGED:
                continue
            n_changed_case = _MIN_CHANGED + int(rng() * (max_changed - _MIN_CHANGED + 1))
            n_changed_case = min(n_changed_case, max_changed)

        culprit_name = eligible[int(rng() * len(eligible)) % len(eligible)]
        other_names = [t["name"] for t in tools if t["name"] != culprit_name]
        # Deterministic shuffle-then-take for the decoy pool (Fisher-Yates via `rng`).
        pool = list(other_names)
        for i in range(len(pool) - 1, 0, -1):
            j = int(rng() * (i + 1))
            pool[i], pool[j] = pool[j], pool[i]
        decoy_names = pool[: n_changed_case - 1]

        changed = [culprit_name, *decoy_names]
        for i in range(len(changed) - 1, 0, -1):  # randomize the culprit's position too
            j = int(rng() * (i + 1))
            changed[i], changed[j] = changed[j], changed[i]

        true_effect_pp = effect_min_pp + rng() * (effect_max_pp - effect_min_pp)

        after_tools: list[dict[str, Any]] = []
        diff_chars: dict[str, int] = {}
        ok = True
        for t in tools:
            if t["name"] == culprit_name:
                # Diff-size decorrelation (measurement artifact #9, see module docstring): draw
                # the culprit's camouflage tier from the SAME distribution/probabilities as decoy
                # tiers, independently of ground truth, so the culprit's total diff length is not
                # a structural giveaway of its role.
                culprit_tier = _DECOY_TIERS[int(rng() * len(_DECOY_TIERS)) % len(_DECOY_TIERS)]
                mutated = _inject_type_enum_contradiction(
                    t, camouflage_suffix=_DECOY_TIER_SUFFIXES[culprit_tier]
                )
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
    whether it is reverted. Each of `n_tasks` synthetic tasks draws a correlated
    `task_effect`/`after_task_effect` pair (scale `CALIBRATED_SIGMA_TASK`, correlation
    `CALIBRATED_RHO` between the before/after arms of the SAME task) plus independent residual
    noise (scale `CALIBRATED_RESID_SD`) per arm -- exactly the variance structure
    `agentgauge.harness.simulate_task_level_pairs` uses to produce this repo's own validated MDE
    figures (measurement artifact #10 fix, see module docstring: the original version of this
    function omitted `task_effect` entirely, making every probe's noise floor structurally lower
    than the harness's own calibration). `n_resamples=500` (vs. harness's own 2000 default) is a
    benchmarking-speed reduction only, documented here rather than silently applied; production
    callers of `diff_server_level` should use its own default.
    """
    magnitude_frac = -case.true_effect_pp / 100.0

    def probe(reverted: frozenset[str]) -> ProbeResult:
        rng = _lcg_random(_stable_seed(seed, reverted))
        defect_active_after = case.true_culprit not in reverted
        before_trials: list[TrialOutcome] = []
        after_trials: list[TrialOutcome] = []
        for i in range(n_tasks):
            task_name = f"t{i}"
            task_effect = _approx_standard_normal(rng) * CALIBRATED_SIGMA_TASK
            indep_component = _approx_standard_normal(rng) * CALIBRATED_SIGMA_TASK
            after_task_effect = (
                CALIBRATED_RHO * task_effect
                + math.sqrt(max(0.0, 1 - CALIBRATED_RHO**2)) * indep_component
            )
            noise_before = _approx_standard_normal(rng) * CALIBRATED_RESID_SD
            noise_after = _approx_standard_normal(rng) * CALIBRATED_RESID_SD
            # "before" arm = current regressed state (nothing reverted): defect always active.
            rate_before = _clip01(
                CALIBRATED_BASELINE_RATE - magnitude_frac + task_effect + noise_before
            )
            # "after" arm = state with `reverted` applied: defect active only if culprit not reverted.
            penalty_after = magnitude_frac if defect_active_after else 0.0
            rate_after = _clip01(
                CALIBRATED_BASELINE_RATE - penalty_after + after_task_effect + noise_after
            )
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


def fractional_rank_from_diffs(culprit_diff: int, decoy_diffs: list[int]) -> float | None:
    """The true culprit's diff-size rank among itself + its case's decoys, on a 0=biggest /
    1=smallest scale, ties averaged. Returns `None` when there are no decoys to rank against (a
    single-tool "case" has no distributional information). This is the artifact-#9 diagnostic
    statistic: under a role-independent (unbiased) generating process, its expectation over many
    cases is 0.5 -- a mean far from 0.5 is direct evidence that diff size is correlated with
    culprit-vs-decoy status, exactly the bias measured and fixed in this module (see the module
    docstring's "Measurement artifact #9" section). Reused, in duplicate but deliberately
    decoupled form, by `agentgauge.audit.check_benchmark_construction_diffsize_bias` -- that
    module intentionally does not import this benchmark-specific module (see its own docstring),
    so the two implementations are independent computations of the same statistic, not one
    calling the other."""
    all_diffs = [culprit_diff, *decoy_diffs]
    n = len(all_diffs)
    if n <= 1:
        return None
    sorted_desc = sorted(all_diffs, reverse=True)
    positions = [i for i, v in enumerate(sorted_desc) if v == culprit_diff]
    avg_pos = sum(positions) / len(positions)
    return avg_pos / (n - 1)


@dataclass
class ConfoundGuardReport:
    """Confirms the mandatory benchmark-construction guard (doctrine Component 1.2): the true
    culprit's position within `changed_tools` is not fixed, decoy diff sizes are not
    systematically smaller than the true culprit's diff, and (measurement artifact #9, added when
    the first two conditions were found insufficient) the culprit's diff-size RANK distribution is
    not systematically skewed toward either end -- see `fractional_rank_from_diffs`."""

    n_cases: int
    position_counts: dict[int, int]
    n_positions_observed: int
    n_cases_culprit_is_max_diff: int
    frac_cases_culprit_is_max_diff: float
    n_cases_a_decoy_exceeds_culprit_diff: int
    frac_cases_a_decoy_exceeds_culprit_diff: float
    mean_culprit_fractional_rank: float
    mean_culprit_diff_chars: float
    mean_decoy_diff_chars: float


def confound_guard_report(cases: list[BenchmarkCase]) -> ConfoundGuardReport:
    """Compute the mandatory confound-guard statistics over a generated benchmark set."""
    position_counts: dict[int, int] = {}
    n_culprit_is_max = 0
    n_decoy_exceeds = 0
    fractional_ranks: list[float] = []
    culprit_diffs: list[int] = []
    decoy_diffs_all: list[int] = []
    for case in cases:
        pos = case.changed_tools.index(case.true_culprit)
        position_counts[pos] = position_counts.get(pos, 0) + 1
        culprit_diff = case.diff_chars.get(case.true_culprit, 0)
        decoy_diffs = [v for k, v in case.diff_chars.items() if k != case.true_culprit]
        culprit_diffs.append(culprit_diff)
        decoy_diffs_all.extend(decoy_diffs)
        if not decoy_diffs or culprit_diff >= max(decoy_diffs):
            n_culprit_is_max += 1
        if any(d > culprit_diff for d in decoy_diffs):
            n_decoy_exceeds += 1
        rank = fractional_rank_from_diffs(culprit_diff, decoy_diffs)
        if rank is not None:
            fractional_ranks.append(rank)
    n = len(cases)
    return ConfoundGuardReport(
        n_cases=n,
        position_counts=position_counts,
        n_positions_observed=len(position_counts),
        n_cases_culprit_is_max_diff=n_culprit_is_max,
        frac_cases_culprit_is_max_diff=n_culprit_is_max / n if n else 0.0,
        n_cases_a_decoy_exceeds_culprit_diff=n_decoy_exceeds,
        frac_cases_a_decoy_exceeds_culprit_diff=n_decoy_exceeds / n if n else 0.0,
        mean_culprit_fractional_rank=(
            sum(fractional_ranks) / len(fractional_ranks) if fractional_ranks else 0.5
        ),
        mean_culprit_diff_chars=sum(culprit_diffs) / len(culprit_diffs) if culprit_diffs else 0.0,
        mean_decoy_diff_chars=(
            sum(decoy_diffs_all) / len(decoy_diffs_all) if decoy_diffs_all else 0.0
        ),
    )


# =============================================================================
# Multi-culprit benchmark (v0.5 Wave 1, scale-curve study, Task 2b, see
# `reports/v0_5_scale_curve.md`). A SEPARATE dataclass/generator/probe-model/confound-guard track
# from the single-culprit machinery above, not a variant bolted onto `BenchmarkCase` -- keeping the
# two explicit avoids ambiguous "is `true_culprit` singular or plural here" call sites and keeps
# every existing single-culprit caller (including `reports/v0_5_attribution_benchmark.md` and
# `reports/v0_5_effect_size_sensitivity.md`'s reproduction scripts) byte-for-byte unaffected.
# =============================================================================


@dataclass
class MultiCulpritBenchmarkCase:
    """One injected-MULTI-culprit scenario: 2 or 3 real, independently-injected
    `type_enum_contradiction` defects within one changed set, alongside benign decoys exactly as
    in `BenchmarkCase`. `true_culprits` is unordered (ground truth, not a ranking);
    `true_effects_pp` gives each culprit's own independently-drawn effect magnitude (same signed
    `_pp` convention as `BenchmarkCase.true_effect_pp`)."""

    case_id: str
    base_tool_set: str
    all_tools_before: list[dict[str, Any]]
    all_tools_after: list[dict[str, Any]]
    changed_tools: list[str]
    true_culprits: list[str]
    true_effects_pp: dict[str, float]
    diff_chars: dict[str, int] = field(default_factory=dict)

    def before_description(self, tool_name: str) -> str:
        return next(t["description"] or "" for t in self.all_tools_before if t["name"] == tool_name)

    def after_description(self, tool_name: str) -> str:
        return next(t["description"] or "" for t in self.all_tools_after if t["name"] == tool_name)

    def tools_before_like(self) -> list[ToolLike]:
        return [ToolLike(t) for t in self.all_tools_before]

    def tools_after_like(self) -> list[ToolLike]:
        return [ToolLike(t) for t in self.all_tools_after]


def generate_multi_culprit_benchmark(
    n_cases: int,
    n_culprits: int,
    n_changed: int,
    seed: int = 42,
    effect_min_pp: float = CAUSAL_EFFECT_MIN_PP,
    effect_max_pp: float = CAUSAL_EFFECT_MAX_PP,
) -> list[MultiCulpritBenchmarkCase]:
    """Generate `n_cases` benchmark cases with `n_culprits` (2 or 3) simultaneous, independently-
    injected real `type_enum_contradiction` defects within one changed set of exactly `n_changed`
    tools -- reusing this module's catalog-loading (`_load_corpus`), eligibility
    (`_eligible_culprits`), and mutation (`_inject_type_enum_contradiction` /
    `_inject_benign_decoy`) machinery unchanged, the same way `generate_benchmark` does.

    Design choices, stated explicitly (per this task's instruction not to leave them implicit):

    - **Effect magnitude**: each of the `n_culprits` culprits independently draws its own effect
      from `[effect_min_pp, effect_max_pp]` (defaulting to the same measured real-agent causal
      range `generate_benchmark` uses) -- no shared or capped total. `make_multi_probe_fn`
      combines them additively (see its docstring); this can push a 3-culprit case's combined
      penalty toward `CALIBRATED_BASELINE_RATE`'s floor at the extreme end of the range -- see
      `reports/v0_5_scale_curve.md` for the measured floor-clipping rate, reported rather than
      silently avoided by shrinking the range.
    - **Candidate-set size**: pinned via `n_changed` (reusing the same pinning mechanism as
      `generate_benchmark`'s `n_changed` parameter), not drawn -- multi-culprit cases need
      `n_changed >= n_culprits + 1` (at least one decoy; a case with zero decoys has no
      localization problem to solve) and this is enforced with a `ValueError`, not silently
      clamped.
    - **Culprit selection**: `n_culprits` DISTINCT eligible tools are chosen via a Fisher-Yates
      shuffle of the catalog's eligible-culprit list (same shuffle-then-take pattern
      `generate_benchmark` uses for decoys), so which tools become culprits is independent of
      catalog order. Cases where a catalog has fewer than `n_culprits` eligible tools are skipped
      and re-drawn, exactly as `generate_benchmark` skips catalogs with no eligible culprit at all.
    - **Position randomization**: culprits and decoys are combined into one list and Fisher-Yates
      shuffled together (not culprits-first) so culprit positions within `changed_tools` are not
      systematically clustered -- required for the position half of the confound guard to mean
      anything for a multi-culprit case (see `multi_confound_guard_report`).
    """
    if n_culprits < 2:
        raise ValueError(
            f"n_culprits must be >= 2 (got {n_culprits}); use generate_benchmark for the "
            "single-culprit case"
        )
    if n_changed < n_culprits + 1:
        raise ValueError(
            f"n_changed ({n_changed}) must be >= n_culprits + 1 ({n_culprits + 1}) -- a "
            "multi-culprit case needs at least one decoy to pose a localization problem"
        )

    corpus = [e for e in _load_corpus() if len(e["tools"]) >= n_changed]
    if not corpus:
        raise RuntimeError(
            f"No usable multi-tool catalogs found in {_TOOL_DEFS_PATH} with >= {n_changed} tools"
        )

    rng = _lcg_random(seed)
    cases: list[MultiCulpritBenchmarkCase] = []
    attempt = 0
    while len(cases) < n_cases and attempt < n_cases * 40:
        attempt += 1
        entry = corpus[int(rng() * len(corpus)) % len(corpus)]
        tools = entry["tools"]
        eligible = _eligible_culprits(tools)
        if len(eligible) < n_culprits:
            continue

        elig_pool = list(eligible)
        for i in range(len(elig_pool) - 1, 0, -1):
            j = int(rng() * (i + 1))
            elig_pool[i], elig_pool[j] = elig_pool[j], elig_pool[i]
        culprit_names = elig_pool[:n_culprits]
        culprit_set = set(culprit_names)

        other_names = [t["name"] for t in tools if t["name"] not in culprit_set]
        pool = list(other_names)
        for i in range(len(pool) - 1, 0, -1):
            j = int(rng() * (i + 1))
            pool[i], pool[j] = pool[j], pool[i]
        n_decoys = n_changed - n_culprits
        if len(pool) < n_decoys:
            continue
        decoy_names = pool[:n_decoys]

        changed = [*culprit_names, *decoy_names]
        for i in range(len(changed) - 1, 0, -1):
            j = int(rng() * (i + 1))
            changed[i], changed[j] = changed[j], changed[i]

        true_effects_pp: dict[str, float] = {
            c: effect_min_pp + rng() * (effect_max_pp - effect_min_pp) for c in culprit_names
        }

        after_tools: list[dict[str, Any]] = []
        diff_chars: dict[str, int] = {}
        ok = True
        for t in tools:
            if t["name"] in culprit_set:
                culprit_tier = _DECOY_TIERS[int(rng() * len(_DECOY_TIERS)) % len(_DECOY_TIERS)]
                mutated = _inject_type_enum_contradiction(
                    t, camouflage_suffix=_DECOY_TIER_SUFFIXES[culprit_tier]
                )
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
            MultiCulpritBenchmarkCase(
                case_id=f"multi{n_culprits}_case_{len(cases):03d}",
                base_tool_set=entry["name"],
                all_tools_before=json.loads(json.dumps(tools)),
                all_tools_after=after_tools,
                changed_tools=changed,
                true_culprits=culprit_names,
                true_effects_pp=true_effects_pp,
                diff_chars=diff_chars,
            )
        )
    return cases


def make_multi_probe_fn(
    case: MultiCulpritBenchmarkCase, n_tasks: int = 24, n_resamples: int = 500, seed: int = 42
) -> ProbeFn:
    """Build a `ProbeFn` for one multi-culprit benchmark case. Directly generalizes
    `make_probe_fn`'s ground-truth model to multiple simultaneous culprits.

    GROUND TRUTH MODEL, effect-combination choice stated explicitly (per this task's instruction
    not to leave it implicit): effects combine ADDITIVELY. Each active (not-yet-reverted) culprit
    contributes its own independently-drawn penalty; reverting a subset S removes exactly the sum
    of the penalties of the culprits in S, leaving every other active culprit's penalty untouched.
    This is the simplest defensible choice (each real regression is an independent cause of task
    failure, and reverting one doesn't change how much a DIFFERENT, still-active regression still
    hurts) and it is a direct, drop-in generalization of `make_probe_fn`'s single-culprit model:
    with `n_culprits=1` this reduces to exactly the same arithmetic `make_probe_fn` uses (confirmed
    by `tests/test_scale_curve.py::TestMakeMultiProbeFn::
    test_reduces_to_single_culprit_model_at_n_culprits_1`).

    As in `make_probe_fn`, the "before" arm is the CURRENT regressed state held constant (ALL
    culprits active, nothing reverted) and the "after" arm reflects the caller-specified `reverted`
    subset -- `delta = probe(reverted).delta` measures exactly the summed effect of the reverted
    culprits' penalties being removed.

    KNOWN LIMITATION, measured not assumed (see `reports/v0_5_scale_curve.md`): summing up to 3
    independently-drawn penalties from the same 13.3-28.9pp range as the single-culprit benchmark
    can push the "before" arm's rate toward/below `CALIBRATED_BASELINE_RATE`'s floor (0.0 after
    `_clip01`), compressing the measured delta below what pure addition would predict at the
    extreme end of the range -- reported as a caveat, not silently avoided by shrinking the range.

    Measurement artifact #10 fix (see module docstring / `make_probe_fn`): each synthetic task also
    draws the same calibrated, correlated `task_effect`/`after_task_effect` pair `make_probe_fn`
    does, not residual-only noise -- required for `test_reduces_to_single_culprit_model_at_n_culprits_1`
    to keep holding (the two functions' RNG draw order/count must stay identical at `n_culprits=1`).
    """
    magnitudes_frac: dict[str, float] = {c: -eff / 100.0 for c, eff in case.true_effects_pp.items()}
    total_magnitude_frac = sum(magnitudes_frac.values())

    def probe(reverted: frozenset[str]) -> ProbeResult:
        rng = _lcg_random(_stable_seed(seed, reverted))
        active_penalty = sum(m for c, m in magnitudes_frac.items() if c not in reverted)
        before_trials: list[TrialOutcome] = []
        after_trials: list[TrialOutcome] = []
        for i in range(n_tasks):
            task_name = f"t{i}"
            # Measurement artifact #10 fix (see module docstring / `make_probe_fn`): draw the same
            # calibrated correlated task-level variance component `make_probe_fn` does, not
            # residual-only noise.
            task_effect = _approx_standard_normal(rng) * CALIBRATED_SIGMA_TASK
            indep_component = _approx_standard_normal(rng) * CALIBRATED_SIGMA_TASK
            after_task_effect = (
                CALIBRATED_RHO * task_effect
                + math.sqrt(max(0.0, 1 - CALIBRATED_RHO**2)) * indep_component
            )
            noise_before = _approx_standard_normal(rng) * CALIBRATED_RESID_SD
            noise_after = _approx_standard_normal(rng) * CALIBRATED_RESID_SD
            # "before" arm = current regressed state (nothing reverted): every culprit active.
            rate_before = _clip01(
                CALIBRATED_BASELINE_RATE - total_magnitude_frac + task_effect + noise_before
            )
            # "after" arm = state with `reverted` applied: only still-active culprits penalize.
            rate_after = _clip01(
                CALIBRATED_BASELINE_RATE - active_penalty + after_task_effect + noise_after
            )
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


def before_arm_floor_clip_rate(
    cases: list[MultiCulpritBenchmarkCase], n_tasks: int = 24, seed: int = 42
) -> float:
    """Diagnostic (not used by `make_multi_probe_fn` itself): the fraction of "before"-arm
    synthetic task rates across all cases/tasks that hit `_clip01`'s 0.0 floor before noise is
    applied -- i.e. `CALIBRATED_BASELINE_RATE - total_magnitude_frac <= 0.0`. Reported directly in
    `reports/v0_5_scale_curve.md` per `make_multi_probe_fn`'s documented "known limitation" rather
    than left as an unmeasured assumption."""
    n_clipped = 0
    n_total = 0
    for case in cases:
        total_magnitude_frac = sum(-eff / 100.0 for eff in case.true_effects_pp.values())
        n_total += n_tasks
        if CALIBRATED_BASELINE_RATE - total_magnitude_frac <= 0.0:
            n_clipped += n_tasks
    return n_clipped / n_total if n_total else 0.0


@dataclass
class MultiConfoundGuardReport:
    """Generalized confound-guard statistics for multi-culprit cases. The single-culprit guard's
    definitions do NOT carry over unchanged (see each field's docstring below for exactly how each
    was generalized, per this task's explicit instruction not to silently reuse singular semantics)
    -- this is a SEPARATE report type from `ConfoundGuardReport`, not a reinterpretation of it."""

    n_cases: int
    n_culprit_instances: int  # n_cases * n_culprits_per_case (used as the fractional-rank sample)
    n_positions_observed: int
    """Distinct positions (within `changed_tools`) occupied by ANY true culprit across all cases
    -- generalizes "culprit position is not fixed" from a single index to the union of positions
    any real culprit has occupied."""
    frac_cases_a_culprit_is_max_diff: float
    """Generalizes "culprit is max-diff tool" (singular) to "*A* culprit is max-diff tool": the
    fraction of cases where the single largest-diff tool in the changed set is a MEMBER of
    `true_culprits` (any one of them, not all). This is the natural multi-culprit analogue of the
    single-culprit check -- it still tests whether `baseline_largest_textual_diff` could win by
    construction (it wins outright, on any case, the instant the top-ranked tool is real)."""
    frac_cases_a_decoy_exceeds_min_culprit_diff: float
    """Generalizes "some decoy diff exceeds the culprit's diff" to: the fraction of cases where
    the LARGEST decoy diff exceeds the SMALLEST culprit diff. This is the multi-culprit analogue of
    "decoys are not systematically smaller than the true signal" -- checked against the weakest
    (smallest-diff) culprit, since that is the one a diff-size heuristic would have to out-rank a
    decoy against to make a genuine top-1/top-k mistake; checking only the largest culprit would
    understate how easy it is for decoys to intrude on the ranking."""
    mean_culprit_fractional_rank: float
    """Per-culprit-instance (not per-case) mean fractional diff-size rank: for EACH true culprit in
    EACH case, its rank is computed among itself + that case's DECOYS ONLY (other simultaneous
    culprits in the same case are excluded from that one culprit's own rank computation) via the
    same `fractional_rank_from_diffs` the single-culprit guard uses. Averaging over all
    `n_culprit_instances` = `n_cases * n_culprits` such computations tests the same "is an
    individual culprit's diff size correlated with being a culprit vs. a decoy" question the
    single-culprit guard tests, applied once per real culprit rather than conflating multiple
    simultaneous culprits' diffs against each other (a different, not-yet-relevant question)."""


def multi_confound_guard_report(cases: list[MultiCulpritBenchmarkCase]) -> MultiConfoundGuardReport:
    """Compute the generalized confound-guard statistics for a multi-culprit benchmark set. See
    `MultiConfoundGuardReport`'s field docstrings for exactly how each single-culprit definition was
    generalized -- this function does not delegate to `confound_guard_report` (that function's
    `case.true_culprit` singular indexing does not apply here)."""
    positions: set[int] = set()
    n_a_culprit_is_max = 0
    n_decoy_exceeds_min_culprit = 0
    fractional_ranks: list[float] = []
    n_culprit_instances = 0
    for case in cases:
        culprit_set = set(case.true_culprits)
        for c in case.true_culprits:
            positions.add(case.changed_tools.index(c))

        culprit_diffs = [case.diff_chars.get(c, 0) for c in case.true_culprits]
        decoy_diffs = [v for k, v in case.diff_chars.items() if k not in culprit_set]

        max_diff_tool = max(case.diff_chars, key=lambda k: case.diff_chars[k])
        if max_diff_tool in culprit_set:
            n_a_culprit_is_max += 1
        if decoy_diffs and culprit_diffs and max(decoy_diffs) > min(culprit_diffs):
            n_decoy_exceeds_min_culprit += 1

        for culprit_diff in culprit_diffs:
            n_culprit_instances += 1
            rank = fractional_rank_from_diffs(culprit_diff, decoy_diffs)
            if rank is not None:
                fractional_ranks.append(rank)

    n = len(cases)
    return MultiConfoundGuardReport(
        n_cases=n,
        n_culprit_instances=n_culprit_instances,
        n_positions_observed=len(positions),
        frac_cases_a_culprit_is_max_diff=n_a_culprit_is_max / n if n else 0.0,
        frac_cases_a_decoy_exceeds_min_culprit_diff=(n_decoy_exceeds_min_culprit / n if n else 0.0),
        mean_culprit_fractional_rank=(
            sum(fractional_ranks) / len(fractional_ranks) if fractional_ranks else 0.5
        ),
    )

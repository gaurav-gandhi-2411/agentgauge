from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from agentgauge.frozen_protocol import JUDGE_SEED
from agentgauge.providers import Message, Provider

# EXP-3 pairwise confusability localizer.
# Reference: docs/research/exp3_pre_registration.md (Sections 2-4).
# Prompt text, trial/seed scheme, parse rules, and vote aggregation below are
# committed verbatim per that pre-registration -- do not paraphrase or retune.

TRIALS_PER_PAIR: int = 3

# A single trial's parsed vote. PARSE-FAILED is a distinct outcome, never
# silently coerced to "NO" -- per the pre-reg's explicit parse-handling rule.
Vote = Literal["YES", "NO", "PARSE-FAILED"]

VOTE_YES: Vote = "YES"
VOTE_NO: Vote = "NO"
VOTE_PARSE_FAILED: Vote = "PARSE-FAILED"

# The pair-level aggregated verdict. UNDETERMINED only occurs when every trial
# for a pair was PARSE-FAILED -- it must never be forced to NOT-CONFUSABLE.
Verdict = Literal["CONFUSABLE", "NOT-CONFUSABLE", "UNDETERMINED"]

CONFUSABLE: Verdict = "CONFUSABLE"
NOT_CONFUSABLE: Verdict = "NOT-CONFUSABLE"
UNDETERMINED: Verdict = "UNDETERMINED"

# Prompt template reproduced verbatim from exp3_pre_registration.md Section 2.
_PROMPT_TEMPLATE = """You are evaluating whether two MCP tool descriptions could cause an AI agent to
select the wrong tool for a task.

Tool A: {name_a}
Description: {desc_a}

Tool B: {name_b}
Description: {desc_b}

Question: Given a task that should call Tool A, could an agent plausibly select
Tool B instead based on these two descriptions? Also consider the reverse: given a
task for Tool B, could an agent plausibly select Tool A? Consider both name
similarity AND described functionality/behavior overlap.

Answer with exactly one line:
CONFUSABLE: YES
or
CONFUSABLE: NO"""

# Strategy 1: explicit "CONFUSABLE: YES/NO" label (case-insensitive, colon optional).
_LABELED_PATTERN = re.compile(r"CONFUSABLE\s*:?\s*(YES|NO)", re.IGNORECASE)
# Strategy 2 (fallback): the first bare YES/NO token anywhere in the response.
_BARE_PATTERN = re.compile(r"\b(YES|NO)\b", re.IGNORECASE)


def build_localizer_prompt(name_a: str, desc_a: str, name_b: str, desc_b: str) -> str:
    """Build the pairwise confusability judge prompt for one candidate pair.

    Reproduces exp3_pre_registration.md Section 2's prompt text verbatim,
    substituting the two tool names and descriptions.
    """
    return _PROMPT_TEMPLATE.format(name_a=name_a, desc_a=desc_a, name_b=name_b, desc_b=desc_b)


def parse_vote(response: str) -> Vote:
    """Parse a single judge response into a YES/NO/PARSE-FAILED vote.

    Per the pre-reg's parse-handling rule: try the labeled ``CONFUSABLE: YES|NO``
    pattern first, fall back to the first bare YES/NO token, and if neither
    matches, report PARSE-FAILED -- never silently counted as NO.
    """
    m = _LABELED_PATTERN.search(response)
    if m:
        return VOTE_YES if m.group(1).upper() == "YES" else VOTE_NO

    m = _BARE_PATTERN.search(response)
    if m:
        return VOTE_YES if m.group(1).upper() == "YES" else VOTE_NO

    return VOTE_PARSE_FAILED


def _aggregate_votes(votes: list[Vote]) -> tuple[Verdict, int]:
    """Aggregate per-trial votes into a pair-level verdict via majority vote.

    >=2 of the non-parse-failed trials voting YES => CONFUSABLE, else
    NOT-CONFUSABLE -- except when every trial is PARSE-FAILED, in which case the
    verdict is UNDETERMINED (not forced to either label).

    Returns: (verdict, parse_failed_count)
    """
    parse_failed_count = votes.count(VOTE_PARSE_FAILED)
    counted = [v for v in votes if v != VOTE_PARSE_FAILED]

    if not counted:
        return UNDETERMINED, parse_failed_count

    yes_count = counted.count(VOTE_YES)
    verdict = CONFUSABLE if yes_count >= 2 else NOT_CONFUSABLE
    return verdict, parse_failed_count


@dataclass(frozen=True)
class PairLocalizationResult:
    """Per-pair localization output: raw votes, aggregated verdict, parse failures."""

    tool_a: str
    tool_b: str
    votes: list[Vote] = field(default_factory=list)
    verdict: Verdict = UNDETERMINED
    parse_failed_count: int = 0


async def localize_pair(
    name_a: str,
    desc_a: str,
    name_b: str,
    desc_b: str,
    provider: Provider,
    *,
    trials: int = TRIALS_PER_PAIR,
) -> PairLocalizationResult:
    """Run the pairwise confusability judge for one candidate tool pair.

    Runs ``trials`` judge calls at seed = JUDGE_SEED + trial_idx (the per-trial
    seed convention -- a single fixed seed across trials is the exact bug this
    experiment must not repeat, per the pre-reg's explicit callout).
    """
    prompt = build_localizer_prompt(name_a, desc_a, name_b, desc_b)
    votes: list[Vote] = []
    for trial_idx in range(trials):
        response = await provider.chat(
            [Message(role="user", content=prompt)], seed=JUDGE_SEED + trial_idx
        )
        votes.append(parse_vote(response))

    verdict, parse_failed_count = _aggregate_votes(votes)
    return PairLocalizationResult(
        tool_a=name_a,
        tool_b=name_b,
        votes=votes,
        verdict=verdict,
        parse_failed_count=parse_failed_count,
    )


async def localize_matrix(
    pairs: list[tuple[str, str, str, str]],
    provider: Provider,
    *,
    trials: int = TRIALS_PER_PAIR,
) -> list[PairLocalizationResult]:
    """Run the pairwise confusability judge over a list of candidate pairs.

    ``pairs`` is a list of (name_a, desc_a, name_b, desc_b) tuples. Returns one
    PairLocalizationResult per pair, in input order -- the "confusability matrix"
    the pre-reg's single-score discoverability judge structurally cannot produce.
    """
    results: list[PairLocalizationResult] = []
    for name_a, desc_a, name_b, desc_b in pairs:
        results.append(await localize_pair(name_a, desc_a, name_b, desc_b, provider, trials=trials))
    return results


# ── EXP-3 Section 7: graded-confidence retry ──────────────────────────────────
# The binary framing above was found degenerate (24/24 CONFUSABLE, precision
# 0.167) -- an unanchored yes/no question with no incentive to discriminate.
# This is the one pre-registered retry: a 0-10 graded confidence score, mirroring
# scorer.py's `_judge_discoverability` / `_parse_distinguish_score` pattern.
# Reference: docs/research/exp3_pre_registration.md Section 7. Prompt text,
# trial/seed scheme, parse rules, and threshold below are committed verbatim --
# do not paraphrase or retune.

# Prompt template reproduced verbatim from exp3_pre_registration.md Section 7.
_GRADED_PROMPT_TEMPLATE = """You are evaluating whether two MCP tool descriptions could cause an AI agent to select the
wrong tool for a task.

Tool A: {name_a}
Description: {desc_a}

Tool B: {name_b}
Description: {desc_b}

On a scale of 0-10, how likely is an AI agent to confuse these two tools when selecting which
one to call for a task?

Scoring guide:
- 0-2: Completely distinct -- no reasonable task would create ambiguity between them
- 3-4: Minor surface similarity (e.g. shared verb or domain) but functionally clearly distinct
- 5-6: Real overlap -- a plausible task could go either way
- 7-8: Strong overlap -- significant chance of agent confusion
- 9-10: Near-identical in function -- an agent would struggle to tell them apart

Answer with exactly one line:
CONFUSABILITY: <number 0-10>"""

# Strategy 1: explicit "CONFUSABILITY: N" label (case-insensitive, colon optional).
_GRADED_LABELED_PATTERN = re.compile(r"CONFUSABILITY\s*:?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
# Strategy 2 (fallback): the last bare number anywhere in the response.
_GRADED_BARE_NUMBER_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\b")

# Pre-registered threshold (Section 7): mean >= this => CONFUSABLE.
GRADED_CONFUSABLE_THRESHOLD: float = 5.0


def build_graded_localizer_prompt(name_a: str, desc_a: str, name_b: str, desc_b: str) -> str:
    """Build the graded-confidence pairwise confusability judge prompt for one pair.

    Reproduces exp3_pre_registration.md Section 7's prompt text verbatim,
    substituting the two tool names and descriptions.
    """
    return _GRADED_PROMPT_TEMPLATE.format(
        name_a=name_a, desc_a=desc_a, name_b=name_b, desc_b=desc_b
    )


def parse_graded_score(response: str) -> float | None:
    """Extract the 0-10 CONFUSABILITY score from a graded judge response.

    Mirrors scorer.py's `_parse_distinguish_score` strategy order:
    1. Labeled: 'CONFUSABILITY: N' (case-insensitive) -- the intended format.
    2. Fallback: the last bare number anywhere in the response.
    3. No digit at all -- returns None (PARSE-FAILED for this trial; never
       silently coerced to 0, per the pre-reg's explicit parse-handling rule).

    Values are clamped to [0, 10] regardless of strategy.
    """
    m = _GRADED_LABELED_PATTERN.search(response)
    if m:
        return max(0.0, min(float(m.group(1)), 10.0))

    all_nums = _GRADED_BARE_NUMBER_PATTERN.findall(response)
    if all_nums:
        return max(0.0, min(float(all_nums[-1]), 10.0))

    return None


def _aggregate_graded_scores(scores: list[float | None]) -> tuple[Verdict, float | None, int]:
    """Aggregate per-trial graded scores into a pair-level verdict.

    Mean is computed over the non-None (non-parse-failed) trial scores only --
    None is never treated as 0. mean >= GRADED_CONFUSABLE_THRESHOLD => CONFUSABLE,
    else NOT-CONFUSABLE -- except when every trial is parse-failed, in which case
    the verdict is UNDETERMINED (not forced to either label).

    Returns: (verdict, mean_score, parse_failed_count)
    """
    parse_failed_count = sum(1 for s in scores if s is None)
    counted = [s for s in scores if s is not None]

    if not counted:
        return UNDETERMINED, None, parse_failed_count

    mean_score = sum(counted) / len(counted)
    verdict = CONFUSABLE if mean_score >= GRADED_CONFUSABLE_THRESHOLD else NOT_CONFUSABLE
    return verdict, mean_score, parse_failed_count


@dataclass(frozen=True)
class PairGradedLocalizationResult:
    """Per-pair graded localization output: raw scores, mean, verdict, parse failures."""

    tool_a: str
    tool_b: str
    scores: list[float | None] = field(default_factory=list)
    mean_score: float | None = None
    verdict: Verdict = UNDETERMINED
    parse_failed_count: int = 0


async def localize_pair_graded(
    name_a: str,
    desc_a: str,
    name_b: str,
    desc_b: str,
    provider: Provider,
    *,
    trials: int = TRIALS_PER_PAIR,
) -> PairGradedLocalizationResult:
    """Run the graded-confidence pairwise confusability judge for one candidate pair.

    Runs ``trials`` judge calls at seed = JUDGE_SEED + trial_idx (the same
    per-trial seed convention as the binary path), collects each trial's parsed
    0-10 score (or None for parse-failed), and aggregates via the mean of the
    non-None scores against the pre-registered >=5.0 threshold.
    """
    prompt = build_graded_localizer_prompt(name_a, desc_a, name_b, desc_b)
    scores: list[float | None] = []
    for trial_idx in range(trials):
        response = await provider.chat(
            [Message(role="user", content=prompt)], seed=JUDGE_SEED + trial_idx
        )
        scores.append(parse_graded_score(response))

    verdict, mean_score, parse_failed_count = _aggregate_graded_scores(scores)
    return PairGradedLocalizationResult(
        tool_a=name_a,
        tool_b=name_b,
        scores=scores,
        mean_score=mean_score,
        verdict=verdict,
        parse_failed_count=parse_failed_count,
    )


async def localize_matrix_graded(
    pairs: list[tuple[str, str, str, str]],
    provider: Provider,
    *,
    trials: int = TRIALS_PER_PAIR,
) -> list[PairGradedLocalizationResult]:
    """Run the graded-confidence pairwise confusability judge over candidate pairs.

    ``pairs`` is a list of (name_a, desc_a, name_b, desc_b) tuples. Returns one
    PairGradedLocalizationResult per pair, in input order.
    """
    results: list[PairGradedLocalizationResult] = []
    for name_a, desc_a, name_b, desc_b in pairs:
        results.append(
            await localize_pair_graded(name_a, desc_a, name_b, desc_b, provider, trials=trials)
        )
    return results

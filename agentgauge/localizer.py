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

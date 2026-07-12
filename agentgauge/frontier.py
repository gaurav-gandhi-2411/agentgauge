from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from agentgauge.tasks import Task

FrontierOutcome = Literal["SELECTED-CORRECT", "SELECTED-WRONG", "ABSTAINED-OR-HEDGED"]

# Patterns that signal the agent is hedging rather than selecting.
# A match means ABSTAINED-OR-HEDGED (thoughtful non-selection, not a bad pick).
_HEDGE_RE = re.compile(
    r"(?i)("
    r"I('m|\s+am)\s+not\s+sure"
    r"|not\s+sure"
    r"|unclear|uncertain|unsure|ambiguous"
    r"|could\s+you|can\s+you|would\s+you"
    r"|clarif(y|ication|ying)"
    r"|please\s+specify|more\s+(context|information|detail|info)"
    r"|either\s+\w+\s+or\b"
    r"|it\s+depends|depending\s+on"
    r"|I\s+(can'?t|cannot|am\s+unable\s+to)"
    r"|unable\s+to\s+(determine|decide|select|choose)"
    r"|without\s+(more|additional|further)\s+(context|information|detail)"
    r"|which\s+(tool|one)"
    r"|both\s+\w+\s+and\b"
    r")"
)


@dataclass
class FrontierRunResult:
    task: Task
    raw_response: str
    outcome: FrontierOutcome


def classify_frontier_outcome(
    response: str,
    valid_tools: frozenset[str],
    gold_tool: str,
) -> FrontierOutcome:
    """Classify a tool-selection response into one of three outcomes.

    SELECTED-CORRECT : first token is exactly the gold tool name.
    SELECTED-WRONG   : first token is a valid (non-gold) tool name.
    ABSTAINED-OR-HEDGED: no valid tool selected — hedge, clarifying question,
                         explicit uncertainty, or multi-word non-tool response.

    parse_failed (malformed args) is tracked separately in RunResult; this
    classifier only addresses the selection semantics so hedging is never
    miscounted as a wrong selection.
    """
    first_token = response.strip().split()[0].rstrip(".,;:!?") if response.strip() else ""

    if first_token in valid_tools:
        return "SELECTED-CORRECT" if first_token == gold_tool else "SELECTED-WRONG"

    # No valid tool in first position — check for hedge signals
    if _HEDGE_RE.search(response):
        return "ABSTAINED-OR-HEDGED"

    # Multi-word response that doesn't start with a tool name → agent explained rather than selected
    if len(response.split()) > 3:
        return "ABSTAINED-OR-HEDGED"

    # Short opaque non-tool response → cannot determine intent; treat as abstain
    return "ABSTAINED-OR-HEDGED"

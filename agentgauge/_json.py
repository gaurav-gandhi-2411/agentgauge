from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(resp: str) -> tuple[dict[str, Any], bool]:
    """Extract a JSON object from an LLM response.

    Handles three common LLM output styles:
    1. Bare JSON: ``{"key": "val"}``
    2. Fenced JSON: `` ```json\\n{"key": "val"}\\n``` ``
    3. JSON with preamble: ``Sure! Here are the args: {"key": "val"}``

    Returns ``(parsed_dict, parse_failed)`` where ``parse_failed=True`` means
    all extraction attempts failed and ``{}`` is returned as the fallback.
    Callers should record or report ``parse_failed=True`` runs — a high failure
    rate is a fixture/harness signal, not a null.
    """
    # Step 1: strip markdown fences (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", resp.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip())

    # Step 2: try direct parse of the cleaned string
    try:
        result = json.loads(cleaned.strip())
        if isinstance(result, dict):
            return result, False
    except (json.JSONDecodeError, ValueError):
        pass

    # Step 3: extract first {...} block (handles preamble / trailing prose)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result, False
        except (json.JSONDecodeError, ValueError):
            pass

    return {}, True

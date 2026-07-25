"""Task 5 (v2.1): measure the per-tool-set false-alarm rate under the
BLOCKING-only severity gate (type_enum_contradiction +
required_references_missing_property), vs. the combined BLOCKING+ADVISORY
rate (equivalent to v2's old single HIGH tier). See
reports/v2_1_severity_gate.md.

Zero LLM calls. Reuses the same clean-corpus definition as Task 2/4.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.linter import lint_tool_set  # noqa: E402
from scripts.v2_defect_injector import _load_clean_corpus  # noqa: E402

OUT_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "v2_1_severity_gate.json"


class _T:
    def __init__(self, d: dict) -> None:
        self.name = d["name"]
        self.description = d["description"]
        self.inputSchema = d["inputSchema"]


def main() -> None:
    clean_corpus = _load_clean_corpus()
    n_tools = 0
    n_blocking_tools = 0
    n_blocking_toolsets = 0
    n_combined_tools = 0
    n_combined_toolsets = 0

    for entry in clean_corpus:
        tools = [_T(t) for t in entry["tools"]]
        report = lint_tool_set(tools)
        n_tools += len(tools)
        ts_blocking = False
        ts_combined = False
        for tr in report.tool_results:
            if tr.blocking:
                n_blocking_tools += 1
                ts_blocking = True
            if tr.blocking or tr.advisory:
                n_combined_tools += 1
                ts_combined = True
        if report.collision_violations:  # ADVISORY (name_collision)
            ts_combined = True
        if ts_blocking:
            n_blocking_toolsets += 1
        if ts_combined:
            n_combined_toolsets += 1

    result = {
        "n_tool_sets": len(clean_corpus),
        "n_tools": n_tools,
        "blocking_only": {
            "n_flagged_tools": n_blocking_tools,
            "pct_flagged_tools": 100.0 * n_blocking_tools / n_tools,
            "n_flagged_toolsets": n_blocking_toolsets,
            "pct_flagged_toolsets": 100.0 * n_blocking_toolsets / len(clean_corpus),
        },
        "blocking_plus_advisory": {
            "n_flagged_tools": n_combined_tools,
            "pct_flagged_tools": 100.0 * n_combined_tools / n_tools,
            "n_flagged_toolsets": n_combined_toolsets,
            "pct_flagged_toolsets": 100.0 * n_combined_toolsets / len(clean_corpus),
        },
    }
    print(json.dumps(result, indent=2))
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()

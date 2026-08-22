from __future__ import annotations

"""scripts/check_superseded_values.py -- BF3.3: catch a superseded number
reused in prose, not just a bad first-citation.

Root cause this exists for (BF3.1): the FPR-stratification error that
reached docs/paper2/main.tex was NOT caught by the provenance ledger,
because the ledger's own regular claims table (provenance.md line 114,
not its section-0 "DO NOT CITE" supersession ledger) still carried the
same stale "0.07%" value the paper did. Checking a restatement against
the ledger is checking it against a second copy that can itself be
stale -- both agree, both are wrong, and nothing catches it. The
ledger's section-0 supersession list is manually curated (someone has
to notice a value was superseded and add a "DO NOT CITE" row); this
value was never added there either.

What this script does instead: every `reports/*.md` source file already
marks its own superseded numbers with a consistent, mechanical marker --
"pre-fix", "(superseded)", "DO NOT CITE", "originally", "before the
fix", or a table column literally named "... (pre-fix)" (confirmed
against reports/v2_2_few_clusters_correction.md's own table, which is
exactly how the 0.07% value was marked in its real source -- this
script's marker list was built FROM that real incident, not guessed).
For every numeric token appearing on a line carrying one of those
markers, this script greps both papers' actual .tex source for that
same literal numeric string and reports every hit -- high-recall by
design (a supersession-context mention like "corrected from 0.07% to
0.08%" will also be flagged; that's a false positive worth a human's
five seconds, not a miss worth hours of not noticing).

Usage: python scripts/check_superseded_values.py
Exit 0 if nothing found, 1 if any candidate leak is found (does not
fail CI by default -- not wired into ci.yml, this is a manual/pre-
submission check, matching this repo's own "no automated price-
scraping" style precedent of trusting a human to look, not a bot).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
PROVENANCE_MD = ROOT / "docs" / "paper2" / "provenance.md"
PAPER_FILES = [
    ROOT / "docs" / "paper2" / "main.tex",
    ROOT / "docs" / "paper" / "latex" / "main.tex",
    ROOT / "docs" / "paper" / "latex" / "body_content.tex",
    ROOT / "docs" / "paper" / "latex" / "abstract_body.tex",
]

# Markers a report/ledger uses, in this repo's own real usage, to flag a
# value as not-current. Built from the actual incident, not guessed --
# extend this list the next time a new marker phrasing is found.
SUPERSEDED_MARKERS = [
    r"\bpre-fix\b",
    r"\(pre-fix\)",
    r"\(superseded\)",
    r"\bDO NOT CITE\b",
    r"\boriginally\b",
    r"\bbefore the fix\b",
    r"\berroneous\b",
    r"\bnot separately stratified\b",  # the exact phrase next to the 0.07% incident
]
MARKER_RE = re.compile("|".join(SUPERSEDED_MARKERS), re.IGNORECASE)

# Numeric tokens worth flagging: percentages and plain decimals with >=2
# significant digits (skip bare small integers like table row counts --
# too noisy, not the class of value this incident was about).
NUMBER_RE = re.compile(r"\b\d+\.\d+%|\b\d{2,}\.\d+\b")


def find_flagged_values() -> dict[str, list[tuple[str, int, str]]]:
    """Return {value_string: [(source_file, line_no, line_text), ...]}."""
    flagged: dict[str, list[tuple[str, int, str]]] = {}

    sources = list(REPORTS_DIR.glob("*.md"))
    if PROVENANCE_MD.exists():
        sources.append(PROVENANCE_MD)

    for path in sources:
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not MARKER_RE.search(line):
                continue
            for match in NUMBER_RE.finditer(line):
                value = match.group(0)
                flagged.setdefault(value, []).append(
                    (str(path.relative_to(ROOT)), lineno, line.strip())
                )
    return flagged


def check_papers_for_leaks(
    flagged: dict[str, list[tuple[str, int, str]]],
) -> list[tuple[str, str, int, str]]:
    """Return [(flagged_value, paper_file, line_no, line_text), ...] for every
    occurrence of a flagged value in either paper's actual .tex source."""
    leaks: list[tuple[str, str, int, str]] = []
    for paper_path in PAPER_FILES:
        if not paper_path.exists():
            continue
        text = paper_path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for value in flagged:
                # Escape for regex (value contains a literal '%' or '.')
                if re.search(re.escape(value), line):
                    leaks.append((value, str(paper_path.relative_to(ROOT)), lineno, line.strip()))
    return leaks


def main() -> int:
    flagged = find_flagged_values()
    print(f"Found {len(flagged)} distinct flagged (marked-superseded) numeric value(s) "
          f"across {REPORTS_DIR.relative_to(ROOT)}/*.md and {PROVENANCE_MD.relative_to(ROOT)}.")
    for value, sites in sorted(flagged.items()):
        print(f"  {value}  (flagged at {len(sites)} site(s), e.g. {sites[0][0]}:{sites[0][1]})")

    leaks = check_papers_for_leaks(flagged)
    print()
    if not leaks:
        print("No flagged value found verbatim in either paper's .tex source. Clean.")
        return 0

    print(f"CANDIDATE LEAKS: {len(leaks)} occurrence(s) of a marked-superseded value "
          f"found in paper text -- review each by hand, some may be legitimate "
          f"supersession-acknowledgment mentions:")
    for value, paper_file, lineno, line in leaks:
        print(f"  [{value}] {paper_file}:{lineno}: {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

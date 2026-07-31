#!/usr/bin/env python3
"""CI guard: every BibTeX entry in this repo must carry a `verified` field.

Why this exists: during the methods-paper wave, 6 of 9 entries in
docs/paper/latex/references.bib were wrong in ways invisible to ordinary proofreading --
wrong full author given names that happened to preserve the correct surname initials (so an
initials-only in-text citation like "Hasan, M. M." looked fine even though the bib entry's
full name was wrong), wrong publication years, and generic team-name attributions
("Anthropic Engineering") standing in for the real named byline. None of these would be
caught by reading the bibliography -- they only surface when each field is independently
checked against the entry's actual primary source (a DOI, an arXiv abstract page, a
publisher's own page, a GitHub API response). This script does not (cannot) re-verify
correctness itself; it only enforces that someone did, and recorded what kind of source they
used, before the entry was allowed to land.

Convention enforced: every `@`-entry must have a `verified = {<type>}` field whose value is
one of ALLOWED_TYPES below. See docs/paper2/README.md, "Bibliography verification protocol",
for what each type means, what counts as satisfying it, and what does not (a search-result
snippet or a memory recall never counts, regardless of confidence).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_TYPES = {
    "doi-crossref",  # DOI resolved via https://doi.org/<doi> or the Crossref API
    "arxiv-api",  # arXiv abstract page (arxiv.org/abs/<id>) or export.arxiv.org/api/query
    "publisher-page",  # the publisher's/venue's own page (ACM DL, journal site, blog post itself)
    "github-api",  # api.github.com REST response (for GitHub issues/repos cited as sources)
    "isbn-catalog",  # a library catalog record (WorldCat, LC, OpenLibrary) keyed on ISBN/LCCN
}

# @type{key, ...} -- capture the type and key, then find the matching closing brace by
# depth-counting (bibtex entries can nest braces inside field values, e.g. {{Team Name}}).
_ENTRY_START = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)
_VERIFIED_FIELD = re.compile(r"verified\s*=\s*\{([^}]*)\}", re.IGNORECASE)


def _split_entries(text: str) -> list[tuple[str, str, str]]:
    """Returns (entry_type, key, full_entry_text) for every @-entry in a .bib file."""
    entries = []
    for m in _ENTRY_START.finditer(text):
        entry_type, key = m.group(1), m.group(2)
        # depth-count from the opening brace (the one matched by `{\s*` before the key)
        # to find this entry's real closing brace.
        start = text.index("{", m.start())
        depth = 0
        i = start
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        entries.append((entry_type, key, text[start : i + 1]))
    return entries


def check_file(path: Path) -> list[str]:
    """Returns a list of problem descriptions for one .bib file (empty = all entries clean)."""
    text = path.read_text(encoding="utf-8")
    problems = []
    for entry_type, key, entry_text in _split_entries(text):
        m = _VERIFIED_FIELD.search(entry_text)
        if not m:
            problems.append(f"{path}: @{entry_type}{{{key}, ...}} has no `verified` field")
            continue
        value = m.group(1).strip()
        if value not in ALLOWED_TYPES:
            problems.append(
                f"{path}: @{entry_type}{{{key}, ...}} has verified={{{value}}}, "
                f"not one of {sorted(ALLOWED_TYPES)}"
            )
    return problems


def main() -> int:
    bib_files = sorted(REPO_ROOT.glob("**/*.bib"))
    if not bib_files:
        print("[SKIP] no .bib files found in repo")
        return 0

    all_problems: list[str] = []
    for path in bib_files:
        problems = check_file(path)
        rel = path.relative_to(REPO_ROOT)
        if problems:
            print(f"[FAIL] {rel}: {len(problems)} unverified/malformed entr{'y' if len(problems) == 1 else 'ies'}")
            all_problems.extend(problems)
        else:
            print(f"[PASS] {rel}: every entry has a valid `verified` field")

    if all_problems:
        print("\nProblems found:")
        for p in all_problems:
            print(f"  - {p}")
        print(
            "\nEvery .bib entry must carry `verified = {<type>}` naming the primary-source "
            "type used to check its author list, title, year, and identifier -- see "
            "docs/paper2/README.md, \"Bibliography verification protocol\"."
        )
        return 1

    print(f"\nBIB-VERIFICATION OVERALL: {len(bib_files)} file(s), all entries verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())

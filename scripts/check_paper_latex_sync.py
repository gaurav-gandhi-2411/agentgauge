#!/usr/bin/env python3
"""CI guard: every commit touching docs/paper/paper.md must also touch docs/paper/latex/.

Lightweight git-diff check, not a content-equivalence parser -- it does not verify the two
sides say the same thing, only that a commit editing the Markdown source didn't skip updating
its LaTeX mirror. See docs/paper/latex/README.md for what the mirror is and why it exists.
"""

from __future__ import annotations

import subprocess
import sys

PAPER_MD = "docs/paper/paper.md"
LATEX_DIR = "docs/paper/latex/"


def _run(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def _commits_in_range(commit_range: str) -> list[str]:
    # --no-merges: a merge commit's own diff is not meaningful here -- the individual
    # commits it brings in are already checked on their own.
    out = _run("log", commit_range, "--no-merges", "--format=%H")
    return [line for line in out.splitlines() if line]


def _files_changed(commit: str) -> list[str]:
    out = _run("show", "--name-only", "--format=", commit)
    return [line for line in out.splitlines() if line]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_paper_latex_sync.py <commit-range>", file=sys.stderr)
        return 2

    commit_range = sys.argv[1]
    violations = []
    for commit in _commits_in_range(commit_range):
        files = _files_changed(commit)
        touches_paper = PAPER_MD in files
        touches_latex = any(f.startswith(LATEX_DIR) for f in files)
        # Directional check: paper.md -> latex only. A latex-only commit (e.g. swapping in a
        # venue .cls, reflowing tables, recompiling main.pdf after an unrelated fix) is a
        # legitimate build-only change and must NOT be flagged -- there's nothing in paper.md
        # for it to be "out of sync" with.
        if touches_paper and not touches_latex:
            violations.append(commit)

    if violations:
        print(f"ERROR: {len(violations)} commit(s) changed {PAPER_MD} without a matching change")
        print(f"       under {LATEX_DIR} in the same commit:")
        for commit in violations:
            subject = _run("log", "-1", "--format=%h %s", commit).strip()
            print(f"  - {subject}")
        print()
        print(f"Resync {LATEX_DIR} (abstract_body.tex / body_content.tex) and recompile main.pdf")
        print("in the same commit, or split the paper.md edit out so it isn't silently unsynced.")
        return 1

    print(f"OK: every commit touching {PAPER_MD} in range also touched {LATEX_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

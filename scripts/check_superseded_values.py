from __future__ import annotations

"""scripts/check_superseded_values.py -- BF3.3 + BH1: catch a superseded number
reused in prose, and a verbatim-copy claim that has drifted from its source.

Root cause this exists for (BF3.1): the FPR-stratification error that reached
docs/paper2/main.tex was NOT caught by the provenance ledger, because the
ledger's own regular claims table (provenance.md line 114, not its section-0
"DO NOT CITE" supersession ledger) still carried the same stale "0.07%" value
the paper did. Checking a restatement against the ledger is checking it
against a second copy that can itself be stale -- both agree, both are wrong,
and nothing catches it.

Second incident this exists for (BH1.1, found by BG2's readiness pass):
docs/paper2/SUBMISSION.md claims its Abstract section is "Reproduced verbatim
from `docs/paper2/main.tex`'s `\\begin{abstract}...\\end{abstract}`" -- and it
drifted, carrying the pre-#98 hypothesis count and model-bucket wording after
main.tex's abstract had already been fixed. A marker-based leak scan (the
original v1 of this script) cannot catch this class of error at all: nothing
in SUBMISSION.md's stale text is *marked* superseded -- it's just a second
copy of text that silently stopped matching its source. This required a
different mechanism: find files claiming a verbatim copy, and directly diff
the claimed copy against its cited source.

Three independent checks, run every time:

1. SUPERSEDED-MARKER LEAK SCAN (original BF3 mechanism, unchanged). Every
   `reports/*.md` source file marks its own superseded numbers with a
   consistent marker phrase ("pre-fix", "(superseded)", "DO NOT CITE",
   "originally", "before the fix", or a table column literally named
   "... (pre-fix)"). For every numeric token on a marked line, grep every
   restatement-risk file (both papers' .tex, plus every doc that restates a
   paper number -- SUBMISSION.md, this repo's top-level README, and the two
   paper-adjacent READMEs) for that same literal numeric string.

2. VERBATIM-ABSTRACT-COPY CHECK (BH1.2, new). For every configured
   (claiming_file, source_file) pair where claiming_file explicitly asserts
   it holds a verbatim copy of source_file's abstract, extract both texts,
   normalize LaTeX markup out of the source, tokenize, and word-diff them.
   Any content divergence (not just whitespace/typography) fails the check.

3. INLINE-QUOTE CHECK (BH1.4, new). provenance.md (and any report) uses the
   convention `Verbatim: "<quoted sentence>"` next to a backtick-quoted
   source filename in the same table row. For every such claim, confirm the
   quoted sentence actually appears (whitespace-normalized) in the cited
   source file.

4. COVERAGE TRANSPARENCY (not a check -- a disclosure). Every other mention
   of the word "verbatim" anywhere in the repo's .md/.tex files (excluding
   LaTeX's `\begin{verbatim}` environment and the evals/fixtures/ corpus,
   neither of which is a content-copy claim) is printed as NOT mechanically
   verified, so a future verbatim-copy claim doesn't silently fall outside
   this script's coverage the way SUBMISSION.md did. Per this repo's own
   rule about controls covering less surface than they imply (CLAUDE.md
   85a): naming what ISN'T checked is part of the check.

Usage: python scripts/check_superseded_values.py
Exit 0 if nothing found, 1 if any candidate leak or mismatch is found (does
not fail CI by default -- not wired into ci.yml, this is a manual/pre-
submission check, matching this repo's own "no automated price-scraping"
style precedent of trusting a human to look, not a bot).
"""

import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
PROVENANCE_MD = ROOT / "docs" / "paper2" / "provenance.md"

PAPER2_MAIN = ROOT / "docs" / "paper2" / "main.tex"
PAPER1_MAIN = ROOT / "docs" / "paper" / "latex" / "main.tex"
PAPER1_BODY = ROOT / "docs" / "paper" / "latex" / "body_content.tex"
PAPER1_ABSTRACT = ROOT / "docs" / "paper" / "latex" / "abstract_body.tex"

# Every file that restates a paper number, not just the papers' own .tex
# source -- BH1.1's extension. A restatement in any of these is exactly as
# capable of drifting as a restatement inside the paper itself.
RESTATEMENT_SCAN_FILES = [
    PAPER2_MAIN,
    PAPER1_MAIN,
    PAPER1_BODY,
    PAPER1_ABSTRACT,
    ROOT / "docs" / "paper2" / "SUBMISSION.md",
    ROOT / "docs" / "paper2" / "README.md",
    ROOT / "docs" / "paper" / "latex" / "README.md",
    ROOT / "README.md",
]

# (claiming_file, claim_section_start, claim_section_end, source_file) --
# every place in the repo that explicitly asserts a verbatim copy of a
# paper's abstract. Add a row here the day a new one is written; the
# coverage-transparency scan below is the backstop for the day someone
# forgets to.
ABSTRACT_VERBATIM_CLAIMS = [
    {
        "claiming_file": ROOT / "docs" / "paper2" / "SUBMISSION.md",
        "section_start": "## Abstract",
        "section_end": "## arXiv categories",
        "source_file": PAPER2_MAIN,
    },
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

VERBATIM_QUOTE_RE = re.compile(r'Verbatim:\s*"([^"]+)"')
BACKTICK_SOURCE_RE = re.compile(r"`([\w./-]+\.md)(?::[\d,\s-]+)?`")
VERBATIM_MENTION_RE = re.compile(r"verbatim", re.IGNORECASE)


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


def check_restatement_leaks(
    flagged: dict[str, list[tuple[str, int, str]]],
) -> list[tuple[str, str, int, str]]:
    """Return [(flagged_value, file, line_no, line_text), ...] for every
    occurrence of a flagged value in any restatement-risk file (both papers'
    .tex source plus every doc that restates a paper number)."""
    leaks: list[tuple[str, str, int, str]] = []
    for target_path in RESTATEMENT_SCAN_FILES:
        if not target_path.exists():
            continue
        text = target_path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for value in flagged:
                if re.search(re.escape(value), line):
                    leaks.append((value, str(target_path.relative_to(ROOT)), lineno, line.strip()))
    return leaks


def _strip_latex(text: str) -> str:
    """Approximate LaTeX -> plain-text normalization, enough to word-diff a
    .tex abstract against a plain-prose copy of it. Not a full LaTeX parser --
    good enough to make real content drift show up as a word-level diff
    without LaTeX-vs-plain formatting noise dominating the result."""
    lines = []
    for line in text.splitlines():
        out = []
        i = 0
        while i < len(line):
            if line[i] == "\\" and i + 1 < len(line) and line[i + 1] == "%":
                out.append("%")
                i += 2
                continue
            if line[i] == "%":
                break  # rest of line is a LaTeX comment (PROV pointers live here)
            out.append(line[i])
            i += 1
        lines.append("".join(out))
    text = "\n".join(lines)

    text = text.replace("\\%", "%").replace("\\$", "$")
    text = text.replace("--", "-")
    text = re.sub(r"\\geq", ">=", text)
    text = re.sub(r"\\leq", "<=", text)
    text = re.sub(r"\\times", "x", text)
    text = re.sub(r"\\sqrt", "sqrt", text)
    text = re.sub(r"\\propto", "propto", text)
    text = re.sub(r"\\textbf\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\texttt\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", text)
    text = text.replace("$", "")
    text = re.sub(r"\\[a-zA-Z]+", "", text)  # drop remaining bare commands
    text = text.replace("{", "").replace("}", "")
    return text


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9.%<>=/-]+", text.lower())


def _extract_between(text: str, start_marker: str, end_marker: str) -> str | None:
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return None
    start_idx += len(start_marker)
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1:
        return None
    return text[start_idx:end_idx]


def _extract_abstract_env(text: str) -> str | None:
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.DOTALL)
    return m.group(1) if m else None


def check_abstract_verbatim_claims() -> list[dict]:
    """Return a list of mismatch reports (empty if every claim holds)."""
    mismatches = []
    for claim in ABSTRACT_VERBATIM_CLAIMS:
        claiming_file = claim["claiming_file"]
        source_file = claim["source_file"]
        if not claiming_file.exists() or not source_file.exists():
            continue

        claiming_text = claiming_file.read_text(encoding="utf-8", errors="replace")
        claimed_copy = _extract_between(claiming_text, claim["section_start"], claim["section_end"])
        if claimed_copy is None:
            mismatches.append(
                {
                    "claiming_file": str(claiming_file.relative_to(ROOT)),
                    "source_file": str(source_file.relative_to(ROOT)),
                    "error": (
                        f"could not locate section between {claim['section_start']!r} and "
                        f"{claim['section_end']!r} -- claim structure changed, re-check by hand"
                    ),
                }
            )
            continue
        # Strip the trailing "(Reproduced verbatim from ...)" meta-note itself --
        # it's commentary about the copy, not part of the copied text.
        claimed_copy = re.split(r"\n\(Reproduced verbatim", claimed_copy)[0]

        source_text = source_file.read_text(encoding="utf-8", errors="replace")
        source_abstract = _extract_abstract_env(source_text)
        if source_abstract is None:
            mismatches.append(
                {
                    "claiming_file": str(claiming_file.relative_to(ROOT)),
                    "source_file": str(source_file.relative_to(ROOT)),
                    "error": "source file has no \\begin{abstract}...\\end{abstract} block",
                }
            )
            continue

        source_tokens = _tokenize(_strip_latex(source_abstract))
        claimed_tokens = _tokenize(claimed_copy)

        matcher = difflib.SequenceMatcher(None, source_tokens, claimed_tokens)
        ratio = matcher.ratio()
        if ratio < 0.97:
            diff_lines = list(
                difflib.unified_diff(
                    source_tokens,
                    claimed_tokens,
                    fromfile=str(source_file.relative_to(ROOT)) + " (abstract, normalized)",
                    tofile=str(claiming_file.relative_to(ROOT)) + " (claimed copy, normalized)",
                    lineterm="",
                )
            )
            mismatches.append(
                {
                    "claiming_file": str(claiming_file.relative_to(ROOT)),
                    "source_file": str(source_file.relative_to(ROOT)),
                    "similarity": ratio,
                    "diff": diff_lines,
                }
            )
    return mismatches


def check_inline_quotes() -> list[dict]:
    """Return a list of mismatch reports for `Verbatim: "..."` claims whose
    quoted text can't be found in the cited source file."""
    mismatches = []
    sources = list(REPORTS_DIR.glob("*.md"))
    if PROVENANCE_MD.exists():
        sources.append(PROVENANCE_MD)

    for path in sources:
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            quote_match = VERBATIM_QUOTE_RE.search(line)
            if not quote_match:
                continue
            quoted = quote_match.group(1)
            source_match = BACKTICK_SOURCE_RE.search(line)
            if not source_match:
                mismatches.append(
                    {
                        "claiming_file": str(path.relative_to(ROOT)),
                        "line": lineno,
                        "quoted": quoted,
                        "error": "no backtick-quoted source .md filename found on this line",
                    }
                )
                continue
            cited_path = REPORTS_DIR / source_match.group(1)
            if not cited_path.exists():
                mismatches.append(
                    {
                        "claiming_file": str(path.relative_to(ROOT)),
                        "line": lineno,
                        "quoted": quoted,
                        "error": f"cited source {cited_path} does not exist",
                    }
                )
                continue
            cited_text = cited_path.read_text(encoding="utf-8", errors="replace")
            normalized_quoted = re.sub(r"\s+", " ", quoted).strip()
            normalized_source = re.sub(r"\s+", " ", cited_text)
            if normalized_quoted not in normalized_source:
                mismatches.append(
                    {
                        "claiming_file": str(path.relative_to(ROOT)),
                        "line": lineno,
                        "quoted": quoted,
                        "cited_source": str(cited_path.relative_to(ROOT)),
                        "error": "quoted text not found (verbatim, whitespace-normalized) in cited source",
                    }
                )
    return mismatches


def find_unclassified_verbatim_mentions() -> list[tuple[str, int, str]]:
    """Every 'verbatim' mention not consumed by a structured check above --
    printed for human awareness, does not fail the exit code on its own."""
    consumed_lines: set[tuple[str, int]] = set()
    for claim in ABSTRACT_VERBATIM_CLAIMS:
        rel = str(claim["claiming_file"].relative_to(ROOT))
        text = claim["claiming_file"].read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "Reproduced verbatim" in line:
                consumed_lines.add((rel, lineno))

    unclassified = []
    skip_dirs = {"evals", "build", "dist", ".git"}
    for pattern in ("*.md", "*.tex"):
        for path in ROOT.rglob(pattern):
            if any(part in skip_dirs for part in path.relative_to(ROOT).parts):
                continue
            rel = str(path.relative_to(ROOT))
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if not VERBATIM_MENTION_RE.search(line):
                    continue
                if "\\begin{verbatim}" in line or "\\end{verbatim}" in line:
                    continue  # LaTeX environment name, not a content-copy claim
                if (rel, lineno) in consumed_lines:
                    continue
                if VERBATIM_QUOTE_RE.search(line):
                    continue  # handled by check_inline_quotes
                unclassified.append((rel, lineno, line.strip()))
    return unclassified


def main() -> int:
    # Restatement-risk text (README.md, main.tex) legitimately contains
    # non-ASCII (>=, en/em dashes) -- Windows' default cp1252 console
    # encoding can't print it. UTF-8 output is correct regardless of platform.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    exit_code = 0

    # --- Check 1: superseded-marker leak scan ---
    flagged = find_flagged_values()
    print(
        f"[1/3] Found {len(flagged)} distinct flagged (marked-superseded) numeric value(s) "
        f"across {REPORTS_DIR.relative_to(ROOT)}/*.md and {PROVENANCE_MD.relative_to(ROOT)}."
    )
    for value, sites in sorted(flagged.items()):
        print(f"      {value}  (flagged at {len(sites)} site(s), e.g. {sites[0][0]}:{sites[0][1]})")

    leaks = check_restatement_leaks(flagged)
    print()
    if leaks:
        exit_code = 1
        print(
            f"CANDIDATE LEAKS: {len(leaks)} occurrence(s) of a marked-superseded value found in "
            f"a restatement-risk file -- review each by hand, some may be legitimate "
            f"supersession-acknowledgment mentions:"
        )
        for value, file, lineno, line in leaks:
            print(f"  [{value}] {file}:{lineno}: {line}")
    else:
        print("No flagged value found in any restatement-risk file. Clean.")

    # --- Check 2: verbatim-abstract-copy diff ---
    print()
    print("[2/3] Verbatim-abstract-copy claims:")
    abstract_mismatches = check_abstract_verbatim_claims()
    if not ABSTRACT_VERBATIM_CLAIMS:
        print("      (none configured)")
    for claim in ABSTRACT_VERBATIM_CLAIMS:
        cf = str(claim["claiming_file"].relative_to(ROOT))
        sf = str(claim["source_file"].relative_to(ROOT))
        hit = next(
            (m for m in abstract_mismatches if m["claiming_file"] == cf and m["source_file"] == sf),
            None,
        )
        if hit is None:
            print(f"      OK  {cf} matches {sf}'s current abstract")
        else:
            exit_code = 1
            if "error" in hit:
                print(f"      ERROR  {cf} vs {sf}: {hit['error']}")
            else:
                print(
                    f"      MISMATCH  {cf} vs {sf} (word-similarity {hit['similarity']:.2%}, "
                    f"threshold 97%):"
                )
                for line in hit["diff"]:
                    print(f"        {line}")

    # --- Check 3: inline verbatim-quote claims ---
    print()
    print('[3/3] Inline `Verbatim: "..."` quote claims:')
    quote_mismatches = check_inline_quotes()
    if not quote_mismatches:
        print("      All inline verbatim-quote claims found in their cited source. Clean.")
    else:
        exit_code = 1
        for m in quote_mismatches:
            print(f"      MISMATCH  {m['claiming_file']}:{m['line']}: {m['error']}")
            print(f"        quoted: {m['quoted']!r}")

    # --- Coverage transparency ---
    unclassified = find_unclassified_verbatim_mentions()
    print()
    if unclassified:
        print(
            f"COVERAGE NOTE: {len(unclassified)} other 'verbatim' mention(s) in the repo are not "
            f"mechanically checked by this script (no configured claim structure) -- human review:"
        )
        for rel, lineno, line in unclassified:
            print(f"  {rel}:{lineno}: {line}")
    else:
        print("COVERAGE NOTE: no unclassified 'verbatim' mentions outside the checks above.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

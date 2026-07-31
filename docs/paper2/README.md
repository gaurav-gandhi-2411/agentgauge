# Building the methods paper

`main.tex` compiles with [tectonic](https://tectonic-typesetting.github.io/), a self-contained
LaTeX engine distributed as a single portable binary. No TeX Live/MiKTeX install, no admin
rights, and no package manager needed beyond `curl`/`unzip`.

## One-time setup (Windows, no admin escalation)

```bash
# Download the tectonic release for your platform and put the binary somewhere on PATH.
# This repo's authors used a user-writable directory already on PATH (C:\Users\<you>\bin);
# any directory you control works the same way -- tectonic has no installer, no registry
# entries, and no dependency on a system-wide LaTeX distribution.
cd /path/on/your/PATH
curl -sL -o tectonic.zip \
  "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip"
unzip -o tectonic.zip
rm tectonic.zip
tectonic --version   # sanity check
```

On macOS/Linux, swap the asset name for the matching release
(`tectonic-<version>-x86_64-apple-darwin.zip`, `...-unknown-linux-musl.tar.gz`, etc.) from
<https://github.com/tectonic-typesetting/tectonic/releases/latest>, or install via your package
manager (`brew install tectonic`, `cargo install tectonic`) if you have one available.

Tectonic fetches the actual TeX packages/fonts it needs (bundle files, `.sty`/`.bst`/`.tfm`
assets) on first use, from its default bundle CDN, and caches them locally -- this requires
outbound internet access the first time a given package is needed, but nothing more than that
(no account, no license, no paid tier).

## Compiling

```bash
cd docs/paper2
tectonic main.tex
```

This produces `main.pdf`. Tectonic automatically detects when BibTeX needs to run (via
`\bibliography{refs}` in `main.tex`, resolving against `refs.bib`) and reruns TeX as many times
as needed to settle cross-references and citations -- no separate `bibtex`/`pdflatex` dance
required, unlike a traditional TeX Live workflow.

A full `tectonic main.tex` run currently: compiles cleanly with **zero errors**, resolves every
`\ref{}`/`\citep{}` (nothing undefined), and produces one cosmetically negligible
`Underfull \hbox (badness 1286)` warning (a slightly loose line in one justified paragraph, well
below the ~3000 badness threshold that's usually worth chasing, and imperceptible in the
rendered PDF). Compile with `tectonic --print main.tex` for the fully verbose per-pass log if you
need to debug a new warning.

## Verifying figures/tables render correctly (no poppler available)

`Read`-based PDF page rendering in this environment requires `pdftoppm` (poppler-utils), which
is not installed and could not be reliably installed without admin rights or a slow `conda`
solve in this sandbox. Rendering was instead verified using
[PyMuPDF](https://pymupdf.readthedocs.io/) (`pip install pymupdf`, pure-Python wheel, no system
dependency), which was already present in this machine's environment:

```python
import fitz
doc = fitz.open("main.pdf")
for i, page in enumerate(doc):
    page.get_pixmap(dpi=150).save(f"page_{i+1:02d}.png")
```

Every page was visually inspected this way during this wave: all 5 figures render correctly, the
taxonomy longtable (Table 1) and every other table fit within the page margins, and no
`\includegraphics` reference is broken.

## Known cosmetic limitation, not fixed

One `Underfull \hbox` warning remains (see above) -- a loose final line in a single paragraph.
Left as-is rather than hand-tuned further: LaTeX flags this on nearly any paragraph whose last
line happens to be short relative to the column width, it has no visible effect at normal
reading distance, and chasing it below the current negligible level would mean rewording prose
purely for typographic effect, which risks drifting a provenance-critical sentence away from its
source wording for no reader-facing benefit.

## Bibliography verification protocol

**The incident that motivated this.** During this wave, an audit of this repo's companion paper's
bibliography (`docs/paper/latex/references.bib`) found 6 of 9 entries wrong in ways invisible to
ordinary proofreading:

- Two entries attributed a real, named author's work to a generic team ("Anthropic Engineering,"
  "GitHub Engineering") instead of the actual byline (Ken Aizawa, Ksenia Bobrova), and stated the
  wrong publication year.
- Four entries had wrong author given/middle names where the **surname initials were still
  correct** -- e.g. "Ramesh S. Babu" instead of the real "Rahul Suresh Babu," "Suzan Wang" instead
  of "Shuaiqiang Wang." Because this paper's in-text citations use initials only (`Babu, R. S.`),
  these errors were invisible in the rendered PDF and survived multiple earlier proofreading
  passes undetected.
- Two entries (GitHub issue citations) had bibkeys and notes asserting the wrong year, with a note
  claiming the real date was "not independently confirmed" when it was directly available via the
  GitHub API the whole time.

None of this is the kind of error proofreading catches, because proofreading checks that a
citation *reads* plausibly, not that its fields match a primary source byte-for-byte. The only
way to catch it is to independently open the actual source (the DOI, the arXiv page, the
publisher's page, the GitHub API response) and check every field against it -- which is what
"verified" means below, and what `scripts/check_bib_verified.py` mechanically enforces the
*presence* of (it cannot itself judge correctness -- see "What this does not catch," below).

**The convention.** Every `@`-entry in every `.bib` file in this repo must carry a
`verified = {<type>}` field, where `<type>` is one of:

| Type | What it means | Example check |
|---|---|---|
| `doi-crossref` | Resolved the entry's DOI via `https://doi.org/<doi>` or the Crossref API (`api.crossref.org/works/<doi>`) and confirmed every field against the returned record | `deng2013cuped` |
| `arxiv-api` | Fetched `https://arxiv.org/abs/<id>` or `http://export.arxiv.org/api/query?id_list=<id>` and confirmed the full author list, title, and year against it | `hasan2026smelly` |
| `publisher-page` | Fetched the publisher's/venue's own page directly (a journal site, a blog post's own URL, an ACM DL / SAGE / Oxford Academic page) | `anthropic2025tools` |
| `github-api` | Fetched `https://api.github.com/repos/<owner>/<repo>/issues/<n>` (or equivalent) for a GitHub-hosted source | `openai2025issue464` |
| `isbn-catalog` | Cross-checked a book's ISBN/LCCN against a library catalog (OpenLibrary, WorldCat, Library of Congress) | `kish1965survey` |

**What counts, what does not.** A search-engine results page, an AI assistant's own recollection,
or a citation copied from another paper's bibliography without independently re-opening the
primary source **do not** satisfy this convention, regardless of how confident the claim looks --
that is exactly the failure mode that produced the incident above (the original wrong entries
were plausible-looking and had correct titles/venues/eprint IDs; only the author names were
wrong, discoverable only by opening the real page).

**What this does not catch.** `scripts/check_bib_verified.py` is a presence check, not a
correctness check -- it can only confirm that a `verified` field exists and names one of the
allowed types, not that whoever wrote it actually did the verification, or did it correctly. It
is the same class of guarantee as a test file existing (proves the discipline was followed by
someone, not that the underlying claim is true). Anyone adding or editing a `.bib` entry is
responsible for actually doing the check described by the type they record; an independent
verifier subagent (or a human reviewer) re-checking a sample of entries against their claimed
verification type, as was done for every entry this wave, is the actual correctness gate.

**Running the check locally:**

```bash
python scripts/check_bib_verified.py
```

Wired into CI as a step in the `hygiene` job (`.github/workflows/ci.yml`), which is one of this
repo's three required status checks -- a `.bib` entry missing its `verified` field blocks merge.

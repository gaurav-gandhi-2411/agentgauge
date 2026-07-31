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

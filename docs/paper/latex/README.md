# Building this paper

LaTeX engine: [tectonic](https://tectonic-typesetting.github.io/) (standalone binary,
no system TeX distribution required). Installed to `~/.local/tectonic/` — not on PATH
by default.

```bash
export PATH="$HOME/.local/tectonic:$PATH"
tectonic main.tex
```

Produces `main.pdf`. `abstract_body.tex` and `body_content.tex` are `\input`-ed by
`main.tex`; `references.bib` holds the bibliography.

Currently a generic single-column `article` class — no venue/workshop template has
been selected yet. Swap in the venue's official `.cls`/`.sty` once chosen (this will
likely require reflowing tables and re-checking page limits).

CI enforces that any commit touching `docs/paper/paper.md` also touches this directory in the
same commit (`scripts/check_paper_latex_sync.py`, wired into the `hygiene` job) — resync and
recompile `main.pdf` before committing a `paper.md` edit.

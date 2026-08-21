# arXiv submission — Paper 1

## Title

Tool-Description Quality Is Not One Axis: A Regime Analysis of Where It Helps and Where It
Backfires

## Abstract

Tool-description quality is widely treated as a broadly-applicable lever for agent tool-use, but
it is not a single better/worse axis: the precision that helps an agent disambiguate within a
family of confusable tools is orthogonal to, or actively harmful for, context-rich selection and
for tool retrieval. We test this with a single frozen evaluation protocol — one classifier, one
judge, one generator family, pre-registered thresholds — across a synthetic confusable-catalog
experiment, two real production MCP-server mirrors (GitHub, AWS IAM), a synthetic internal-proxy
catalog, and a pre-registered pilot of ten public Python MCP servers. The effect is real but
regime-bounded, not a general law: an oracle description helps at one tested catalog density (60
tools/10 families, +34.5pp on gemma2:9b, and not collapsing on a substantially stronger model,
Llama-3.3-70B) with no headroom; realizing it safely through automatic generation is a separate
condition, requiring documented source. Outside these conditions the effect is null or reverses
(zero headroom on two well-documented production servers; −20pp harm on one already-resolved
family; harm to retrieval across three retriever types). Contributions: a falsifiable regime map
of where description quality helps, harms, or does nothing; a pre-registered prevalence
measurement finding the behavioral regime in 0 of 9 testable Python MCP servers — a lower bound,
not a population estimate; and a localizability boundary — a pairwise LLM-judge confusability
method fails under two independent framings, via two distinct failure mechanisms.

(Reproduced verbatim from `docs/paper/latex/abstract_body.tex`, with the source's `---` em-dash
markup rendered as literal `—` characters for a plain-text-safe paste into arXiv's abstract field.
No other content differs from the compiled PDF's abstract block.)

## arXiv categories

**FINAL.**

- **Primary:** cs.SE (Software Engineering)
- **Cross-list:** cs.AI (Artificial Intelligence)

**Why, in one line:** the single closest analog — Hasan et al., "Model Context Protocol (MCP)
Tool Descriptions Are Smelly!" (arXiv:2602.14878), which does nearly the same combination of
things this paper does (audits real MCP servers' tool descriptions and measures the behavioral
consequence for agent task success) — is cs.SE primary and didn't even cross-list cs.AI; that,
plus this paper's own EXP-1 prevalence study (§5) and RW1/RW2 real-server evaluation (§4.3.1)
being built on classic empirical-software-engineering methodology (a stratified GitHub sampling
frame, documented extraction-tool limitations, a revision history), outweighs the alternative
analog (Babu & Iyer's ToolChoiceConfusion, arXiv:2606.06284, cs.AI primary/no cross), which is a
weaker match because it has no real-server empirical-SE component.

## Author / affiliation

**Gaurav Gandhi**
Independent Researcher, Bengaluru, India
`https://github.com/gaurav-gandhi-2411`

Set directly in the paper's typeset front matter (`\author{}` in `docs/paper/latex/main.tex`) as:

```latex
\author{Gaurav Gandhi \\ Independent Researcher, Bengaluru, India \\ \url{https://github.com/gaurav-gandhi-2411}}
```

Identical to paper 2's author block (`docs/paper2/SUBMISSION.md`); both are companion papers by
the same sole author. No email appears in the rendered PDF, by design — the GitHub profile is the
contact point. arXiv's own submission form separately requires a name/affiliation at upload time
regardless of what the typeset PDF shows — this section states what to enter there.

## License

**CC BY 4.0** — final, matches paper 2. This repository's code remains Apache License 2.0
(`LICENSE`); arXiv's distribution license is a separate, independent choice made at upload time
and does not need to match the code license.

## Code availability

Source: `https://github.com/gaurav-gandhi-2411/agentgauge` (Apache-2.0). Unlike paper 2, this
paper's own text does not carry a `pip install` reproduction line — its Section 9
("Reproducibility Artifact") instead points directly at committed fixture files and SHA-256
hashes (e.g. `evals/fixtures/frontier_t18_step2_result.json`, `evals/fixtures/
frontier_t18_step2_raw_calls.json`) verified against a specific commit reachable from `HEAD`, with
the full trace in `docs/paper/evidence_table.md` and the frozen protocol in
`docs/research/frozen_protocol.md`. No live API key or paid model call is required to reproduce
any result.

## Source bundle

The complete arXiv source bundle is exactly these four files (no figures — this paper has no
`\includegraphics` calls, confirmed by grep):

```
main.tex
abstract_body.tex
body_content.tex
references.bib
```

**Verified 2026-08-11:** copied exactly this file set into a directory outside the repository (no
`.git`, no sibling `docs/` content) and compiled with `tectonic main.tex` from within that
directory — zero errors, two cosmetic warnings (an underfull hbox in a long author-name table row
and one in the bibliography), output `main.pdf` = 150.6 KiB. Re-extracted the packaged
`.tar.gz` into a second, separately isolated directory and recompiled from scratch to confirm the
tarball itself (not just the staged file copies) is genuinely self-contained — same zero-error
result, same 150.6 KiB / 154,229-byte output.

**PDF hash difference, explained (not merely observed):** the two compiles' PDF bytes are not
bit-identical — `cmp -l` found 1,614 differing bytes out of 154,230, clustered in the file's final
~4 KB. Traced to the cause: the file's trailer `/ID` entry (`grep -a -o "/ID *\[[^]]*\]"`) reads
`6dd5c0de548e597d145d252e20f6f384` in one compile and `f96faea2ceff1c6b997a42e8901687b5` in the
other — the two-part file identifier the PDF spec (ISO 32000-1 §14.4) recommends generating fresh
per write (typically seeded by a timestamp/content digest), specifically so it varies even across
byte-identical-content writes. No literal `/CreationDate` string exists anywhere in either file
(`grep -c` = 0), so that field is either absent or not the source here — the `/ID` value is. The
file uses a compressed cross-reference stream (`/Type /XRef` present, 3 `/ObjStm` compressed
object streams) rather than a classic plain-text trailer, so that one differing `/ID` value sits
inside a DEFLATE-compressed stream — a single-input change there shifts the entire subsequent
compressed byte sequence, which is why 1,614 bytes differ rather than just the ~66 bytes the `/ID`
string itself occupies. Confirmed harmless: not a content or figure/table difference, and not a
concern for arXiv (which recompiles from the uploaded `.tex` source, not from either PDF).
To reproduce the bundle at submission time:

```bash
mkdir arxiv-bundle && cd arxiv-bundle
cp path/to/repo/docs/paper/latex/{main.tex,abstract_body.tex,body_content.tex,references.bib} .
tectonic main.tex   # sanity check: must compile standalone before uploading
```

## Companion paper

`docs/paper2/`'s submission plan and category reasoning are in `docs/paper2/SUBMISSION.md`.

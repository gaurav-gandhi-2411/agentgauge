# arXiv submission — Paper 2

## Title

Powering Agent Evaluations: Variance Structure, Measurement Artifacts, and Minimum Detectable
Effects in Tool-Use Benchmarks

## Abstract

Agent evaluations are routinely reported without a power analysis, without a stated detection
floor, and without screening for measurement artifacts. This paper measures the variance
structure of agent task outcomes on a 253-task, 3-model tool-use corpus (intraclass correlation
0.793 within tool-set/task; 56.1% of outcome variance is between-task), shows the direct
consequence for experimental design (repeated trials on the same task carry little independent
information), and gives a paired, common-random-numbers, task-clustered-bootstrap, CUPED,
sequential-testing estimator that reaches a minimum detectable effect of 0.0537 at n=253 tasks
(from an uncorrected-baseline MDE of 0.433 at n=20). We catalogue ten measurement-artifact
classes discovered during this project, each with an automated detector shipped in
`agentgauge audit`, including two cases where an artifact produced a false positive the authors
initially believed: a −76.7 to −80.0 percentage-point causal effect that a scoring bug corrected
to a near-null (clean null for two of three models, a CI-includes-zero result for the third), and
a 100% top-1 localization-accuracy claim that a probe-noise miscalibration corrected to 58.33%.
We report a structural negative result on regression localization: the accuracy a localizer needs
(task volume, since MDE ∝ 1/√n) is precisely the cost a localizer exists to avoid, producing a
real cost-crossover at 2–4 changed tools against full re-evaluation. Finally, we report a
falsification record: four pre-registered hypotheses failed, including the authors' own product
thesis that an eight-axis tool-description quality score predicts agent task success. This paper
began as an attempt to validate that score as a commercial product. It did not survive contact
with an adequately powered, artifact-screened measurement. That failure is the paper's subject,
not an incidental footnote to it.

(Reproduced verbatim from `docs/paper2/main.tex`'s `\begin{abstract}...\end{abstract}`, with the
inline `% PROV:` provenance comments stripped — those comments are source-only, invisible in the
compiled PDF, and not part of the reader-facing abstract text.)

## arXiv categories

**FINAL (superseding both prior passes below — do not re-litigate without new evidence).**

- **Primary:** cs.LG (Machine Learning)
- **Cross-list:** cs.AI (Artificial Intelligence)

**Why, in one line:** the single closest analog by content — not just topic — is "Pre-Registering
the Detectable Effect: A Paired-MDE Budget for 4-bit Quantization Benchmarks" (arXiv:2605.28873),
which matches this paper's own framing almost term-for-term (paired, pre-registered, MDE budget)
and is cs.LG primary with no cross-list at all; across a targeted 7-paper set of paired-testing/
MDE/power-analysis papers for ML benchmarks, cs.LG was the most common CS-side primary (2/7,
plus 3/7 in the stat.* family) and cs.SE appeared in zero of them.

<details>
<summary>Superseded reasoning (kept for the record, not for re-derivation)</summary>

**Pass 1 (original):** cs.SE primary, cs.LG + cs.AI cross — reasoned from the abstract's own
"measurement methodology for evaluating software changes to agent systems" framing, without
checking comparable papers.

**Pass 2:** cs.AI primary, cs.LG + cs.SE cross — after checking 8 *broad* agent-eval-methodology
comparables (cs.CL primary 4/8, cs.AI 1/8, cs.SE 1/8, cs.LG 1/8, stat.ML 1/8; cs.AI appeared
primary-or-cross on 6/8). Superseded because the comparable set was too broad — matched on topic
("agent evaluation") rather than on this paper's actual technical content (paired MDE estimators,
CUPED, cluster-robust bootstrap, sequential testing).

**Pass 3 (final, above):** re-ran the comparable-paper check against a *tighter* set matched on
technical content, not just topic, which reversed the cs.AI-primary call in favor of cs.LG.
</details>

No change to `main.tex`'s abstract, introduction, or conclusion is needed for any of this — the
paper's own text never frames its contribution in software-engineering-specific terms; category
placement has been a metadata judgment layered on top of neutral text throughout, not something
baked into the prose.

## Author / affiliation

**Gaurav Gandhi**
Independent Researcher, Bengaluru, India
`https://github.com/gaurav-gandhi-2411`

Set directly in both papers' typeset front matter (`\author{}` in `docs/paper2/main.tex` and
`docs/paper/latex/main.tex`) as:

```latex
\author{Gaurav Gandhi \\ Independent Researcher, Bengaluru, India \\ \url{https://github.com/gaurav-gandhi-2411}}
```

No email address appears in either rendered PDF, by design — the GitHub profile is the contact
point. (Name cross-checked against this repository's package metadata,
`pyproject.toml`'s `authors` field, as the canonical source; not fabricated.) arXiv's own
submission form separately requires a name/affiliation at upload time regardless of what the
typeset PDF shows -- this section states what to enter there, matching the PDF.

## License

**CC BY 4.0** — final. This repository's code remains Apache License 2.0 (`LICENSE`); arXiv's
distribution license is a separate, independent choice made at upload time and does not need to
match the code license. Paper 1 (`docs/paper/SUBMISSION.md`) uses the same choice for consistency
between the two companion papers.

## Code availability

The harness, corpus, and every script referenced by a provenance pointer in
`docs/paper2/provenance.md` are published and installable:

```bash
pip install agentgauge-harness==0.5.2
```

Source: `https://github.com/gaurav-gandhi-2411/agentgauge` (Apache-2.0). Every statistical result
in this paper reproduces from the fixtures committed under `evals/` and the scripts named
alongside each report in `docs/paper2/provenance.md`; none require a live API key or a paid model
call (see `docs/paper2/main.tex` Appendix D, "Reproduction instructions").

## Source bundle

The complete arXiv source bundle is exactly these files (nothing else — no repo-relative paths,
no local machine paths):

```
main.tex
refs.bib
figures/allocation_grid_heatmap.png
figures/estimator_ablation.png
figures/mde_curve.png
figures/artifact_taxonomy_table.png
figures/attribution_cost_crossover.png
```

All five are the only `\includegraphics` targets in `main.tex` (confirmed by grep); no other
file in the repository is required to compile. `refs.bib` has zero absolute local paths (grepped
for `C:\Users\` and equivalents — no matches).

**Verified this wave:** copied exactly this file set into a directory outside the repository
(no `.git`, no sibling `docs/` content, no relative access to anything else in this project) and
compiled with `tectonic main.tex` from within that directory — zero errors, output byte-size
matches the in-repo compile (~404 KB), confirming the bundle is genuinely self-contained rather
than only working by accident inside the full repo checkout. Not committed as a duplicate copy in
the repository (the same five files already live at `docs/paper2/{main.tex,refs.bib}` and
`docs/paper2/figures/`; copying them again into a `docs/paper2/arxiv_bundle/`-style directory
would create a second, driftable copy of already-tracked source). To reproduce the bundle at
submission time:

```bash
mkdir arxiv-bundle && cd arxiv-bundle
mkdir figures
cp path/to/repo/docs/paper2/main.tex .
cp path/to/repo/docs/paper2/refs.bib .
cp path/to/repo/docs/paper2/figures/{allocation_grid_heatmap,estimator_ablation,mde_curve,artifact_taxonomy_table,attribution_cost_crossover}.png figures/
tectonic main.tex   # sanity check: must compile standalone before uploading
```

## Companion paper's bundle (verified alongside, since its bibliography changed this wave)

`docs/paper/latex/`'s source bundle is `main.tex`, `abstract_body.tex`, `body_content.tex`,
`references.bib` (no figures; confirmed via grep, no `\includegraphics` in that paper). Verified
this wave to compile standalone in an isolated directory the same way, zero errors, output
byte-size matches the in-repo compile (~144 KB).

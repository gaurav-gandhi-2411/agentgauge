# Research drafts (text formerly in the README "The paper" section)

**Status, 2026-10-11: two research drafts, not peer-reviewed, claims being re-verified.** This file
keeps the README's former description of the first draft so nothing is lost, with the statements
that a 2026-10 audit found false or unsupported corrected or marked. It makes no new result claims.

Sources (both in this repository):

- Draft 1, "Tool-Description Quality Is Not One Axis: A Regime Analysis of Where It Helps and Where It
  Backfires": `docs/paper/paper.md` (canonical), LaTeX mirror and PDF in `docs/paper/latex/`.
- Draft 2, a methods paper on power analysis, measurement-artifact screening and a falsification
  record for tool-description evaluation: `docs/paper2/main.tex`, PDF `docs/paper2/main.pdf`.

There is no arXiv identifier for either draft. (The README formerly carried the placeholder
`arXiv:XXXX.XXXXX`; it has been removed.)

## Draft 1, former README summary

Tool-description quality is widely treated as a broadly-applicable lever for agent tool-use, but it
is not a single better/worse axis: the precision that helps an agent disambiguate within a family of
confusable tools is orthogonal to, or actively harmful for, context-rich selection and for tool
retrieval. The draft argues the effect is regime-bounded and maps the boundary (catalog density,
headroom, documented source).

[CORRECTED 2026-10-11: the original added "and finds it rare in a pilot sample of real servers".
That pilot is 10 Python servers from a single source, not the 28 servers / all languages / 5 sources
that was pre-registered, and "0 of 9" in the draft is 0 of 7 testable servers. Servers in the
"real server" experiments are stubbed mirrors, not live servers.]

### The Two-Condition Regime Test (as described in the draft)

1. **Fail**: does the agent fail at least one contested task under the server's real, shipped
   descriptions?
2. **Recover**: if it fails, does a hand-written, ground-truth description recover it?

If (1) is NO there is nothing to fix; if (1) is YES but (2) is NO the failure is not
description-shaped. Only if both are YES is the server inside the regime where better descriptions
help. This is the two-step check the draft's own experiments used, not a separately validated
instrument.

### Reproducibility, corrected

The README formerly said: "Every experiment in the paper runs under a single frozen evaluation
protocol ... pre-registered thresholds" and "Every figure in the paper traces to a committed,
hash-verified fixture". **Both statements were false and are withdrawn:**

- `docs/research/frozen_protocol.md` was first committed in `1493791` on 2026-06-22 (02:18 +05:30)
  and edited once more in `5a20d06` on 2026-07-11 (wording only). The experiments T18 (2026-06-07),
  Q2-Q6 (2026-06-07/08), RW1 (2026-06-10), RW2 (2026-06-11), FRONTIER-T18 (2026-06-14), P2-A and F2
  (2026-06-15) all have result commits dated **before** the protocol existed. They are **not**
  pre-registered under it. Only EXP-1 and EXP-3 (2026-07-04) had their design committed before their
  results. (F2 has its own query/interpretation commits `5f538e5` and `c72e7fa` before scoring; that
  is a per-experiment note, not the frozen protocol.)
- Trial-level data for the headline T18-gemma2 result (+34.5pp) and for Q2-Q6, RW1, RW2 and P2-A are
  not committed (only STATUS.md prose and git-ignored console output), so those figures cannot be
  recomputed from the repository. The FRONTIER-T18 `plan_event` task was reworded in `5269645`, the
  commit that recorded the result, so "identical T18 fixture" overstates.

`./scripts/verify.sh` runs the repository's test suite (LLM always mocked, no network, no
credentials); that is a code check, not a reproduction of the experiments.

### Building the PDF

`docs/paper/paper.md` is the canonical source; `docs/paper/latex/` is a maintained mirror (CI fails if
a commit changes one without the other):

```bash
export PATH="$HOME/.local/tectonic:$PATH"
cd docs/paper/latex
tectonic main.tex
```

**Scope note:** pilot-scale research artifact: synthetic fixtures, two stubbed real-server mirrors
and a 10-server pilot. Not a validated product claim. Tasks, gold labels and oracles appear to have
been authored by AI-assistant sessions (BELIEVED, from a code comment; not independently confirmed).

## Draft 2

The abstract's description of its data and several numbers (the variance structure was measured on
a fixed-seed corpus and has since been re-measured with per-trial seeds, moving ICC from 0.793 to
0.731 and MDE(100x1) from 0.0848 to 0.0878; a pooled causal-chain figure; an omitted strategy
inversion) were found inconsistent with the repository by the 2026-10 audit and are being
re-verified. See `measurement-history.md` for the
corrections that apply to the shared numbers.

# Paper 1 (tool-description quality as a regime-bounded effect)

**Superseded draft — not peer-reviewed. Known false or unsupported claims:**

Sources are `paper.md` (the text) and `latex/` (the LaTeX build, PDF `latex/main.pdf`). Neither has
been corrected; the PDF still contains every claim below. The list is the Paper-1 half of the
Phase 0 audit of 2026-10-11 (findings 1, 6 and 7; findings 2-4 and 8 concern
[Paper 2](../paper2/README.md)). Pointers are to files and commits in this repository; the audit's
claim-by-claim working tables were kept locally and are not committed.

1. **"Committed once ... never edited after any experiment's results were collected" is false**
   (`paper.md:179`, same sentence in `latex/body_content.tex`). `docs/research/frozen_protocol.md`
   was first committed in `1493791` (2026-06-22T02:18+05:30), after T18 (2026-06-07), Q2-Q6
   (06-07/08), RW1 (06-10), RW2 (06-11), FRONTIER-T18 (06-14) and P2-A/F2 (06-15). It was edited
   again in `5a20d06` (2026-07-11), after EXP-1/EXP-3 (07-04). Only EXP-1 and EXP-3 had their
   design committed before their results.
   Evidence: `git log --format='%h %aI %s' -- docs/research/frozen_protocol.md`; also
   [`docs/history/research-drafts.md`](../history/research-drafts.md).
2. **"Every figure in Sections 4-6 traces to a committed file" is false** (`paper.md:705`). The
   T18 +34.5 pp headline (exact value +34.58 pp), Q2-Q6, RW1, RW2 and P2-A have no trial-level
   data committed: only `STATUS.md` prose and git-ignored console text files. 14 of the 77 audited
   claims could not be recomputed from the repository.
   Evidence: `docs/paper/evidence_table.md` (what the paper itself says is committed) against
   `git ls-files evals/fixtures`.
3. **Undisclosed or overstated items:**
   - FRONTIER-T18: the `plan_event` task was reworded in `5269645`, the commit that records the
     result, after the oracle failed on it; the paper says "identical T18 fixture".
     Evidence: `git show 5269645`, `docs/research/frontier_t18_result.md`.
   - "0 of 9" is 0 of 7 testable servers.
   - The pre-registered pilot asked for 28 servers across languages and sources; 10 Python servers
     from one source were delivered. EXP-1 tasks and gold labels were first committed together with
     the results. Evidence: `docs/research/exp1_*`, `git log` for those paths.
   - No confidence intervals and no multiplicity correction. The Jupyter -15 pp "harm" is one task;
     EXP-3 graded scores have AUC 0.45; "ruled out noise" in P2-A rests on one discordant task.
   - The GitHub "flat 70/100" equals the `MockProvider` constant (believed, not verified).
   - Guard-B regressed 2 of 14 thorough tools on the RW2 mirror per `STATUS.md`; the paper omits it.
   - Tasks, gold labels and oracle descriptions were authored by an AI assistant session
     (believed, from a code comment), and the "real" servers are stubbed mirrors:
     `docs/paper/threats_to_validity.md`, `reports/v2_5_task2_fixture_validation.md` (3 of 10
     newest fixtures contained a factual error against vendor docs).

Numbers in the README (project root) were re-checked and corrected on 2026-10-11; this paper's
text was not.

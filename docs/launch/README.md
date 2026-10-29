# Launch copy drafts

Status: **DRAFTS. Nothing here has been posted anywhere.**

| File | Venue | Words (excluding banner, markdown link targets and bare repo URLs) |
|---|---|---|
| [`show-hn.md`](show-hn.md) | Show HN (title 77 characters) | 566 |
| [`reddit-ml.md`](reddit-ml.md) | r/MachineLearning, flair [P] | 624 |
| [`linkedin.md`](linkedin.md) | LinkedIn | 344 |
| [`blog.md`](blog.md) | Blog post | 859 (body between the BODY markers; `wc -w` of the body incl. link targets: 865, target 600-900) |

## Prerequisites before any post

1. **Merge `docs/gw-truncation-correction`** (0524f65, unmerged at the time of writing). Every draft
   describes the corrected google_workspace result (65%/65%, was published as 0%/0%), and its links point
   at the files as they will be on main after that merge. Posting before the merge would present a
   number as changed that main still publishes.
2. Re-run `python scripts/check_launch_claims.py` on the merged main; it must print
   `0 failures`. After the merge the `origin/docs/gw-truncation-correction` refs in `claims.json` can be
   switched to the working tree (remove the `ref` fields).
3. Optional: `fix/ollama-num-ctx` carries the `num_ctx` sizing and the Ollama truncation guard. It is not
   on main, so all four drafts say so (the shipped tool does not size the window itself). If that branch
   merges first, rewrite those sentences and flip the `guard-not-on-main` and `num-ctx-not-on-main`
   claims. The same applies if v0.6.0 is released first: `release/v0.6.0` already contains that fix, so
   a release makes the "not on main / shipped tool does not size the window" sentences stale.
   At posting time, check the PyPI version (`pip index versions agentgauge-harness`; 0.5.3 on
   2026-10-29) in a fresh venv, and check that the `pip install` / `lint` / `diff` / `init` examples and the
   blog's `No violations found.` output still match what that version prints.
4. Convert nothing else: links are absolute `github.com/.../blob/main/...` URLs already. Show HN and
   LinkedIn do not render markdown, so they carry bare URLs in a reference list at the end (the
   checker verifies bare URLs the same way as markdown links). The blog's guard link is a commit
   permalink (`blob/<sha>/...`) on `fix/ollama-num-ctx`, so it cannot rot if the branch moves.
5. Not done here, still needed for a real post: a final read by the author, and the 30-day rule below.

## Timing rule

agentgauge launches **at least 30 days after tracegauge**. These drafts are not to be posted before
then.

## How claims are traced

Every factual sentence in the drafts links to a committed file, and `claims.json` records for each
claim: the source path (and a git ref where the file exists only on an unmerged branch), a literal
quote that must be found in that source, the numbers it vouches for, and the draft phrase it backs.
`scripts/check_launch_claims.py` verifies all of it, and also fails on any number in draft prose that
no claim vouches for and on any repo link (markdown or bare URL; branch or commit permalink) that
does not resolve. Any other repo URL form (tree, raw, commit) fails closed. It fails closed: a missing file, ref
or quote is a failure. Tests: `tests/test_check_launch_claims.py`.

Scope of the check: it proves each quote exists in its source and that drafts contain the phrases and
numbers; it does not prove that the sentence's wording is a fair reading of the quote. That remains a
human review step.

## Claims table

| Claim (short) | Source |
|---|---|
| Harness measures change in task success between two server variants | `README.md` |
| MDE 8.5 pp at 100 tasks/arm, 1 trial/task, 80% power | `README.md` |
| False-alarm rate under 5% in every stratum (1.57% = 11 of 700 null comparisons for fewer than 10 tasks) | `README.md`, `reports/v2_2_few_clusters_correction.md` |
| ICC=0.793 motivates tasks over repeats | `README.md` |
| 21.6% abstention (`insufficient_sensitivity`) under the null: v2.1 estimator, 44 historical tool sets, 2200 null comparisons, before the 100-tasks/arm allocation (not measured at 100 tasks/arm) | `README.md`, `reports/v2_1_estimator_rebuild.md` |
| One lint rule with validated effect: -13.3 to -28.9 pp in 3 model families; two measured nulls | `README.md` |
| Audit gate blocks bad measurements; a scoring bug (-76.7 to -80.0 pp) was corrected to a null | `README.md` |
| Argument degradation: 253 tasks, no practically significant effect | `README.md` |
| Attribution costs 1.01x to 20.24x a full re-eval, gated `--experimental` | `README.md` |
| Pilot: 7 fresh servers with a testable family + 2 anchor servers = 9; 0 of 9 in regime (regime = shipped descriptions fail a contested task and an oracle description recovers it); lower bound | `docs/paper/paper.md`, `STATUS.md` (gw branch) |
| MDE assumes about 100 user-authored tasks | `reports/v2_2_optimal_allocation.md` |
| Argument degradation: llama3.1:8b CI excludes zero at +0.055, below the 0.05 practical threshold | `README.md` |
| `scan` is the legacy v1 surface; `diff` effects are on gemma2:9b, llama3.1:8b, qwen2.5:7b | `README.md` |
| Judge pinned to llama3.1:8b; scores not comparable across judges | `CLAUDE.md` |
| google_workspace: 116 tools, published 0%/0%, truncation at 4096 tokens, rerun 65% (13/20), +0 pp, 4 tasks x 5 trials on gemma2:9b; 7 misses per arm = 5 gws_4 (manage_deployment) + 2 scattered | `STATUS.md`, `docs/paper/paper.md`, `docs/evidence/gw_rerun_check.json` (gw branch) |
| Truncation guard (`OllamaTruncationError`) and `num_ctx` sizing exist only on `fix/ollama-num-ctx`, absent from main | `agentgauge/providers.py` (branch vs main) |

## Left out on purpose (no committed source)

- `agentgauge demo`: not on main.
- That no other committed Ollama result exceeds 4096 tokens: stated only in a commit message of the gw
  branch, not in a committed file.
- Any user, download or star count, any comparison with other tools.

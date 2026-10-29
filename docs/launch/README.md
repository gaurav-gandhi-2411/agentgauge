# Launch copy drafts

Status: **DRAFTS. Nothing here has been posted anywhere.**

| File | Venue | Words (excluding banner and link targets) |
|---|---|---|
| [`show-hn.md`](show-hn.md) | Show HN (title 77 characters) | 349 |
| [`reddit-ml.md`](reddit-ml.md) | r/MachineLearning, flair [P] | 411 |
| [`linkedin.md`](linkedin.md) | LinkedIn | 219 |
| [`blog.md`](blog.md) | Blog post | 638 (body between the BODY markers) |

## Prerequisites before any post

1. **Merge `docs/gw-truncation-correction`** (0524f65, unmerged at the time of writing). Every draft
   describes the corrected google_workspace result (65%/65%, was published as 0%/0%), and its links point
   at the files as they will be on main after that merge. Posting before the merge would present a
   number as changed that main still publishes.
2. Re-run `python scripts/check_launch_claims.py` on the merged main; it must print
   `0 failures`. After the merge the `origin/docs/gw-truncation-correction` refs in `claims.json` can be
   switched to the working tree (remove the `ref` fields).
3. Optional: `fix/ollama-num-ctx` carries the Ollama truncation guard. It is not on main, so
   `blog.md` says it is on a branch. If that branch merges first, rewrite that one sentence and flip the
   `guard-not-on-main` claim.
4. Convert nothing else: links are absolute `github.com/.../blob/main/...` URLs already.
5. Not done here, still needed for a real post: a final read by the author, and the 30-day rule below.

## Timing rule

agentgauge launches **at least 30 days after tracegauge**. These drafts are not to be posted before
then.

## How claims are traced

Every factual sentence in the drafts links to a committed file, and `claims.json` records for each
claim: the source path (and a git ref where the file exists only on an unmerged branch), a literal
quote that must be found in that source, the numbers it vouches for, and the draft phrase it backs.
`scripts/check_launch_claims.py` verifies all of it, and also fails on any number in draft prose that
no claim vouches for and on any repo link that does not resolve. It fails closed: a missing file, ref
or quote is a failure. Tests: `tests/test_check_launch_claims.py`.

Scope of the check: it proves each quote exists in its source and that drafts contain the phrases and
numbers; it does not prove that the sentence's wording is a fair reading of the quote. That remains a
human review step.

## Claims table

| Claim (short) | Source |
|---|---|
| Harness measures change in task success between two server variants | `README.md` |
| MDE 8.5 pp at 100 tasks/arm, 1 trial/task, 80% power | `README.md` |
| False-alarm rate under 5% in every stratum (1.57% for fewer than 10 tasks) | `README.md` |
| ICC=0.793 motivates tasks over repeats | `README.md` |
| 21.6% abstention (`insufficient_sensitivity`) under the null | `README.md` |
| One lint rule with validated effect: -13.3 to -28.9 pp in 3 model families; two measured nulls | `README.md` |
| Audit gate blocks bad measurements; a scoring bug (-76.7 to -80.0 pp) was corrected to a null | `README.md` |
| Argument degradation: 253 tasks, no practically significant effect | `README.md` |
| Attribution costs 1.01x to 20.24x a full re-eval, gated `--experimental` | `README.md` |
| Pilot: 0 of 9 testable servers in regime, lower bound | `docs/paper/paper.md` |
| Judge pinned to llama3.1:8b; scores not comparable across judges | `CLAUDE.md` |
| google_workspace: 116 tools, published 0%/0%, truncation at 4096 tokens, rerun 65% (13/20), +0 pp | `STATUS.md`, `docs/paper/paper.md` (gw branch) |
| Truncation guard exists only on `fix/ollama-num-ctx`, absent from main | `agentgauge/providers.py` (branch vs main) |

## Left out on purpose (no committed source)

- `agentgauge demo`: not on main.
- That no other committed Ollama result exceeds 4096 tokens: stated only in a commit message of the gw
  branch, not in a committed file.
- Any user, download or star count, any comparison with other tools.

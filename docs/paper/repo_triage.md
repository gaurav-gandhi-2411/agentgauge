# Repo triage — 2026-07-11

Post-#54-merge hygiene pass. Scope: safe-set actions (branch deletion for confirmed-merged
lineage, closing one confirmed-stale status-snapshot PR), plus report-only triage for everything
else. §§1-6 below are the original report-and-recommend pass, in which nothing was merged to
`main`. §7 records a follow-up pass that acted on three of those recommendations: merging PR
#40 (its own direct merge), and a STATUS.md fix + CI sync guard (bundled into draft PR #57, not
yet merged — held for review). Nothing under `evals/fixtures/` was touched in either pass; PR
#50 and PR #37 were left open and untouched per explicit protection throughout.

---

## 1. Branches deleted (SAFE SET — confirmed merged before deletion)

Each verified two ways before deletion: (a) `git branch --merged origin/main` listed it, and (b)
`git merge-base --is-ancestor <tip> origin/main` confirmed the branch tip is a real ancestor of
`main`. Deleted with plain `git branch -d` (not `-D`) — git's own safety check independently
agreed each was merged, since `-d` refuses to delete an unmerged branch. Local and remote both
removed.

| Branch | Tip commit | Merged via | Merge commit on `main` |
|---|---|---|---|
| `claude/paper-evidence-prep` | `e3b9ec0` (local) / `d74bf9c` (remote-tracked tip) | PR #54 | `24fe75b` |
| `claude/paper-packaging-pass` | `a4893a9` | PR #55 (into #54's branch, then #54→main) | `d74bf9c`, then `24fe75b` |
| `claude/frozen-protocol-exp4` | `1493791` | PR #52 (auto-resolved merged when #54 landed) | `24fe75b` (contains `1493791`) |
| `claude/exp3-localizer` | `8fadbe0` | PR #53 (auto-resolved merged when #54 landed) | `24fe75b` (contains `8fadbe0`) |

No other branches were deleted — see §6 for other already-merged-but-undeleted branches, reported
but not acted on (out of this task's explicit SAFE SET scope, which named only this lineage).

---

## 2. PR #38 disposition

**Closed**, not deleted-branch (branch `claude/blocker-2026-06-05` left untouched — only the PR
was closed, per the SAFE SET instruction to close-with-comment, not delete).

**Reason:** inspected before acting. Single file changed (`BLOCKER.md`, +29/-0), an
autonomous-loop-generated report dated 2026-06-05 stating the TODO queue in `TASKS.md` was empty
that run. No code, no research result, no unmerged finding. Its own body already flags the board
state as stale ("IN-REVIEW | Ty (PR #36) | Already merged — board needs reconciliation"), and
everything it references (T1-T17, Tx, Ty) is long since superseded by T18, EXP-1/3/4, and the
full paper now on `main`. Meets the exact closing criterion in the task brief: "confirmed to be
an autonomous-loop status snapshot / blocker report and NOT a work product."

Comment posted on close: *"Superseded status snapshot, no unique artifact; closing for
hygiene..."* (full text on the PR).

---

## 3. Triage-only recommendations (no action taken)

### PR #40 — `docs(ty2): clean-harness rerun — parse_failed=0/180, Ty2 floor confirmed real`

**Contents:** re-runs the pre-registered `ty2_tasks.py` fixture (unchanged) on the fixed harness
from PR #39, adding a `parse_failed` diagnostic printed *before* any headroom interpretation.
Result: `parse_failed = 0/180` — the old harness was not silently coercing parse failures to
`{}` and scoring them incorrect. Arm A baseline unchanged at 33.3%. **Conclusion: the earlier
Ty-Run-2 abort was NOT a harness artifact — the 33.3% floor is genuine model behavior.** Files:
`STATUS.md` (+finding), `scripts/run_ty2_oracle_ab.py` (+diagnostic instrumentation, purely
additive).

**Conflict status:** conflicts with `main` in `STATUS.md` only (checked via `git merge-tree`) —
a small, mechanical conflict: the "Current as of" header-date line, plus a clean textual
addition. `scripts/run_ty2_oracle_ab.py`'s diff against the version already on `main` is
purely additive (263 new lines, zero removed, zero collisions) — that file would merge without
any conflict on its own.

**Already captured in `main`?** **No.** `main`'s `STATUS.md` has no mention of this rerun, no
"parse_failed=0/180," and no "harness-artifact hypothesis eliminated" language.

**Recommendation: MERGE, after a two-minute manual resolution of the `STATUS.md` header-line
conflict.** This is a small, valuable, currently-uncaptured finding (it closes a live
confound question — "was Ty2's abort a bug, or real?") with no code risk (the script change is
additive-only). Low effort, real value, no reason to leave it stranded.

### PR #37 — `feat(ty2): guessable-constraints oracle A/B — ABORT (Arm A 36.7%, partial regime unreachable)`

**Contents:** the third and final Ty2 attempt — guessable-but-error-prone constraints
(near-miss enums, RFC3339 formats, ms-magnitude units, required-field presence) on gemma2:9b.
Arm A baseline **36.7%**, below the pre-registered 40% headroom gate → **ABORT, no A/B run**.
Well-instrumented: 25 new CI tests (`tests/test_ty_guessable_fixture.py`), fixture
(`evals/fixtures/ty_guessable_tasks.py`), two example servers (Arm A/oracle), a runner script,
and a `verify.sh`-green report (293 passed, 89.61% coverage) in the PR body. Establishes, across
three progressive attempts (Ty Run 1: 0%, tautological; Ty Run 2: 33.3%, floor; Ty2: 36.7%,
floor), that **the partial-ability regime (40-70%) is unreachable by fixture design on
gemma2:9b for `call_correctness`** — a definitive close on that sub-question, with a named next
step (weaker-agent construct-validity test).

**Naming collision flagged:** PR #40 above also uses "Ty2" to refer to what PR #37's own body
calls "Ty Run 2" (the 33.3% exotic-format/unit attempt) — these are two *different* experiments
(`evals/fixtures/ty2_tasks.py` vs `evals/fixtures/ty_guessable_tasks.py`). Read both PRs' body
text carefully before merging either; do not conflate the two 33.3%-and-36.7% numbers.

**Conflict status:** conflicts with `main` in 3 files (`git merge-tree`: "changed in both" ×3 —
almost certainly `STATUS.md`, `TASKS.md`, `spec.md`, the three "living docs" every research
branch touches and that have since diverged, `spec.md` especially, having been fully rewritten
for the paper). `evals/fixtures/ty_guessable_tasks.py` and the other new files do not exist on
`main` at all — genuinely new, not superseded.

**Already documented in `main`?** **Partially, and misleadingly.** `main`'s `STATUS.md` (L700)
still lists "Guessable-but-error-prone constraints" as a **proposed future test** ("Use
constraints the agent 'knows' but..."), and its Ty summary (L749) only captures the first two
attempts ("unguessable tokens → tautological; format/unit constraints → floor") — it does **not**
record that the guessable-constraints attempt was actually run and aborted at 36.7%, or that the
whole partial-ability-regime question for `call_correctness` on gemma2:9b is now closed.
**`main` currently overstates this as open work when it's actually a completed, aborted line.**

**Recommendation: do NOT merge the branch wholesale** (3-file conflict, and `spec.md` in
particular has diverged too far to auto-resolve safely). **Instead, preserve the finding without
losing provenance:** add a short manual addition to `main`'s `STATUS.md` recording the Ty2
guessable-constraints ABORT (36.7%, three-attempt progression, partial-regime-unreachable
conclusion), citing PR #37 by number and branch name as the source of record for the full
fixture/CI detail — the same "recorded in STATUS.md, full detail lives in the branch" pattern
already used elsewhere in this codebase (e.g. how `evidence_table.md` cites branch-level detail).
Leave PR #37 and its branch open and untouched (as instructed) — it remains the durable,
CI-verified record.

### PR #50 — `feat(frontier-t18): T18 durability on frontier agent — ApiAgentProvider + 3-outcome classifier`

**Contents:** the harness code behind the paper's FRONTIER-T18 result (§4.2.3, +40.8pp on
Llama-3.3-70B) — `agentgauge/frontier.py` (new), `ApiAgentProvider` addition to
`agentgauge/providers.py`, `scripts/run_frontier_t18.py` (new), `tests/test_frontier.py` (new).
This is precisely the gap the paper's own §9.2/§8.5 name explicitly: the FRONTIER-T18 *data* is
committed and independently re-derivable (`evals/fixtures/frontier_t18_step2_result.json` etc.),
but the *harness code that produced it* lives only here, unmerged.

**Conflict status against `main`:** `git merge-tree` reports "changed in both" in 3 files —
`STATUS.md`, `TASKS.md`, `spec.md` (same pattern as PR #37, same root cause: these three files
have moved on since June while this branch hasn't been rebased). Confirmed the four **code**
files are clean: `agentgauge/frontier.py`, `scripts/run_frontier_t18.py`, and
`tests/test_frontier.py` don't exist on `main` at all (no collision possible); the diff to
`agentgauge/providers.py` is purely additive (263 lines, the new `ApiAgentProvider` class, zero
lines removed or changed) — a clean merge of the code itself.

**What a clean merge would require (prep note for a later dedicated task, not attempted now):**
1. Rebase or manually resolve the 3-file docs conflict (`STATUS.md`/`TASKS.md`/`spec.md`) —
   same shape of conflict as PR #37 and PR #40, likely resolvable the same way (take `main`'s
   docs structure, splice in this branch's specific findings/entries).
2. Re-run `./scripts/verify.sh` post-merge to confirm `tests/test_frontier.py` and the existing
   suite both pass together (untested combination since the branch is 30 days stale relative to
   `main`).
3. Confirm no naming/behavior drift in `agentgauge/providers.py`'s `Provider` Protocol between
   what this branch assumes and what's shipped on `main` today (the additive diff suggests none,
   but worth a direct read given a month of intervening changes).

**No recommendation to act now** — flagged as prep for the dedicated follow-up task per the
brief.

---

## 4. Other already-merged-but-undeleted branches (not in this task's SAFE SET — reported only)

These are also confirmed ancestors of `origin/main` (via `git branch -r --merged origin/main`)
but were **not** named in this task's SAFE SET, so they were left alone:

`calib/judge-70b`, `chore/add-ci`, `chore/autonomy-dedup`, `docs/readme-license`,
`feat/t2-error-legibility`, `fix/stdio-python`, `fix/variance-and-calibration`, `t1-runner` —
all dated 2026-05-30/31, from the project's earliest phase. Same deletion logic as §1 would
apply cleanly if you want them gone too.

**Local-only branches** (no remote counterpart — some already merged, some not):
`claude/exp1-prevalence`, `claude/p2a-internal-proxy`, `claude/t17-selection-limited` are
confirmed merged into `main` (their remotes were evidently already deleted in an earlier
cleanup; these are just stale local pointers — safe to `git branch -d` locally, zero risk).
`claude/t18-discoverability-scale` shows as "not an ancestor" by raw commit hash, but its work
**is** on `main` — merged via PR #41 under a different commit shape (verified:
`evals/fixtures/t18_catalog.py` exists on `main`, and PR #41 shows `MERGED` in `gh pr list
--state all`). The local branch is just a stale/divergent pointer, not lost work.
`chore/conditional-automerge`, `chore/fix-operator-policy`, `chore/handoff-docs`,
`chore/queue-render-json-dedup`, `chore/v2-backlog-seed`, `fix/robustness-semantics` are
local-only with no remote backup and did not resolve as ancestors of `main` — **not
individually forensically verified in this pass** (out of today's proportionate scope); flagging
that they're a single-point-of-failure risk (local-disk-only) and recommending either pushing
them to preserve as remote backups or explicitly deciding to discard, rather than leaving them
silently exposed to loss.

---

## 5. Redundant/orphaned file candidates (report only — nothing deleted)

| File | Why it looks redundant | Recommendation |
|---|---|---|
| `docs/paper/skeleton.md` | Explicitly scaffolding-only ("Section headers + one-line intent only — NO PROSE," per its own header). Served its purpose before `paper.md` was written; not cited by `paper.md` itself (confirmed in an earlier scrub pass). | Candidate to archive or delete — the paper it scaffolded is done. Low risk either way; your call. |
| `paper_framing_options.md` (repo root) | The "Framing A vs B" decision it exists to support is resolved — `paper.md` shipped as Framing A, content-final. Still cited (as provenance, not as an open question) by `docs/paper/evidence_table.md`, `skeleton.md`, and `threats_to_validity.md`. | Since it's cited-by-path from reader-facing docs, don't delete outright — but consider whether those citations should become "see git history" instead, letting the file itself be archived. Decide, don't delete, per your framing. |
| `BLOCKER.md` | Does not currently exist on `main` (checked) — the only copy lived in now-closed PR #38. | No action needed; nothing to clean up here, noting for completeness. |
| Local-only branches with no remote backup (§4) | Single point of failure; several look abandoned (dated May 30-31, superseded by the project's later direction). | Push-to-preserve or explicitly discard — listed in §4, not itemized further here. |

**Confirmed correctly excluded, not an issue:** `reports/` (repo root) — contains real files on
disk (`frontier_phase1_research.md`, `frontier_t18_pr_body.md`, etc.) but is properly listed in
`.gitignore` (line 58) and is not tracked by git — exactly as the paper's own Appendix A.5
describes it ("gitignored on every branch"). No cleanup needed.

---

## 6. `paper.md` vs `docs/paper/latex/` sync check

**Both currently load-bearing, and currently in sync.** `paper.md` is the canonical source
(confirmed by `docs/paper/latex/main.tex`'s own build comment: section numbers are "hard-coded
as literal text... exactly as written in `docs/paper/paper.md`"); the `latex/` files are the
arXiv build target, not a duplicate — different audiences (GitHub readers vs. arXiv/PDF), not
redundant copies of the same thing.

**Sync verified directly, not assumed:** the abstract in `paper.md` and
`docs/paper/latex/abstract_body.tex` diff byte-for-byte identical after normalizing
Markdown-em-dash vs. LaTeX-em-dash conventions (only difference was a trailing-newline
artifact of the diff method, not real content). `body_content.tex` was last touched in the same
commit (`cfa95c4`) that last substantively edited `paper.md`'s body sections — nothing has
edited either side since without the other being updated in lockstep across this whole revision
arc (verified by walking the commit history of each edit this session).

**The real risk is process, not current state:** there is no automated check (CI lint, pre-commit
hook, or script) enforcing this sync — it has held only because every edit this session was
manually mirrored to both files as a matching step. Any future edit to `paper.md` that skips the
mirror step will silently desync the two, and nothing will catch it until someone notices the
PDF looks stale.

**Recommendation (decide, don't delete, per the task brief):**
- **Keep dual-maintaining** if a genuinely different LaTeX build (venue `.cls`/`.sty`,
  page-limit reflow) is coming soon — collapsing now just means re-deriving the LaTeX again
  later.
- **Add a lightweight guard** either way: a `scripts/check_paper_latex_sync.py` (or a
  `pre-commit` hook) that fails CI if `paper.md` changes without a matching `docs/paper/latex/`
  change in the same commit, would convert this from "held by discipline" to "held by tooling" —
  worth it once the paper is being revised by more than one contributor, or across a gap long
  enough that the manual-mirror habit could lapse.
- Alternative if you'd rather not maintain the guard script: regenerate `latex/` from `paper.md`
  via pandoc on demand (at each real revision boundary, e.g. pre-submission) instead of keeping
  it hand-mirrored continuously — trades "always in sync" for "sync only recomputed when it
  matters," at the cost of re-reviewing the pandoc output's fidelity to the hand-tuned LaTeX
  conventions each time.

---

## 7. Actions taken (follow-up pass, acting on §3's recommendations)

Three of §3's recommendations were acted on. #37 and #50 were explicitly excluded from action
(protected, per this pass's constraints) — only the STATUS.md *misrepresentation* of #37 was
fixed, not a merge of its branch.

### Action 1 — merged PR #40 (Ty2 clean-harness rerun)

Read both PR #40 and PR #37's full body text first, per instruction, to avoid the naming
collision the original triage flagged: PR #40's "Ty2 fixture" (`evals/fixtures/ty2_tasks.py`,
33.3%) is PR #37's own table's "Ty Run 2" — a *different* experiment from PR #37 itself, which
is the "Ty2-guessable" attempt at 36.7%. Kept these numbers separated throughout.

**Conflict resolution:** the raw `git diff`/merge between the two branch tips was not usable
directly — `claude/ty2-rerun` forked from `main` five weeks earlier, when `STATUS.md` was ~550
lines; `main`'s `STATUS.md` is now 1145+ lines. A line-by-line conflict resolution across that
much drift would have been unreliable. Instead: diffed PR #40's branch against **its own
merge-base** (not against current `main`) to isolate the actual ~25-line delta it introduces,
reset `STATUS.md` to current `main`'s version, and manually spliced in that isolated delta at
the three matching anchor points. One piece of PR #40's own diff was deliberately **not**
applied: a stale `Test suite: 268 tests, 89.61%` count — current `main` already read `432
tests, 90%` at the time (now 710 after this session's changes), so applying the branch's old
number would have been a regression, not a splice.

`agentgauge/scripts/run_ty2_oracle_ab.py`: confirmed zero collisions before merging — the diff
against `main`'s existing copy is purely additive (24 new lines, the `parse_failed` diagnostic
blocks, nothing removed or changed).

**Verification:** `./scripts/verify.sh` run locally post-resolution: **710 passed, 94.79%
coverage, PASSED.** Pushed to `claude/ty2-rerun`, PR #40 marked ready for review, CI
(`verify` + `hygiene`) watched to green on GitHub Actions, then merged (human-reviewed merge
button via `gh pr merge --merge`, no auto-merge).

**Merge commit: `694d09e8592913333e2343cf276a24182465a185`.**

### Action 2 — fixed STATUS.md's misrepresentation of PR #37

**Before** (`main`, pre-fix):
```
**Candidate explanations to test next:**
- *(a) Guessable-but-error-prone constraints:* Use constraints the agent "knows" but
  applies inconsistently — e.g., ISO date formats, HTTP status codes, standard SI units.
  These should land in the 40–70% zone because the agent has partial exposure but not
  perfect recall. Requires pre-registration and inferability guard.
- *(b) Weaker runner agent:* ...
...
  Which fork to take (another Ty attempt via (a) vs. weaker-agent pivot (b) vs. write the
  meta-finding as the deliverable) is a design decision — tracked as open in TASKS.md.
```
and, in the cross-experiment table:
```
| Ty (call construction) | calls | **inconclusive** — ABORTED all runs | unguessable tokens → tautological; format/unit constraints → floor |
```

**After:** bullet (a) rewritten in past tense as **TESTED, ABORTED (Ty2, PR #37, branch
`claude/ty2-guessable-constraints`, 2026-06-05)**, recording: the constraint types tried
(near-miss enums, RFC3339 formats, ms-magnitude units, required-field presence), the **36.7%**
Arm A result against the 40% gate, the full three-attempt progression (Run 1: 0%, tautological;
Run 2: 33.3%, floor, clean-harness-confirmed by #40 above; Ty2-guessable: 36.7%, floor), the
closing conclusion (**the 40-70% partial-ability window is unreachable by fixture design on
gemma2:9b for `call_correctness`**), and a citation to PR #37 + its branch as the source of
record for the full fixture (`evals/fixtures/ty_guessable_tasks.py`) and CI detail (25 tests).
The closing "which fork to take" sentence now reads: *"With (a) now closed..., the only
remaining fork is (b) weaker-agent pivot vs. writing the meta-finding as the deliverable."* The
cross-experiment table row now reads *"**inconclusive** — ABORTED all 3 runs | ...
guessable-but-error-prone (Ty2, PR #37) → floor (36.7%) — partial-ability window unreachable by
fixture design."*

PR #37 and branch `claude/ty2-guessable-constraints`: confirmed still open, untouched — this
was a documentation-only fix on `main`, not a merge.

Commit: `cffd780` on branch `chore/status-fix-and-sync-guard` (draft PR #57, unmerged, held for
review).

### Action 3 — paper.md ↔ latex sync guard

Added `scripts/check_paper_latex_sync.py`: walks each non-merge commit in a given range,
flags any commit that touches `docs/paper/paper.md` without also touching something under
`docs/paper/latex/`. Deliberately a git-diff-only check — no Markdown/LaTeX parsing, no
content-equivalence claim, per the "lightweight" instruction.

**Tested against real history before wiring into CI:**
- `93d2efd..cfa95c4` → correctly **flagged** `65ac284` (the draft-banner-removal commit, which
  predates the `latex/` mirror's existence) as a real violation.
- `e3b9ec0..a4893a9` (the full abstract-precision-fix arc from this session) → **passed clean**,
  confirming every `paper.md` edit in that arc was correctly co-committed with its `latex/`
  counterpart.

**CI wiring:** added as a new step inside the existing `hygiene` job in
`.github/workflows/ci.yml`, reusing that job's already-computed commit range (`origin/main..HEAD`
for PRs, `before..sha` for pushes to `main`) rather than recomputing it. Verified live on GitHub
Actions via draft PR #57: both `verify` and `hygiene` (including the new sync-guard step) passed.

**Docs:** one line added to `docs/paper/latex/README.md` pointing at the guard and what it
enforces.

Commit: `2fdf64f` on branch `chore/status-fix-and-sync-guard` (draft PR #57, unmerged, held for
review — same PR as Action 2, per the task's bundling instruction).

### Summary of state after this pass

| Item | Status |
|---|---|
| PR #40 | **Merged to `main`** (`694d09e`) |
| STATUS.md #37 fix | Committed on draft PR #57, **awaiting your review/merge** |
| Sync guard (script + CI + README) | Committed on draft PR #57, **awaiting your review/merge** |
| PR #37 (branch + PR) | Open, untouched |
| PR #50 (branch + PR) | Open, untouched |
| `evals/fixtures/*` | Untouched throughout |
| `skeleton.md`, `paper_framing_options.md` | Not deleted, as instructed |

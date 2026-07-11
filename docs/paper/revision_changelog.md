# Revision changelog — packaging pass

Scope: readability and leak-removal only, per the packaging-pass brief. No number, result,
p-value, sample size, verdict, or scientific claim was changed. Every edit is
phrasing/placement/length only; every claim below is claim-equivalent to its original.

Source of truth: `docs/paper/paper.md`. The LaTeX mirror
(`docs/paper/latex/abstract_body.tex`, `docs/paper/latex/body_content.tex`) was resynced to
match and `main.pdf` recompiled with tectonic.

---

## 1. Abstract

**Word count: 592 words (before) -> 228 words (after).** Ceiling was 230; target was ~200.
(An intermediate 222-word draft conflated the density-effect and generation-safety findings into
one "when X and Y" clause; the verifier flagged this as risking a reader coming away thinking
they were tested jointly, when the body is emphatic they are two distinct conditions from
different experiments — §1.3, §7.1, §10. Fixed by splitting into two clauses, +6 words, still
under the 230 ceiling.)

**Before** (opening and structure — full original text preserved in git history at
`93d2efd:docs/paper/paper.md`): opened on "Tool-description quality is widely treated as a
broadly-applicable, improvable lever..." and ran ~592 words restating, in sequence: the central
finding, the density-bracket caveat (60/10 vs 16/8, "bracketed not measured"), the
capability-survival caveat ("not directly comparable... different harness"), the generation
result (12.5% recovery), all four out-of-regime findings individually, the 0-of-9 prevalence
result with its full scope caveat, the localizer's binary-and-graded framing detail, and the
false-negative-asymmetry pointer (§8.3.1) — essentially a compressed version of the entire
paper's caveat structure, all in one paragraph.

**After** (full text):

> Tool-description quality is widely treated as a broadly-applicable lever for agent tool-use,
> but it is not a single better/worse axis: the precision that helps an agent disambiguate
> within a family of confusable tools is orthogonal to, or actively harmful for, context-rich
> selection and for tool retrieval. We test this with a single frozen evaluation protocol — one
> classifier, one judge, one generator family, pre-registered thresholds — across a synthetic
> confusable-catalog experiment, two real production MCP-server mirrors (GitHub, AWS IAM), a
> synthetic internal-proxy catalog, and a pre-registered pilot of ten public Python MCP servers.
> The effect is real but regime-bounded, not a general law: a hand-written oracle description
> helps at one tested catalog density (60 tools/10 families, +34.5pp on gemma2:9b, surviving at
> +40.8pp on Llama-3.3-70B) when the agent lacks headroom; realizing it safely through automatic
> generation is a separate condition, requiring documented source. Outside these conditions the
> effect is null or reverses (zero headroom on two well-documented production servers; −20pp
> harm on one already-resolved family; harm to retrieval across three retriever types).
> Contributions: a falsifiable regime map of where description quality helps, harms, or does
> nothing; a pre-registered prevalence measurement finding this regime in 0 of 9 testable Python
> MCP servers — a lower bound, not a population estimate; and a localizability boundary — a
> pairwise LLM-judge confusability method fails under two independent framings, via two distinct
> failure mechanisms.

Structure: (a) one confident sentence stating the central finding before any hedge, (b) scope
(frozen protocol; synthetic + 2 real MCP mirrors + N=10 Python pilot; "regime-bounded, not a
general law"), (c) the three contributions (regime map, 0/9 prevalence, localizer-fails
boundary).

Detail dropped from the abstract for length (all still stated in full in their home sections,
unchanged): the exact 16-tool/8-cluster untested bracket and "not directly comparable in
magnitude" harness caveat (§4.2.1, §4.2.3); the 12.5% interface-only generation-recovery figure
(§4.2.2); the per-family breakdown of which already-resolved families show no harm (§4.3.2); the
binary-vs-graded localizer framing detail (§6.3–6.4); the explicit §8.3.1 pointer (the caveat
itself is unchanged and still opens Section 8).

---

## 2. De-hedging — repeated caveats consolidated to one home + optional abstract mention

Two caveats were restated at up to 5-7 locations across the paper (abstract, intro, §1.3
contributions, §4.4 synthesis, §7.1 discussion, §10 conclusion). Each is now stated in full
exactly once, in its home section, with all other locations trimmed to a short `(§X.Y)`
back-reference. No instance of either caveat was removed from the paper — every one still
appears, in full, in its home section, unchanged:

| Caveat | Home (unchanged, full statement) | Trimmed to back-reference |
|---|---|---|
| Density-bracket: oracle effect tested+positive at 60-tool/10-family, untested (not disproven) at 16-tool/8-cluster, threshold unmeasured | §4.2.1 | §1.3 (contribution bullet), §4.4 (synthesis diagram), §7.1 (discussion), §10 (conclusion) |
| EXP-1's 0-of-9 result uses the general behavioral regime construct, not a re-test of the 60-tool density point specifically | §5.1 | §1.3 (contribution bullet), §7.1 (discussion), §10 (conclusion) |

"Not a general law" / "not a demonstrated general law about description quality": already at
exactly 2 locations before this pass (abstract, §1.1 intro thesis statement) — within budget,
no edit needed.

§8 (Threats to Validity) was left untouched by this de-hedging pass — it is the paper's
designated, dedicated limitations catalog (per its own §8 preamble: "every item there traces to
a specific finding already reported in Sections 4-6, not a hedge added at write-up time"), not a
redundant restatement site. Sections 5.2 (sampling frame) and 5.5 (Scope) were likewise left
untouched — they are Section 5's own dedicated method/scope subsections, not duplicates of each
other.

---

## 3. §8.3.1 — reframed as a bound, not a confession

Substance is 100% unchanged: both false positives (Section 5.4), the mirror-image blind-spot
mechanism, "we have not found evidence of such a bug; we also have no mechanism that would
necessarily surface one," and the recalibration instruction to the reader are all still present,
verbatim, in the same paragraph.

**Before (heading + opening):**
> ### 8.3.1 The false-negative asymmetry (read this one first)
>
> **This paper's positive findings were caught being wrong; its negative findings have no
> analogous check.** Section 5.4 reports two false positives from a seed-configuration bug...
> [...] This asymmetry means EXP-1's 0-of-9 headline, and EXP-3's localizer-fails headline,
> carry a category of risk that this paper's own error-detection track record does not bound.

**After (heading + opening):**
> ### 8.3.1 The false-negative asymmetry — the epistemic bound on this paper's null claims (read this one first)
>
> **Every null and boundary claim in this paper — EXP-1's 0-of-9 headline, EXP-3's
> localizer-fails headline — is bounded by one asymmetry in what this pipeline's error-detection
> can catch, and this section states that bound precisely.** Section 5.4 reports two false
> positives from a seed-configuration bug... [...] this is the bound this paper's nulls should be
> read against, not a suggestion that they are unreliable.

Change: the sentence naming EXP-1/EXP-3's exposure was moved into the opening topic sentence
(so it reads as the section's stated purpose rather than a mid-paragraph aside), and one clause
was added ("not a suggestion that they are unreliable") to make the bound-not-confession framing
explicit. Nothing was deleted.

---

## 4. Fourth-wall / internal-process leaks removed

**Grep results, `docs/paper/paper.md`, after all edits** (pattern:
`GG|compression request|ANTHROPIC_API_KEY|this session`): **zero matches.**

Same grep against `docs/paper/latex/abstract_body.tex` and `docs/paper/latex/body_content.tex`:
**zero matches.**

Edits:
- **A.6** — removed "per GG's compression request" parenthetical; appendix content (the
  five-revision sampling-frame history) unchanged.
- **A.7** — removed "per GG's compression request" parenthetical; appendix content (the
  four-stage Q3-Q6 progression table) unchanged.
- **§3.1** — `ANTHROPIC_API_KEY` is never used in any experiment reported here, to keep
  judge/generator/agent model families structurally independent of the assistant used to run
  the research program.
  -> Judge, generator, and agent model families are structurally independent of any assistant
  used to author or orchestrate this research program — no shared credentials, infrastructure,
  or model family.
  (Independence guarantee preserved; the literal key name removed.)
- **"this session" (7 occurrences in `paper.md` + 1 line-wrap-split instance the literal
  replace-all initially missed, §1.1 citation parentheticals + Appendix A.5 bibliography notes;
  8 separate occurrences in the LaTeX mirror `body_content.tex`)** — normalized to "during this
  paper's preparation" for consistency with the phrasing already used elsewhere in the same
  appendix (e.g. §9.2, §8.5).
- **`docs/paper/latex/main.tex`** (build-preamble comment, not paper prose) — "once GG picks
  one" -> "once one is picked." Flagged by the executor as outside the 11-edit mirror scope
  (it's a LaTeX build comment, not mirrored reader-facing text); fixed anyway since it's a
  one-line, zero-risk match to the same leak-removal intent.

No other leak patterns found (no TODO/FIXME, no other author initials, no internal-process
phrasing beyond the above; `reports/frontier_phase1_research.md` and `STATUS.md` references in
the bibliography section are legitimate provenance/reproducibility pointers, not fourth-wall
breaks, and were left as-is).

---

## 5. Final coherence pass

One full top-to-bottom read after edits 1-4. No dangling back-references or broken transitions
found; every trimmed `(§X.Y)` reference resolves to a section that still carries the full
caveat. No further content changes were made.

---

## 6. LaTeX mirror + PDF

`docs/paper/latex/abstract_body.tex` and `docs/paper/latex/body_content.tex` were manually
patched at the corresponding 11 locations (not regenerated via pandoc, to avoid re-reviewing
~1,325 unrelated lines). `main.pdf` recompiled with tectonic — no errors, only pre-existing
cosmetic hbox warnings unrelated to this pass. Recompiled a second time after the post-verifier
abstract disambiguation fix (§1 above); same clean result.

---

## 7. Docs scrub — reproducibility/threats/evidence trail

Follow-up pass: the paper's leak-free bar (§4 above) extended to every file the paper cites by
path as part of its reproducibility, threats, and evidence trail — "the published surface" is
the paper plus what it points a reader to, not just `paper.md` itself. No number, path, hash,
verdict, or governance rule was altered in this pass — only author-name and internal-process
phrasing.

**Which files the paper actually cites by path** (checked before editing, per task instruction):

| File | Cited by `paper.md`? | Where |
|---|---|---|
| `docs/paper/threats_to_validity.md` | Yes | §8 preamble ("Full list: ...") |
| `docs/paper/evidence_table.md` | Yes | §9.1, A.1, A.3, A.6, A.7 |
| `docs/paper/skeleton.md` | **No** | not referenced — scaffolding artifact, scrubbed as a precaution per task instruction regardless |
| `docs/research/frozen_protocol.md` | Yes | §3 intro, A.3 |
| `docs/research/exp3_pre_registration.md` | Yes | A.2 |
| `docs/research/exp4_regime_map.md` | Yes | A.1, A.7 |

The last three (`docs/research/...`) were not in the original named task list but meet the
task's own stated criterion — cited by path, part of the reproducibility trail — so they were
scrubbed under the same rule, decision made and logged here rather than silently expanding
scope.

### Before -> after, per file

**`docs/paper/skeleton.md`** (not cited, scrubbed as precaution):
- L9: "...is DROPPED — ratified by GG, see `spec.md`." -> "...is DROPPED — ratified, see `spec.md`."
- L84: "6.4 GG-ratified graded-confidence retry..." -> "6.4 Ratified graded-confidence retry..."

**`docs/paper/evidence_table.md`** (cited, reader-facing):
- L3: "Compiled while awaiting GG's Framing A vs B decision" -> "Compiled while awaiting the Framing A vs B decision"
- L68: "**RESOLVED (this session, GG-directed).**" -> "**RESOLVED (during this paper's preparation).**"
- L108: "**Precision note for drafting (FIXED, GG-directed):**" -> "**Precision note for drafting (FIXED):**"

**`docs/paper/threats_to_validity.md`** (cited, reader-facing):
- L50-53: "...is DROPPED — ratified by GG (`spec.md` EXP-2 section, `0c78f49`) — because the
  underlying regime this session could verify is already rare..." -> "...is DROPPED — ratified
  (`spec.md` EXP-2 section, `0c78f49`) — because the underlying regime this paper's preparation
  could verify is already rare..."

**`docs/research/frozen_protocol.md`** (cited, reader-facing):
- "`ANTHROPIC_API_KEY` must **never** be set or used in any experiment." -> "No assistant-vendor
  credentials (e.g. coding-assistant API keys) may be set or used in any experiment —
  judge/generator/agent model families stay structurally independent of the tooling used to run
  the research program." (Rule strengthened/clarified, not weakened: same never-use constraint,
  generalized past one specific vendor's key name, plus the independence rationale made
  explicit.)
- "escalate to GG before executing" -> "escalate to the author before executing" (the
  human-review gate itself — DRAFT PR + escalation for any judge/scorer/rubric change — is
  unchanged; only the name is gone.)

**`docs/research/exp3_pre_registration.md`** (cited, reader-facing):
- "escalated to GG before merge" (condition #1 notice) -> "escalated to the author before merge"
- "**Ratified by GG:**" -> "**Ratified:**"
- "other option GG offered" -> "other option considered"
- "escalated to GG before merge" (§8 Governance) -> "escalated to the author before merge"
- "`ANTHROPIC_API_KEY` is never set." -> "No assistant-vendor credentials are set or used."

**`docs/research/exp4_regime_map.md`** (cited, reader-facing):
- "condition #1, escalated to GG" -> "condition #1, escalated to the author"
- "**GG-ratified graded-confidence retry...**" -> "**Ratified graded-confidence retry...**"
- "## Paper Claim Inventory (for GG ratification...)" -> "## Paper Claim Inventory (for author ratification...)"
- "GG ratifies all external framing" -> "The author ratifies all external framing"

### Full `docs/` tree grep, every hit — fixed or left, with reason

Pattern: `GG|compression request|ANTHROPIC_API_KEY|TODO|FIXME` (author-initials check folded
into the `GG` pattern; `TODO`/`FIXME` also swept).

| File:line | Hit | Status | Reason |
|---|---|---|---|
| `docs/paper/skeleton.md:9,84` | `GG` | **Fixed** | listed above |
| `docs/paper/evidence_table.md:3,68,108` | `GG` | **Fixed** | listed above |
| `docs/paper/threats_to_validity.md:52` | `GG` | **Fixed** | listed above |
| `docs/research/frozen_protocol.md:21,22` | `ANTHROPIC_API_KEY`, `GG` | **Fixed** | listed above |
| `docs/research/exp3_pre_registration.md:12,188,199,261,264` | `GG`, `ANTHROPIC_API_KEY` | **Fixed** | listed above |
| `docs/research/exp4_regime_map.md:197,207,282,284` | `GG` | **Fixed** | listed above |
| `docs/research/frontier_t18_result.md:46` | `ANTHROPIC_API_KEY` (in "no ANTHROPIC_API_KEY used anywhere") | **Left** | not cited by path anywhere in `paper.md` (confirmed by grep) — not part of the published surface as scoped by this task; also not a leak in the security sense, a factual negative-use statement in an internal-only doc |
| `docs/paper/revision_changelog.md:127,133,135,137,149,154` | `GG`, `compression request`, `ANTHROPIC_API_KEY` | **Left** | this changelog's own job is to document what was removed and where — quoting the removed strings is the historical record, not a leak; the file is a process artifact, not cited by `paper.md`, not part of the published surface |

No `TODO`/`FIXME` hits anywhere in `docs/`. No other author-initial patterns found beyond `GG`.

**Boundary note, not fixed (out of the stated `docs/` scope, flagged for awareness):**
`STATUS.md` is cited by path four times in `paper.md` (§8 A.4, A.6, A.7 — "Full narrative:
`STATUS.md` ... section") and, as the project's main execution tracker, almost certainly
contains extensive `GG` references — but it lives at the repo root, not under `docs/`, so it
falls outside this task's explicitly stated grep scope ("the ENTIRE docs/ tree"). Flagging the
gap rather than silently expanding scope to a large, actively-used operational file without
being asked.

`docs/research/phase1-buyer-and-landscape.md` (cited once, §2.3/related-work sourcing) was
checked and has zero hits on any pattern — no action needed.

### Verification

`grep -n "\bGG\b" docs/paper/skeleton.md docs/paper/evidence_table.md
docs/paper/threats_to_validity.md docs/research/frozen_protocol.md
docs/research/exp3_pre_registration.md docs/research/exp4_regime_map.md` -> zero matches, all
six files. `grep -n "ANTHROPIC_API_KEY" docs/research/frozen_protocol.md
docs/research/exp3_pre_registration.md` -> zero matches. Independently re-run after the edits,
not just taken from the executor's report.

---

## 8. STATUS.md scrub + final full-repo sweep

### Cite-site check (task instruction: verify before editing)

`STATUS.md` is cited by path **3 times** in `docs/paper/paper.md` (not 4 — the prior turn's
report over-counted; corrected here):

| Line | Citation |
|---|---|
| 771 | A.4: "Per-server EXP-1 table: Section 5.3 above (reproduced from `STATUS.md` EXP-1 section)." |
| 857 | A.6: "Full commit-level trail: `STATUS.md` EXP-1 section, 'Frame history' paragraph; ratification..." |
| 882 | A.7: "Full narrative: `docs/research/exp4_regime_map.md` §Regime 2; `STATUS.md` Q3/Q4/Q5/Q6 sections..." |

All three are path/section pointers, not references to specific line content — the scrub below
doesn't require any corresponding edit in `paper.md` itself.

### Pre-edit grep of STATUS.md (reported before editing, per task instruction)

`\bGG\b`: **10 hits** — lines 7, 51, 67, 77, 90, 93, 152, 227, 301, 331.
`ANTHROPIC_API_KEY` / vendor-credential rule phrasing: **0 hits** — no such rule stated in this
file, nothing to generalize.
`compression request`: **0 hits**.
`TODO`/`FIXME`: **3 hits** (lines 1114, 1125, 1127) — all part of the phrase "`TASKS.md` TODO
queue" / "highest-priority TODO from `TASKS.md`", describing the project's real automated
work-queue mechanism, not a leftover code-comment marker. **Left as-is** — not a leak, and the
task scope is "GG / author-initials / internal-process phrasing / ANTHROPIC_API_KEY", not
general TODO markers describing an actual system.

### Before -> after (all 10 `GG` hits, author-initial -> "the author", governance gates preserved)

| Line | Before | After |
|---|---|---|
| 7 | "...condition #1, escalated to GG)" | "...condition #1, escalated to the author)" |
| 51 | "**GG-ratified retry (graded confidence...**" | "**Ratified retry (graded confidence...**" |
| 67 | "hard stop per GG's pre-registered instruction" | "hard stop per the author's pre-registered instruction" |
| 77 | "...DRAFT PR #53, escalated to GG for review before merge." | "...DRAFT PR #53, escalated to the author for review before merge." |
| 90 | "held pending GG's scope decision" | "held pending the author's scope decision" |
| 93 | "**Frame history (5 rebuilds, each re-escalated to GG, none silent):**" | "**Frame history (5 rebuilds, each re-escalated to the author, none silent):**" |
| 152 | "**Scope decision — RATIFIED by GG, 2026-07-04:**" | "**Scope decision — RATIFIED, 2026-07-04:**" |
| 227 | "**ESCALATION TO GG — F2 direction decision...**" | "**ESCALATION TO THE AUTHOR — F2 direction decision...**" |
| 301 | "**CONSOLIDATED P2-A + F2 PICTURE FOR GG...**" | "**CONSOLIDATED P2-A + F2 PICTURE FOR THE AUTHOR...**" |
| 331 | "Bringing to GG as a consolidated direction escalation." | "Bringing to the author as a consolidated direction escalation." |

Every edit is a name substitution only — the escalation/ratification gate itself (a real
human-review checkpoint before merge/scope decisions) is stated identically before and after.
File line count unchanged (1145 -> 1145): pure in-place substitution, nothing reformatted or
restructured.

### Post-edit verification (independently re-run, not taken from the executor's report alone)

`grep -n "\bGG\b" STATUS.md` -> **zero matches**. `grep -n "ANTHROPIC_API_KEY|compression
request" STATUS.md` -> **zero matches**.

### Final full-repo sweep (tracked files, `git grep -n -E "\bGG\b|compression request|ANTHROPIC_API_KEY"`)

Beyond `STATUS.md` (now clean) and this changelog (intentional — see §7), the sweep surfaces
hits in six other locations. None were edited. Each is reported with its disposition and reason:

| Location | Hits | Disposition | Reason |
|---|---|---|---|
| `evals/fixtures/exp1_exclusion_log.json`, `exp1_pre_registration.json`, `exp1_server_frame.json`, `p2a_f2_retrieval_spec.json` | ~20 `GG` refs across the four files | **Left — must not touch** | These are pre-registered fixture files. The frozen protocol this paper documents (§3.2, and `docs/research/frozen_protocol.md`) states fixture contents are "never edited after results are in hand" as a core integrity rule. Editing them post-hoc — even just to remove a name — would violate the exact governance this packaging pass is protecting, and would invalidate their pre-registration timestamps. Also not cited by path from `paper.md` (only the two hash-pinned `frontier_t18_step2_*.json` files are cited, at §9.2 — checked directly, zero `GG` hits in those two) — so not part of the published surface either. Two independent reasons to leave untouched. |
| `TASKS.md` | 7 `GG` refs (lines 33, 36, 40, 44, 52, 70, 75, 85, 107, 109, 123 — governance/escalation task-queue notes) | **Left** | Not cited by path anywhere in `paper.md` — an internal operational task tracker, not part of the published surface. |
| `agentgauge/exp1_doc_density.py:8` | 1 `GG` ref (code comment: "GG's correction (2026-07-02)...") | **Left** | Source code comment, not cited by `paper.md`, not reader-facing documentation. |
| `scripts/exp1_discover_registry.py:5`, `scripts/exp1_discover_servers.py:4,170` | 3 `GG` refs (code comments) | **Left** | Same — source code, not cited, not published surface. |
| `spec.md` | 4 `GG` refs (lines 48, 64, 71, 91 — the paper-rewrite planning doc discussed in the earlier commit `65ac284`) | **Left** | Checked: not cited by path anywhere in `paper.md`. An internal planning/process document, not part of the reproducibility trail a reader is pointed to. |
| `docs/research/frontier_t18_result.md:46` | 1 `ANTHROPIC_API_KEY` ref ("no ANTHROPIC_API_KEY used anywhere") | **Left** (already reported in §7) | Not cited by path in `paper.md`; a factual negative-use statement, not a leak. |

**Scope boundary stated plainly:** this task's mandate was "STATUS.md, tightly scoped." The
full-repo sweep above is a reporting/audit pass, not a mandate to scrub the whole repository —
consistent with the published-surface principle used throughout §§4/7/8 (paper + everything it
cites by path). Nothing outside that boundary was touched. If the codebase comments or `spec.md`
/`TASKS.md` need the same treatment, that's a separate decision — flagging rather than acting
unilaterally, per the same discipline applied to the `STATUS.md` citation gap noted in §7.

---

## 9. Abstract precision fixes

Two one-line accuracy fixes to the abstract only (`docs/paper/paper.md` and the LaTeX mirror
`docs/paper/latex/abstract_body.tex`). No result, claim, or scope changed — both fixes correct
which finding a phrase refers to, or remove a non-comparable figure the body itself forbids
presenting as a direct comparison.

### Fix 1 — "this regime" incorrectly bound to the density regime

**Verified against §5.1 before editing:** "**This is the general behavioral construct, not a
re-test of Section 4.2.1's specific density point.**" (`paper.md` L437-438) — §5.1 explicitly
warns against exactly the misreading "this regime" invited in the abstract (binding EXP-1's
0-of-9 result to the §4.2.1 density regime rather than the general two-condition behavioral
regime it actually measures). The fix is supported by the paper's own text, not a new claim.

**Before:** "...a pre-registered prevalence measurement finding **this regime** in 0 of 9
testable Python MCP servers — a lower bound, not a population estimate..."

**After:** "...a pre-registered prevalence measurement finding **the behavioral regime** in 0 of
9 testable Python MCP servers — a lower bound, not a population estimate..."

### Fix 2 — +40.8pp figure removed from adjacency with +34.5pp

§3.5 states the two figures are "explicitly **not** part of a single controlled ladder... and
are never combined into a claim that the effect 'grows with capability,' only that it
'survives'"; §4.2.3 frames FRONTIER-T18 as "a survival claim, not a growth claim." Showing both
numbers side-by-side in the abstract's compressed form risked exactly the growth/comparison
reading both sections forbid. The survival claim stays in the abstract; the non-comparable
number is dropped, matching the guidance to state the qualitative result ("does not collapse")
rather than the two magnitudes together.

**Before:** "...a hand-written oracle description helps at one tested catalog density (60
tools/10 families, +34.5pp on gemma2:9b, **surviving at +40.8pp on Llama-3.3-70B**) when the
agent lacks headroom; realizing it safely through automatic generation is a separate condition,
requiring documented source."

**After:** "...an oracle description helps at one tested catalog density (60 tools/10 families,
+34.5pp on gemma2:9b, **and not collapsing on a substantially stronger model, Llama-3.3-70B**)
with no headroom; realizing it safely through automatic generation is a separate condition,
requiring documented source."

("hand-written oracle description" was also trimmed to "oracle description" — a length-only cut
to stay under the word ceiling after fix 2 added net words; "oracle" is already the paper's
defined term for hand-written ground-truth descriptions, used interchangeably with the full
phrase throughout the body, e.g. §4.2.1's own heading and running text. "when the agent lacks
headroom" was tightened to "with no headroom" for the same reason — both phrasings state the
identical fact using the paper's own term, "headroom," defined in §3.2.)

### Word count

**228 words (before this task's two fixes) -> 230 words (after).** At the ceiling, not over it.
The two requested fixes added net words (+1 for fix 1, +3 for fix 2's literal requested text);
two additional length-only trims within the same two edited clauses — dropping "hand-written"
and tightening "when the agent lacks headroom" to "with no headroom" — brought the total back
under the ceiling without touching any other sentence or any claim.

### Verification

- `paper.md` and `abstract_body.tex` abstracts diffed word-for-word after normalizing
  Markdown-em-dash (`—`) vs LaTeX-em-dash (`---`) conventions: **identical**.
- `main.pdf` recompiled with tectonic: clean, only the same pre-existing cosmetic underfull/
  overfull-hbox warnings present before this change (unrelated to content).
- Nothing outside the abstract paragraph was touched in either file.

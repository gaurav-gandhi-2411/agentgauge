# AgentGauge v0.4.0 — Task 3: docs/paper/ audit for the argument-degradation thesis

Grepped every paper source file (`docs/paper/paper.md`, `docs/paper/latex/{abstract_body,body_content,main}.tex`,
`docs/paper/evidence_table.md`, `docs/paper/threats_to_validity.md`,
`docs/paper/skeleton.md`) for `degrad`, `blind spot`, `argument.constr`,
`argument accuracy`, `hurt`, `harm`, `worsen`, `catches what`, `other
tools`, `only tool`, and a bare `\bargument\b` sweep to catch any casual
mention outside the narrower phrases.

## Finding: the paper's claims are scoped to selection/retrieval, not argument construction — confirmed in writing, nothing changed

**The paper never discusses argument construction, argument accuracy, or
tool-call argument correctness at all.** The `\bargument\b` sweep returns
exactly one hit, `paper.md:278` — "the two endpoints carry the argument" —
ordinary English for "support the reasoning," not a reference to tool-call
arguments. The paper's entire "helps / does nothing / backfires" thesis
(title: *"Tool-Description Quality Is Not One Axis: A Regime Analysis of
Where It Helps and Where It Backfires"*) is scoped to two mechanisms,
neither of which is argument construction:

1. **Tool selection** — disambiguation within a family of confusable tools
   (`paper.md:9`, `:34`), including the P2-A `account_query` harm case
   (`paper.md:339-356`, `-20pp`, reproduced under two generation strategies)
   and the EXP-1/jupyter-mcp-server replication (`paper.md:468`, `-15pp`).
2. **Tool retrieval** — whether a better description helps or hurts a
   retriever (BM25/TF-IDF/embedding) surface the right tool from a larger
   catalog (`paper.md:373-378`, F2 study, harm across all three retriever
   types tested).

Every "harm"/"degrade" hit found (dozens, across both `.md` and `.tex`
sources — full list available via the grep command above) traces to one of
these two mechanisms, always with the paper's own stated regime-boundedness
caveat ("The effect is real but regime-bounded, not a general law," `paper.md:12-13`
and `abstract_body.tex:4-19`) — never a general "descriptions degrade
success" claim, and never about argument construction specifically. This is
a **genuinely different research question** from what v0.4.0's live
measurement (253 tasks, 3 models, argument-construction accuracy) resolved
as a null — the two findings do not overlap, contradict, or need
reconciling with each other.

## "Blind spot" — one hit, unrelated to the flagged marketing pattern

`paper.md:652` / `body_content.tex:946`: *"That same mechanism has a
mirror-image blind spot: a bug that instead silently suppressed a real
in-regime signal — turning a true positive into a false null — would
produce a result indistinguishable from a correctly-measured null."* This
is `§8.3.1`, "The false-negative asymmetry" — the paper's own
**threats-to-validity self-criticism** about a possible undetected flaw in
its *own* measurement pipeline, disclosed as an epistemic bound on its
*null* claims (EXP-1's 0-of-9, EXP-3's localizer-fails headline). It is the
literal opposite of the flagged pattern ("AgentGauge detects a blind spot
other tools miss") — it is the paper disclosing a blind spot in *its own*
method, not claiming to catch one others miss. No correction needed; this
is exemplary of the honest-methodology standard this whole project holds
itself to, not an instance of the overclaim being audited for.

## Conclusion

**Confirmed in writing per this task's own instruction: the paper's claims
are scoped to tool-selection and tool-retrieval regime-boundedness only.
Nothing in `docs/paper/` needed changing.** No file was edited.

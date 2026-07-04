# spec.md — PAPER: "When Does Tool-Description Quality Actually Improve Agent Behavior? A Regime Analysis"

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** current main · target: arXiv + workshop.
**Routing:** research program, multiple DRAFT PRs, all human-merged. Condition-#1 (judge/scorer/
rubric/calibration) changes — the localization method touches the judge — stay DRAFT + escalated.
generator != judge != agent preserved. Never set ANTHROPIC_API_KEY.

**Thesis:** the negative/boundary results ARE the contribution — a falsifiable, regime-bounded map of
WHERE tool-description quality changes agent behavior and where it does not. Every claim scoped to its
evidence; the RW no-headroom finding and the strong +40.8pp survival finding are BOTH reported (they
are about different regimes, not in tension).

---

## FROZEN EVALUATION PROTOCOL (the paper's credibility backbone — define ONCE, reuse everywhere)
Reviewer risk #1 is uncontrolled cross-condition comparisons. Mitigation: a single pre-registered
protocol every experiment runs through.
- ONE classifier: the existing 3-outcome (SELECTED-CORRECT / SELECTED-WRONG / ABSTAINED-OR-HEDGED) +
  parse_failed, reported separately, ALWAYS.
- ONE judge (frozen model + version + seed) for any judged metric; ONE generator family for oracle/
  Guard-B; the AGENT is the variable only where the experiment says so.
- Pre-registration: spec committed at each experiment's branch start; metric/fixture/threshold never
  edited after results; null/abort first-class; never tune to a positive.
- Effect = Arm B(oracle) − Arm A on parse-success contested tasks; task-clustered sign test; report N,
  power, and stability (flippers across trials excluded from the stable-set analysis).
- Commit seeds, model strings/versions, fixture hashes for every run.

---

## EXP 1 — SERVER-POPULATION PREVALENCE (the headline empirical contribution)

**Question:** what FRACTION of real MCP servers live in the regime where description quality changes
agent behavior?

**Operationalize "in the regime" BEHAVIORALLY (not by description properties — that would be circular):**
A confusable family on a server is "in the regime" iff, on the FROZEN protocol with a fixed agent:
(a) Arm A = the server's REAL shipped descriptions fails >=1 contested task (agent selects wrong),
AND (b) Arm B = oracle description recovers it. "Thin descriptions" is an INPUT property and is NOT
the regime definition — only behavior-that-the-fix-repairs counts. Report the regime classifier
explicitly as this two-condition test.

**Sampling frame (pre-registered, reproducible — this defends the number):**
- Define the frame BEFORE scoring: e.g. top-N by popularity (stars/downloads) from the official MCP
  registry + a directory (Glama/PulseMCP) as of a fixed date, source-available, deduplicated. Target
  20-50 servers. SCORE EVERY ONE; drop none post-hoc; log any excluded + the pre-stated reason
  (e.g. no source, un-runnable).
- Build local MIRRORS (real names/schemas/VERBATIM docstrings, stub bodies — RW1/RW2 method, NO live
  APIs/keys). Assert docstrings verbatim vs source (independence rule).
- For each server: identify confusable families (name/embedding clusters), build anti-tautological
  contested tasks (intent, not tool names), run the frozen protocol.

**Report:** fraction of servers (and of families) in-regime; the distribution; per-server table.
**Pre-registered honest caveat (state in the paper):** public servers skew documented -> this
prevalence is a LOWER BOUND on the under-documented internal segment, which is unsampleable (no public
data). Do not generalize beyond "public, source-available MCP servers as of date D."

---

## EXP 2 — CAPABILITY-LADDER CURVE — DROPPED (ratified by GG, 2026-07-04)

**Status: DROPPED from paper scope.** Paper = EXP-4 + EXP-1 + EXP-3. Justification: EXP-1's
completed prevalence result (0/9 scored servers IN-REGIME on the N=10 Python-only pilot, a clean
null across every doc-density tier — see `docs/research/` and `STATUS.md`) found the regime
uncommon in the sampled population. A capability ladder characterizing how an effect's SIZE varies
with agent capability has limited external relevance when the underlying regime this session could
verify is this rare to begin with. EXP-3 (localizer) remains the paper's positive contribution
regardless of this decision — a confusable-pair localization method is useful independent of how
often the regime occurs — and is queued next. Design notes below are preserved for reference/a
possible future revisit, not deleted, since a rare-but-real regime is still worth a ladder if a
future, larger or non-Python-verified sample changes the prevalence picture.

**Question:** how does the description effect size vary with AGENT CAPABILITY?

**Design for apples-to-apples (the reviewer killer is confounds):**
- LADDER = SAME model family at increasing sizes (hold architecture ~constant, vary size): e.g.
  Qwen-2.5 7B / 32B / 72B, or Llama 8B / 70B. Avoid mixing families (that reintroduces the
  gemma-vs-Llama non-comparability). Add a frontier API point ONLY if a non-Anthropic key is
  provisioned (escalate; open-weight ladder is the core result).
- IDENTICAL everything except the agent: same T18 fixture, same tasks, same prompt template, same
  frozen classifier, same trials/seeds.
- PARSE CONTROL (mandatory): report parse_failed PER MODEL; confirm the effect holds on
  parse-success-only. A model showing "no effect" must be ruled out as a parsing artifact, not a
  capability finding. Same for abstain rate per model.

**Report:** effect size (B−A, with CI) as a FUNCTION of capability; the CURVE. Either shape is a
finding: shrinks-with-capability (market sunsets) or persists (durable). Explicitly flag the prior
gemma +34.5 / Llama +40.8 numbers as NOT part of this controlled ladder (different harness).

---

## EXP 3 — CONFUSABILITY LOCALIZATION (positive method on top of the negative)

**Decision: BUILD the positive method** (more publishable than another null). The single-score
discoverability judge fails to localize because it's asked for ONE catalog number (structural limit —
report this as the baseline/negative it already is).

**Method (simple, clean):** PAIRWISE confusability — for each tool pair within a family, ask the frozen
judge "could a task intended for tool A plausibly select tool B (and vice versa) given their
descriptions?" -> a confusability MATRIX -> localized output "tools X,Y confusable for task-type Z."
This is a CONDITION-#1 change (uses the judge) -> DRAFT + escalate; re-validate the judge on a
held-out set.

**Validation:** does the pairwise localizer flag the families that EXP-1's behavioral regime test
found in-regime (i.e. where the agent actually confused tools)? Localizer precision/recall vs the
behavioral ground truth. Compare against the single-score baseline (which flags ~nothing). A localizer
that predicts behavioral confusion = the positive methodological contribution.

---

## EXP 4 (lighter) — consolidate the existing results into the paper's regime map
No new runs: assemble the already-banked findings into the WHERE-it-helps / WHERE-it-doesn't map:
- Helps: confusable-at-scale (T18), under-documented source (Q3/Q5 Guard-B 83% recovery, safe,
  non-degrading), effect survives a strong agent.
- Doesn't / harms: well-documented real servers (RW1/RW2 no headroom — agents resolve from
  names+context); descriptions can HARM already-resolved families (P2-A account_query); F2
  retrieval-readiness CLOSED negative (BM25/TFIDF/embedding); single-score can't localize.
- The mechanism throughline: description precision helps within-family disambiguation but is
  orthogonal/anti-correlated to what context-rich agents need and what retrieval rewards.

---

## REPRODUCIBILITY ARTIFACT (a paper strength — lean in)
- One command reproduces every figure: exact server set (frame + date + hashes), model strings+
  versions, seeds, frozen protocol. PyPI-installable. Frozen judge/generator. Governance documented.
- This artifact is also EXP-1's sampling-frame defense — reviewers can re-run the prevalence number.

## Acceptance / rigor (all experiments)
- Pre-register each experiment's spec at branch start; report parse_failed/headroom/control/stability
  BEFORE any effect; behavioral (not property-based) regime definition; sampling frame fixed before
  scoring, none dropped post-hoc; cross-experiment comparisons ONLY through the frozen protocol;
  negative results first-class; never set ANTHROPIC_API_KEY; condition-#1 (EXP-3 judge) DRAFT+escalated.
- Honest scoping everywhere: public-server prevalence is a lower bound; the ladder is open-weight
  (+ frontier only if key provisioned); one fixture for the ladder = one fixture.

## Sequencing
EXP-4 (consolidation, free, immediate) -> EXP-1 (prevalence, the headline, sampling + mirrors) ->
EXP-3 (localizer, local judge) -> ~~EXP-2 (ladder)~~ DROPPED, ratified by GG 2026-07-04, see EXP-2
section above. EXP-1 completed 2026-07-04: 0/9 scored servers IN-REGIME, N=10 Python-only pilot
(non-Python mechanical extraction proved unreliable and was dropped mid-experiment — see
`STATUS.md` for the full frame-correction history). Paper scope is now EXP-4 + EXP-1 + EXP-3.
EXP-3 is next.

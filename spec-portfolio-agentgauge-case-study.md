# Portfolio case study — AgentGauge

**Site:** `gaurav-gandhi.vercel.app`
**Route:** `/projects/agentgauge`
**Source repo:** `C:\Users\gaura\ml-projects\agentgauge` (main at v0.5.2)
**Live artifact:** `agentgauge-harness` v0.5.2 on PyPI, Apache-2.0

---

## 1. Why this case study is different from the other twelve

Every other project on the site tells a shipping story. This one tells a
**falsification** story: a commercial thesis was pre-registered, tested, and killed
by its own data — then the project was rebuilt around what survived, and shipped.

For a Senior/Principal Applied AI Scientist audience, that is the rarer and more
valuable signal. Most portfolios show what worked. This one shows the ability to
design an experiment that can prove you wrong, run it honestly, and act on the
result. Do not soften the negative results into a redemption arc; the falsifications
*are* the substance.

---

## 2. The narrative arc (five beats)

1. **The thesis.** An 8-axis LLM-judged quality score for MCP tool descriptions,
   intended to ship as a CI gate. Pre-registered decision rule written before data
   collection: CONFIRM / PIVOT / FALSIFY, with explicit criteria for each.
2. **The falsification.** Controlling for description length, the composite score
   drops to partial rho = 0.262 (p = 0.089) — not significant, uncorrected. No axis
   survives multiple-comparison correction net of length. A free `len()` heuristic is
   statistically indistinguishable from eight LLM-judged axes. Thesis dead by its own
   pre-registered rule.
3. **What survived, and the pivot.** The *measurement infrastructure* was the real
   asset. Rebuilt as a regression harness: does this tool-description change make the
   agent measurably better or worse, with a stated detection floor?
4. **Making it work.** ICC = 0.793 showed repeated trials carry almost no independent
   information — the compute was being spent wrong. Reallocating toward task
   diversity, plus a paired design with common random numbers, task-clustered
   bootstrap, and CUPED, took MDE from 0.433 to 0.0537.
5. **Shipped, and one more kill.** v0.5.2 on PyPI. Regression *attribution* was built,
   measured, and killed: localization accuracy requires task volume (MDE proportional
   to 1/sqrt(n)), and task volume is exactly the cost a localizer exists to avoid.
   Shipped disabled behind `--experimental` with the cost numbers in its help text.

---

## 3. Headline numbers (all measured, all traceable to committed reports)

| Claim | Value |
|---|---|
| Minimum detectable effect | 0.0537 at n = 253 tasks |
| False-alarm rate under the null | 0.59% |
| Replay determinism | 100%, across six model-provider adapters |
| Competing approach (single-prompt LLM judge) | 97.1% false-alarm at 100% recall — a degenerate always-flag detector |
| Lint rules with a measured causal effect | 1 of 6 (`type_enum_contradiction`, −13.3 to −28.9pp across three model families) |
| Measurement artifacts found and encoded as automated detectors | 10 |
| Hypotheses falsified against pre-registered criteria | 4 |
| Total cloud spend across the entire program | $29.19 |

Every number on the page carries provenance to a committed report. This site has a
metric-provenance rule; it applies here without exception.

---

## 4. The section that makes this page unlike any other portfolio

**"Ten ways an agent evaluation can measure nothing."**

Each artifact gets: the mechanism, the spurious result it produced, and the automated
detector that now catches it. Two entries should be told at length, because they are
cases where a *wrong* number was believed before being caught:

- The −80pp effect that became a clean null. A scoring bug looked up the pre-rename
  parameter name against post-rename arguments, so agents that got the task
  completely right scored as total failures.
- The 100% attribution accuracy that became 58%. The synthetic probe model omitted
  the between-task variance component, inflating detection power 3–7×.

Both were caught by adversarial self-audit before publication, not by review. That is
the point of the section.

---

## 5. The CEO-lens framing (short, near the end)

Written as a product decision, not a technical postmortem:

- Buyer: platform teams running many internal MCP servers where agent reliability is
  production-critical.
- Value claim: a stated detection floor with a stated false-alarm rate,
  deterministically reproducible.
- Why the competing approach fails: measured, not asserted — 97.1% false alarm.
- What was deliberately *not* shipped, and why: the quality score (indistinguishable
  from `len()`), and attribution (uneconomical against a full re-eval).

The last bullet is the most commercially credible thing on the page. Most portfolios
never mention what the author chose not to ship.

---

## 6. Build requirements

- Match the site's existing case-study template, typography, and navigation exactly.
  This is one of thirteen; it must not read as a different site.
- Every metric wired to the existing provenance mechanism. No hardcoded numbers
  without a source pointer.
- Links out to: the PyPI package, the GitHub repo, and both papers once they are
  public (placeholder-safe until arXiv IDs exist — the page must not ship with dead
  links or invented IDs).
- One diagram: the MDE improvement curve (0.433 → 0.188 → 0.0537) with the estimator
  components that produced each step. It is the clearest single visual of the
  engineering.
- Add to the existing Playwright E2E route coverage. Keep axe at 0 violations and
  Lighthouse at current scores.
- Feed the page into the existing RAG chatbot index at `/ask` so it is answerable.

---

## 7. Non-negotiables

- No number without provenance to a committed report.
- Superseded numbers must not resurface: the −80pp effect (now null), the −40.0pp
  upper bound (now −28.9pp), and 100% attribution accuracy (now 58.33%) all appear in
  early reports under superseding banners. Cite the terminal authority only.
- MEASURED vs NOT MEASURED distinction preserved wherever the page makes a claim.
- Do not frame the falsifications as setbacks that were overcome. They are results.

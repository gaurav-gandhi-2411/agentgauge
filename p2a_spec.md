# p2a_spec.md — P2-A: Synthetic Internal-Proxy Frequency Probe

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 2eca4b7  
**Branch:** `claude/p2a-internal-proxy`  
**Routing:** DRAFT PR. Pre-registered before any fixture code or run.

---

## What this measures

RW1 (GitHub MCP) and RW2 (AWS IAM MCP) showed **0/2 maintained public catalogs with recoverable
headroom** (gemma2:9b, Arm A = real production docstrings, 100% accuracy on contested sets).
Both catalogs are actively maintained; their maintainers have already self-fixed confusion.

The load-bearing unmeasured question is: how often does the **buyer segment** — large internal /
custom MCP catalogs that are under-documented — hit the confusable-at-scale regime where Guard-B
can recover selection accuracy?

No public data exists for this segment. P2-A builds a **SYNTHETIC INTERNAL-PROXY** that explicitly
models the buyer segment and runs the headroom gate on it. The proxy's value is data-on-demand for
a segment that has no public evidence, not a claim about the real market.

---

## Pre-registered design decisions (locked — no post-hoc adjustment)

### Proxy identity
- Label: **SYNTHETIC INTERNAL-PROXY** in all output. Never "measured the buyer market."
- Scope claims: "on a synthetic model of large internal under-documented catalogs." Nothing broader.

### Catalog
- **48 tools across 7 families** (see catalog fixture for full enumeration).
- **Naming**: mid-prior business-domain objects — orders, invoices, tickets, accounts, shipments,
  payments. Not abstract (record/item — too prior-free, artificially hard). Not a specialized domain
  (payment-processor jargon — agent over-resolves from domain conventions).
- **Contested set**: name-collision + thin-description families only (31 of 48 tools). Families
  where agent names carry interchangeable verbs (get/fetch/load/retrieve, update/upsert/patch/replace,
  search/filter/query/find/lookup, notify/push/dispatch/message/contact,
  confirm/approve/fulfill/process, schedule/queue/stage/draft, delete/archive/purge/expire).
- **Thorough set**: 17 tools with clearly distinctive names or well-described behavior. Serve as
  do-no-harm control; Guard-B must not regress these.

### Arm A (baseline — the thin under-documented state being tested)
- **Uniform accurate-but-non-distinguishing ONE-LINE descriptions**: "Get the order.", "Fetch the
  order.", "Update an invoice.", etc.
- NOT empty/absent descriptions (empty = the T18 regime, already proven; this is the realistic
  under-documented state, not the worst-case).
- NOT multi-sentence descriptions (that would not model the under-documented buyer).

### Independence rule (critical — verifier asserts this)
- The mirror server (`examples/p2a_internal_proxy_mirror.py`) is the single ground truth.
- Oracle descriptions are derived ONLY from reading the mirror handler docstrings — not invented.
- Guard-B generation (Phase 1) uses the same mirror source.
- No distinction may be claimed in oracle or Guard-B that the mirror body or docstring does not support.
- CI asserts independence signals: each handler docstring contains a phrase that encodes its
  distinguishing behavioral axis, and the oracle description contains the same substance.

### Bodies
- Real-behavior-bearing stubs: return values differ by family and encode the behavioral distinction.
- Stubs are sufficient for Guard-B source-aware generation; they don't need to be working implementations.

### No-construction-bias rule (hard)
- Difficulty is set by honest modeling of a realistic internal catalog, NOT by what makes the
  fixer look good.
- If during build a family is found to be name-resolvable without descriptions, do NOT add more
  confusion — document it, keep it in the thorough set or as a control, and report it.
- If the proxy produces no-headroom, that is the finding. Report it. Do not adjust.

---

## Run plan

### Headroom gate (Step 1 — run first, cheap)
- **What**: Arm A only on contested tasks (31 tools × 1 trial × 2 models).
- **Models**: gemma2:9b (local Ollama) AND llama-3.3-70b-instruct (Groq free tier; fall back to
  local Ollama if Groq throttles as in prior sessions).
- **Gate**: if Arm A ≥ 85% on contested set → NO HEADROOM for that model. Report and stop.
  If Arm A < 85% → HEADROOM CONFIRMED → proceed to Step 2.
- **Cost**: $0 (local models only; Groq free tier if used).

### Full A/B (Step 2 — only if headroom confirmed per model)
- Arm A vs Arm B (oracle), contested set, 3 trials.
- Guard-B recovery metric: (Guard-B − A) / (Oracle − A) on contested tasks.
- Sign test (task-clustered): contested tasks where B > A vs A > B.
- Per-family breakdown (which families drove the headroom, which didn't).

---

## Pre-registered outcomes (all are publishable; no outcome is a failure)

| Headroom gate result | Finding |
|---|---|
| Both gemma + llama-70b < 85% on contested | Confusable-at-scale regime EXISTS in the buyer-segment proxy at both capability tiers — regime is durable |
| gemma < 85%, llama-70b ≥ 85% | Regime EXISTS but shrinks as buyers adopt stronger agents |
| Both ≥ 85% | Even a deliberately thin realistic proxy is resolvable at both tiers — regime appears rare even in the buyer segment; bounds market hard |
| One model not runnable (throttle/VRAM) | Report result for available model only; note gap |

**No-headroom is publishable and scope-bounding.** If the finding is no-headroom, the conclusion is:
"A synthetic proxy built to model realistic internal under-documented catalogs does not exhibit the
confusable-at-scale regime at [model tier]. The buyer problem, as modeled, appears rare."

---

## Headroom gate threshold
Pre-registered at **85%** (same as FRONTIER-T18 STEP 1). No adjustment after seeing numbers.

## Trials
Gate: 1 trial. Full A/B: 3 trials. Pre-registered; not adjusted based on gate result.

## Agent ≠ judge ≠ generator
- Agent: gemma2:9b / llama-3.3-70b-instruct
- Judge: llama3.1:8b (for description quality scoring, not for the A/B metric)
- Generator (Phase 1 Guard-B): qwen3:8b
- All three must differ; asserted by harness.

---

## Acceptance criteria

1. **CI (deterministic, no network):**
   - Catalog fixture integrity: all 48 tools have schema, Arm A description, oracle description, task.
   - Independence signals: each contested handler docstring contains expected behavioral signal phrase.
   - ARM_A_DESCRIPTIONS == one-line thin descriptions (no multi-sentence Arm A).
   - 85% gate asserted in harness code.
   - verify.sh green; coverage ≥ 60%.

2. **Real-model run (manual, local models only):**
   - Step 1: headroom gate on gemma2:9b + llama-3.3-70b. Report per-model accuracy on contested set.
   - Step 2 (if headroom): full 3-trial A/B on models with headroom. Guard-B recovery on contested set.
   - Report findings per pre-registered outcome table. Scope to proxy.

3. **No-tuning rule**: proxy families and descriptions are fixed at pre-registration. If headroom
   is found, Guard-B recovery is the metric. No mid-experiment hardening or softening of descriptions.

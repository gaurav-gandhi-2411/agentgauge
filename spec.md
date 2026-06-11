# spec.md — RW2: real-world value test on the AWS IAM MCP server (the buyer segment)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 4207615 ·
**Branch:** `claude/rw2-aws-iam`
**Routing:** DRAFT PR. New real-tool mirror fixture + reuse scan + Q5 Guard-B fixer + real-agent A/B.
Draft-forcing #2/#3. **NOT condition #1** (scan + Guard-B reused unchanged).

**Pre-registration:** committed at branch start. Mirror construction, the CONTESTED-SET DEFINITION,
the skip-the-thorough control, and the destructive-confusion metric are fixed before the run.

---

## Why (CEO framing)

RW1 (GitHub) found no headroom — docs too good, agent saturated, fixer idle. It bounded the buyer to
UNDER-documented servers. RW2 tests the buyer segment directly: the AWS IAM MCP server (awslabs/mcp,
src/iam) — real, enterprise, source-available, ~50% thin / ~50% thorough docs, 4 confusable families
where the thin description is the only disambiguator, 3 destructive pairs, and NO tool-search escape
hatch (thin descriptions hurt direct selection with no fallback). Picking attach_user_policy vs
attach_group_policy wrong is a real PERMISSION LEAK — the painkiller, concrete.

## What RW2 is and is NOT (set expectations)

- It is: REPLICATION of Q5 Guard-B on REAL thin docstrings + a STAKES test (do destructive-confusable
  pairs flip the agent, does the fix prevent it) + a DO-NO-HARM test on the already-thorough tools.
- It is NOT a brand-new mechanism. The thin tools' distinctions live in the source (Q3-DOC regime
  Guard-B already handles). Frame the result as "the validated fixer delivers on a real
  under-documented server," not a new capability.

## The headroom trap (pin this or RW2 becomes RW1)

Thin != contested. The through-line: capable agents resolve from NAMES. delete_user is thin but its
NAME says delete-a-user — the agent likely picks it correctly with no description. Real headroom
exists ONLY where NAMES COLLIDE and the thin description fails to break the tie. So:
- CONTESTED SET = NAME-COLLISION + THIN-DESCRIPTION families ONLY:
  - Family A: attach_user_policy / attach_group_policy / detach_user_policy / detach_group_policy
    (names differ only by user/group; identical thin docstrings).
  - Family C: list_policies / list_user_policies / list_role_policies / list_users / list_groups /
    list_roles (similar names, fundamentally different operations).
  - Destructive pairs in B/E: delete_user_policy / delete_role_policy; (and EKS
    manage_k8s_resource delete — only if EKS is mirrored; IAM-first is fine).
- Tasks target a specific member requiring the principal/scope distinction. Tasks state INTENT
  (e.g. "revoke the billing policy from the deploy GROUP"), NOT tool names.
- Pre-register: if Arm A (real AWS docstrings) is already >=~80% on the contested set, that's a
  no-headroom finding (names sufficed) — REPORT it, do not manufacture headroom.

---

## Design — local mirror, NO live AWS API

- Build a LOCAL MIRROR from awslabs/mcp src/iam PUBLIC SOURCE: REAL tool names, schemas, and the
  VERBATIM docstrings (thin ones thin, thorough ones thorough — do NOT normalize). Stub bodies, NO
  AWS calls, NO credentials, NO destructive operations.
- Reuse: AgentGauge scan/discoverability scorer (unchanged); Q5 Guard-B source-aware fixer with the
  skip-above-band / abstain behavior (unchanged).

**ARMS:**
- Arm A = real AWS docstrings as shipped (thin where thin, thorough where thorough).
- Arm GuardB = Q5 Guard-B descriptions generated from the real source.
- (Arm O = hand-written oracle, optional ceiling.)

## Three measurements (the product demo in one run)

1. **VALUE (thin confusable families):** parse-success selection accuracy A vs GuardB on the
   contested set. Does the fixer recover where thin docs + colliding names fail?
2. **DO-NO-HARM (already-thorough tools):** the ~14 thorough tools the agent already selects
   correctly. Does Guard-B SKIP/preserve them (skip-above-band) and leave selection unregressed?
   ZERO regressions required. (This is the half-thin/half-thorough split working as the demo.)
3. **PAINKILLER (destructive confusion):** wrong-DESTRUCTIVE-tool selection rate A vs GuardB,
   reported separately. The headline CEO number: does fixing thin docs reduce
   wrong-principal/irreversible-action selection.

## Rigor (whole Q-arc discipline)

- parse_failed first; stability pre-screen on the contested set; task-clustered analysis;
  anti-tautology (intent not tool names); agent gemma2:9b (!= judge != generator); generator
  qwen3:8b; phase-separated GPU, silence qwen3:30b first; generate ONCE, seed recorded.
- Docstring integrity: Arm A docstrings VERBATIM from awslabs/mcp source (assert; this is RW2's
  independence rule — no normalization, no paraphrase).
- No post-hoc fixture tuning.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** mirror loads with VERBATIM AWS IAM names/schemas/
   docstrings (stub bodies, NO network); contested families + destructive pairs documented/asserted;
   the thorough-tool control set identified; gold mapping intact; scan + Guard-B paths unchanged.
   Assert Arm A docstrings match source verbatim.
2. **Real-agent + scan (manual, in PR description):**
   - SCAN: does the discoverability scorer flag the thin confusable families (and NOT the thorough
     ones)? Report — this is RW2's score-validity check on a server with KNOWN thin/thorough split.
   - GPU exclusivity + parse_failed; HEADROOM (Arm A accuracy on contested set; if >=~80% report
     no-headroom).
   - VALUE table: A / GuardB (/ O) on contested set + improvement + sign test.
   - DO-NO-HARM: thorough-tool subset A vs GuardB; count regressions (target ZERO); confirm Guard-B
     skipped/preserved them.
   - PAINKILLER: wrong-destructive-tool rate A vs GuardB, separately.
   - VERDICT (CEO):
     - GuardB improves thin confusable selection + reduces destructive confusion + zero harm on
       thorough tools: the product is VALIDATED on the real buyer segment — sales-demo result.
     - No headroom (names sufficed even on thin tools): the fixer's value is narrower than the
       buyer-segment hypothesis assumed — report honestly.
     - Regressions on thorough tools: skip/abstain behavior insufficient on real docs — localize.
3. scorer.py / judge / rubrics / calibration / Guard-B logic untouched; verify.sh green; coverage >= 60%.

## Housekeeping

- TASKS.md: RW2 (TODO -> IN-REVIEW). STATUS.md: scan validity on thin/thorough split, value on
  contested set, destructive-confusion delta, do-no-harm on thorough tools — framed as the
  buyer-segment value verdict. Do NOT claim "validated on real servers" beyond "on the AWS IAM
  server"; one real under-documented server is one datapoint.

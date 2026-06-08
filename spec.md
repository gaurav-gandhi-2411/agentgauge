# spec.md — RW1: real-world external validity on the GitHub MCP server (value test)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 32a099c ·
**Branch:** `claude/rw1-github-mcp`
**Routing:** DRAFT PR. New real-tool fixture + reuse scan + Guard-B fixer + real-agent A/B.
Draft-forcing #2/#3. **NOT condition #1** (no scorer/judge/rubric/calibration/generator-logic
changes — scan and Guard-B reused as-is).

**Pre-registration:** committed at branch start. The mirror-fixture construction, the confusable-
family identification, the score-validity check, and the wrong-tool / wrong-destructive metrics are
fixed before the run.

---

## Why (CEO framing)

Every prior result is on synthetic fixtures + gemma2:9b. RW1 is the first EXTERNAL-VALIDITY +
VALUE test: does the pipeline (scan -> Guard-B fix from source -> measurable selection improvement)
work on a REAL, large, confusable, documented server — and does it reduce the failure that actually
costs customers (wrong DESTRUCTIVE tool selection)? Target: the GitHub MCP server (github/
github-mcp-server) — 162 tools / 20 toolsets, open-source Go with real docstrings, and a server whose
own maintainers consolidated tools to fight confusability (validating the problem is real and costly).

## Scope — local mirror, NO live API

- Build a LOCAL MIRROR fixture from the GitHub MCP server's PUBLIC SOURCE (pkg/github/*.go: tool
  names, JSON schemas, and docstrings/comments). Stub bodies — NO live GitHub API, NO auth, NO write
  operations (avoids cost, auth, and destructive-action risk). The mirror carries the REAL interface
  + REAL source text the fixer would consume.
- Reuse: AgentGauge scan/discoverability scorer (unchanged); Q5 Guard-B source-aware fixer
  (unchanged). Only the fixture + a task set are new.

**OUT:** live GitHub API; changes to scorer/fixer logic; the full 162-tool set if intractable —
scope to the confusable subset that matters (see below).

## Part 1 — SCORE VALIDITY (does scan flag what GitHub hand-fixed?)

- Run the discoverability scorer on the mirrored GitHub toolset. Identify the families the scorer
  flags as confusable (low discoverability).
- CROSS-CHECK against ground truth GitHub itself provides: tools GitHub CONSOLIDATED/RENAMED to
  reduce confusion (e.g. the 6->3 Projects consolidation; read-variant overlaps like
  get_file_contents / pull_request_read / list_* / search_*). If the scorer flags the families
  GitHub's own engineers spent effort de-confusing, that's external evidence the SCORE predicts real
  problems. Report overlap between scorer-flagged and GitHub-hand-fixed families.

## Part 2 — FIX VALUE (does Guard-B reduce wrong-tool selection on real tools?)

- Pick the most confusable real families (e.g. the read/fetch family: get_file_contents,
  pull_request_read, list_*, search_* variants; the projects family). Build a task set: each task
  targets one specific tool whose correct selection requires distinguishing it from its real
  neighbors.
- Arm A = original GitHub docstrings (as shipped). Arm GuardB = Q5 Guard-B descriptions generated
  from the real source. (Optional Arm O = hand-written oracle, as a ceiling.)
- Metric: parse-success selection accuracy on the confusable task set. Recovery / improvement A->GuardB.
- **PAINKILLER METRIC (the CEO number):** flag any DESTRUCTIVE-confusable pairs in the real toolset
  (a write/delete tool confusable with a safer neighbor). Report WRONG-DESTRUCTIVE-tool selection
  rate separately from overall wrong-tool rate. This is the metric that translates to customer pain.

## Rigor (carry the whole Q-arc discipline)

- Headroom: Arm A (original GitHub docstrings) must MISS some confusable tasks (real headroom). If
  GitHub's real docstrings already disambiguate everything, that itself is a finding (their docs are
  good; our fix adds little THERE) — report it; don't manufacture headroom.
- parse_failed reported first; stability pre-screen; task-clustered analysis; anti-tautology (tasks
  state intent, not tool names); agent gemma2:9b (!= judge != generator); generator qwen3:8b;
  phase-separated GPU, silence qwen3:30b first.
- No post-hoc fixture tuning.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** mirror fixture loads with real GitHub tool
   names/schemas/docstrings (stub bodies, NO network calls in tests); confusable families documented;
   destructive-confusable pairs flagged; task gold mapping intact; scan + Guard-B paths unchanged.
2. **Real-agent + scan (manual, in PR description):**
   - PART 1: scorer-flagged confusable families vs GitHub-hand-fixed families — report overlap +
     verdict on score validity.
   - PART 2: GPU exclusivity + parse_failed; headroom (Arm A original-docstring accuracy on the
     confusable task set); table A / GuardB (/ O) + improvement + sign test; WRONG-DESTRUCTIVE-tool
     rate A vs GuardB separately.
   - VERDICT (CEO):
     - Scan flags real confusables AND Guard-B reduces wrong-tool (esp. destructive) selection on
       real tools: external validity + value CONFIRMED on a representative large server.
     - Scan flags but Guard-B doesn't help (GitHub docstrings already good): the fix's value is in
       UNDOCUMENTED/poorly-documented servers, not well-maintained ones — bounds the buyer.
     - Scan doesn't flag the hand-fixed families: score-validity gap on real servers — critical,
       report.
3. scorer.py / judge / rubrics / calibration / Guard-B generator logic untouched; verify.sh green;
   coverage >= 60%.

## Housekeeping

- TASKS.md: RW1 (TODO -> IN-REVIEW). STATUS.md: record score-validity overlap, fix improvement +
  wrong-destructive-tool delta on real GitHub tools, and the buyer-bounding verdict (does the fix add
  value on a WELL-documented real server, or only on poorly-documented ones?). Frame the result in
  customer-value terms.

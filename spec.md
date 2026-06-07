# spec.md — Q3: source-aware description generation (docstring vs body-only)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ f01fe94 ·
**Branch:** `claude/q3-source-aware`
**Routing:** DRAFT PR. New fixture + generator-input change + real-agent A/B. Draft-forcing #2/#3.
**NOT condition #1** (no judge/scorer/rubric/calibration changes).

**Pre-registration:** committed at branch start. Fixture, the independence rule, the two source
conditions, recovery metric, and the no-fabrication control are fixed before the run.

---

## Why

Q2a (per-tool) and Q2b (catalog-aware) both recovered only 12.5% of the T18 oracle gain. Diagnosis,
confirmed twice: the distinguishing information (cache vs SQL vs queue, soft vs hard delete, channel,
directionality) is absent from the interface — names + identical {query:string} schemas carry no
signal. The only place it can live is the tools' SOURCE. Q3 tests whether feeding the generator the
source recovers the gain — and splits the claim into two capability levels.

## The fixture must be built (the T18 tools are echo-stubs)

The T18 60-tool catalog has NO real implementations — call_tool echoes {tool, query}. There is no
source to read. Q3 therefore requires a NEW fixture with REAL, working tool bodies whose behavior
genuinely differs (a cache uses a TTL store; an HTTP tool issues a request; a soft-delete sets an
`archived` flag; an INSERT-only tool raises on existing key).

### INDEPENDENCE RULE (the central hazard — non-negotiable)

The source must encode each distinction INDEPENDENTLY of the oracle description. If bodies/docstrings
are written FROM the oracle prose, "source-aware generation recovers the oracle" is tautological
(the source IS the oracle restated). To enforce:
- Write the implementations FIRST, as a working server would (real library calls / real logic),
  WITHOUT looking at the T18 oracle text. The oracle description is then DERIVABLE from the behavior
  but is not its origin.
- A reviewer (human) must be able to confirm, per tool, that the distinguishing fact is present in
  the CODE (e.g. `redis.setex(...)`, `requests.post(url)`, `if exists: raise`, `row.archived=True`)
  and NOT merely paraphrased from the oracle sentence.
- Keep the gold task-to-tool mapping and the confusable family structure aligned with T18 so results
  are comparable, but the disambiguator now lives in source, not in a handed-over description.

## Two source conditions (both arms, compared — this comparison IS the finding)

- **Q3-DOC (easy):** tools have real bodies AND honest docstrings stating behavior. Tests whether the
  generator can EXTRACT a stated-but-not-in-interface fact. = "point the fixer at a documented repo."
- **Q3-BODY (hard):** SAME tools, docstrings STRIPPED — body only. Tests whether the generator can
  INFER behavior from code (cache from setex, HTTP from requests.post). = "undocumented real server."
- Report Q3-DOC and Q3-BODY recovery SEPARATELY. The gap between them is the dependence-on-prose
  measure. Do NOT collapse them into one number.

---

## Design (arms)

- Arm A = empty descriptions (floor, as T18). Arm O = oracle (ceiling, as T18).
- Arm F-DOC = generator fed {name, schema, source-with-docstring}. Arm F-BODY = generator fed
  {name, schema, source-body-only}.
- Generator path: extend description generation to accept an optional `source` string; new prompt
  variant instructs the generator to describe the tool and how it differs from neighbors USING THE
  SOURCE, with the SAME no-fabrication guard from Q2b ("only state a difference supported by the
  evidence; if not supported, say what it does plainly"). Reuse the shared JSON/text extractor.
- Metric: parse-success selection_accuracy on the contested tasks; recovery = (F-A)/(O-A) for each of
  F-DOC and F-BODY; sign tests vs A and vs O.
- Agent gemma2:9b; generator qwen3:8b; phase-separated GPU (generate -> ollama stop -> A/B
  gemma-only watchdog). Silence the qwen3:30b reactive requester before launch.

## No-fabrication control (carry from Q2b)

The genuinely-ambiguous tools (T18 double-zeros: find_entries/lookup_data, book_slot/plan_event) get
real implementations that are ACTUALLY equivalent. Q3 generators must NOT invent a distinction for
them. Classify FAITHFUL/FABRICATED per ambiguous tool, both source conditions. Any FABRICATED -> FAIL.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** new fixture loads (real bodies; docstring + stripped
   variants both present); independence assertions (each contested tool's distinguishing token is in
   the code, gold mapping intact); generator prompt assembles source context; no-fabrication
   instruction present; shared extractor used; MockProvider tests for the source-fed path. No real
   model in committed tests.
2. **Real-agent A/B (manual, in PR description):**
   - GPU exclusivity + parse_failed FIRST.
   - Table: Arm A / F-DOC / F-BODY / Arm O (parse-success contested) + recovery fraction for F-DOC
     and F-BODY separately + sign tests.
   - No-fabrication control: FAITHFUL/FABRICATED per ambiguous tool, each condition. Any FABRICATED -> FAIL.
   - Per-task diagnosis: for each contested task, did F-DOC / F-BODY encode the real distinction?
   - Verdict matrix:
     - F-DOC recovers, F-BODY recovers: source-inference works even undocumented — strongest claim.
     - F-DOC recovers, F-BODY does not: the fixer needs DOCUMENTED source; on undocumented servers it
       can't infer from code. Bounds the feature precisely.
     - Neither recovers: even source can't be turned into discriminating descriptions by this
       generator — the limit is the generator, not the information source.
     - Any FABRICATED on control -> unsafe regardless of recovery.
3. scorer.py / judge / rubrics / calibration untouched; generator != judge asserted; verify.sh green;
   coverage >= 60%.

## Housekeeping

- TASKS.md: Q3 (TODO -> IN-REVIEW). STATUS.md: record F-DOC and F-BODY recovery SEPARATELY + the
  no-fabrication control. State the verdict-matrix cell reached. Do not claim "source-aware fixing
  works" without specifying which source condition.

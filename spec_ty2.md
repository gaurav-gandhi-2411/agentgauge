# spec_ty2.md — Ty Run 2: Partial-Headroom Mixed-Constraint Fixture

**Branch:** `claude/ty-call-correctness`
**Pre-registered:** before Run 2 data is collected. This file committed before any agent run.
**Status:** Run 1 (floor-effect design) labeled PRELIMINARY — see below.

---

## Why Run 1 is labeled preliminary / floor-effect

Run 1 used 4 "hard" tools with fully arbitrary enum codes (`ACQ_BURST`, `CODEC_R8`, etc.) plus 16
inert "easy" tasks (no constrained params). This design has a structural confound:

- Hard tasks: Arm A is pinned at ~0% by construction (arbitrary codes the agent cannot guess).
  All delta comes from Arm B supplying a token the agent could not know existed.
- Easy tasks: always 100% in both arms — 16 ties that inflate N without contributing signal.
- Reported Arm A: 50% (padded by 16 easy tasks). Hard-task Arm A: 0%.

**What Run 1 can show (with those caveats):**
Supplying a non-guessable enum in the oracle schema causes the agent to emit it (near-tautological
lookup — agent saw the token in schema and produced it). This is not the same claim as
"better schema improves call RELIABILITY where the agent had partial ability."

**What Run 1 cannot show:**
That schema quality affects the agent's ability to construct calls when it already has partial
ability. The product-relevant finding requires an Arm A with variance — where some calls succeed
by convention and some fail, so Arm B can demonstrably close the gap.

---

## Run 2: Research question

Same question as Ty: does showing the agent an oracle schema (with precise constraints) reduce
malformed calls? But now asked in a regime where the agent already has partial ability:

- Arm A: ~40–70% of hard-task trials succeed (agent sometimes constructs valid calls from
  convention or inference alone).
- Arm B: ~75–95% of hard-task trials succeed (oracle constraints narrow the answer space).

If the delta holds up under sign test, schema quality has RELIABILITY benefit — not just
token-supply benefit.

---

## Fixture design

**6 hard tools only. No inert easy tasks. 5 tasks per tool = 30 tasks.**

The headroom gate applies to ALL surviving tasks (not a padded average).

### Constraint mix

Three constraint types, 2 tools each:

| # | Type | Mechanism | Scoring rule |
|---|------|-----------|--------------|
| 1–2 | Format pattern | String must match `[A-Z]{2}[0-9]{2}` or `ERR[0-9]{3}` — agent partially uses similar conventions | `re.fullmatch(pattern, value)` |
| 3–4 | Semi-conventional enum | Enum with both conventional values (agent guesses ~85%) and opaque values (agent guesses ~5%) | exact match to gold |
| 5–6 | Non-standard unit/bound | Integer param in centiseconds/deciseconds; agent's conventional guess often misses the range | `min_val <= int(value) <= max_val` |

### Why each type creates partial Arm A (40–70%, not 0%)

**Format:** Agents have prior exposure to codes like "CH04", "ERR001" from training data. They do
not consistently produce the exact pattern required, but they are right a meaningful fraction of
the time. Expected Arm A: ~30–50%.

**Semi-conventional enum:** Tasks are split between gold values that are standard domain terms
(agent gets ~85%) and one opaque vendor code (agent gets ~5%). With equal task weighting, average
Arm A = ~47%. The key: conventional-value tasks are NOT easy — they test whether the agent reads
the enum to confirm the right term rather than guessing a near-synonym.

**Unit/bound:** Agents know what "centiseconds" and "deciseconds" mean (rare but not opaque), but
consistently use the wrong unit scale under Arm A (outputting milliseconds or seconds). The
valid range [1, 25] cs or [5, 60] ds is passed only when the agent uses the correct scale.
Expected Arm A: ~35–55%.

### Anti-tautology guard (strengthened from Run 1)

Run 2 tasks must:
1. Not contain the constraint value string (enum code, format pattern, numeric target).
2. Not state the unit (no "milliseconds" or "centiseconds" in task text).
3. Not uniquely imply the exact value — the schema must carry additional information beyond
   what the task text provides.

### Inferability check (strengthened)

For each constraint, explicitly assert:
- The constrained param's name does not contain the enum code as a substring.
- No gold value appears verbatim in any task description.
- ADDITIONALLY for format/range: the constraint cannot be satisfied by a trivially obvious value
  (e.g., if any integer in [1, 100] satisfies the range, the task must not trivially lead to
  a small positive integer — the task must instead lead the unprompted agent to a DIFFERENT
  scale, creating real wrong-unit failures in Arm A).

---

## Tools and schemas

### Tool 1: `register_channel(site_id: string, channel_ref: string)` — FORMAT

Arm A schema:
```json
{"type": "object",
 "properties": {"site_id": {"type": "string"}, "channel_ref": {"type": "string"}},
 "required": ["site_id", "channel_ref"]}
```

Arm B oracle schema (channel_ref):
```json
{"type": "string", "pattern": "[A-Z]{2}[0-9]{2}",
 "description": "Channel reference code: exactly 2 uppercase letters followed by 2 zero-padded digits (e.g. PH04, TM07, FL12). No separator."}
```

Score: `bool(re.fullmatch(r'[A-Z]{2}[0-9]{2}', value))`

Tasks (5):
1. "Register the primary pressure sensor channel at facility site F1"
2. "Add a new temperature monitoring channel for site S3"
3. "Register the flow rate measurement channel at site A2"
4. "Set up a humidity sensor channel for site H9"
5. "Register a voltage measurement channel at site V5"

No gold values — any valid format counts. Arm A: agent sometimes produces 2-letter + 2-digit
codes from convention; often produces names like "pressure_01", "CH_TEMP", etc.

---

### Tool 2: `log_fault(unit_id: string, fault_code: string, message: string)` — FORMAT

Arm A schema: fault_code `{"type": "string"}`

Arm B oracle schema (fault_code):
```json
{"type": "string", "pattern": "ERR[0-9]{3}",
 "description": "Fault reference code: ERR followed by exactly 3 zero-padded digits (e.g. ERR001, ERR042, ERR100). No spaces or separators."}
```

Score: `bool(re.fullmatch(r'ERR[0-9]{3}', value))`

Tasks (5):
1. "Log an overtemperature fault on unit U7"
2. "Record an undervoltage fault detected on unit U2"
3. "Report a sensor communication timeout on unit U11"
4. "Log a calibration failure for unit U5"
5. "Record a watchdog expiry fault on unit U8"

Arm A: agent sometimes produces "ERR001" style; often produces "FAULT_001", "OVR", "E042", etc.

---

### Tool 3: `set_output_encoding(pipeline_id: string, encoding: string)` — SEMI-CONVENTIONAL ENUM

Oracle enum: `["utf-8", "ascii", "base64", "XOR16"]`
- "utf-8", "ascii", "base64": well-known in web/API contexts — agent guesses ~80–90%
- "XOR16": opaque vendor code — agent cannot guess (~5%)

Arm A schema: encoding `{"type": "string"}`

Arm B oracle schema (encoding):
```json
{"type": "string",
 "enum": ["utf-8", "ascii", "base64", "XOR16"],
 "description": "Output encoding: utf-8=Unicode variable-width (default for most APIs), ascii=7-bit ASCII only, base64=MIME-safe binary-to-text, XOR16=proprietary 16-bit XOR obfuscation for legacy device compatibility"}
```

Score: exact match to gold

Tasks (5) with gold values:
1. "Encode pipeline P1 output for international text including non-ASCII characters" → gold: "utf-8"
2. "Set pipeline P2 to use 7-bit encoding only, rejecting multi-byte characters" → gold: "ascii"
3. "Configure pipeline P3 to output binary data safely over a text-only channel" → gold: "base64"
4. "Apply the encoding required for compatibility with the legacy TRS-80 protocol on pipeline P4" → gold: "XOR16"
5. "Set pipeline P5 to the encoding that handles all Unicode code points" → gold: "utf-8"

Task distribution: utf-8 ×2, ascii ×1, base64 ×1, XOR16 ×1 → expected Arm A ≈ (85+85+80+75+5)/5 = 66%
(base64 somewhat guessable; XOR16 not at all). This is at the top of the 40–70% range.

---

### Tool 4: `set_trigger_mode(sensor_id: string, trigger: string)` — SEMI-CONVENTIONAL ENUM

Oracle enum: `["rising", "falling", "both", "XP7"]`
- "rising", "falling", "both": standard edge-detection terms — agent guesses ~85–90%
- "XP7": opaque firmware-defined pattern — agent cannot guess (~5%)

Arm A schema: trigger `{"type": "string"}`

Arm B oracle schema (trigger):
```json
{"type": "string",
 "enum": ["rising", "falling", "both", "XP7"],
 "description": "Trigger edge condition: rising=detect low-to-high transition, falling=detect high-to-low transition, both=detect any edge transition, XP7=firmware-defined proprietary pattern (vendor-specific, requires firmware >=2.4)"}
```

Score: exact match to gold

Tasks (5) with gold values:
1. "Configure sensor S01 to fire whenever its input signal transitions from low to high" → gold: "rising"
2. "Set sensor S02 to trigger on the downward edge of the input signal" → gold: "falling"
3. "Configure sensor S03 to react to signal changes in either direction" → gold: "both"
4. "Enable the special firmware-level detection mode on sensor S04 that requires the 2.4 firmware" → gold: "XP7"
5. "Configure sensor S05 to detect only when the voltage rises above threshold" → gold: "rising"

Task distribution: rising ×2, falling ×1, both ×1, XP7 ×1 → expected Arm A ≈ (85+85+85+80+5)/5 = 68%
(just at the 70% ceiling — actual may vary by model).

---

### Tool 5: `set_debounce_delay(sensor_id: string, delay_cs: integer)` — UNIT/BOUND

Valid: integer in centiseconds [1, 25] (10 ms to 250 ms)
1 cs = 10 ms

Arm A schema: delay_cs `{"type": "integer"}`

Arm B oracle schema (delay_cs):
```json
{"type": "integer", "minimum": 1, "maximum": 25,
 "description": "Debounce delay in centiseconds (1 cs = 10 ms). Valid range: 1 to 25 (10 ms to 250 ms)."}
```

Score: `1 <= int(value) <= 25` (range check — any valid centisecond value accepted)

Tasks (5) — all describe purpose/impact, no unit or number hints:
1. "Suppress mechanical bounce on the reed switch input for sensor S01"
2. "Filter out rapid false triggers on the vibration sensor S02"
3. "Add a debounce interval to prevent multiple registrations from the door sensor S03"
4. "Reduce noise on the contact sensor S04 caused by spring oscillation"
5. "Apply signal filtering to eliminate chatter on the limit switch for sensor S05"

No numeric targets in tasks. Arm A: agent likely outputs values in ms scale (50–200 range), which
are all out of range [1, 25] cs. Agent might output small integers (5, 10) which happen to be in
range. Expected Arm A: ~30–50%.

Note on inferability: "_cs" suffix is a partial hint. But centiseconds is non-standard and the
agent typically defaults to ms. The schema supplies the conversion factor and valid range.

---

### Tool 6: `configure_watchdog(node_id: string, timeout_ds: integer)` — UNIT/BOUND

Valid: integer in deciseconds [5, 60] (0.5 s to 6 s)
1 ds = 100 ms

Arm A schema: timeout_ds `{"type": "integer"}`

Arm B oracle schema (timeout_ds):
```json
{"type": "integer", "minimum": 5, "maximum": 60,
 "description": "Watchdog timeout in deciseconds (1 ds = 100 ms). Valid range: 5 to 60 (0.5 s to 6 s)."}
```

Score: `5 <= int(value) <= 60` (range check)

Tasks (5) — purpose/urgency only, no numbers or units:
1. "Set a short watchdog on node N1 that will restart it if it stops responding quickly"
2. "Configure a generous watchdog timeout for node N2, which runs slow background tasks"
3. "Set a medium-length watchdog for node N3 that balances responsiveness and stability"
4. "Apply a conservative watchdog to node N4 to allow for slow initialization"
5. "Configure the tightest acceptable watchdog on node N5 for a real-time loop"

Arm A: agent likely outputs seconds (e.g., 5, 10, 30 for watchdog), which translates to 50, 100,
300 ds — mostly out of range [5, 60]. Small integer guesses (5, 10) happen to land in range.
Expected Arm A: ~35–50%.

---

## Scoring rules summary

```python
# constraint kinds: "enum" | "format" | "range"
# enum: value must equal gold exactly (case-sensitive)
# format: re.fullmatch(pattern, str(value)) is not None
# range: min_val <= int(value) <= max_val
```

For Tools 1–2 (format): no gold value per task. Any valid-format output counts as correct.
For Tools 3–4 (enum): gold value specified per task. Must match exactly.
For Tools 5–6 (range): no gold value per task. Any in-range integer counts as correct.

This deliberately tests WELL-FORMEDNESS (does the agent produce a valid call?), not exact
semantic accuracy (does it pick the exact intended value?). The oracle provides the constraints
needed to be well-formed; Arm A lacks them.

---

## Pre-checks (hard tasks only — no easy tasks to inflate)

1. Manipulation check: Arm A vs Arm B tool listing differ (oracle adds enum/pattern/range).
2. Stability screen: run Arm A twice × 3 stability trials. Drop tasks where
   `|successes_run1 − successes_run2| > 1`. Report dropped count.
3. Headroom check on SURVIVING HARD TASKS ONLY (all tasks are hard):
   - Arm A aggregate on surviving tasks must be in [40%, 70%].
   - Below 40%: constraints too hard — Arm A is still effectively a floor.
   - Above 70%: constraints too easy — Arm A leaves little room for oracle improvement.
   - If outside range: STOP. Report as fixture-quality failure. Do not interpret.
4. N check: N_surviving ≥ 25 (30 pre-registered; 5-task drop margin allowed).

---

## Analysis plan

Task-clustered sign test on task-level deltas (consistent with Run 1 and T17 protocol):
- Compute per-task Arm A and Arm B correctness rates (fraction of trials correct).
- delta_i = rate_B_i − rate_A_i
- Sign test on tasks where delta ≠ 0 (exclude ties).
- Wilcoxon signed-rank test on all non-zero deltas if N_nontied ≥ 10.
- Report: n_plus, n_minus, n_ties, p-value.

Honest verdict:
- POSITIVE (oracle > A AND p < 0.05): oracle schema improves call reliability where
  the agent had partial ability. Schema quality has genuine behavioral headroom on calls.
- NULL (oracle ~ A OR p ≥ 0.05): oracle schema does not improve call reliability beyond
  what the agent achieves from convention alone. Combined with the selection finding and
  Run 1's floor-effect result, schema quality appears behaviorally inert for gemma2:9b.
- DIRECTIONAL (oracle > A, p ≥ 0.05): report delta and p, flag as underpowered.

---

## Files

- `examples/call_constraints_v2_server.py` — Arm A (vague schemas)
- `examples/call_constraints_v2_server_oracle.py` — Arm B (oracle schemas)
- `evals/fixtures/ty2_tasks.py` — tasks, constraints, gold values
- `tests/test_ty2_fixture.py` — CI tests
- `scripts/run_ty2_oracle_ab.py` — real-agent run script

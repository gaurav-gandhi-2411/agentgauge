# Provider-compat ablation probe: design (committed before any call)

**Status:** design frozen at this commit. Approved by GG, relayed via Claude (chat), 2026-10-30. Every result is
**POST-HOC**: the rejections being probed were seen before this design was written, and the 24 catalogs are the ones
the lint rule was built from.

## Why

The miss diagnosis (`reports/provider_compat_posthoc.md`) could not say what causes the rejection in the units where
**only a combination of tools** is rejected: R3, R5 and the two group-only units of R4. The existing bisection log
records only accept/reject for tool subsets, and no keyword-removal run was ever made on a multi-tool unit.

Re-deriving the units from that log for this design found **five** such units, not four. R5 has two independent
group-only units, a 3-tool group and a 10-tool group; the published table names only the 3-tool group. That row will be
corrected with the results.

| Unit | From | Tools | Each half accepted alone |
|---|---|---|---|
| U1 | R3 | 2 | yes |
| U2 | R4 | 4 | yes |
| U3 | R4 | 32 | yes |
| U4 | R5 | 3 | yes |
| U5 | R5 | 10 | yes |

R1 and the single-tool units of R2 and R4 are **not** probed: they are outside the approved scope, and their
single-keyword removals already ran.

## Question and hypotheses

**Q.** For each unit, which construct must be present for Vertex to reject it, and is the rejection a property of one
construct instance or of an aggregate across the request?

- **H-budget (complexity budget).** The rejection is caused by an aggregate quantity summed over all declarations in
  the request, consistent with Vertex's documented "too many states" class of schema error. No single instance of a
  construct is necessary.
- **H-instance.** A specific construct instance is necessary. It is rejected only together with the rest of the unit,
  since every tool is accepted alone.

**Predictions, fixed here:**

| Test | H-budget | H-instance |
|---|---|---|
| B: forward and reverse reconstruction | find **different** threshold instances | find the **same** instance |
| C: duplication test | renamed copies of one accepted tool are rejected at some copy count ≤ 4 | copies stay accepted |

## Call protocol

**Common to every call:**

| Setting | Value |
|---|---|
| Model | `gemini-3.8-flash` on Vertex, the model used by the original bisection |
| User text | `"Call one of the available tools."`, the fixed probe text; no study item |
| System prompt | the same request builder as the bisection |
| Tools | the unit's **raw** schemas. Not the `wire1`-stripped form, and no `$ref` inlining |
| Output | `max_output_tokens` 512 |
| Retries | none |

- **Outcome per call:** `rejected` (HTTP 400), `accepted`, or `other`. `other` is any other error; it is recorded and
  never counted as either.
- **Transforms:** removal of a construct reuses the bisection's transform unchanged. It removes the keyword at every
  schema level and never touches property names. `type_list`, `type_null` and `empty_schema` are neutralised to a
  single type.
- **Instance order:** tools in unit order, then depth-first order within a schema. This order is deterministic.

### Phase A: reproduce and remove one construct at a time

1. **A0.** Send the raw unit (1 call per unit). If it is accepted, the unit is labelled `not reproduced`, and that unit
   stops.
2. **A1.** For each construct from the bisection's list that is present in the unit, send the unit with that construct
   removed **everywhere** (one call per construct). A construct that turns rejection into acceptance is a *flipping
   construct*.

| Unit | A0 calls | A1 calls | Constructs present |
|---|---|---|---|
| U1 | 1 | 4 | anyOf, enum, maxItems, minItems |
| U2 | 1 | 9 | additionalProperties, enum, maxItems, maxLength, maximum, minItems, minLength, minimum, pattern |
| U3 | 1 | 14 | the U2 set plus default, empty_schema, examples, title, type_list |
| U4 | 1 | 10 | $schema, enum, format, maxItems, maxLength, maximum, minItems, minLength, minimum, pattern |
| U5 | 1 | 11 | the U4 set without minItems, plus additionalProperties and propertyNames |

**Phase A total:** 53 calls.

### Phase B: additive reconstruction (the H-budget test)

**Scope:** up to two flipping constructs per unit. maxItems comes first if it flips; otherwise the order is the first
two flipping constructs in the list order above.

- **Base:** the unit with the construct removed everywhere. A1 showed that it is accepted.
- **Search:** add back the first *n* of its *N* instances in the fixed order. Binary search finds the smallest *n*
  that is rejected, assuming the outcome only flips once as *n* grows; the boundary pair (*n*−1 accepted, *n*
  rejected) is observed directly.
- **Two orders:** the search is run in the forward order and in the reverse order. Each order costs
  ≤ ⌈log₂N⌉ + 1 calls.
- **Single-instance check:** one call per order sends the base plus **only** the threshold instance.

**Classification:**

| Class | When |
|---|---|
| `aggregate` | The two orders give different threshold instances, and neither instance alone (added to the base) is rejected. Supports H-budget |
| `instance-critical` | Both orders give the same instance, and that instance alone is rejected. Supports H-instance |
| `inconsistent` | Anything else, such as a non-monotone boundary. Reported as such and never forced into a class |

### Phase C: duplication test (the replication arm of H-budget)

Only for units classed `aggregate`.

- Take the unit's tool with the most instances of the flipping construct; it was accepted alone.
- Send 2, then 3, then 4 renamed copies (name suffix `_c2`, `_c3`, …). Stop at the first rejection.
- At most 3 calls per unit.

### Phase D: magnitude

Only for a flipping construct with a numeric value (maxItems, maximum, minimum, maxLength, minLength, minItems).

- Send the raw unit with **every** value of that construct set to 1, then with every value doubled.
- 2 calls per unit. This answers whether the value matters, not only whether the keyword is present.

### Phase S: stability

- At the end, repeat A0 for every unit. Rejected calls are unbilled.
- Repeat the Phase B boundary pair once for maxItems.
- A boundary that does not reproduce marks that unit's class `unstable`.

## Exact call list and order

**Run order (budget-aware):**

1. A for all units, U1→U5.
2. B, first construct, for all units.
3. C.
4. D.
5. B, second construct.
6. S.

If the cap stops the run, the most informative calls have already been made. The cap cannot stop A0 or S when a unit
is still rejected, because rejected calls are unbilled.

**Planned calls:**

| Phase | Calls | Status |
|---|---|---|
| A | 53 | fixed |
| B | ≤ 10 per unit per construct, ≤ 100 in all | adaptive: the binary-search midpoints depend on earlier outcomes |
| C | ≤ 15 | adaptive |
| D | ≤ 10 | adaptive |
| S | ≤ 15 | adaptive |

- **Upper bound:** about 193 calls.
- **The frozen record:** the complete Phase A list, plus the deterministic rules for B to S, are written by the probe
  script's dry run to a private plan file before the first live call. The plan has unit membership, tool names and the
  per-call transform. Its sha256 is recorded in the private DECISIONS log at the same time.
- **The live run refuses to start** if the plan file's digest differs from the recorded one.

## Cost and cap

- **Measured basis:** the original bisection, 2026-10-29.
  - 102 calls; 63 were rejected and 0 of those were billed.
  - The 39 accepted calls cost ₹13.18 in total: mean ₹0.34, max ₹0.90.
- **Offline worst case per accepted call:** (characters / 3.84 × 1.25) prompt tokens, plus 512 output and 256
  thinking tokens.
  - U1 ₹0.80, U2 ₹0.76, U3 ₹1.85, U4 ₹0.86, U5 ₹2.12.
- **Worst case if every planned call were accepted:**
  - Phase A: ₹74.
  - Phases B, C and D: about ₹100.
  - Total: about ₹175.
- **Expected:** about ₹40–80. Roughly half of the calls are rejections, and billed tokens ran at 0.67–1.19 of the
  estimate.
- **Hard cap: ₹200, enforced by the existing spend ledger.**
  - The ledger is the same file as F (`vertex_ledger.ndjson`), so all Vertex spend stays in one record.
  - The ledger's absolute cap is set to the ledger total at the start of the probe plus ₹200. The script refuses to
    start if that total differs from the value recorded in DECISIONS when the run is authorised.
  - Each call reserves its worst case after a free countTokens and before generation, so the cap can never be
    exceeded. The per-call guard is ₹10, the same as the original probe.
  - The ledger's Vertex deadline, 2026-11-09 23:59 IST, applies.
  - F's ₹3,000 cap is separate and unchanged.

## What is published, and what changes

- **Published:** an aggregate-only report, `reports/provider_compat_ablation.{json,md}`, with the **POST-HOC** banner.
  - It contains unit labels U1–U5 and R-labels only: no tool name, schema text, server identifier, limit value or
    per-catalog hash.
  - Per unit, it gives the flipping constructs, the Phase B class, the duplication-test copy count and the magnitude
    result.
  - Raw call rows stay in the private data directory.
- **The lint rule changes only for a limit the probe isolates.** A limit counts as isolated when **all** of these hold:
  1. the same construct is `aggregate` or `instance-critical` and stable in ≥ 2 units;
  2. one stated quantity (for example, the count of maxItems instances in a request) separates every accepted probe
     request from every rejected one;
  3. the quantity can be computed statically from a schema.

  Otherwise the result is documentation only, and the diagnosis table is updated. Any new or changed check stays INFO
  and opt-in.
- **Validation and launch claims:** no launch claim follows from this probe. Every unit comes from the 24 catalogs used
  to build the rule. Validating a changed check requires catalogs **not** among those 24. That would need new calls
  outside this design, and is a separate proposal for GG.
- **Verification:** an independent verifier reviews the script against this design before the live run. A second
  verifier recomputes the report from the private rows afterwards.

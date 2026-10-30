# Provider-compat lint rule: post-hoc re-measurement after the array-length note

> **POST-HOC: rule changed after seeing these outcomes; in-sample; not a validation.**

The rule gained one INFO check (`provider_compat_array_length`) AFTER the 5 Vertex rejections below were seen and diagnosed. The same 24 catalogs and 29 probe calls (outcomes fixed) are re-scored. These numbers cannot support a validation claim. The original report, `provider_compat_validation.md`, is unchanged.

Zero-LLM, aggregate-only: no model or network call was made, and this report contains counts and construct-level descriptions only (no tool names, descriptions, schemas, server identifiers or per-server rows).

## Provenance

- Date: 2026-10-30
- Rule file sha256 `e255106dea116e7549a958a5157518e23e73c45b3b4f6783a31ae81e15a227d7`; run at HEAD `77148ddcfb7be12e6bb6aef4e90754c3b4357042` (`agentgauge/` tree dirty: False).
- Script sha256 (LF-normalised): `feabc9b3fd74181cd39d7aba38fb04d147e355a2e05ad2a7a9449e57d01918ef`
- Original report reproduced exactly by the unchanged checks: **True** (validation and prevalence blocks compared with `provider_compat_validation.json`).
- Input files: same private files and hashes as the original report (`provider_compat_validation.md`, Provenance).

## Headline

- Vertex, any-violation (the gate predicate): unchanged, recall 1/5 = 0.200 [0.036, 0.624], precision 1/1 = 1.000 [0.207, 1.000]. The new check is INFO tier, so it cannot change it. The launch-claim gate is therefore **still NOT met**.
- Vertex, any-finding: unchanged (TP 5 / FP 13 / FN 0 / TN 6 -> TP 5 / FP 13 / FN 0 / TN 6) because the pre-existing `provider_compat_schema_size` note already fired on all 5 rejections and on every catalog that has `maxItems`.
- Vertex, the new check on its own: TP 5 / FP 2 / FN 0 / TN 17; precision 5/7 = 0.714 [0.359, 0.918], recall 5/5 = 1.000 [0.566, 1.000], specificity 17/19 = 0.895 [0.686, 0.971]. In-sample and selected from the documented contributors because the bisection implicated it.
- No documented limit explains R2-R5 as a violation. The docs name the contributor qualitatively and publish no threshold, so none could be encoded as a violation-tier check. Recall of any-violation therefore stays 1/5.

## Per-miss diagnosis (construct level)

Source: the existing Vertex probe and bisection logs only (private; no new call of any kind was
made). The five rejected catalogs are R1-R5, numbered by ascending sha256 of the server
identifier; the mapping is deliberately not recorded. R1 is the one the `$ref` check caught;
R2-R5 are the four misses. The bisection log stores only accept/reject per tool subset and
per single-keyword removal, so a construct can be pinned only where such a removal was run.

**Reading guide.** "Unit" = the smallest tool subset the bisection could still show rejected.
"Flips" = removal of that single keyword (everywhere in the unit) made the unit accepted;
"does not flip" = removal left it rejected. The probe's HTTP 400 body is the opaque
"Request contains an invalid argument." with no reason text, so identifying the cause with the
documented "too many states" wording is an inference, not an observation.

| Label | Smallest unit established | Single-keyword removals that flip it | Constructs present in the unit | Class |
|---|---|---|---|---|
| R1 (caught by `$ref`) | one tool | `maxItems` only (not: `anyOf`, `$schema`, `additionalProperties`, `minLength`, `maxLength`, `enum`, type-null). Removing or inlining `$ref` was never run. | 3 arrays with `maxItems`=100; 2 local `$ref` that are not direct children of `$defs`; 1 `anyOf` | `$ref` check is DOCUMENTED, but its TP is **not shown causal**: the only keyword that flips it is `maxItems` |
| R2 (miss) | one tool | `maxItems` or `oneOf` (not: `const`, `default`, `$schema`, `minimum`, `maximum`, `minLength`, `maxLength`, `minItems`, `enum`) | 100 properties, depth 7, 16 arrays with `maxItems` (limits 5 to 10), 13 of them nested inside an array and under a `oneOf` branch | DOCUMENTED (qualitative; see below) |
| R3 (miss) | a pair of tools, each accepted alone; no keyword-removal run | none run | per tool: depth 6, 11 properties, one array with `maxItems`=20 and a `minItems` whose items contain another array, 4 enums (3 to 7 values), 1 `anyOf`; the two tools are near-identical in shape and are the only `maxItems` in the 29-tool catalog | UNDETERMINED from existing logs (which construct); the only documented contributor present is `maxItems` on nested arrays |
| R4 (miss) | at least four independent rejected units: two single tools, a 4-tool group whose two 2-tool halves are each accepted, and a 32-tool group whose two 16-tool halves are each accepted | single tool A: `maxItems` or `oneOf` (not: `const`, `additionalProperties`, empty schema, `maxLength`); single tool B: `maxItems` or `maximum` (not: `anyOf`, `pattern`, `additionalProperties`, `minimum`, `minLength`, `maxLength`, `minItems`, type-null) | each single tool has one array with `maxItems`=100 (A also has one `oneOf` and 6 `const`; B has 2 `minimum`/2 `maximum` pairs and 8 `pattern`); the 4-tool group has `maxItems` 20, 50, 50 across three tools; the 32-tool group has `maxItems` 2 to 200 across five arrays; whole catalog: 15 arrays with `maxItems` (2 to 200) | the two single-tool units: DOCUMENTED (qualitative; large `maxItems`); the two group-only units: UNDETERMINED |
| R5 (miss) | a 3-tool group; its 1-tool and 2-tool parts are each accepted; no keyword-removal run | none run | arrays with `maxItems` 200 and 50 in two of the three tools; the largest tool also has 3 `minimum`/3 `maximum` pairs, string length limits, `pattern`/`format`; whole catalog: 5 arrays with `maxItems` (6 to 200) | UNDETERMINED from existing logs |

### What the evidence supports, and how strongly

1. **Every rejected catalog contains `maxItems`; most accepted ones do not.** 5 of 5 rejected
   catalogs carry at least one array with `maxItems`; 17 of 19 accepted catalogs carry none (the
   other 2 carry 7 such arrays each, largest limits 10 and 50, and were accepted). This is a
   descriptive in-sample contingency, not a test.
2. **Where a removal was run, `maxItems` always flips.** Of the 4 single-tool units with
   keyword-removal runs (R1, R2, R4 x2), removing `maxItems` alone made all 4 accepted; no other
   single keyword flips more than 2 of them (`oneOf` flips 2, `maximum` flips 1). High
   confidence for "an array length limit participates" in those 4 units; it does NOT show that
   `maxItems` alone suffices (the units are also accepted after one other removal in 3 of 4
   cases, so a second construct is needed there too).
3. **Size of the limit is not the whole story.** R2's arrays all have limits of at most 10 yet
   the unit is rejected, so "large `maxItems`" in the docs' wording does not describe R2; count
   and nesting (13 limited arrays nested under a `oneOf` branch in one tool) fit better. Not
   established.
4. **Aggregation across tools.** R3, R5 and two R4 units are rejected only as a group while every
   smaller part is accepted. That is consistent with an additive budget over the whole
   function-declaration set, which no page checked states (UNDOCUMENTED, below).
5. **R1's `$ref` TP is weaker than it looks.** The `$ref` check fired on R1 and R1 was
   rejected, but the bisection shows R1's rejection flips on removing `maxItems` and was never
   tested for `$ref` removal. The single TP of `provider_compat_ref` is therefore compatible with
   coincidence.

### Documentation search (fetched 2026-10-30; page "Last updated" in brackets)

Pages checked for a documented limit that covers the misses:

- Vertex function calling, <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling> (redirects to `.../gemini-enterprise-agent-platform/models/tools/function-calling/`) [2026-10-28]
- Vertex function-calling model reference, <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/function-calling> [2026-10-28]
- Vertex structured output, <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output> (redirects to `.../gemini-enterprise-agent-platform/models/capabilities/control-generated-output`) [2026-10-28]
- Gemini API function calling, <https://ai.google.dev/gemini-api/docs/function-calling> [2026-09-23]
- Gemini API structured output, <https://ai.google.dev/gemini-api/docs/structured-output> [2026-10-21]
- Searched with no relevant hit: Vertex quotas page, Vertex `Schema` REST reference, Gemini API troubleshooting page (no schema-complexity, `maxItems` or function-declaration size text).

**DOCUMENTED (qualitative, no number, sibling feature).** Two pages name array length limits as
a cause of schema-complexity rejection. Both are about structured-output response schemas, not
function declarations:

- Gemini API structured output: "Schema complexity: Very large or deeply nested schemas may be rejected with a 400 INVALID_ARGUMENT error that says the schema produces a constraint with too many states or too much branching for serving. Common causes are large maxItems limits (especially on nested arrays), very long property or enum names, enums with many values, long runs of optional properties, anyOf with many alternatives, and numeric minimum/maximum bounds. To fix it, lower or remove nested array limits, shorten names, or intersperse required properties among optional ones." (<https://ai.google.dev/gemini-api/docs/structured-output>, section Limitations)
- Vertex structured output: "A complex schema can result in an InvalidArgument: 400 error. Complexity might come from long property names, long array length limits, enums with many values, objects with lots of optional properties, or a combination of these factors." and the fixes "Flatten nested arrays." and "Reduce the number of properties with constraints, such as numbers with minimum and maximum limits." (<https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output>, section Considerations)
- Function-calling pages say only: "Only a subset of the OpenAPI schema is supported. For any mode, the API may reject very large or deeply nested schemas." (Gemini API) and list the supported attributes as "type, nullable, required, format, description, properties, items, enum, anyOf, $ref, and $defs. Remaining attributes are not supported." (Vertex). `maxItems`, `minimum`, `maximum`, `oneOf`, `const` are not in that list, yet 11 accepted catalogs carry validation-only keywords (the schema-size note fires on 16 of the 24) and removing `maxItems` flips rejections, so on this endpoint they are evidently processed rather than ignored; the pages do not say so.

**UNDOCUMENTED (searched; nothing found on any page above):** (a) any numeric threshold for
"large" / "long" / "many" in the complexity wording; (b) that the complexity budget is
aggregated across all function declarations in a request (R3, R5, two R4 units); (c) that the
structured-output complexity rule applies to function declarations in mode ANY at all (the
function-calling pages state only the generic "very large or deeply nested" sentence).

**Documented limits found that are unrelated to these misses and NOT added:** at most 128
function declarations per request (model reference page: "The maximum number of function
declarations that can be provided with the request is 128."; the largest catalog here has 82
tools) and self-reference through `$defs` limited to two levels ("Recursion depth in defs
(self-reference) is limited to two."). Out of scope for a miss diagnosis; candidates for a
separate change.

### What changed in the rule, and why only this

Added `provider_compat_array_length` (INFO, opt-in under `--provider-compat`): fires when any
array declares `maxItems`. It encodes the one documented, structurally checkable contributor that
the bisection also implicates, **by presence only**: the docs give no number, so no threshold is
encoded, and the finding says it makes no claim of rejection. Not encoded, deliberately: size
cut-offs for `maxItems`, nesting-depth cut-offs, per-catalog count budgets (all inferred from
this sample, none documented), and the other qualitative contributors (long names, many enum
values, optional-property runs, `anyOf` breadth, numeric bounds), which have no checkable
definition without inventing a threshold. **Selection caveat:** `maxItems` was chosen from the
documented contributors because the bisection implicated it; the post-hoc numbers below are
therefore optimistic for it by construction.

## Before / after: Vertex (primary), 24 catalogs

POST-HOC. n = 24 (5 rejected, 19 accepted).

### Before (rule as originally validated)

| Predicate | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity |
|---|---|---|---|---|---|---|---|
| `provider_compat_tool_name` | 0 | 0 | 5 | 19 | undefined (0/0) | 0/5 = 0.000 [0.000, 0.434] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_schema_depth` | 0 | 0 | 5 | 19 | undefined (0/0) | 0/5 = 0.000 [0.000, 0.434] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_ref` | 1 | 0 | 4 | 19 | 1/1 = 1.000 [0.207, 1.000] | 1/5 = 0.200 [0.036, 0.624] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_schema_size` | 5 | 11 | 0 | 8 | 5/16 = 0.312 [0.142, 0.556] | 5/5 = 1.000 [0.566, 1.000] | 8/19 = 0.421 [0.231, 0.637] |
| `provider_compat_tool_count` | 5 | 4 | 0 | 15 | 5/9 = 0.556 [0.267, 0.811] | 5/5 = 1.000 [0.566, 1.000] | 15/19 = 0.789 [0.567, 0.915] |
| `any_violation` | 1 | 0 | 4 | 19 | 1/1 = 1.000 [0.207, 1.000] | 1/5 = 0.200 [0.036, 0.624] | 19/19 = 1.000 [0.832, 1.000] |
| `any_finding` | 5 | 13 | 0 | 6 | 5/18 = 0.278 [0.125, 0.509] | 5/5 = 1.000 [0.566, 1.000] | 6/19 = 0.316 [0.154, 0.540] |

### After (original checks + `provider_compat_array_length`)

| Predicate | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity |
|---|---|---|---|---|---|---|---|
| `provider_compat_tool_name` | 0 | 0 | 5 | 19 | undefined (0/0) | 0/5 = 0.000 [0.000, 0.434] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_schema_depth` | 0 | 0 | 5 | 19 | undefined (0/0) | 0/5 = 0.000 [0.000, 0.434] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_ref` | 1 | 0 | 4 | 19 | 1/1 = 1.000 [0.207, 1.000] | 1/5 = 0.200 [0.036, 0.624] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_schema_size` | 5 | 11 | 0 | 8 | 5/16 = 0.312 [0.142, 0.556] | 5/5 = 1.000 [0.566, 1.000] | 8/19 = 0.421 [0.231, 0.637] |
| `provider_compat_tool_count` | 5 | 4 | 0 | 15 | 5/9 = 0.556 [0.267, 0.811] | 5/5 = 1.000 [0.566, 1.000] | 15/19 = 0.789 [0.567, 0.915] |
| `provider_compat_array_length` | 5 | 2 | 0 | 17 | 5/7 = 0.714 [0.359, 0.918] | 5/5 = 1.000 [0.566, 1.000] | 17/19 = 0.895 [0.686, 0.971] |
| `any_violation` | 1 | 0 | 4 | 19 | 1/1 = 1.000 [0.207, 1.000] | 1/5 = 0.200 [0.036, 0.624] | 19/19 = 1.000 [0.832, 1.000] |
| `any_finding` | 5 | 13 | 0 | 6 | 5/18 = 0.278 [0.125, 0.509] | 5/5 = 1.000 [0.566, 1.000] | 6/19 = 0.316 [0.154, 0.540] |

## Before / after: Gemini API preflight (secondary; not independent of Vertex)

POST-HOC. n = 12 (3 rejected, 9 accepted); a subset of the 24 catalogs on a different endpoint, not pooled with the table above.

### Before

| Predicate | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity |
|---|---|---|---|---|---|---|---|
| `provider_compat_tool_name` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `provider_compat_schema_depth` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `provider_compat_ref` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `provider_compat_schema_size` | 3 | 5 | 0 | 4 | 3/8 = 0.375 [0.137, 0.694] | 3/3 = 1.000 [0.439, 1.000] | 4/9 = 0.444 [0.189, 0.733] |
| `provider_compat_tool_count` | 3 | 2 | 0 | 7 | 3/5 = 0.600 [0.231, 0.882] | 3/3 = 1.000 [0.439, 1.000] | 7/9 = 0.778 [0.453, 0.937] |
| `any_violation` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `any_finding` | 3 | 6 | 0 | 3 | 3/9 = 0.333 [0.121, 0.646] | 3/3 = 1.000 [0.439, 1.000] | 3/9 = 0.333 [0.121, 0.646] |

### After

| Predicate | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity |
|---|---|---|---|---|---|---|---|
| `provider_compat_tool_name` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `provider_compat_schema_depth` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `provider_compat_ref` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `provider_compat_schema_size` | 3 | 5 | 0 | 4 | 3/8 = 0.375 [0.137, 0.694] | 3/3 = 1.000 [0.439, 1.000] | 4/9 = 0.444 [0.189, 0.733] |
| `provider_compat_tool_count` | 3 | 2 | 0 | 7 | 3/5 = 0.600 [0.231, 0.882] | 3/3 = 1.000 [0.439, 1.000] | 7/9 = 0.778 [0.453, 0.937] |
| `provider_compat_array_length` | 3 | 0 | 0 | 9 | 3/3 = 1.000 [0.439, 1.000] | 3/3 = 1.000 [0.439, 1.000] | 9/9 = 1.000 [0.701, 1.000] |
| `any_violation` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `any_finding` | 3 | 6 | 0 | 3 | 3/9 = 0.333 [0.121, 0.646] | 3/3 = 1.000 [0.439, 1.000] | 3/9 = 0.333 [0.121, 0.646] |

## Prevalence on the held Smithery set, before -> after

Same 3138 lintable catalogs as the original report (the first-listed Smithery servers, not a random sample; prevalence describes this held set only). Only the new predicate and the two aggregates that could move are shown; every other column is unchanged.

| Stratum | n | `provider_compat_array_length` before -> after | `any_violation` before -> after | `any_finding` before -> after |
|---|---|---|---|---|
| ALL | 3138 | n/a (new) -> 475/3138 = 0.151 [0.139, 0.164] | 34/3138 = 0.011 [0.008, 0.015] -> 34/3138 = 0.011 [0.008, 0.015] | 1808/3138 = 0.576 [0.559, 0.593] -> 1808/3138 = 0.576 [0.559, 0.593] |
| below_S(1-2 tools) | 422 | n/a (new) -> 20/422 = 0.047 [0.031, 0.072] | 0/422 = 0.000 [0.000, 0.009] -> 0/422 = 0.000 [0.000, 0.009] | 124/422 = 0.294 [0.252, 0.339] -> 124/422 = 0.294 [0.252, 0.339] |
| S | 722 | n/a (new) -> 62/722 = 0.086 [0.068, 0.109] | 4/722 = 0.006 [0.002, 0.014] -> 4/722 = 0.006 [0.002, 0.014] | 305/722 = 0.422 [0.387, 0.459] -> 305/722 = 0.422 [0.387, 0.459] |
| M | 1093 | n/a (new) -> 177/1093 = 0.162 [0.141, 0.185] | 11/1093 = 0.010 [0.006, 0.018] -> 11/1093 = 0.010 [0.006, 0.018] | 584/1093 = 0.534 [0.505, 0.564] -> 584/1093 = 0.534 [0.505, 0.564] |
| L | 628 | n/a (new) -> 121/628 = 0.193 [0.164, 0.225] | 9/628 = 0.014 [0.008, 0.027] -> 9/628 = 0.014 [0.008, 0.027] | 522/628 = 0.831 [0.800, 0.858] -> 522/628 = 0.831 [0.800, 0.858] |
| XL | 273 | n/a (new) -> 95/273 = 0.348 [0.294, 0.406] | 10/273 = 0.037 [0.020, 0.066] -> 10/273 = 0.037 [0.020, 0.066] | 273/273 = 1.000 [0.986, 1.000] -> 273/273 = 1.000 [0.986, 1.000] |

## Caveats

- POST-HOC and in-sample: the rule was changed after these outcomes were seen. The post-hoc precision of the new check is optimistic by construction.
- n = 24 catalogs with 5 positives; intervals are Wilson 95 % and wide.
- The probe's rejection bodies carry no reason text; the link to the documented 'too many states' failure is an inference.
- Prevalence says how often a note appears, not how often a provider rejects.

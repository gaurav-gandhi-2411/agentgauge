# Provider-compat lint rule: post-hoc re-measurement after two documented-limit notes

> **POST-HOC: rule changed after seeing these outcomes; in-sample; not a validation.**

The rule gained two INFO checks (`provider_compat_array_length`, `provider_compat_unsupported_attribute`) AFTER the 5 Vertex rejections below were seen and diagnosed. The same 24 catalogs and 29 probe calls (outcomes fixed) are re-scored. These numbers cannot support a validation claim. The original report, `provider_compat_validation.md`, is unchanged.

Zero-LLM, aggregate-only: no model or network call was made, and this report contains counts and construct-level descriptions only (no tool names, descriptions, schemas, server identifiers or per-server rows).

## Provenance

- Date: 2026-10-30
- Rule file sha256 `44c6ac3be41057af153b489e82c0ee0883007b49cb2933fe9c6f0845fd82b105`; run at HEAD `33ec49121e2229b947092b3a662d595a95b78893` (`agentgauge/` tree dirty: False).
- Script sha256 (LF-normalised): `743b7a270a8933af0e8c0311125d16b225ce02bb9e8e5a0abe247101e0ed9481`
- Original report reproduced exactly by the unchanged checks: **True** (validation and prevalence blocks compared with `provider_compat_validation.json`).
- Input files: same private files and hashes as the original report (`provider_compat_validation.md`, Provenance).

## Headline

- **Selection bias (array-length note).** `maxItems` was picked from the documented contributors because the bisection had already implicated it, so its precision (5/7 = 0.714 [0.359, 0.918]) is selection-biased by construction; it cannot be read as validation.
- **No added coverage.** any_finding is unchanged by the array-length note (TP 5 / FP 13 / FN 0 / TN 6 -> TP 5 / FP 13 / FN 0 / TN 6): it adds nothing beyond `provider_compat_schema_size`, which already fires on every rejected catalog and on every catalog with `maxItems`. The unsupported-attribute check changes any_finding to TP 5 / FP 15 / FN 0 / TN 4: no new true positive, only added false positives.
- Vertex, any-violation (the gate predicate): unchanged, recall 1/5 = 0.200 [0.036, 0.624], precision 1/1 = 1.000 [0.207, 1.000]. Both new checks are INFO tier, so they cannot change it. The launch-claim gate is therefore **still NOT met**.
- Vertex, array-length note alone: TP 5 / FP 2 / FN 0 / TN 17; precision 5/7 = 0.714 [0.359, 0.918], recall 5/5 = 1.000 [0.566, 1.000], specificity 17/19 = 0.895 [0.686, 0.971].
- Vertex, unsupported-attribute check alone (documented list, no selection from outcomes): TP 5 / FP 15 / FN 0 / TN 4; precision 5/20 = 0.250 [0.112, 0.469], recall 5/5 = 1.000 [0.566, 1.000], specificity 4/19 = 0.211 [0.085, 0.433]. The rule was still changed after the outcomes were seen, so this is in-sample too.
- No documented limit explains R2-R5 as a violation. The docs name the contributor qualitatively and publish no threshold, so none could be encoded as a violation-tier check. Recall of any-violation therefore stays 1/5.

## Per-miss diagnosis (construct level)

Source: the existing Vertex probe and bisection logs (private) and, for the multi-tool units,
the later post-hoc ablation probe (design commit 3d5d6e6; aggregate report
`reports/provider_compat_ablation.md`). This script makes no call of any kind. The five rejected catalogs are R1-R5, arbitrary labels; the mapping is deliberately not
recorded, and this table is kept at construct level: no identifiers, catalog sizes or limit
values. It does give the size of the smallest rejected unit (one tool, a pair, a small group) and
coarse descriptors such as "small limits", because those are the diagnostic finding. R1 is the one the `$ref` check caught;
R2-R5 are the four misses. The bisection log stores only accept/reject per tool subset and per
single-keyword removal, so a construct can be pinned only where such a removal was run (for the multi-tool units, the
ablation probe ran them).

**Reading guide.** "Unit" = the smallest tool subset the bisection could still show rejected.
"Flips" = removal of that single keyword (everywhere in the unit) made the unit accepted;
"does not flip" = removal left it rejected. The probe's HTTP 400 body is the opaque
"Request contains an invalid argument." with no reason text, so identifying the cause with the
documented "too many states" wording is an inference, not an observation.

| Label | Smallest unit established | Single-keyword removals that flip it | Constructs present in the unit | Class |
|---|---|---|---|---|
| R1 (caught by `$ref`) | one tool | `maxItems` only; other single removals tried did not flip it. Removing or inlining `$ref` was never run. | arrays with `maxItems`; local `$ref` that are not direct children of `$defs`; `anyOf` | `$ref` check is DOCUMENTED, but its TP is **not shown causal**: the only keyword that flips it is `maxItems` |
| R2 (miss) | one tool | `maxItems` or `oneOf`; other single removals tried did not flip it | many properties, moderate nesting, many arrays with `maxItems` (all with small limits), most of them nested inside an array and under a `oneOf` branch | documented contributor (maxItems) present; magnitude not covered by any documented number |
| R3 (miss) | a pair of tools, each accepted alone | `maxItems` or `enum` (post-hoc probe) | per tool: moderate nesting, an array with `maxItems` whose items contain another array, several enums, an `anyOf`; the two tools are near-identical in shape and are the only tools in their catalog with `maxItems` | post-hoc probe: needs a combination of constructs; no single statically computable limit separates accepted from rejected (see `reports/provider_compat_ablation.md`). Aggregate (several instances together, no single instance responsible); renamed copies of one tool were accepted |
| R4 (miss) | at least four independent rejected units: two single tools and two multi-tool groups (a 4-tool and a 32-tool unit) whose halves are each accepted | single tool A: `maxItems` or `oneOf`; single tool B: `maxItems` or `maximum`; other single removals tried did not flip either; 4-tool group (post-hoc probe): `maxItems` or `maximum` (`maximum` inconsistent: the forward and reverse threshold instances disagree, one is rejected alone; measured once); 32-tool group: `maxItems` or `enum` | each single tool has an array with `maxItems` (A also has one `oneOf`; B also has paired `minimum`/`maximum` and `pattern`); both groups carry `maxItems` across several tools | the two single-tool units: documented contributor (maxItems) present; magnitude not covered by any documented number; the two group-only units: post-hoc probe: needs a combination of constructs; no single statically computable limit separates accepted from rejected (see `reports/provider_compat_ablation.md`) |
| R5 (miss) | TWO independent group-only units (a 3-tool and a 10-tool group), each with every smaller part accepted. Correction: an earlier version of this row named only the 3-tool group; the second unit came from re-deriving the units for the ablation probe | 3-tool unit: `maxItems` or `format`, with `format` instance-critical (one specific instance is needed); 10-tool unit: `maximum` only (removing `maxItems` does not flip it) | 3-tool unit: arrays with `maxItems` in two of the three tools; the largest tool also has paired `minimum`/`maximum`, string length limits, `pattern`/`format`. 10-tool unit: many paired `minimum`/`maximum`, plus `enum`, `format`, `pattern`, string length limits; `maxItems` present but not flipping | post-hoc probe: needs a combination of constructs; no single statically computable limit separates accepted from rejected (see `reports/provider_compat_ablation.md`). The 10-tool unit has no stability boundary, so it is unreplicated |

### What the evidence supports, and how strongly

1. **Every rejected catalog contains `maxItems`; most accepted ones do not.** 5 of 5 rejected
   catalogs carry at least one array with `maxItems`; 17 of 19 accepted catalogs carry none (the
   other 2 carry some and were accepted). This is a descriptive in-sample contingency, not a test.
2. **In every single-tool unit with a removal run, `maxItems` flips; in the multi-tool units it
   flips in 4 of 5.** Of the 4 single-tool units with
   keyword-removal runs (R1, R2, R4 x2), removing `maxItems` alone made all 4 accepted; no other
   single keyword flips more than 2 of them (`oneOf` flips 2, `maximum` flips 1). High
   confidence for "an array length limit participates" in those 4 units; it does NOT show that
   `maxItems` alone suffices (the units are also accepted after one other removal in 3 of 4
   cases, so a second construct is needed there too). In the 5 multi-tool units (post-hoc probe)
   removing `maxItems` flipped 4; the 10-tool R5 unit flipped only on removing `maximum`, so
   `maxItems` is not necessary everywhere.
3. **Size of the limit is not the whole story.** R2's array limits are all small yet the unit
   is rejected, so "large `maxItems`" in the docs' wording does not describe R2; the number of
   limited arrays and their nesting fit better. Not established. This is why the R2 and R4
   single-tool rows carry the label "documented contributor (maxItems) present; magnitude not
   covered by any documented number" rather than a bare DOCUMENTED.
4. **Aggregation across tools: probed, not isolated.** Five multi-tool units (R3, two R4, two R5)
   are rejected only as a group while every smaller part is accepted. The post-hoc ablation
   probe found no single construct instance responsible in most of them, but could not show an
   additive budget: renamed copies of one tool, up to 4, were accepted in 3 units, and no single
   statically computable quantity separated accepted from rejected requests, so the evidence is
   compatible with a specific conjunction of instances as much as with a budget. No page checked
   states such a limit (UNDOCUMENTED, below). All of it is in-sample, one model.
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
- Function-calling pages: the Gemini API page says only "Only a subset of the OpenAPI schema is supported. For any mode, the API may reject very large or deeply nested schemas." and gives NO attribute list. The Vertex page says "We support the following attributes: type, nullable, required, format, description, properties, items, enum, anyOf, $ref, and $defs. Remaining attributes are not supported." That list is checked by `provider_compat_unsupported_attribute` (section below). `maxItems`, `minimum`, `maximum`, `oneOf`, `const` are not in it, yet 11 accepted catalogs carry validation-only keywords (the schema-size note fires on 16 of the 24) and removing `maxItems` flips rejections, so on this endpoint they are evidently processed rather than ignored; the pages do not say so.

**UNDOCUMENTED (searched; nothing found on any page above):** (a) any numeric threshold for
"large" / "long" / "many" in the complexity wording; (b) that the complexity budget is
aggregated across all function declarations in a request (the five multi-tool units); (c) that the
structured-output complexity rule applies to function declarations in mode ANY at all (the
function-calling pages state only the generic "very large or deeply nested" sentence).

**Documented limits found that are unrelated to these misses and NOT added:** at most 128
function declarations per request (model reference page: "The maximum number of function
declarations that can be provided with the request is 128.") and self-reference through `$defs`
limited to two levels ("Recursion depth in defs (self-reference) is limited to two."). Out of
scope for a miss diagnosis; candidates for a separate change.

### What changed in the rule, and why only these

Added two INFO checks, opt-in under `--provider-compat`, both by presence only.
`provider_compat_array_length` fires when any array declares `maxItems`: the one documented,
structurally checkable contributor that the bisection also implicates. The docs give no number,
so no threshold is encoded and the finding says it makes no claim of rejection.
`provider_compat_unsupported_attribute` fires when a schema node carries a keyword outside the
Vertex-documented supported-attribute list; it quotes the sentence and URL, says unsupported
attributes may be ignored rather than rejected, and encodes no threshold. Not encoded,
deliberately: size cut-offs for `maxItems`, nesting-depth cut-offs, per-catalog count budgets
(all inferred from this sample, none documented), and the other qualitative contributors (long
names, many enum values, optional-property runs, `anyOf` breadth, numeric bounds), which have no
checkable definition without inventing a threshold. The later ablation probe isolated no limit,
so no check was added or changed on its account. **Selection caveat:** `maxItems` was chosen
from the documented contributors because the bisection implicated it; the post-hoc numbers below
are therefore optimistic for it by construction.

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

### After (original checks + both new INFO checks)

| Predicate | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity |
|---|---|---|---|---|---|---|---|
| `provider_compat_tool_name` | 0 | 0 | 5 | 19 | undefined (0/0) | 0/5 = 0.000 [0.000, 0.434] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_schema_depth` | 0 | 0 | 5 | 19 | undefined (0/0) | 0/5 = 0.000 [0.000, 0.434] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_ref` | 1 | 0 | 4 | 19 | 1/1 = 1.000 [0.207, 1.000] | 1/5 = 0.200 [0.036, 0.624] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_schema_size` | 5 | 11 | 0 | 8 | 5/16 = 0.312 [0.142, 0.556] | 5/5 = 1.000 [0.566, 1.000] | 8/19 = 0.421 [0.231, 0.637] |
| `provider_compat_tool_count` | 5 | 4 | 0 | 15 | 5/9 = 0.556 [0.267, 0.811] | 5/5 = 1.000 [0.566, 1.000] | 15/19 = 0.789 [0.567, 0.915] |
| `provider_compat_array_length` | 5 | 2 | 0 | 17 | 5/7 = 0.714 [0.359, 0.918] | 5/5 = 1.000 [0.566, 1.000] | 17/19 = 0.895 [0.686, 0.971] |
| `provider_compat_unsupported_attribute` | 5 | 15 | 0 | 4 | 5/20 = 0.250 [0.112, 0.469] | 5/5 = 1.000 [0.566, 1.000] | 4/19 = 0.211 [0.085, 0.433] |
| `any_violation` | 1 | 0 | 4 | 19 | 1/1 = 1.000 [0.207, 1.000] | 1/5 = 0.200 [0.036, 0.624] | 19/19 = 1.000 [0.832, 1.000] |
| `any_finding` | 5 | 15 | 0 | 4 | 5/20 = 0.250 [0.112, 0.469] | 5/5 = 1.000 [0.566, 1.000] | 4/19 = 0.211 [0.085, 0.433] |
| `posthoc_selected_keywords_present[maxItems,oneOf,maximum]` | 5 | 5 | 0 | 14 | 5/10 = 0.500 [0.237, 0.763] | 5/5 = 1.000 [0.566, 1.000] | 14/19 = 0.737 [0.512, 0.882] |

### any_finding by stage (Vertex)

| Stage | any_finding | Precision [95% CI] | Recall [95% CI] | Specificity |
|---|---|---|---|---|
| 0: original five checks | TP 5 / FP 13 / FN 0 / TN 6 | 5/18 = 0.278 [0.125, 0.509] | 5/5 = 1.000 [0.566, 1.000] | 6/19 = 0.316 [0.154, 0.540] |
| 1: + array-length note | TP 5 / FP 13 / FN 0 / TN 6 | 5/18 = 0.278 [0.125, 0.509] | 5/5 = 1.000 [0.566, 1.000] | 6/19 = 0.316 [0.154, 0.540] |
| 2: + unsupported-attribute note | TP 5 / FP 15 / FN 0 / TN 4 | 5/20 = 0.250 [0.112, 0.469] | 5/5 = 1.000 [0.566, 1.000] | 4/19 = 0.211 [0.085, 0.433] |

### The selected-keyword predicate (POST-HOC SELECTED, illustration only)

`posthoc_selected_keywords_present[maxItems,oneOf,maximum]` fires when any of `maxItems`, `oneOf`, `maximum` is present. These three keywords were selected AFTER seeing which single-keyword removals flipped a rejection in the bisection, so this row is the optimistic ceiling of the idea, not an estimate of anything. It is not a check and is not in the rule. Vertex: TP 5 / FP 5 / FN 0 / TN 14; precision 5/10 = 0.500 [0.237, 0.763], recall 5/5 = 1.000 [0.566, 1.000], specificity 14/19 = 0.737 [0.512, 0.882].

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
| `provider_compat_unsupported_attribute` | 3 | 7 | 0 | 2 | 3/10 = 0.300 [0.108, 0.603] | 3/3 = 1.000 [0.439, 1.000] | 2/9 = 0.222 [0.063, 0.547] |
| `any_violation` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `any_finding` | 3 | 7 | 0 | 2 | 3/10 = 0.300 [0.108, 0.603] | 3/3 = 1.000 [0.439, 1.000] | 2/9 = 0.222 [0.063, 0.547] |
| `posthoc_selected_keywords_present[maxItems,oneOf,maximum]` | 3 | 2 | 0 | 7 | 3/5 = 0.600 [0.231, 0.882] | 3/3 = 1.000 [0.439, 1.000] | 7/9 = 0.778 [0.453, 0.937] |

## Prevalence on the held Smithery set, before -> after

Same 3138 lintable catalogs as the original report (the first-listed Smithery servers, not a random sample; prevalence describes this held set only). Only the new predicates, the two aggregates that could move and the post-hoc selected-keyword predicate are shown; every other column is unchanged.

| Stratum | n | `provider_compat_array_length` before -> after | `provider_compat_unsupported_attribute` before -> after | `any_violation` before -> after | `any_finding` before -> after | `posthoc_selected_keywords_present[maxItems,oneOf,maximum]` before -> after |
|---|---|---|---|---|---|---|
| ALL | 3138 | n/a (new) -> 475/3138 = 0.151 [0.139, 0.164] | n/a (new) -> 2242/3138 = 0.714 [0.698, 0.730] | 34/3138 = 0.011 [0.008, 0.015] -> 34/3138 = 0.011 [0.008, 0.015] | 1808/3138 = 0.576 [0.559, 0.593] -> 2369/3138 = 0.755 [0.740, 0.770] | n/a (new) -> 1263/3138 = 0.402 [0.385, 0.420] |
| below_S(1-2 tools) | 422 | n/a (new) -> 20/422 = 0.047 [0.031, 0.072] | n/a (new) -> 201/422 = 0.476 [0.429, 0.524] | 0/422 = 0.000 [0.000, 0.009] -> 0/422 = 0.000 [0.000, 0.009] | 124/422 = 0.294 [0.252, 0.339] -> 205/422 = 0.486 [0.438, 0.533] | n/a (new) -> 73/422 = 0.173 [0.140, 0.212] |
| S | 722 | n/a (new) -> 62/722 = 0.086 [0.068, 0.109] | n/a (new) -> 455/722 = 0.630 [0.594, 0.665] | 4/722 = 0.006 [0.002, 0.014] -> 4/722 = 0.006 [0.002, 0.014] | 305/722 = 0.422 [0.387, 0.459] -> 467/722 = 0.647 [0.611, 0.681] | n/a (new) -> 228/722 = 0.316 [0.283, 0.351] |
| M | 1093 | n/a (new) -> 177/1093 = 0.162 [0.141, 0.185] | n/a (new) -> 835/1093 = 0.764 [0.738, 0.788] | 11/1093 = 0.010 [0.006, 0.018] -> 11/1093 = 0.010 [0.006, 0.018] | 584/1093 = 0.534 [0.505, 0.564] -> 839/1093 = 0.768 [0.742, 0.792] | n/a (new) -> 507/1093 = 0.464 [0.434, 0.494] |
| L | 628 | n/a (new) -> 121/628 = 0.193 [0.164, 0.225] | n/a (new) -> 509/628 = 0.811 [0.778, 0.839] | 9/628 = 0.014 [0.008, 0.027] -> 9/628 = 0.014 [0.008, 0.027] | 522/628 = 0.831 [0.800, 0.858] -> 585/628 = 0.932 [0.909, 0.949] | n/a (new) -> 281/628 = 0.447 [0.409, 0.487] |
| XL | 273 | n/a (new) -> 95/273 = 0.348 [0.294, 0.406] | n/a (new) -> 242/273 = 0.886 [0.843, 0.919] | 10/273 = 0.037 [0.020, 0.066] -> 10/273 = 0.037 [0.020, 0.066] | 273/273 = 1.000 [0.986, 1.000] -> 273/273 = 1.000 [0.986, 1.000] | n/a (new) -> 174/273 = 0.637 [0.579, 0.692] |

### Unsupported-attribute keywords on the held Smithery set

Catalogs using each keyword outside the documented list (keywords used by fewer than 10 catalogs are not listed). Keywords are counted from schema nodes only, never property names.

| Keyword | Catalogs using it |
|---|---|
| `default` | 1466/3138 = 0.467 [0.450, 0.485] |
| `minimum` | 1168/3138 = 0.372 [0.355, 0.389] |
| `maximum` | 1155/3138 = 0.368 [0.351, 0.385] |
| `minLength` | 702/3138 = 0.224 [0.209, 0.239] |
| `additionalProperties` | 701/3138 = 0.223 [0.209, 0.238] |
| `maxLength` | 602/3138 = 0.192 [0.178, 0.206] |
| `maxItems` | 475/3138 = 0.151 [0.139, 0.164] |
| `minItems` | 473/3138 = 0.151 [0.139, 0.164] |
| `pattern` | 422/3138 = 0.134 [0.123, 0.147] |
| `title` | 296/3138 = 0.094 [0.085, 0.105] |
| `exclusiveMinimum` | 217/3138 = 0.069 [0.061, 0.079] |
| `const` | 140/3138 = 0.045 [0.038, 0.052] |
| `propertyNames` | 120/3138 = 0.038 [0.032, 0.046] |
| `oneOf` | 51/3138 = 0.016 [0.012, 0.021] |
| `examples` | 36/3138 = 0.011 [0.008, 0.016] |
| `uniqueItems` | 15/3138 = 0.005 [0.003, 0.008] |
| `example` | 13/3138 = 0.004 [0.002, 0.007] |
| `not` | 12/3138 = 0.004 [0.002, 0.007] |
| `allOf` | 11/3138 = 0.004 [0.002, 0.006] |

## Caveats

- POST-HOC and in-sample: the rule was changed after these outcomes were seen. The post-hoc precision of the array-length check is optimistic by construction.
- n = 24 catalogs with 5 positives; intervals are Wilson 95 % and wide.
- The probe's rejection bodies carry no reason text; the link to the documented 'too many states' failure is an inference.
- Prevalence says how often a note appears, not how often a provider rejects.

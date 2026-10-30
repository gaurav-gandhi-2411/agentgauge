# Provider-compat lint rule: validation and prevalence

Zero-LLM, aggregate-only: no model or network call was made, and this report contains counts only (no tool names, descriptions, schemas, server identifiers or per-server rows). Reproduce with `scripts/provider_compat_study.py` (see provenance).

## Provenance

- Date: 2026-10-30
- Rule code: `agentgauge/provider_compat.py` last changed in commit `9c3090158ca207bcebf64e4b32d8562c635c7ab1`; file sha256 `664d09b6d7270463104e30b9e0219e4a2b322a3fad049c990263123ead8d3ba1`; study run at HEAD `336f69ea3a45e6807ddb1f0724adcdf58ac9690c` (working tree dirty: False).
- Study script sha256: `ea723ff9d4c44ed3fd32309c37b78ff822ae2666bceee7e79a1ba9b86c965305`
- Input file sha256 (private data; hashes only):
  - vertex_probe (f1_schema_probe.jsonl): `bf642d4f333154ebdee6f8b337cf4b1749bccb76dc130825193e4c651ee2020b`
  - vertex_probe_after_strip (f1_schema_probe_wire1.jsonl): `8b498a28b7c9ba72c35e1bde0e20ea683a28cd1b12332a58b8c3da4b723f562d`
  - gemini_api_preflight (pilot_a5/preflight.json): `6fb696a3e0361382d456b05be4de78adaef1da9cafc94d0fc7ee4e819dc6dbda`
  - frame (frame_official_smithery.jsonl): `a2198a12214e6ec5e55466440eb4e34d32f5c93897db86158f990554a77e1fa8`
  - smithery_details (smithery_details.jsonl): `f85b54e721ecc17c49f20ed6a89f81a52f0f3482215a8c2a76f59c63dd208bf8`
  - catalog files (24 files, hashes sorted, file names withheld because they are server identifiers):
    - `035bb5df3227fb6b626f5093d355e76827a0d4ca81e982655948505937ca6260`
    - `0c9bd8474232a9f29105799fe40780da1b16178dc296ee5138e1c1370834928e`
    - `3663a901020d0be605fd363670e853a4b16e62d6d4c9d527493927ab30857610`
    - `3eb0ff9adfb21017e34cd5f8aee76f53620d0718c7a4792086b5ac4472c29821`
    - `400f714d214663d8cdee456a23a3063ac83dd10df32dbd6e7af861f7939cd8e3`
    - `41914c95eef98b28ec1dca54ad31810f199f20154a28a6f4aaca675790e86d7e`
    - `4d0abaf1be51ad18f77be2a321d6d8a36f89bf276f68ab72f2026f33904ede77`
    - `4d2cd6067969acac36b0ef46489ec3972b1e8dcce0e8cb783221e88ca3748c27`
    - `5fea6fb1d0bbc00f9642469a2e0c84f5e58cad958a1d50d0aaa2bae23e0c62e4`
    - `66cc7a447493e7b15fcdebe5fa5b8fea88d31892b5d8ad75febf84ea51f2665d`
    - `6bdc56c67552c350cb76ef72db21adda0405a4ea2a22a4e74f60dc08afa72bca`
    - `76122b5dfd3f61e378b8787ec66631fb372d42d6d4ebc8819ab47af6205475df`
    - `86a0b171e1f4d14bc5133eb4472d0541c66416d926470fc23e762e5b26923823`
    - `8dacd72e210ab390f786066845ea2db5dcf986fd9e75151bcbe2350b1df7c338`
    - `9de4ef5fe9a0af2d71414ce98dd9928e1f5bbf198339e17ad05e742e7673d064`
    - `c6caaab3bcd1eb7be8789c53dd8be9d0dc66a42fba1fb66e4aaa3d913a226c17`
    - `ce52dabaefaea0eb4938f589739ecf97dda08811154dffa36698fc87f20fc271`
    - `d14ad66f6918eeac1ab73d09b0f25f5b0863f61c8b530a4d58573ee37b8e4e4e`
    - `d2bc9715d0ba448553b4d270237b319ea38b5cb42e2c312f2cfb15f4685d3e6e`
    - `e6e2d6e2a666b84c0b5a3dcc7ea287e3d2ff42fedf0ad6e50e2e5e2ac8208d87`
    - `ebc0a7e302ac7f2cee5c2cdc3aadad0baa531a4980f3ba8adae2f8c2c923c9b3`
    - `edd1a34bb7063b46d90f9664a66bbfbbe8a663e0211b766b1e552ea985d73516`
    - `efcdaec6d339b431765bfbc06f3688357153fea4cb966e2fb5f2e11a699c75aa`
    - `f4567d87ab62f0629d81253887e6b676b214f92f1f9d04e800932763238d92e7`

## Read this first: in-sample, wide intervals, low recall is expected

- **In-sample.** The rule family was designed AFTER the 5 Vertex rejections analysed in (a) were seen; those same catalogs are the validation set. This is a descriptive check of the rule on the data that motivated it, not an out-of-sample estimate.
- **Not a random sample.** The held Smithery set is 3,327 of the 6,610 Smithery frame members: the first listed (github-homepage servers first, then by use count). It is not a random sample, so prevalence in section (b) describes only this held set, not the ecosystem.
- **Wide intervals.** n = 24 with 5 positives. Wilson 95 % intervals are reported and are wide; no claim should rest on a point value alone.
- Launch-claim gate (precision >= 0.9, judged on the Wilson lower bound of any-violation precision): **NOT met**. Any-violation precision is 1/1 with Wilson lower bound 0.207; any-finding precision 0.278.
- **Low recall is legitimate.** The private diagnostic (DECISIONS 36) found the rejections consistent with an AGGREGATE schema-complexity limit, not any single documented keyword. The rule deliberately implements only DOCUMENTED limits, plus two advisories that make no pass/fail claim; it is not a rejection predictor.

## (a) Validation against observed accept/reject outcomes

### What the "29" is

The Vertex schema probe made **29 calls over 24 catalogs**: {'flash:HTTP_400': 5, 'flash:ok': 19, 'pro:HTTP_400': 3, 'pro:ok': 2}. Flash was called on every catalog (5 rejected with HTTP 400, 19 accepted); Pro was called on 5 of them (3 rejected). So n = 24 catalogs, not 29: 29 is the call count. Positive = rejected by Flash and/or Pro (5); negative = accepted by everything it was sent to (19). A second probe (29 calls) re-probed the same catalogs after the uniform, pre-registered stripping of validation keywords; it accepted 29 of them.

### Definitions

- Predicted positive = the rule (or rule set) fires on the catalog at least once, linting the catalog as stored (no `$ref` dereferencing, no keyword stripping).
- Limit violations (`any_violation`) = the three ADVISORY-severity checks that mirror a documented limit: tool name, schema depth, `$ref`. Advisories = the two INFO-severity notes: `provider_compat_schema_size` (any validation-only keyword present) and `provider_compat_tool_count` (> 20 tools). `any_finding` = violations or advisories.
- Precision = TP/(TP+FP), recall = TP/(TP+FN), specificity = TN/(TN+FP), each with a Wilson 95 % CI. When a predicate flags nothing, precision is **undefined** (reported as `undefined`), not 0 or 1.

### Vertex (primary)

| Predicate | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity |
|---|---|---|---|---|---|---|---|
| `provider_compat_tool_name` | 0 | 0 | 5 | 19 | undefined (0/0) | 0/5 = 0.000 [0.000, 0.434] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_schema_depth` | 0 | 0 | 5 | 19 | undefined (0/0) | 0/5 = 0.000 [0.000, 0.434] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_ref` | 1 | 0 | 4 | 19 | 1/1 = 1.000 [0.207, 1.000] | 1/5 = 0.200 [0.036, 0.624] | 19/19 = 1.000 [0.832, 1.000] |
| `provider_compat_schema_size` | 5 | 11 | 0 | 8 | 5/16 = 0.312 [0.142, 0.556] | 5/5 = 1.000 [0.566, 1.000] | 8/19 = 0.421 [0.231, 0.637] |
| `provider_compat_tool_count` | 5 | 4 | 0 | 15 | 5/9 = 0.556 [0.267, 0.811] | 5/5 = 1.000 [0.566, 1.000] | 15/19 = 0.789 [0.567, 0.915] |
| `any_violation` | 1 | 0 | 4 | 19 | 1/1 = 1.000 [0.207, 1.000] | 1/5 = 0.200 [0.036, 0.624] | 19/19 = 1.000 [0.832, 1.000] |
| `any_finding` | 5 | 13 | 0 | 6 | 5/18 = 0.278 [0.125, 0.509] | 5/5 = 1.000 [0.566, 1.000] | 6/19 = 0.316 [0.154, 0.540] |

Precision gate (launch claim needs precision >= 0.9):

- `any violation`: point precision 1.000, Wilson lower bound 0.207; point >= 0.9: **True**; lower bound >= 0.9: **False**.
- `any finding`: point precision 0.278, Wilson lower bound 0.125; point >= 0.9: **False**; lower bound >= 0.9: **False**.

Launch-claim gate (precision >= 0.9, judged on the Wilson lower bound of any-violation precision): **NOT met**. Any-violation precision is 1/1 with Wilson lower bound 0.207; any-finding precision 0.278.

### Gemini API free-tier preflight (secondary; different endpoint)

Separate validation set: the pilot's Gemini API preflight (not Vertex) over 12 catalogs: 3 rejected even after lossless translation, 9 accepted untranslated. These catalogs are a subset of the 24 above, and 3 of the 3 rejected ones are also Vertex rejections, so this set is NOT independent of the primary one and adds no out-of-sample evidence; it only shows the outcome on a second endpoint. It is NOT pooled with the Vertex table.

| Predicate | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | Specificity |
|---|---|---|---|---|---|---|---|
| `provider_compat_tool_name` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `provider_compat_schema_depth` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `provider_compat_ref` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `provider_compat_schema_size` | 3 | 5 | 0 | 4 | 3/8 = 0.375 [0.137, 0.694] | 3/3 = 1.000 [0.439, 1.000] | 4/9 = 0.444 [0.189, 0.733] |
| `provider_compat_tool_count` | 3 | 2 | 0 | 7 | 3/5 = 0.600 [0.231, 0.882] | 3/3 = 1.000 [0.439, 1.000] | 7/9 = 0.778 [0.453, 0.937] |
| `any_violation` | 0 | 0 | 3 | 9 | undefined (0/0) | 0/3 = 0.000 [0.000, 0.561] | 9/9 = 1.000 [0.701, 1.000] |
| `any_finding` | 3 | 6 | 0 | 3 | 3/9 = 0.333 [0.121, 0.646] | 3/3 = 1.000 [0.439, 1.000] | 3/9 = 0.333 [0.121, 0.646] |

## (b) Prevalence on locally held official-registry + Smithery catalogs (no Glama)

Frame entries: 42972 (by source: {'official': 36384, 'official+smithery': 168, 'smithery': 6420}). The official registry carries no tool schemas, so only Smithery detail records can be linted. Smithery detail records: 3327 (HTTP {'200': 3308, '404': 19}); HTTP 200 with zero tools: 155; servers with tool schemas: 3153; after frame-entry dedup (rule below): **3138** (15 collapsed). **No schema available, excluded from the denominator: 39834** of 42972. Malformed catalogs skipped: 0. Lintable source mix (counts): {'official+smithery': 161, 'smithery': 2977}.

- Dedup rule: the unit is a frame entry (official U Smithery, deduplicated by normalised repo URL in the private snapshot). If several fetched Smithery servers share one entry, the one with the most tools is kept (ties: smallest qualified name).
- Strata by tool count, from agentgauge-r1 `src/agentgauge_r1/sampling/strata.py` (`S_MAX, M_MAX, L_MAX = 5, 15, 40`, `MIN_TOOLS = 3`): S 3-5, M 6-15, L 16-40, XL >= 41; catalogs with 1-2 tools are outside R1's strata and shown separately. R1's additional "> 20K tokens -> XL" rule is not applied (tool count only).
- The Smithery set is the first 3,327 listed servers (github-homepage first, then by use count), not a random sample of the registry: prevalence describes this held set, not the ecosystem.

| Stratum | n | `provider_compat_tool_name` | `provider_compat_schema_depth` | `provider_compat_ref` | `provider_compat_schema_size` | `provider_compat_tool_count` | `any_violation` | `any_finding` |
|---|---|---|---|---|---|---|---|---|
| ALL | 3138 | 4/3138 = 0.001 [0.000, 0.003] | 0/3138 = 0.000 [0.000, 0.001] | 31/3138 = 0.010 [0.007, 0.014] | 1514/3138 = 0.482 [0.465, 0.500] | 679/3138 = 0.216 [0.202, 0.231] | 34/3138 = 0.011 [0.008, 0.015] | 1808/3138 = 0.576 [0.559, 0.593] |
| below_S(1-2 tools) | 422 | 0/422 = 0.000 [0.000, 0.009] | 0/422 = 0.000 [0.000, 0.009] | 0/422 = 0.000 [0.000, 0.009] | 124/422 = 0.294 [0.252, 0.339] | 0/422 = 0.000 [0.000, 0.009] | 0/422 = 0.000 [0.000, 0.009] | 124/422 = 0.294 [0.252, 0.339] |
| S | 722 | 0/722 = 0.000 [0.000, 0.005] | 0/722 = 0.000 [0.000, 0.005] | 4/722 = 0.006 [0.002, 0.014] | 305/722 = 0.422 [0.387, 0.459] | 0/722 = 0.000 [0.000, 0.005] | 4/722 = 0.006 [0.002, 0.014] | 305/722 = 0.422 [0.387, 0.459] |
| M | 1093 | 1/1093 = 0.001 [0.000, 0.005] | 0/1093 = 0.000 [0.000, 0.004] | 10/1093 = 0.009 [0.005, 0.017] | 583/1093 = 0.533 [0.504, 0.563] | 0/1093 = 0.000 [0.000, 0.004] | 11/1093 = 0.010 [0.006, 0.018] | 584/1093 = 0.534 [0.505, 0.564] |
| L | 628 | 1/628 = 0.002 [0.000, 0.009] | 0/628 = 0.000 [0.000, 0.006] | 8/628 = 0.013 [0.006, 0.025] | 314/628 = 0.500 [0.461, 0.539] | 406/628 = 0.646 [0.608, 0.683] | 9/628 = 0.014 [0.008, 0.027] | 522/628 = 0.831 [0.800, 0.858] |
| XL | 273 | 2/273 = 0.007 [0.002, 0.026] | 0/273 = 0.000 [0.000, 0.014] | 9/273 = 0.033 [0.017, 0.061] | 188/273 = 0.689 [0.631, 0.741] | 273/273 = 1.000 [0.986, 1.000] | 10/273 = 0.037 [0.020, 0.066] | 273/273 = 1.000 [0.986, 1.000] |

## Caveats

- Validation labels come from one provider/model family probed on one date; a rejection is a property of that endpoint at that time.
- The `provider_compat_schema_size` advisory fires whenever any validation-only keyword is present, so it is expected to have low precision as a rejection predictor; it is an information note, not a prediction.
- Prevalence says how often a finding appears, not how often a provider rejects.

# AgentGauge v2 — deterministic linter evaluation (Task 2)

Per the eval doctrine (`reports/v2_eval_doctrine.md`, Component 1): this linter's task is binary
defect detection, evaluated by precision/recall/false-alarm rate — never correlation. All numbers
below are measured against `agentgauge/linter.py` as committed, with checks and fixes documented as
they were found, not smoothed over.

## 2a/2b. What shipped, and why (rebuild + bug fixes)

Kept as HIGH severity (on by default): `described_not_in_schema` (a), `type_enum_contradiction` (c),
`required_references_missing_property` (e), plus a new `name_collision` check extracted from v1's
`discoverability` axis per `reports/v2_axis_triage.md`. Demoted to INFO (off by default):
`required_not_mentioned` (b), per the predictive-validity study's tier-stratified finding that it
fires nearly as often on real-world professional docs as on deliberately-bad fixtures.

**Two named bugs fixed, with regression tests** (`tests/test_linter.py`):
- `type_enum_contradiction`'s negation false-positive ("no pagination" triggering a boolean-language
  match on the bare word "no"): fixed by requiring an explicit boolean **phrase**
  (`true/false`, `yes/no`, `boolean`) co-occurring in the **same sentence** as the parameter mention,
  not a common negation word anywhere in the whole description.
- `described_not_in_schema`'s Returns-section false-positive (return-value field names mistaken for
  missing input parameters): fixed by excluding both a formal `Returns:`/`Output:` section header
  and, found during clean-corpus measurement below, a standalone sentence whose main verb is
  "Returns"/"Return" even with no formal heading.

**Two more false-positive mechanisms found and fixed during clean-corpus measurement** (not in the
original bug list, found empirically while building this evaluation, each with its own regression
test):
- Sibling-tool-name references in workflow guidance ("use `watch_topic` before calling this")
  mistaken for missing parameters — fixed by excluding any identifier matching another tool's name
  in the same tool set.
- Identifiers inside an `Examples:` section's illustrative string values (e.g. an example URI
  `core://my_user/survival_state`) mistaken for missing parameters — fixed by excluding text after
  an `Examples:` heading, same pattern as the `Returns:` fix.

**One measurement artifact found and fixed in the test harness itself, not the linter:** the initial
clean-corpus run linted the predictive-validity study's cost-bounded 12-tool T18 subsets rather than
the full 60-tool catalog, making legitimate sibling tool names (from families outside the 12-tool
filter) look like unknown identifiers. Fixed by extracting the full, unfiltered catalog for every
manifest entry (`scripts/v2_extract_tool_definitions.py`) — this was never a linter bug, but is
recorded here because it drove a large, misleading swing in early false-alarm measurements
(`t18_q2b_server`: 11 → 0 HIGH violations once corrected) and is exactly the kind of artifact this
study's constraints explicitly warned to hunt for.

## 2c. Clean-corpus false-alarm rate

**Corpus:** 21 unique tool sets (tier ∈ {`real-world-mirror`, `real-world-mirror-improved`, `good`,
`mediocre-good`} — declared *before* running the measurement, not selected after seeing results;
2 further `t18_*_set2` entries were excluded as byte-identical duplicates of their non-set2
counterparts once the cost-bounding tool filter was dropped). 521 tools total. Excludes `fixer-improved`
tier (5 entries known/suspected to contain the exact defect class this checker targets) and `bad`/
`mediocre` tiers (deliberately degraded, not a clean-corpus candidate).

| Granularity | Flagged | Total | Rate |
|---|---|---|---|
| **Tools with ≥1 HIGH violation** | 18 | 521 | **3.45%** — clears the <5% target |
| Tool sets with ≥1 HIGH violation anywhere | 14 | 21 | 66.67% |

**Both numbers are reported because they tell different stories, and reporting only the passing one
would be misleading.** The task's stated target ("<5% of clean tools flagged") is a per-tool rate,
which passes. But at the tool-SET level — the granularity a CI gate is more likely to use ("does
this PR's tool set have any new finding") — two-thirds of even genuinely clean tool sets have at
least one flagged tool somewhere. A product built on "any flag anywhere = block the PR" would fail
its own false-alarm target; a product built on "flagged-tool rate per tool set" would not.

**By check, on the clean corpus (51 total HIGH violations):**

| Check | Violations on clean corpus | Read |
|---|---|---|
| `required_references_missing_property` (e) | 0 | Perfect — 0% false-alarm rate, fully deterministic, no NLP judgment involved |
| `type_enum_contradiction` (c) | 0 | The negation-bug fix eliminated all false alarms found in this corpus |
| `described_not_in_schema` (a) | 29 | Elevated — see below |
| `name_collision` (f) | 22 | Elevated — see below |

**`described_not_in_schema` (a) carries residual, only-partially-fixable noise.** Beyond the two
fixed mechanisms above, hand inspection of the remaining clean-corpus flags on `p2a_arm_oracle` and
`exp1_stickerdaniel_linkedin_mcp_server_mirror` found at least two more genuine false-positive
categories not fixed in this session: (i) descriptions documenting valid **enum-style values** in
prose for a plain-`string`-typed schema property with no declared `enum` list (e.g. `search_jobs`'s
`full_time`/`part_time`/`on_site` employment-type values), and (ii) disambiguating clarifications
that name a *related but different* field for contrast (`find_account`'s "NOT the internal
`account_id`"). Each additional fix found a new category rather than closing the gap, which is
itself evidence this heuristic's ceiling on natural prose is a real, not-fully-patchable limitation
— reported honestly rather than claimed fixed.

**`name_collision` (f) inherits a known, already-published limitation, not a new bug.** Three of its
22 clean-corpus flags are verb-differentiated pairs (`load_order`/`void_order`,
`amend_invoice`/`send_invoice`, `create_notification_rule`/`delete_notification_rule`) that a human
would not confuse — the exact failure mode the companion arXiv paper (§4.3.4) already documented for
this same Levenshtein heuristic on `attach_user_policy`/`detach_user_policy`. Extracting this check
from v1's `discoverability` axis (per the axis-triage decision) does not fix this pre-existing,
already-published limitation; it is carried forward, not newly introduced.

## 2d. Defect-injection corpus — the headline evaluation

**Corpus:** 276 labeled defects across 276 injected tool-set instances, derived from the same 21
clean base tool sets (up to 3 distinct target tools × 5 defect types per base, capped so no single
large tool set dominates). **Honest scope note:** "≥30 tool sets" is met if counting injected
instances (276 ≫ 30); the number of distinct *underlying* base files is 21, short of 30 — reported
plainly rather than padded by including tool sets already known/suspected to contain pre-existing
defects (which would contaminate ground truth).

| Defect type | n | Detected | **Recall** | Expected check |
|---|---|---|---|---|
| `contradictory_required_claim` | 63 | 63 | **100.0%** | `required_references_missing_property` |
| `type_flipped` | 57 | 57 | **100.0%** | `type_enum_contradiction` |
| `enum_dropped` | 57 | 57 | **100.0%** | `type_enum_contradiction` |
| `required_unmentioned_prose` | 51 | 48 | **94.1%** | `required_not_mentioned` (INFO severity) |
| `param_renamed` | 48 | 11 | **22.9%** | `described_not_in_schema` |

**`param_renamed`'s low recall has a precise, quantified cause, not a vague one.** Splitting the 48
cases by whether the renamed property was a multi-word (`snake_case`) or single-word identifier:

| Property name shape | n | Detected | Recall |
|---|---|---|---|
| Multi-word (`snake_case`) | 13 | 10 | 76.9% |
| Single-word (e.g. `field`, `key`, `id`) | 35 | 1 | 2.9% |

`described_not_in_schema`'s identifier-extraction regex only matches backtick-quoted text or
multi-segment `snake_case` tokens — a deliberate precision/recall tradeoff to avoid flagging every
common English word in a description as a candidate parameter reference. The consequence, now
measured rather than assumed: **this check has near-zero recall on single-word parameter renames**,
which is a real gap for a class of defect the task brief explicitly named as a target. Broadening
the regex to catch single words would explode the clean-corpus false-alarm rate (nearly every common
noun would become a candidate); narrowing further would only reduce recall more. This is reported as
a genuine, measured limitation, not fixed in this session.

**`required_unmentioned_prose`'s 94.1% recall is on the demoted INFO-severity check**, meaning a
user running only the default HIGH-severity surface will **not** see this defect class flagged at
all — the demotion decision (justified by this check's poor tier-discrimination in the predictive-
validity study) trades away detection of a real, commonly-injectable defect type. This trade-off is
named explicitly, not left implicit: teams that care about this specific defect class should enable
the INFO-severity check.

## 2e. Baseline comparisons

**(ii) Raw JSON-Schema structural validation** (`jsonschema.Draft7Validator.check_schema()`, applied
to all 276 injected schemas): **0.0% recall.** Every injected defect produces a syntactically valid
JSON-Schema document — none of the five defect types make the schema itself malformed per the
JSON-Schema specification; they are all semantic mismatches between description prose and schema
structure, which structural validation cannot see by construction. This is not a close comparison:
the deterministic linter's weakest defect type (`param_renamed`, 22.9%) already exceeds this
baseline's 0% on every defect type tested.

**(iii) Single-prompt LLM "find inconsistencies" baseline:** **not measured in this session** — local
GPU was contended (confirmed via `nvidia-smi`, <500MB free) at every point this evaluation was run,
and per this study's standing constraint, no inference is run without checking GPU availability
first. Deferred, not silently skipped — flagged in `reports/v2_product_readiness.md` as an open
measurement.

**(i) No linter at all:** by construction, 0% recall on every defect type — the deterministic linter
beats "ship nothing" on every measured axis at zero marginal LLM cost.

## Summary against the doctrine's pre-declared bar

- False-alarm rate: **passes** at the per-tool granularity (3.45% < 5%), but the tool-set-level rate
  (66.67%) is materially worse and should inform how this linter is actually wired into a CI gate
  (per-tool reporting, not per-tool-set blocking).
- Precision on the clean corpus, by check: `required_references_missing_property` and
  `type_enum_contradiction` are clean (0 false alarms found); `described_not_in_schema` and
  `name_collision` both carry real, partially-irreducible noise, documented rather than hidden.
- Recall on the defect-injection corpus: strong (94-100%) on four of five defect types; genuinely
  weak (22.9%) on `param_renamed` specifically when the renamed property is a single word — the
  majority real-world case for parameter names.
- Beats the JSON-Schema-validation baseline decisively (0% recall) on every defect type tested. The
  LLM baseline comparison remains outstanding pending GPU availability.

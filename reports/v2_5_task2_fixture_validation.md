# AgentGauge v2.5 — Task 2: real-API fixture validation

The 10 new v2.4-corpus fixtures (GitHub Issues, Stripe Payments, Google
Calendar, Jira Issues, Slack Messaging, Docker Containers, Kubernetes
Workloads, Twilio Messaging, AWS S3, Spotify Playlists) were each authored by
an independent executor agent, most plausibly from model memory of the real
API rather than a fetched schema. This task validates every one of them
against a real, live-fetched source, fixes what's wrong, and quantifies the
hallucination rate.

## 2a/2b — methodology

10 parallel, **read-only** research agents (no file writes, no git commands —
per the standing "no concurrent authoring agents on one git index"
constraint), one per fixture, each instructed to fetch the real, official API
documentation for its domain and check every tool name, parameter name, type,
required/optional status, and enum/format value against it.

Official documentation was fetchable for **all 10 domains** — the 2b
multi-LLM-consensus fallback (for domains with no fetchable schema) was not
needed. Each finding below was independently re-verified by me directly
against the primary source (WebFetch against the live docs page, not taken on
the validating agent's word alone) before any fix was applied — this
matters, because the validating agents' own findings are themselves LLM
output and could in principle be wrong; the GitHub `state_reason` and Stripe
`customer` findings were both re-confirmed against `docs.github.com` /
`docs.stripe.com` directly, and the Kubernetes DNS-1123 finding was
re-confirmed against `kubernetes.io`'s own docs (which was the one case where
my own prior belief actually disagreed with the validator, and the live doc
resolved it in the validator's favor — see below).

## 2c — per-fixture results

| Fixture | Verified correct | Wrong | Unverifiable | Verdict |
|---|---|---|---|---|
| GitHub Issues | 3/4 tools clean | `state_reason` enum missing real 4th value `'duplicate'` | 0 | **Fixed** |
| Stripe Payments | 3/4 tools clean | `create_charge`'s `customer_id` (required) should be `customer` (optional) | 0 | **Fixed** |
| Kubernetes Workloads | 3/4 tools clean | DNS-1123 label regex allowed a leading digit; real k8s validation requires a leading letter | 0 | **Fixed** |
| Docker Containers | 4/4 functionally correct | 2 framing gaps: `timeout_seconds` silently renames the real API's `t` param; `driver` enum implies exhaustiveness Docker doesn't have (`macvlan`/`ipvlan`/plugins exist too) | 0 | **Fixed (doc clarity only, no schema/constraint change)** |
| Spotify Playlists | 4/4 correct | none — `public` modeled as a string enum instead of Spotify's real boolean is a **documented, deliberate simplification** (already fully disclosed in `spotify_playlists_NOTES.md`), not a hallucination | 0 | **Clean, no fix needed** |
| Google Calendar | 4/4 correct | none — `NOTES.md` understated the `start_time`/`end_time` divergence as "casing-only" when it's casing + object-flattening | 0 | **Fixed (doc wording only)** |
| Jira Issues | 4/4 correct | none — `NOTES.md` disclosed `issue_type`/`transition` configurability but not `priority` scheme configurability (inconsistent disclosure, not a factual error) | 0 | **Fixed (doc wording only)** |
| Slack Messaging | 4/4 correct | none | 0 | **Clean** |
| Twilio Messaging | 4/4 correct | none | 0 | **Clean** |
| AWS S3 | 4/4 correct | none | 0 | **Clean** |

**Hallucination rate: 3/10 fixtures (30%) had an outright factual defect** in
a schema, required/optional status, or constraint (GitHub, Stripe,
Kubernetes) — all three now fixed. A further 1/10 (Docker) had accurate but
incomplete/misleadingly-framed documentation (not a wrong schema or wrong
gold value, just prose that implied more exhaustiveness/less renaming than
is true) — also fixed. 2/10 (Google Calendar, Jira) had minor `NOTES.md`
wording gaps, fixed. 1/10 (Spotify) is a deliberate, already-disclosed
design choice, not a hallucination. 3/10 (Slack, Twilio, AWS S3) were fully
clean on first check.

**Judged material** per Task 2e: 30% of a hand-authored, real-API fixture
corpus containing an outright factual defect (one that would have silently
mis-scored every correct agent response for that parameter) is a material
rate, not noise — hence artifact #8 below.

### Fixes applied (2d)

1. **GitHub Issues** — `examples/github_issues_server_fixed.py`: added
   `'duplicate'` to the `state_reason` description prose (confirmed against
   `docs.github.com/en/rest/issues/issues`: the real enum is `completed` /
   `not_planned` / `duplicate` / `reopened` / `null`).
   `evals/fixtures/v2_4_corpus/github_issues_fixture.py`: added a 6th
   `update_issue_state` task+constraint exercising `state_reason='duplicate'`
   (previously 0 of the fixture's 5 tasks covered this real value at all) —
   fixture now 21 tasks (was 20).
2. **Stripe Payments** — `examples/stripe_payments_server.py` and
   `..._fixed.py`: renamed `customer_id` → `customer`, removed it from
   `required` (confirmed against `docs.stripe.com/api/charges/create`: the
   real param is `customer`, optional). No `TASK_CONSTRAINTS` entry
   referenced the old name, so no fixture-content change was needed.
3. **Kubernetes Workloads** — `evals/fixtures/v2_4_corpus/k8s_workloads_fixture.py`:
   narrowed `_DNS_1123_LABEL_PATTERN`'s leading character class from
   `[a-z0-9]` to `[a-z]` (confirmed against
   `kubernetes.io/docs/concepts/overview/working-with-objects/names/`: despite
   RFC 1123 technically permitting a leading digit, Kubernetes' actual
   validation requires both RFC 1035 and RFC 1123 labels to start with a
   letter). Also corrected the matching prose in
   `examples/k8s_workloads_server_fixed.py`'s `create_pod`/`create_namespace`
   descriptions, which both said "starting ... with an alphanumeric
   character."
4. **Docker Containers** — `examples/docker_containers_server_fixed.py`:
   `stop_container`'s description now notes the real Engine API calls this
   parameter `t`, renamed here for readability; `create_network`'s
   description now says explicitly that `driver`'s four listed values are
   "four of Docker's built-in drivers," not the complete set, and names
   `macvlan`/`ipvlan`/third-party plugins as real drivers this tool doesn't
   model. No schema or constraint change — the enum constraint's 4 gold
   values are still real, valid drivers; only the description's implied
   exhaustiveness was corrected.
5. **Google Calendar** — `gcal_NOTES.md`: corrected "only the casing
   convention is a wrapper-layer paraphrase" to also disclose the real API's
   `start`/`end` object-nesting that this fixture flattens.
6. **Jira Issues** — `jira_issues_NOTES.md`: added the same
   real-Jira-is-configurable-per-site caveat to the `priority` enum note that
   `issue_type`/`transition` already had.

No fixture needed removal — every defect found was fixable in place without
invalidating its task pool.

## 2e — artifact #8 and a new audit check

**Artifact #8, logged**: hallucinated fixture-authoring facts. A fixture
built to model a real external API can assert an incorrect required/optional
status, enum member set, or format rule if authored from an LLM's memory of
the domain instead of a fetched schema — and because these fixtures'
`inputSchema`s are deliberately type-only (no `"enum": [...]` declared, to
test whether an agent can infer values from the description alone), nothing
in the schema itself can catch this. 3 of 10 fixtures in this corpus had
exactly this defect (see 2c). `agentgauge/audit.py`'s docstring and
`tests/test_audit.py`'s header have both been updated to document this as
the eighth artifact class.

**New check**: `agentgauge.audit.check_enum_schema_fidelity` — for every task
with an `enum`-kind constraint, WARN if the connected tool's schema doesn't
declare an `"enum"` array for that parameter. This is deliberately WARN, not
BLOCK: type-only enum schemas are this project's own intentional design (to
test description-driven inference), so the finding fires on essentially
every real-API fixture in this corpus by construction — it is not a defect
to block on, it's a standing reminder that **this specific gold_value's
correctness cannot be checked by the tool itself** and must be source-checked
by hand, exactly the step that was skipped for GitHub/Stripe/Kubernetes.
Wired into `run_audit` alongside the existing schema checks, so it now runs
automatically on every `agentgauge diff`/`eval` invocation. 4 new regression
tests in `tests/test_audit.py::TestEnumSchemaFidelity`, seeded with the real
historical case (GitHub's `state_reason`, pre-fix).

**Scope note, stated plainly**: this check cannot and does not verify a
`gold_value` against any live external ground truth — `agentgauge audit` runs
offline, deterministically, with no network access, by design (it must work
in CI with no paid credentials and no internet). It only makes the
*unverifiable* class of assertion visible instead of silent. The actual
fact-checking done in this task (WebFetch against live docs) is not something
this audit check can automate; it remains a manual (or multi-model-consensus,
per 2b) step for any future real-API fixture.

## 2f — broader contamination and anti-tautology re-check

Two verifications, run directly against all 10 fixture modules (not taken on
any prior self-report):

1. **Cross-fixture content contamination**: for every one of the 10
   fixtures, every task's `tool_name` was confirmed to exist in that same
   fixture's own `ALL_TOOL_NAMES`, AND every name in `ALL_TOOL_NAMES` was
   confirmed present in that fixture's own paired `*_server_fixed.py` file
   (regex-matched tool `name=` declarations). All 10/10 pairs: **OK, no
   mismatch.** This is stronger evidence than the earlier commit-message
   investigation alone: even if a commit's *message* is wrong (the two
   already-disclosed cases), the *file pairing* itself — which fixture's
   tasks reference which server's tools — is internally consistent
   everywhere, meaning no fixture's task pool is silently testing against a
   different domain's tool set.
2. **Anti-tautology compliance**: every one of the corpus's 191 tasks
   (190 original + the 1 new GitHub `duplicate` task) checked for its own
   gold `tool_name` (both underscored and space-separated form) appearing
   literally in its own task description, case-insensitively. **0/191
   violations.**
3. **Constraint completeness**: 0/191 tasks missing a
   `TASK_CONSTRAINTS` entry (re-confirmed after the GitHub Issues addition;
   was 0/190 before).

## Independent verification

A separate verifier agent re-ran the full test suite (see checkpoint in
`PLAN.md`/commit log for the pass count), re-ran the three WebFetch
verifications independently against `docs.github.com`, `docs.stripe.com`,
and `kubernetes.io` to confirm the primary-source claims in this report are
not fabricated, and re-ran the 2f cross-fixture/anti-tautology script from
scratch, reproducing 191/191 clean. Findings below, if any, are recorded
verbatim.

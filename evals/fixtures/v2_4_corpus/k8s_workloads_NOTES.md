# Kubernetes workloads fixture — provenance notes

## Real Kubernetes API operations modeled

Four tools, each a simplified wrapper around a real Kubernetes API operation or a
real, well-known field on a Kubernetes API object:

| Tool                          | Modeled on real Kubernetes API operation / field                                                                                                                                    |
|--------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `create_pod`                   | `POST /api/v1/namespaces/{namespace}/pods` — create a Pod. `spec.restartPolicy` is a genuine Pod-spec field with exactly three real enum values (`Always`, `OnFailure`, `Never`); `metadata.namespace` and `metadata.name` are subject to Kubernetes' real DNS-1123 label naming rule. |
| `scale_deployment`             | `PATCH /apis/apps/v1/namespaces/{namespace}/deployments/{name}/scale` — the real Deployment scale subresource, whose body is `{"spec": {"replicas": N}}`.                             |
| `set_pod_image_pull_policy`    | Real Pod-spec field `spec.containers[].imagePullPolicy`, with exactly three real enum values (`Always`, `IfNotPresent`, `Never`). Modeled as a standalone tool for a clean one-parameter enum constraint rather than as part of the full container-spec object `create_pod` would otherwise need. |
| `create_namespace`             | `POST /api/v1/namespaces` — create a Namespace. `metadata.name` is subject to the same real DNS-1123 label naming rule as above.                                                       |

All 4 tools are constrained (unlike the Stripe pilot, no inert 4th tool was needed
here — every operation chosen has at least one genuine constrained parameter).

## Constraint provenance

- **`namespace` / `name` format** (`create_pod`, `create_namespace`): Kubernetes'
  real naming convention for most object names (including Namespace names and the
  `namespace` field referenced by namespaced resources) is a DNS-1123 label:
  lowercase alphanumeric characters or `-`, starting and ending with an
  alphanumeric character, capped at 63 characters. The regex used here
  (`[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?`) is a simplification of the real rule
  (it encodes the character-class and start/end constraints and caps total length
  at 63 via the bounded `{0,61}` quantifier, but does not separately enforce
  Kubernetes' additional length rules for some specific resource kinds). No
  gold value is checked for these tasks — any value matching the pattern counts,
  matching this repo's existing convention for format constraints (see
  `github_issues_fixture.py`'s `repo`/`assignee` format constraints, which are
  handled the same way).
- **`restart_policy` enum** (`create_pod`): `spec.restartPolicy` is a real Pod-spec
  field. Its three real values are `Always` (the real API default), `OnFailure`,
  and `Never`.
- **`pull_policy` enum** (`set_pod_image_pull_policy`): `spec.containers[].imagePullPolicy`
  is a real container-spec field. Its three real values are `Always`,
  `IfNotPresent`, and `Never`. (The real API's actual default value depends on
  whether the image tag is `:latest`/omitted (`Always`) or pinned (`IfNotPresent`) —
  this fixture's tool always requires an explicit value rather than modeling that
  conditional-default behavior, a deliberate simplification for a clean
  one-parameter enum constraint.)
- **`replicas` range** (`scale_deployment`): the Deployment scale subresource's
  `spec.replicas` is a real, genuinely unbounded non-negative integer field (no
  Kubernetes-enforced minimum/maximum beyond `>= 0`). The specific per-task
  min/max bands used in `TASK_CONSTRAINTS` (e.g. `0-0` for "take it offline
  entirely", `10-50` for "many parallel copies at once") are fixture-authored
  bands chosen to match each task's qualitative framing, not a literal
  Kubernetes-enforced constraint — the same pattern already used for the
  `amount` range in `stripe_payments_fixture.py` and the debounce/timeout ranges
  in `evals/fixtures/ty2_tasks.py`.

## Honesty about sourcing

This fixture was authored from the author's existing knowledge of the Kubernetes
API (core `v1` Pod/Namespace objects and the `apps/v1` Deployment scale
subresource) — there was no live internet access available to verify field
names, enum values, or the exact DNS-1123 label grammar against Kubernetes'
current published API reference at authoring time. All tool descriptions (the
prose in `examples/k8s_workloads_server_fixed.py`) are the author's own
paraphrase, not copied verbatim from any Kubernetes document. The specific
field names (`restartPolicy`, `imagePullPolicy`, the Deployment scale
subresource, DNS-1123 label naming) and their enum values are believed accurate
to the real Kubernetes API as of this agent's training data, but were not
re-verified against a live source before committing. If a byte-exact match to
Kubernetes' current API reference matters for downstream use, re-verify against
`https://kubernetes.io/docs/reference/generated/kubernetes-api/` before relying
on this fixture for anything beyond fixture-internal self-consistency (which is
fully verified — see the import/lint checks in the corresponding commit).

## Task design

- 20 tasks total: 5 per tool x 4 tools (`create_pod`, `scale_deployment`,
  `set_pod_image_pull_policy`, `create_namespace`).
- Anti-tautology: task text never states an enum value (`Always`/`OnFailure`/
  `Never`/`IfNotPresent`), a literal replica count, or an already-formatted
  namespace/name string. `create_pod` tasks imply `restart_policy` via a
  real-world scenario (e.g. "run once to completion and never be restarted" ->
  `Never`, "must always come back up automatically" -> `Always`) without naming
  it. `set_pod_image_pull_policy` tasks imply `pull_policy` the same way (e.g.
  "never tries to reach out to any container registry" -> `Never`).
  `scale_deployment` tasks imply a replica-count band via qualitative phrasing
  ("offline entirely", "a single running copy", "many parallel copies") rather
  than a digit. `create_pod`/`create_namespace` tasks describe an environment
  or team by intent (e.g. "the QA team", "the finance environment") and rely on
  the format constraint's no-gold-value design — any DNS-1123-valid identifier
  the agent invents satisfies the constraint.

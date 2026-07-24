# Jira Issues fixture — provenance notes

## Real Jira API operations modeled

Four tools, each a simplified wrapper around a real Atlassian Jira REST API
(v3, Issues resource) operation:

| Tool                  | Modeled on real Jira REST API operation                             |
|------------------------|---------------------------------------------------------------------|
| `create_issue`         | `POST /rest/api/3/issue` — create an issue. The real endpoint nests fields under a `fields` object (`fields.project.key`, `fields.issuetype.name`, `fields.summary`, `fields.description`); simplified here to flat top-level `project_key`, `issue_type`, `summary`, `description` params for a clean fixture, mirroring how `github_issues_fixture.py`'s `add_assignee` flattens GitHub's real `assignees` array to a single `assignee` string. |
| `transition_issue`     | `POST /rest/api/3/issue/{issueIdOrKey}/transitions` — the real endpoint identifies the target transition by an opaque, workflow-specific numeric `transition.id`, not by the status name directly; simplified here to a `transition` string carrying the human-readable target status name instead of an ID, since the underlying default Jira Software workflow's status names (`To Do`, `In Progress`, `Done`) are stable and well known. |
| `set_issue_priority`   | `PUT /rest/api/3/issue/{issueIdOrKey}` — the real endpoint sets `fields.priority.name`; simplified here to a flat `priority` string. |
| `add_issue_comment`    | `POST /rest/api/3/issue/{issueIdOrKey}/comment` — the real v3 endpoint's comment body is an Atlassian Document Format (ADF) object, not a plain string (the older v2 API accepted a plain string); simplified here to a flat `comment_body` string for fixture clarity. |

## Constraint provenance

- **`project_key` format** (`create_issue`): Jira project keys are uppercase
  letters, length 2-10 by default (Jira's original limit was shorter; it was
  later raised to 10 characters). The regex used here (`[A-Z]{2,10}`) is a
  simplification — it does not enforce Jira's actual "must start with a
  letter" rule beyond what an all-uppercase-letter pattern already implies,
  and does not model site-specific customizations to the allowed key format.
- **`issue_type` enum** (`create_issue`): `Bug`, `Task`, `Story`, and `Epic`
  are Jira's real default issue types in a standard Jira Software (Scrum/
  Kanban) project. Real Jira also has `Sub-task`, omitted here to keep the
  enum to four members matching this task's example.
- **`transition` enum** (`transition_issue`): `To Do`, `In Progress`, and
  `Done` are the three status names in Jira's real default simplified
  workflow. Real Jira workflows are configurable per project and can have
  many more statuses/transitions than these three; this fixture models only
  the unconfigured default.
- **`priority` enum** (`set_issue_priority`): `Highest`, `High`, `Medium`,
  `Low`, `Lowest` are Jira's real default priority scheme values, in
  decreasing order of urgency.
- **`issue_key` format** (`add_issue_comment`): real Jira issue keys are the
  project key, a hyphen, and an integer (e.g. `PROJ-123`). The regex used
  here (`[A-Z][A-Z0-9]{1,9}-[0-9]+`) is a simplification chosen to match the
  style of this repo's existing format-constraint fixtures (e.g.
  `evals/fixtures/ty2_tasks.py`, `github_issues_fixture.py`) — it does not
  enforce the full `project_key` grammar validated above, only a
  representative "letters-then-hyphen-then-digits" shape.

## Honesty about sourcing

This fixture was authored from the author's existing knowledge of the Jira
REST API (Issues resource, API v3) — there was no live internet access
available to verify field names, enum values, or endpoint paths against
Atlassian's current published API reference at authoring time. All
descriptions and schema shapes are the author's own paraphrase, not copied
verbatim from any Atlassian document. The endpoint paths, the nested
`fields.project.key` / `fields.issuetype.name` / `fields.priority.name`
structure, the default issue types, the default simplified workflow's status
names, the default priority scheme, and the project-key / issue-key shapes
are believed accurate to the real Jira product as of recent memory, but were
not re-verified against a live source before committing. If a byte-exact
match to Atlassian's current API reference matters for downstream use,
re-verify against `https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/`
before relying on this fixture for anything beyond fixture-internal
self-consistency (which is fully verified — see the import/lint checks in
the corresponding commit).

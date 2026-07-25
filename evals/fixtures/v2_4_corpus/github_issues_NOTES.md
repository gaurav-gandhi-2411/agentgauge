# GitHub Issues fixture — provenance notes

## Real GitHub API operations modeled

Four tools, each a simplified wrapper around a real GitHub REST API (Issues)
operation:

| Tool                  | Modeled on real GitHub REST API operation                          |
|------------------------|---------------------------------------------------------------------|
| `create_issue`         | `POST /repos/{owner}/{repo}/issues` — create an issue. `title` is genuinely required by the real API; `body`, `labels`, `assignee`/`assignees` are genuinely optional. |
| `add_assignee`         | `POST /repos/{owner}/{repo}/issues/{issue_number}/assignees` — the real endpoint takes an `assignees` array; simplified here to a single `assignee` string for a clean one-parameter format constraint. |
| `update_issue_state`   | `PATCH /repos/{owner}/{repo}/issues/{issue_number}` — the real endpoint's `state` (`open`/`closed`) and `state_reason` (`completed`/`not_planned`/`reopened`) fields. |
| `add_label`            | `POST /repos/{owner}/{repo}/issues/{issue_number}/labels` — the real endpoint takes a `labels` array; simplified here to a single `label` string. |

## Constraint provenance

- **`repo` format** (`create_issue`): GitHub's real repository full-name
  convention is `owner/repo` (e.g. `octocat/Hello-World`). The regex used here
  (`[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+`) is a simplification of the real
  constraint — it does not enforce GitHub's actual leading/trailing-hyphen
  rules for the owner segment, only the two-segment slash-separated shape.
- **`assignee` format** (`add_assignee`): real GitHub usernames may contain
  only alphanumeric characters and hyphens, cannot begin or end with a
  hyphen, and are capped at 39 characters. The regex used here
  (`[A-Za-z0-9][A-Za-z0-9-]{0,38}`) is a simplification (it does not forbid a
  trailing hyphen) chosen to match the style of this repo's existing
  format-constraint fixtures (e.g. `evals/fixtures/ty2_tasks.py`, which also
  uses simplified patterns rather than fully rigorous ones).
- **`state` / `state_reason` enum** (`update_issue_state`): these are real
  GitHub API fields and real enum values. `state_reason` is only meaningful
  once GitHub added it as a way to record *why* an issue's state changed
  (`completed`, `not_planned` on close; `reopened` on reopen).
- **`label` enum** (`add_label`): the nine label names and one-line
  descriptions used (`bug`, `documentation`, `duplicate`, `enhancement`,
  `good first issue`, `help wanted`, `invalid`, `question`, `wontfix`) are
  GitHub's real default labels, auto-created on every new repository.

## Honesty about sourcing

This fixture was authored from the author's existing knowledge of the GitHub
REST API (Issues resource) — there was no live internet access available to
verify field names, enum values, or label text against GitHub's current
published API reference at authoring time. All descriptions and schema
shapes are the author's own paraphrase, not copied verbatim from any GitHub
document. The specific field names, the `state`/`state_reason` enum values,
and the nine default label names are believed accurate to the real GitHub
product as of recent memory, but were not re-verified against a live source
before committing. If a byte-exact match to GitHub's current API reference
matters for downstream use, re-verify against
`https://docs.github.com/en/rest/issues` before relying on this fixture for
anything beyond fixture-internal self-consistency (which is fully verified —
see the import/lint checks in the corresponding commit).

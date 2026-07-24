from __future__ import annotations

# GitHub Issues call-correctness fixture — pre-registered tasks and gold constraints.
#
# Corpus-expansion pilot (v2_4_corpus): a real-domain sibling to the synthetic
# call_constraints_v2 fixture (evals/fixtures/ty2_tasks.py), modeled on GitHub's
# real Issues REST API instead of an invented industrial-sensor domain.
#
# 4 tools, all constrained — 5 tasks each, except update_issue_state which has 6
# (a 'duplicate' state_reason case was added in v2.5 Task 2 to cover GitHub's real
# 4th enum value, found missing during real-API validation) = 21 tasks.
# Constraint mix (2 tools per type), mirroring ty2_tasks.py's "2 per type" design:
#   FORMAT : create_issue (repo, "owner/repo" shape)
#            add_assignee (assignee, GitHub username shape)
#   ENUM   : update_issue_state (state, state_reason)
#            add_label (label, one of GitHub's standard default repository labels)
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only. They must NOT
# contain the literal enum value (e.g. "not_planned", "bug") or the literal
# format shape (e.g. an actual "owner/repo" string or a username token) that the
# agent is meant to construct. The agent must derive the correct value from the
# tool's SCHEMA/description (fixed variant) or fail correctly (bad variant), not
# from the task text.
#
# See github_issues_NOTES.md for provenance of the real GitHub API fields used.
from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

TASKS: list[Task] = [
    # create_issue (format constraint on `repo`, "owner/repo" shape) — 5 tasks
    Task(
        "create_issue",
        "File a bug in the React project reporting that useEffect cleanup functions "
        "aren't running when a component unmounts.",
    ),
    Task(
        "create_issue",
        "Open an issue on the VS Code repository describing that the integrated "
        "terminal loses focus after a window resize.",
    ),
    Task(
        "create_issue",
        "Report a crash in the Kubernetes project that happens when applying a "
        "deeply nested Helm chart.",
    ),
    Task(
        "create_issue",
        "Create an issue in the Django repository about a regression in the ORM's "
        "bulk_update method.",
    ),
    Task(
        "create_issue",
        "Log a bug in the Requests library repository regarding a connection pool "
        "leak under high concurrency.",
    ),
    # add_assignee (format constraint on `assignee`, GitHub username shape) — 5 tasks
    Task(
        "add_assignee",
        "Assign the memory leak issue in the Node.js repo to Ryan Dahl, the creator of Node.js.",
    ),
    Task(
        "add_assignee",
        "Give the flaky-test issue in the PostgreSQL project to the maintainer "
        "known for triaging CI failures.",
    ),
    Task(
        "add_assignee",
        "Assign the newly filed security advisory in the OpenSSL repo to the "
        "team's lead security contact.",
    ),
    Task(
        "add_assignee",
        "Route the failing nightly-build issue in the Rust compiler repo to the "
        "on-call compiler team lead.",
    ),
    Task(
        "add_assignee",
        "Assign the accessibility regression in the Vue.js repository to its original creator.",
    ),
    # update_issue_state (enum constraints on `state` + `state_reason`) — 6 tasks
    Task(
        "update_issue_state",
        "Close issue #45 in the payments-service repo since the reported bug has "
        "been fixed in the latest release.",
    ),
    Task(
        "update_issue_state",
        "Close the feature request issue in the mobile-app repo because the team "
        "decided not to implement it.",
    ),
    Task(
        "update_issue_state",
        "Reopen issue #12 in the api-gateway repo — it was closed by mistake and "
        "the problem is still happening.",
    ),
    Task(
        "update_issue_state",
        "Mark the typo issue in the docs-site repo as resolved now that the "
        "underlying text has been corrected.",
    ),
    Task(
        "update_issue_state",
        "Close out the stale enhancement suggestion in the cli-tool repo — the "
        "team has decided it's out of scope for this project.",
    ),
    Task(
        "update_issue_state",
        "Close issue #88 in the design-system repo since issue #61 already tracks "
        "the exact same problem.",
    ),
    # add_label (enum constraint on `label`, standard default GitHub labels) — 5 tasks
    Task(
        "add_label",
        "Tag the issue about the login button not responding on mobile as a "
        "defect in the app's behavior.",
    ),
    Task(
        "add_label",
        "Label the issue requesting a new export-to-PDF capability as a feature "
        "suggestion rather than a defect.",
    ),
    Task(
        "add_label",
        "Mark the issue where the setup instructions in the README are unclear "
        "as a documentation problem.",
    ),
    Task(
        "add_label",
        "Flag this newly filed issue as a repeat of one that was already reported last week.",
    ),
    Task(
        "add_label",
        "Label this small, well-scoped issue as approachable for someone "
        "contributing to the project for the first time.",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
# Format tasks: no gold value — any value matching the pattern counts.
# Enum tasks: gold_value is the specific expected enum member.
TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # create_issue — format: owner/repo
    (
        "create_issue",
        "File a bug in the React project reporting that useEffect cleanup functions "
        "aren't running when a component unmounts.",
    ): [Constraint("repo", "format", pattern=r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")],
    (
        "create_issue",
        "Open an issue on the VS Code repository describing that the integrated "
        "terminal loses focus after a window resize.",
    ): [Constraint("repo", "format", pattern=r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")],
    (
        "create_issue",
        "Report a crash in the Kubernetes project that happens when applying a "
        "deeply nested Helm chart.",
    ): [Constraint("repo", "format", pattern=r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")],
    (
        "create_issue",
        "Create an issue in the Django repository about a regression in the ORM's "
        "bulk_update method.",
    ): [Constraint("repo", "format", pattern=r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")],
    (
        "create_issue",
        "Log a bug in the Requests library repository regarding a connection pool "
        "leak under high concurrency.",
    ): [Constraint("repo", "format", pattern=r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")],
    # add_assignee — format: GitHub username (alphanumeric/hyphen, simplified)
    (
        "add_assignee",
        "Assign the memory leak issue in the Node.js repo to Ryan Dahl, the creator of Node.js.",
    ): [Constraint("assignee", "format", pattern=r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")],
    (
        "add_assignee",
        "Give the flaky-test issue in the PostgreSQL project to the maintainer "
        "known for triaging CI failures.",
    ): [Constraint("assignee", "format", pattern=r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")],
    (
        "add_assignee",
        "Assign the newly filed security advisory in the OpenSSL repo to the "
        "team's lead security contact.",
    ): [Constraint("assignee", "format", pattern=r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")],
    (
        "add_assignee",
        "Route the failing nightly-build issue in the Rust compiler repo to the "
        "on-call compiler team lead.",
    ): [Constraint("assignee", "format", pattern=r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")],
    (
        "add_assignee",
        "Assign the accessibility regression in the Vue.js repository to its original creator.",
    ): [Constraint("assignee", "format", pattern=r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")],
    # update_issue_state — enum: state (open/closed) + state_reason
    (
        "update_issue_state",
        "Close issue #45 in the payments-service repo since the reported bug has "
        "been fixed in the latest release.",
    ): [
        Constraint("state", "enum", gold_value="closed"),
        Constraint("state_reason", "enum", gold_value="completed"),
    ],
    (
        "update_issue_state",
        "Close the feature request issue in the mobile-app repo because the team "
        "decided not to implement it.",
    ): [
        Constraint("state", "enum", gold_value="closed"),
        Constraint("state_reason", "enum", gold_value="not_planned"),
    ],
    (
        "update_issue_state",
        "Reopen issue #12 in the api-gateway repo — it was closed by mistake and "
        "the problem is still happening.",
    ): [
        Constraint("state", "enum", gold_value="open"),
        Constraint("state_reason", "enum", gold_value="reopened"),
    ],
    (
        "update_issue_state",
        "Mark the typo issue in the docs-site repo as resolved now that the "
        "underlying text has been corrected.",
    ): [
        Constraint("state", "enum", gold_value="closed"),
        Constraint("state_reason", "enum", gold_value="completed"),
    ],
    (
        "update_issue_state",
        "Close out the stale enhancement suggestion in the cli-tool repo — the "
        "team has decided it's out of scope for this project.",
    ): [
        Constraint("state", "enum", gold_value="closed"),
        Constraint("state_reason", "enum", gold_value="not_planned"),
    ],
    (
        "update_issue_state",
        "Close issue #88 in the design-system repo since issue #61 already tracks "
        "the exact same problem.",
    ): [
        Constraint("state", "enum", gold_value="closed"),
        Constraint("state_reason", "enum", gold_value="duplicate"),
    ],
    # add_label — enum: standard default GitHub labels
    (
        "add_label",
        "Tag the issue about the login button not responding on mobile as a "
        "defect in the app's behavior.",
    ): [Constraint("label", "enum", gold_value="bug")],
    (
        "add_label",
        "Label the issue requesting a new export-to-PDF capability as a feature "
        "suggestion rather than a defect.",
    ): [Constraint("label", "enum", gold_value="enhancement")],
    (
        "add_label",
        "Mark the issue where the setup instructions in the README are unclear "
        "as a documentation problem.",
    ): [Constraint("label", "enum", gold_value="documentation")],
    (
        "add_label",
        "Flag this newly filed issue as a repeat of one that was already reported last week.",
    ): [Constraint("label", "enum", gold_value="duplicate")],
    (
        "add_label",
        "Label this small, well-scoped issue as approachable for someone "
        "contributing to the project for the first time.",
    ): [Constraint("label", "enum", gold_value="good first issue")],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    ["create_issue", "add_assignee", "update_issue_state", "add_label"]
)
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["create_issue", "add_assignee"])
ENUM_TOOL_NAMES: frozenset[str] = frozenset(["update_issue_state", "add_label"])

# Enum gold values referenced in tasks (for inferability tests)
ENUM_GOLD_VALUES: list[str] = [
    "open",
    "closed",
    "completed",
    "not_planned",
    "reopened",
    "bug",
    "enhancement",
    "documentation",
    "duplicate",
    "good first issue",
]
# Format patterns (for inferability tests — these should not appear verbatim in task text)
FORMAT_PATTERNS_SAMPLE: list[str] = [
    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
    r"[A-Za-z0-9][A-Za-z0-9-]{0,38}",
    "facebook/react",
    "octocat",
]

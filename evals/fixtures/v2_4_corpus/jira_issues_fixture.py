from __future__ import annotations

# Jira Issues call-correctness fixture — pre-registered tasks and gold constraints.
#
# Corpus-expansion pilot (v2_4_corpus): a real-domain sibling to the synthetic
# call_constraints_v2 fixture (evals/fixtures/ty2_tasks.py) and to this corpus's
# github_issues_fixture.py, modeled on Atlassian Jira's real REST API (Issues)
# instead of an invented industrial-sensor domain.
#
# 4 tools, all constrained — 5 tasks each = 20 tasks.
# Constraint mix:
#   FORMAT : create_issue (project_key, 2-10 uppercase-letter Jira project key
#            shape), add_issue_comment (issue_key, "PROJ-123" issue-key shape)
#   ENUM   : create_issue (issue_type, one of Jira's default issue types —
#            dual-constrained alongside project_key, mirroring
#            github_issues_fixture.py's update_issue_state dual-enum design),
#            transition_issue (transition, one of a default Jira workflow's
#            status names), set_issue_priority (priority, Jira's default
#            priority scheme)
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only. They must NOT
# contain the literal enum value (e.g. "Bug", "In Progress", "Highest") or the
# literal format shape (e.g. an actual project key or issue key like "PROJ-123")
# that the agent is meant to construct. The agent must derive the correct value
# from the tool's SCHEMA/description (fixed variant) or fail correctly (bad
# variant), not from the task text.
#
# See jira_issues_NOTES.md for provenance of the real Jira API fields used.
from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

TASKS: list[Task] = [
    # create_issue (format constraint on `project_key`; enum constraint on
    # `issue_type`) — 5 tasks
    Task(
        "create_issue",
        "File a defect report in the mobile app team's Jira project describing that the "
        "checkout button doesn't respond on iOS Safari.",
    ),
    Task(
        "create_issue",
        "Create an issue in the platform team's Jira project to track the work of "
        "migrating the logging pipeline to structured JSON.",
    ),
    Task(
        "create_issue",
        "Add an issue to the growth team's Jira project for the new user-facing "
        "referral-invite feature the product manager requested.",
    ),
    Task(
        "create_issue",
        "Open an issue in the infrastructure team's Jira project for the multi-quarter "
        "initiative to migrate all services off the legacy datacenter.",
    ),
    Task(
        "create_issue",
        "Log an issue in the billing team's Jira project reporting that invoices are "
        "being generated with the wrong tax rate.",
    ),
    # transition_issue (enum constraint on `transition`) — 5 tasks
    Task(
        "transition_issue",
        "Kick off work on the payment-retry issue in the billing project now that a "
        "developer has picked it up.",
    ),
    Task(
        "transition_issue",
        "Close out the issue for the deprecated API endpoint now that it's been fully "
        "removed from production.",
    ),
    Task(
        "transition_issue",
        "Move the new onboarding-flow issue back into the backlog since no one has "
        "started working on it yet.",
    ),
    Task(
        "transition_issue",
        "Mark the memory-leak investigation as finished now that the root cause has "
        "been patched and verified.",
    ),
    Task(
        "transition_issue",
        "Begin work on the flaky-test issue now that a QA engineer has started digging into it.",
    ),
    # set_issue_priority (enum constraint on `priority`) — 5 tasks
    Task(
        "set_issue_priority",
        "Flag the production outage issue as needing to be fixed immediately since it's "
        "blocking all customers from checking out.",
    ),
    Task(
        "set_issue_priority",
        "Raise the urgency on the login-timeout issue so it gets addressed as soon as "
        "possible this sprint.",
    ),
    Task(
        "set_issue_priority",
        "Set the newsletter-typo issue's urgency to a normal, ordinary level — nothing "
        "is broken, just cosmetic.",
    ),
    Task(
        "set_issue_priority",
        "Mark the icon-alignment issue as something that can wait and only be worked on "
        "when convenient.",
    ),
    Task(
        "set_issue_priority",
        "Tag the outdated-comment-in-code issue as trivial, with essentially no real "
        "impact on anything.",
    ),
    # add_issue_comment (format constraint on `issue_key`) — 5 tasks
    Task(
        "add_issue_comment",
        "Post a comment on the login-bug issue in the auth team's board explaining that "
        "the fix has been deployed to staging for verification.",
    ),
    Task(
        "add_issue_comment",
        "Add a note to the flaky-CI issue letting the team know the failure only "
        "reproduces on the Windows runner.",
    ),
    Task(
        "add_issue_comment",
        "Leave a comment on the customer-reported outage issue summarizing today's "
        "incident timeline for the support team.",
    ),
    Task(
        "add_issue_comment",
        "Comment on the pending security-review issue asking the assignee for an ETA on "
        "completing the review.",
    ),
    Task(
        "add_issue_comment",
        "Add a comment to the duplicate-report issue linking it to the original ticket "
        "it duplicates.",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
# Format tasks: no gold value — any value matching the pattern counts.
# Enum tasks: gold_value is the specific expected enum member.
TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # create_issue — format: project_key; enum: issue_type
    (
        "create_issue",
        "File a defect report in the mobile app team's Jira project describing that the "
        "checkout button doesn't respond on iOS Safari.",
    ): [
        Constraint("project_key", "format", pattern=r"[A-Z]{2,10}"),
        Constraint("issue_type", "enum", gold_value="Bug"),
    ],
    (
        "create_issue",
        "Create an issue in the platform team's Jira project to track the work of "
        "migrating the logging pipeline to structured JSON.",
    ): [
        Constraint("project_key", "format", pattern=r"[A-Z]{2,10}"),
        Constraint("issue_type", "enum", gold_value="Task"),
    ],
    (
        "create_issue",
        "Add an issue to the growth team's Jira project for the new user-facing "
        "referral-invite feature the product manager requested.",
    ): [
        Constraint("project_key", "format", pattern=r"[A-Z]{2,10}"),
        Constraint("issue_type", "enum", gold_value="Story"),
    ],
    (
        "create_issue",
        "Open an issue in the infrastructure team's Jira project for the multi-quarter "
        "initiative to migrate all services off the legacy datacenter.",
    ): [
        Constraint("project_key", "format", pattern=r"[A-Z]{2,10}"),
        Constraint("issue_type", "enum", gold_value="Epic"),
    ],
    (
        "create_issue",
        "Log an issue in the billing team's Jira project reporting that invoices are "
        "being generated with the wrong tax rate.",
    ): [
        Constraint("project_key", "format", pattern=r"[A-Z]{2,10}"),
        Constraint("issue_type", "enum", gold_value="Bug"),
    ],
    # transition_issue — enum: transition
    (
        "transition_issue",
        "Kick off work on the payment-retry issue in the billing project now that a "
        "developer has picked it up.",
    ): [Constraint("transition", "enum", gold_value="In Progress")],
    (
        "transition_issue",
        "Close out the issue for the deprecated API endpoint now that it's been fully "
        "removed from production.",
    ): [Constraint("transition", "enum", gold_value="Done")],
    (
        "transition_issue",
        "Move the new onboarding-flow issue back into the backlog since no one has "
        "started working on it yet.",
    ): [Constraint("transition", "enum", gold_value="To Do")],
    (
        "transition_issue",
        "Mark the memory-leak investigation as finished now that the root cause has "
        "been patched and verified.",
    ): [Constraint("transition", "enum", gold_value="Done")],
    (
        "transition_issue",
        "Begin work on the flaky-test issue now that a QA engineer has started digging into it.",
    ): [Constraint("transition", "enum", gold_value="In Progress")],
    # set_issue_priority — enum: priority
    (
        "set_issue_priority",
        "Flag the production outage issue as needing to be fixed immediately since it's "
        "blocking all customers from checking out.",
    ): [Constraint("priority", "enum", gold_value="Highest")],
    (
        "set_issue_priority",
        "Raise the urgency on the login-timeout issue so it gets addressed as soon as "
        "possible this sprint.",
    ): [Constraint("priority", "enum", gold_value="High")],
    (
        "set_issue_priority",
        "Set the newsletter-typo issue's urgency to a normal, ordinary level — nothing "
        "is broken, just cosmetic.",
    ): [Constraint("priority", "enum", gold_value="Medium")],
    (
        "set_issue_priority",
        "Mark the icon-alignment issue as something that can wait and only be worked on "
        "when convenient.",
    ): [Constraint("priority", "enum", gold_value="Low")],
    (
        "set_issue_priority",
        "Tag the outdated-comment-in-code issue as trivial, with essentially no real "
        "impact on anything.",
    ): [Constraint("priority", "enum", gold_value="Lowest")],
    # add_issue_comment — format: issue_key
    (
        "add_issue_comment",
        "Post a comment on the login-bug issue in the auth team's board explaining that "
        "the fix has been deployed to staging for verification.",
    ): [Constraint("issue_key", "format", pattern=r"[A-Z][A-Z0-9]{1,9}-[0-9]+")],
    (
        "add_issue_comment",
        "Add a note to the flaky-CI issue letting the team know the failure only "
        "reproduces on the Windows runner.",
    ): [Constraint("issue_key", "format", pattern=r"[A-Z][A-Z0-9]{1,9}-[0-9]+")],
    (
        "add_issue_comment",
        "Leave a comment on the customer-reported outage issue summarizing today's "
        "incident timeline for the support team.",
    ): [Constraint("issue_key", "format", pattern=r"[A-Z][A-Z0-9]{1,9}-[0-9]+")],
    (
        "add_issue_comment",
        "Comment on the pending security-review issue asking the assignee for an ETA on "
        "completing the review.",
    ): [Constraint("issue_key", "format", pattern=r"[A-Z][A-Z0-9]{1,9}-[0-9]+")],
    (
        "add_issue_comment",
        "Add a comment to the duplicate-report issue linking it to the original ticket "
        "it duplicates.",
    ): [Constraint("issue_key", "format", pattern=r"[A-Z][A-Z0-9]{1,9}-[0-9]+")],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    ["create_issue", "transition_issue", "set_issue_priority", "add_issue_comment"]
)
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["create_issue", "add_issue_comment"])
ENUM_TOOL_NAMES: frozenset[str] = frozenset(
    ["create_issue", "transition_issue", "set_issue_priority"]
)

# Enum gold values referenced in tasks (for inferability tests)
ENUM_GOLD_VALUES: list[str] = [
    "Bug",
    "Task",
    "Story",
    "Epic",
    "To Do",
    "In Progress",
    "Done",
    "Highest",
    "High",
    "Medium",
    "Low",
    "Lowest",
]
# Format patterns (for inferability tests — these should not appear verbatim in task text)
FORMAT_PATTERNS_SAMPLE: list[str] = [
    r"[A-Z]{2,10}",
    r"[A-Z][A-Z0-9]{1,9}-[0-9]+",
    "PROJ",
    "PROJ-123",
]

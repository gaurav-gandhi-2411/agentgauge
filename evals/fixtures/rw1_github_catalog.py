from __future__ import annotations

# RW1 pre-registered catalog — GitHub MCP server (github/github-mcp-server) mirror.
#
# LOCAL MIRROR ONLY: real tool names, JSON schemas, and docstrings from the public
# Go source (pkg/github/*.go). Stub bodies — NO live GitHub API, NO auth, NO write ops.
#
# 21 tools across 5 confusable families:
#   pr_read_family   (6): get/diff/files/reviews/comments + merge (destructive)
#   search_family    (4): repositories / code / issues / users
#   file_ops_family  (3): get_file_contents / create_or_update_file / push_files (2 destructive)
#   list_family      (4): pull_requests / issues / commits / branches
#   repo_ops_family  (4): get / list / create / fork repository (2 destructive)
#
# DESTRUCTIVE-CONFUSABLE PAIRS (painkiller metric):
#   5 pairs where a safe read-tool shares ≥2 required params with a write/delete neighbor.
#   Selecting the wrong one causes irreversible side-effects (file commit, repo creation, merge).
#
# GITHUB_HAND_FIXED_FAMILIES: ground truth for Part 1 score-validity cross-check.
#   These are families GitHub's own maintainers consolidated/restructured to reduce confusion.
#
# INDEPENDENCE RULE: the mirror server (rw1_github_mirror.py) was written to faithfully
# represent each tool's real behavior. Oracle descriptions are DERIVED from reading the
# mirror docstrings, not invented separately.
from pathlib import Path

from agentgauge.tasks import Task

_MIRROR_SERVER_PATH = Path(__file__).parent.parent.parent / "examples" / "rw1_github_mirror.py"


def get_mirror_source() -> str:
    """Return the mirror server source (rw1_github_mirror.py), including docstrings."""
    return _MIRROR_SERVER_PATH.read_text(encoding="utf-8")


# ── Tool families ──────────────────────────────────────────────────────────────
# WHY confusable is documented per family.

FAMILIES: dict[str, list[str]] = {
    # WHY confusable: all 5 read tools require (owner, repo, pullNumber); names share
    # "get_pull_request_" prefix. Terse descriptions risk collapsing to the same phrase.
    # merge_pull_request is the destructive neighbor with identical required params.
    "pr_read_family": [
        "get_pull_request",
        "get_pull_request_diff",
        "get_pull_request_files",
        "get_pull_request_reviews",
        "get_pull_request_comments",
        "merge_pull_request",
    ],
    # WHY confusable: all 4 tools have an identical top-level schema {query, page, perPage}.
    # Only the type of entity searched differs — agents must infer from description.
    "search_family": [
        "search_repositories",
        "search_code",
        "search_issues",
        "search_users",
    ],
    # WHY confusable: all 3 operate on (owner, repo, path/branch/files).
    # create_or_update_file and push_files are DESTRUCTIVE neighbors of get_file_contents.
    "file_ops_family": [
        "get_file_contents",
        "create_or_update_file",
        "push_files",
    ],
    # WHY confusable: all 4 list resources in a repo; names all start with "list_".
    # list_issues vs list_pull_requests are especially confusable (overlapping semantics).
    "list_family": [
        "list_pull_requests",
        "list_issues",
        "list_commits",
        "list_branches",
    ],
    # WHY confusable: all 4 named "*_repository" / "*_repositories".
    # create_repository and fork_repository are DESTRUCTIVE neighbors of get_repository.
    "repo_ops_family": [
        "get_repository",
        "list_repositories",
        "create_repository",
        "fork_repository",
    ],
}

FAMILY_MAP: dict[str, str] = {
    tool: family for family, tools in FAMILIES.items() for tool in tools
}

ALL_TOOLS: list[str] = [t for tools in FAMILIES.values() for t in tools]

# ── Per-tool JSON schemas (real GitHub MCP server schemas) ─────────────────────
# Derived from pkg/github/*.go mcp.NewTool(..., mcp.WithInputSchema(...)) calls.

_OWNER_REPO = {
    "owner": {"type": "string", "description": "Repository owner (username or organization)"},
    "repo": {"type": "string", "description": "Repository name"},
}
_PR_NUMBER = {"pullNumber": {"type": "integer", "description": "Pull request number"}}
_PAGINATION = {
    "page": {"type": "integer", "description": "Page number (default: 1)"},
    "perPage": {"type": "integer", "description": "Results per page (max 100)"},
}

TOOL_SCHEMAS: dict[str, dict] = {
    "get_pull_request": {
        "type": "object",
        "properties": {**_OWNER_REPO, **_PR_NUMBER},
        "required": ["owner", "repo", "pullNumber"],
    },
    "get_pull_request_diff": {
        "type": "object",
        "properties": {**_OWNER_REPO, **_PR_NUMBER},
        "required": ["owner", "repo", "pullNumber"],
    },
    "get_pull_request_files": {
        "type": "object",
        "properties": {**_OWNER_REPO, **_PR_NUMBER},
        "required": ["owner", "repo", "pullNumber"],
    },
    "get_pull_request_reviews": {
        "type": "object",
        "properties": {**_OWNER_REPO, **_PR_NUMBER},
        "required": ["owner", "repo", "pullNumber"],
    },
    "get_pull_request_comments": {
        "type": "object",
        "properties": {**_OWNER_REPO, **_PR_NUMBER},
        "required": ["owner", "repo", "pullNumber"],
    },
    "merge_pull_request": {
        "type": "object",
        "properties": {
            **_OWNER_REPO,
            **_PR_NUMBER,
            "commitTitle": {"type": "string", "description": "Commit title (optional)"},
            "commitMessage": {"type": "string", "description": "Commit message body (optional)"},
            "mergeMethod": {
                "type": "string",
                "description": "Merge strategy: merge, squash, or rebase (default: merge)",
            },
        },
        "required": ["owner", "repo", "pullNumber"],
    },
    "search_repositories": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            **_PAGINATION,
        },
        "required": ["query"],
    },
    "search_code": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            **_PAGINATION,
        },
        "required": ["query"],
    },
    "search_issues": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            **_PAGINATION,
        },
        "required": ["query"],
    },
    "search_users": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            **_PAGINATION,
        },
        "required": ["query"],
    },
    "get_file_contents": {
        "type": "object",
        "properties": {
            **_OWNER_REPO,
            "path": {"type": "string", "description": "Path to file or directory"},
            "ref": {
                "type": "string",
                "description": "Branch, tag, or commit SHA (defaults to default branch)",
            },
        },
        "required": ["owner", "repo", "path"],
    },
    "create_or_update_file": {
        "type": "object",
        "properties": {
            **_OWNER_REPO,
            "path": {"type": "string", "description": "File path to create or update"},
            "message": {"type": "string", "description": "Commit message"},
            "content": {"type": "string", "description": "New file content (UTF-8 text)"},
            "sha": {
                "type": "string",
                "description": "Current file SHA (required when updating an existing file)",
            },
            "branch": {"type": "string", "description": "Branch to commit to (optional)"},
        },
        "required": ["owner", "repo", "path", "message", "content"],
    },
    "push_files": {
        "type": "object",
        "properties": {
            **_OWNER_REPO,
            "branch": {"type": "string", "description": "Branch to push to"},
            "files": {
                "type": "array",
                "description": "Array of {path, content} objects for each file to push",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
            },
            "message": {"type": "string", "description": "Commit message"},
        },
        "required": ["owner", "repo", "branch", "files", "message"],
    },
    "list_pull_requests": {
        "type": "object",
        "properties": {
            **_OWNER_REPO,
            "state": {
                "type": "string",
                "description": "Filter by state: open, closed, or all (default: open)",
            },
            "head": {"type": "string", "description": "Filter by head branch"},
            "base": {"type": "string", "description": "Filter by base branch"},
            "sort": {
                "type": "string",
                "description": "Sort by: created, updated, popularity, long-running",
            },
            "direction": {"type": "string", "description": "asc or desc"},
            **_PAGINATION,
        },
        "required": ["owner", "repo"],
    },
    "list_issues": {
        "type": "object",
        "properties": {
            **_OWNER_REPO,
            "state": {"type": "string", "description": "open, closed, or all"},
            "labels": {"type": "string", "description": "Comma-separated label names"},
            "assignee": {"type": "string", "description": "Filter by assignee username"},
            "sort": {"type": "string", "description": "created, updated, or comments"},
            "direction": {"type": "string", "description": "asc or desc"},
            "since": {
                "type": "string",
                "description": "ISO 8601 timestamp — only issues updated after this time",
            },
            **_PAGINATION,
        },
        "required": ["owner", "repo"],
    },
    "list_commits": {
        "type": "object",
        "properties": {
            **_OWNER_REPO,
            "sha": {
                "type": "string",
                "description": "Branch or commit SHA to start listing from",
            },
            "path": {"type": "string", "description": "Only include commits touching this path"},
            "author": {"type": "string", "description": "Filter by author GitHub login"},
            **_PAGINATION,
        },
        "required": ["owner", "repo"],
    },
    "list_branches": {
        "type": "object",
        "properties": {
            **_OWNER_REPO,
            "protected": {
                "type": "boolean",
                "description": "If true, return only protected branches",
            },
            **_PAGINATION,
        },
        "required": ["owner", "repo"],
    },
    "get_repository": {
        "type": "object",
        "properties": {**_OWNER_REPO},
        "required": ["owner", "repo"],
    },
    "list_repositories": {
        "type": "object",
        "properties": {
            "username": {"type": "string", "description": "GitHub username to list repos for"},
            "type": {
                "type": "string",
                "description": "Repository type: all, owner, or member (default: owner)",
            },
            "sort": {
                "type": "string",
                "description": "Sort by: created, updated, pushed, or full_name",
            },
            "direction": {"type": "string", "description": "asc or desc"},
            **_PAGINATION,
        },
        "required": ["username"],
    },
    "create_repository": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Repository name"},
            "description": {"type": "string", "description": "Repository description"},
            "private": {"type": "boolean", "description": "Whether the repository is private"},
            "autoInit": {
                "type": "boolean",
                "description": "Initialize with a README file",
            },
            "org": {
                "type": "string",
                "description": "Organization name (creates under org instead of user account)",
            },
        },
        "required": ["name"],
    },
    "fork_repository": {
        "type": "object",
        "properties": {
            **_OWNER_REPO,
            "organization": {
                "type": "string",
                "description": "Organization to fork into (optional; defaults to user account)",
            },
            "name": {
                "type": "string",
                "description": "Optional new name for the fork",
            },
        },
        "required": ["owner", "repo"],
    },
}

# ── Real GitHub docstrings (as shipped in the MCP server's tool descriptions) ──
# Source: pkg/github/*.go — mcp.WithDescription(...) arguments.
# These are intentionally terse; they are Arm A for the A/B test.
# Note: unlike previous experiments (Q3–Q6), Arm A here is NOT empty —
# it is the REAL documented state of the GitHub MCP server.

GITHUB_DOCSTRINGS: dict[str, str] = {
    "get_pull_request": "Get details of a specific pull request",
    "get_pull_request_diff": "Get the diff of a pull request",
    "get_pull_request_files": "Get the list of files changed in a pull request",
    "get_pull_request_reviews": "Get the reviews of a pull request",
    "get_pull_request_comments": "Get the review comments on a pull request",
    "merge_pull_request": "Merge a pull request",
    "search_repositories": "Search for GitHub repositories",
    "search_code": "Search for code across GitHub repositories",
    "search_issues": "Search for issues and pull requests across GitHub repositories",
    "search_users": "Search for GitHub users and organizations",
    "get_file_contents": "Get the contents of a file or directory in a GitHub repository",
    "create_or_update_file": "Create or update a file in a GitHub repository",
    "push_files": "Push multiple files to a GitHub repository in a single commit",
    "list_pull_requests": "List and filter repository pull requests",
    "list_issues": "List and filter repository issues",
    "list_commits": "Get list of commits of a branch in a GitHub repository",
    "list_branches": "List branches in a GitHub repository",
    "get_repository": "Get details of a GitHub repository",
    "list_repositories": "List repositories for a GitHub user",
    "create_repository": "Create a new GitHub repository",
    "fork_repository": "Fork a GitHub repository to your account or specified organization",
}

# Arm A uses the real GitHub docstrings (not empty — this is the baseline being tested)
ARM_A_DESCRIPTIONS: dict[str, str] = dict(GITHUB_DOCSTRINGS)

# ── Oracle descriptions (Arm O ceiling) ───────────────────────────────────────
# Derived from reading rw1_github_mirror.py docstrings — NOT invented.
# Each contested tool's description encodes the distinguishing behavioral axis.

ARM_O_DESCRIPTIONS: dict[str, str] = {
    # pr_read_family — distinguishing axis: WHAT IS RETURNED
    "get_pull_request": (
        "Returns metadata for a pull request: title, body, state (open/closed/merged), author, "
        "head and base branch names, and merge readiness. Does NOT return code changes, "
        "file lists, or review comments."
    ),
    "get_pull_request_diff": (
        "Returns the raw unified diff showing all line-level code additions and deletions across "
        "every file changed in the pull request. Use when you need to inspect the exact code "
        "changes, not just which files were touched."
    ),
    "get_pull_request_files": (
        "Returns the list of file paths changed in a pull request with per-file statistics: "
        "filename, change status (added/modified/removed), and addition/deletion counts. "
        "Does not include the actual code diff text."
    ),
    "get_pull_request_reviews": (
        "Returns top-level review decisions on a pull request: each review's author, state "
        "(APPROVED / CHANGES_REQUESTED / COMMENTED), and overall review body. "
        "Does NOT return inline per-line comments — use get_pull_request_comments for those."
    ),
    "get_pull_request_comments": (
        "Returns inline review comments attached to specific lines in a pull request's diff. "
        "Each comment includes the file path, line number, and comment text. "
        "Does NOT return top-level review approvals — use get_pull_request_reviews for those."
    ),
    "merge_pull_request": (
        "Merges an open pull request into its base branch using the specified merge method "
        "(merge, squash, or rebase). Accepts an optional commit title and message. "
        "IRREVERSIBLE — the merge cannot be undone via the API."
    ),
    # search_family — distinguishing axis: WHAT IS SEARCHED
    "search_repositories": (
        "Searches GitHub repository metadata — name, description, topics, README content — "
        "matching the query. Returns repository records. Does NOT search file contents; "
        "use search_code to find code patterns inside files."
    ),
    "search_code": (
        "Searches the actual contents of files across GitHub repositories for the query. "
        "Returns file paths and matching code snippets. Use to find function definitions, "
        "variable usages, or specific code patterns inside source files."
    ),
    "search_issues": (
        "Searches issue and pull request text (title, body, comments) across repositories "
        "matching the query. Returns issue and PR records with state, labels, and assignees. "
        "Does NOT search repository metadata or code."
    ),
    "search_users": (
        "Searches GitHub user and organization profiles — username, full name, bio, location — "
        "matching the query. Returns user records. Does NOT search repositories, code, or issues."
    ),
    # file_ops_family — distinguishing axis: READ vs WRITE
    "get_file_contents": (
        "Retrieves the decoded text content of a file, or a directory listing, at a specific "
        "path in a repository. Accepts an optional ref (branch, tag, or SHA); defaults to the "
        "repository's default branch. Read-only — does not modify the repository."
    ),
    "create_or_update_file": (
        "Creates a new file or replaces an existing file at the given path, committing the "
        "change to the repository. Requires a commit message and file content. Requires the "
        "existing file's SHA when updating. WRITES to the repository — creates a new commit."
    ),
    "push_files": (
        "Pushes multiple files to a branch in a single commit. Each file entry specifies a "
        "path and content. Creates the branch if it does not exist. WRITES to the repository. "
        "Use when committing several files atomically; use create_or_update_file for a single file."
    ),
    # list_family — distinguishing axis: WHICH RESOURCE IS LISTED
    "list_pull_requests": (
        "Lists pull requests for a repository, filterable by state, head branch, base branch, "
        "and sort order. Returns pull request records — NOT issues or commits. "
        "Use list_issues if you need issues."
    ),
    "list_issues": (
        "Lists issues for a repository, filterable by state, labels, assignee, and date range. "
        "Returns issues only — NOT pull requests (even though PRs are issues internally). "
        "Use list_pull_requests to enumerate PRs."
    ),
    "list_commits": (
        "Returns the commit history of a branch or file path, ordered newest-first. Filterable "
        "by SHA/branch name, file path, and author login. Returns commit records — not PRs or "
        "issues."
    ),
    "list_branches": (
        "Returns all branch names in a repository with each branch's head commit SHA. Use to "
        "discover what branches currently exist before creating or targeting one."
    ),
    # repo_ops_family — distinguishing axis: READ vs CREATE
    "get_repository": (
        "Returns metadata for a specific repository: owner, name, description, visibility "
        "(public/private), default branch, fork status, star count, and clone URLs. "
        "Read-only — does not modify anything."
    ),
    "list_repositories": (
        "Returns a list of repositories accessible to a specific GitHub user. Filterable by "
        "type (all/owner/member), sort field, and direction. Returns repository records for "
        "an existing user — does not create repositories."
    ),
    "create_repository": (
        "Creates a NEW GitHub repository under the authenticated user or a specified "
        "organization. Configures name, description, visibility, and auto-initialization. "
        "CREATES a permanent repository — cannot be undone without deleting the repo."
    ),
    "fork_repository": (
        "Creates a fork of an existing repository under the authenticated user or a specified "
        "organization. The fork is a permanent, independent copy of the source. "
        "CREATES a new repository."
    ),
}

# ── Destructive tools and confusable pairs (painkiller / CEO metric) ───────────

# Tools that perform irreversible write, create, or merge operations.
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        "merge_pull_request",       # irreversible merge
        "create_or_update_file",    # commits new/modified file
        "push_files",               # commits multiple files
        "create_repository",        # creates permanent repository
        "fork_repository",          # creates permanent fork
    }
)

# (safe_tool, destructive_tool) pairs where both tools share ≥2 required params
# and the names are semantically related. Selecting the wrong one causes real damage.
DESTRUCTIVE_CONFUSABLE_PAIRS: list[tuple[str, str]] = [
    # Both take (owner, repo, pullNumber); names share "_pull_request"
    ("get_pull_request", "merge_pull_request"),
    # Both take (owner, repo, path); names share the file-path concept
    ("get_file_contents", "create_or_update_file"),
    # Both target a repository by path; push_files takes (owner, repo, branch, files)
    ("get_file_contents", "push_files"),
    # Both take (owner, repo); names share "_repository"
    ("get_repository", "fork_repository"),
]

# ── GitHub hand-fixed families (ground truth for Part 1 score-validity check) ─
# These are families GitHub's own maintainers consolidated or restructured to
# reduce agent/user confusion. If our scorer flags the same families, that is
# external evidence the score predicts real problems.

GITHUB_HAND_FIXED_FAMILIES: dict[str, str] = {
    "projects": (
        "Consolidated from 6 tools (get_project, list_project_items, get_project_item, "
        "add_project_item, update_project_item, delete_project_item) to 3 in a documented "
        "simplification pass — GitHub acknowledged the 6-tool surface was too confusing."
    ),
    "pr_read_variants": (
        "5 tools with the identical required-param signature (owner, repo, pullNumber) and "
        "names sharing the get_pull_request_ prefix. GitHub separated these as individual "
        "tools (each returning a different subset of PR data) rather than adding query params "
        "to a single endpoint — a structural source of confusion acknowledged in PR discussions."
    ),
    "search_variants": (
        "4 tools (search_repositories, search_code, search_issues, search_users) with "
        "identical top-level schemas {query, page, perPage}. The only disambiguation is the "
        "name suffix and description — no schema difference distinguishes them."
    ),
}

# ── Independence signals — phrases expected in mirror docstrings ───────────────
# CI asserts each signal appears in the corresponding handler's docstring.
# These are the behavioral facts that distinguish confusable tools.
MIRROR_DOCSTRING_SIGNALS: dict[str, str] = {
    "get_pull_request": "metadata",
    "get_pull_request_diff": "unified diff",
    "get_pull_request_files": "files changed",
    "get_pull_request_reviews": "review decisions",
    "get_pull_request_comments": "inline",
    "merge_pull_request": "IRREVERSIBLE",
    "get_file_contents": "Read-only",
    "create_or_update_file": "WRITES",
    "push_files": "multiple files",
    "search_repositories": "repository metadata",
    "search_code": "contents of files",
    "search_issues": "issues and pull requests",
    "search_users": "user profiles",
    "list_pull_requests": "pull request records",
    "list_issues": "issues only",
    "list_commits": "commit history",
    "list_branches": "branch names",
    "get_repository": "Read-only —",
    "list_repositories": "list of repositories",
    "create_repository": "CREATES",
    "fork_repository": "permanent",
}

# ── Tasks (21 pre-registered, 1 per tool, anti-tautology) ─────────────────────
# Each task describes intent only — does NOT name the gold tool or use oracle tokens.
# Tasks are designed so Arm A (real GitHub docstrings) may miss some contested ones,
# providing headroom for Guard-B to recover.

TASKS: list[Task] = [
    # pr_read_family — agent must distinguish between 5 terse "Get the <X> of a PR" descriptions
    Task(
        "get_pull_request",
        "Show me the title, description, and whether PR #142 in acme-corp/backend-api "
        "has been merged or is still open.",
    ),
    Task(
        "get_pull_request_diff",
        "Show the exact code changes line by line introduced by PR #142 "
        "in acme-corp/backend-api.",
    ),
    Task(
        "get_pull_request_files",
        "Which files did PR #142 in acme-corp/backend-api touch, and how many lines "
        "were added or removed in each file?",
    ),
    Task(
        "get_pull_request_reviews",
        "Has anyone approved or requested changes on PR #142 in acme-corp/backend-api?",
    ),
    Task(
        "get_pull_request_comments",
        "What inline comments have reviewers left on specific lines of code "
        "in PR #142 of acme-corp/backend-api?",
    ),
    Task(
        "merge_pull_request",
        "Squash-merge PR #142 into main in acme-corp/backend-api.",
    ),
    # search_family — same schema, distinguished only by what entity is searched
    Task(
        "search_repositories",
        "Find public GitHub repositories related to transformer-based language models.",
    ),
    Task(
        "search_code",
        "Find all places in GitHub where the Python function calculate_discount is defined.",
    ),
    Task(
        "search_issues",
        "Search for open GitHub issues mentioning 'null pointer exception' in the last month.",
    ),
    Task(
        "search_users",
        "Find GitHub users named Alex Chen who work at data science companies.",
    ),
    # file_ops_family — read vs write vs multi-write
    Task(
        "get_file_contents",
        "Read the current content of src/config/database.yaml from the main branch "
        "of acme-corp/backend-api.",
    ),
    Task(
        "create_or_update_file",
        "Update docs/changelog.md in acme-corp/backend-api on the docs branch with "
        "the v2.1 release notes; commit message should be 'docs: add v2.1 changelog'.",
    ),
    Task(
        "push_files",
        "Push three updated files to the feature/auth branch of acme-corp/backend-api "
        "in a single commit: app/auth.py, app/tokens.py, and tests/test_auth.py.",
    ),
    # list_family — each lists a different resource type
    Task(
        "list_pull_requests",
        "Show all open pull requests targeting the main branch of acme-corp/backend-api.",
    ),
    Task(
        "list_issues",
        "What open issues in acme-corp/backend-api are currently labeled 'bug'?",
    ),
    Task(
        "list_commits",
        "Show the ten most recent commits on the main branch of acme-corp/backend-api.",
    ),
    Task(
        "list_branches",
        "What branches exist in the acme-corp/backend-api repository right now?",
    ),
    # repo_ops_family — read vs create vs fork
    Task(
        "get_repository",
        "What is the default branch and visibility setting of the acme-corp/backend-api "
        "repository?",
    ),
    Task(
        "list_repositories",
        "What repositories does the GitHub user jsmith currently have?",
    ),
    Task(
        "create_repository",
        "Create a new private repository named data-pipeline under the acme-corp organization.",
    ),
    Task(
        "fork_repository",
        "Fork the tensorflow/tensorflow repository into the acme-corp organization.",
    ),
]

# Control task pairs: tasks where either tool in the pair is a valid answer.
# The pre-registered gold label is the first element — arbitrary where both are valid.
# These tasks are EXCLUDED from contested-task analysis.
CONTROL_TASK_PAIRS: list[tuple[str, str]] = [
    # None in RW1 — all families have clearly distinct intended tools.
    # The get_pull_request vs get_pull_request_diff distinction is real
    # (metadata vs diff are different outputs); no genuinely-equivalent pairs.
]

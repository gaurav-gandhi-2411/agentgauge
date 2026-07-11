from __future__ import annotations

# RW1 GitHub MCP server — LOCAL MIRROR with real docstrings, stub bodies.
#
# Tool names, JSON schemas, and docstrings are derived from the PUBLIC source of
# github/github-mcp-server (pkg/github/*.go). Bodies are stubs that return canned
# JSON — NO live GitHub API, NO auth tokens, NO write operations are performed.
#
# This file is the "source" input for the Guard-B fixer (Phase 1).
# _extract_scoped_function() extracts each _handle_<tool>() body + docstring.
# Independence signals in each docstring are verified by test_rw1_github.py.
#
# 5 confusable families, 21 tools. See evals/fixtures/rw1_github_catalog.py.

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from evals.fixtures.rw1_github_catalog import GITHUB_DOCSTRINGS, TOOL_SCHEMAS

server = Server("rw1-github-mirror")


# ── pr_read_family ─────────────────────────────────────────────────────────────


async def _handle_get_pull_request(owner: str, repo: str, pullNumber: int) -> str:
    """Get details of a specific pull request.

    Returns pull request metadata: title, body, state (open/closed/merged),
    author login, head branch, base branch, and merge readiness flags.
    Does NOT return the code diff, the list of changed files, or review comments.
    """
    return json.dumps({"stub": True, "tool": "get_pull_request", "pullNumber": pullNumber})


async def _handle_get_pull_request_diff(owner: str, repo: str, pullNumber: int) -> str:
    """Get the diff of a pull request.

    Returns the raw unified diff showing all line-level additions and deletions
    across every file changed in the pull request. Use when you need to inspect
    the exact code changes, not just which files were touched.
    """
    return json.dumps({"stub": True, "tool": "get_pull_request_diff", "pullNumber": pullNumber})


async def _handle_get_pull_request_files(owner: str, repo: str, pullNumber: int) -> str:
    """Get the list of files changed in a pull request.

    Returns a list of files changed in the pull request. Each entry includes the
    file path, change status (added/modified/removed), and addition/deletion counts.
    Does NOT include the actual diff text — use get_pull_request_diff for that.
    """
    return json.dumps({"stub": True, "tool": "get_pull_request_files", "pullNumber": pullNumber})


async def _handle_get_pull_request_reviews(owner: str, repo: str, pullNumber: int) -> str:
    """Get the reviews of a pull request.

    Returns top-level review decisions submitted by reviewers: each review's author,
    state (APPROVED / CHANGES_REQUESTED / COMMENTED), and the review body text.
    These are review decisions — NOT inline per-line comments on specific diff lines.
    Use get_pull_request_comments to retrieve inline per-line comments.
    """
    return json.dumps(
        {"stub": True, "tool": "get_pull_request_reviews", "pullNumber": pullNumber}
    )


async def _handle_get_pull_request_comments(owner: str, repo: str, pullNumber: int) -> str:
    """Get the review comments on a pull request.

    Returns inline review comments attached to specific lines in the pull request's
    diff. Each comment includes the file path, line number, and comment body.
    These are inline per-line comments — NOT top-level review decisions (approvals /
    change requests). Use get_pull_request_reviews to retrieve review decisions.
    """
    return json.dumps(
        {"stub": True, "tool": "get_pull_request_comments", "pullNumber": pullNumber}
    )


async def _handle_merge_pull_request(
    owner: str,
    repo: str,
    pullNumber: int,
    commitTitle: str = "",
    commitMessage: str = "",
    mergeMethod: str = "merge",
) -> str:
    """Merge a pull request.

    Merges an open pull request into its base branch using the specified merge method
    (merge, squash, or rebase). Accepts an optional commit title and message body.
    IRREVERSIBLE — once merged, the merge cannot be undone via the API. This is a
    write operation that permanently modifies the target branch's commit history.
    """
    return json.dumps({"stub": True, "tool": "merge_pull_request", "pullNumber": pullNumber})


# ── search_family ──────────────────────────────────────────────────────────────


async def _handle_search_repositories(query: str, page: int = 1, perPage: int = 30) -> str:
    """Search for GitHub repositories.

    Searches GitHub repository metadata — name, description, topics, and README
    content — matching the query string. Returns repository records including star
    count, language, and owner. Does NOT search the contents of source files;
    use search_code to find code patterns inside files.
    """
    return json.dumps({"stub": True, "tool": "search_repositories", "query": query})


async def _handle_search_code(query: str, page: int = 1, perPage: int = 30) -> str:
    """Search for code across GitHub repositories.

    Searches the actual contents of files across GitHub repositories for the query
    string. Returns file paths and matching code snippets with surrounding context.
    Use to find function definitions, variable usages, or specific code patterns
    inside source files. Does NOT search repository metadata or issue text.
    """
    return json.dumps({"stub": True, "tool": "search_code", "query": query})


async def _handle_search_issues(query: str, page: int = 1, perPage: int = 30) -> str:
    """Search for issues and pull requests across GitHub repositories.

    Searches issue and pull request text — title, body, and comments — across
    GitHub repositories matching the query. Returns issue and pull request records
    with state, labels, and assignees. Does NOT search repository metadata or
    source file contents.
    """
    return json.dumps({"stub": True, "tool": "search_issues", "query": query})


async def _handle_search_users(query: str, page: int = 1, perPage: int = 30) -> str:
    """Search for GitHub users and organizations.

    Searches GitHub user and organization profiles — username, full name, bio,
    company, and location — matching the query string. Returns user profiles.
    Does NOT search repositories, source files, or issues.
    """
    return json.dumps({"stub": True, "tool": "search_users", "query": query})


# ── file_ops_family ────────────────────────────────────────────────────────────


async def _handle_get_file_contents(
    owner: str, repo: str, path: str, ref: str = ""
) -> str:
    """Get the contents of a file or directory in a GitHub repository.

    Returns the decoded text content of a file at the given path, or a directory
    listing if the path points to a directory. Accepts an optional ref (branch,
    tag, or commit SHA); defaults to the repository's default branch.
    Read-only — does not modify the repository in any way.
    """
    return json.dumps({"stub": True, "tool": "get_file_contents", "path": path})


async def _handle_create_or_update_file(
    owner: str,
    repo: str,
    path: str,
    message: str,
    content: str,
    sha: str = "",
    branch: str = "",
) -> str:
    """Create or update a file in a GitHub repository.

    Creates a new file or replaces an existing file at the given path, committing
    the change directly to the repository. Requires a commit message and the new
    file content. Requires the existing file's SHA when updating an existing file.
    WRITES to the repository — creates a new commit on the target branch.
    """
    return json.dumps({"stub": True, "tool": "create_or_update_file", "path": path})


async def _handle_push_files(
    owner: str, repo: str, branch: str, files: list, message: str
) -> str:
    """Push multiple files to a GitHub repository in a single commit.

    Commits multiple files to a branch atomically in a single commit. Each file
    entry specifies a path and content. Creates the branch if it does not exist.
    WRITES to the repository. Use when committing several files together;
    use create_or_update_file for a single file.
    """
    return json.dumps(
        {"stub": True, "tool": "push_files", "branch": branch, "file_count": len(files)}
    )


# ── list_family ────────────────────────────────────────────────────────────────


async def _handle_list_pull_requests(
    owner: str,
    repo: str,
    state: str = "open",
    head: str = "",
    base: str = "",
    sort: str = "created",
    direction: str = "desc",
    page: int = 1,
    perPage: int = 30,
) -> str:
    """List and filter repository pull requests.

    Returns pull request records for a repository. Filterable by state
    (open/closed/all), head branch, base branch, sort field, and direction.
    Returns pull request records only — NOT issues or commits.
    Use list_issues if you need issue records.
    """
    return json.dumps({"stub": True, "tool": "list_pull_requests"})


async def _handle_list_issues(
    owner: str,
    repo: str,
    state: str = "open",
    labels: str = "",
    assignee: str = "",
    sort: str = "created",
    direction: str = "desc",
    since: str = "",
    page: int = 1,
    perPage: int = 30,
) -> str:
    """List and filter repository issues.

    Returns issues only for a repository. Filterable by state, labels, assignee,
    and update timestamp. Returns issues only — NOT pull requests, even though
    pull requests are implemented as issues internally in GitHub's data model.
    Use list_pull_requests to enumerate pull requests.
    """
    return json.dumps({"stub": True, "tool": "list_issues"})


async def _handle_list_commits(
    owner: str,
    repo: str,
    sha: str = "",
    path: str = "",
    author: str = "",
    page: int = 1,
    perPage: int = 30,
) -> str:
    """Get list of commits of a branch in a GitHub repository.

    Returns the commit history of a branch or file path, ordered newest-first.
    Each entry includes commit SHA, author, timestamp, and message. Filterable
    by starting SHA/branch name, file path, and author login. Returns commit
    records — not pull requests, issues, or branches.
    """
    return json.dumps({"stub": True, "tool": "list_commits"})


async def _handle_list_branches(
    owner: str, repo: str, protected: bool = False, page: int = 1, perPage: int = 30
) -> str:
    """List branches in a GitHub repository.

    Returns all branch names for a repository with each branch's head commit SHA.
    Optionally filter to protected branches only. Use to discover what branches
    currently exist before creating or targeting one for a commit or pull request.
    """
    return json.dumps({"stub": True, "tool": "list_branches"})


# ── repo_ops_family ────────────────────────────────────────────────────────────


async def _handle_get_repository(owner: str, repo: str) -> str:
    """Get details of a GitHub repository.

    Returns metadata for a specific repository: owner, name, description,
    visibility (public/private), default branch, fork status, star count, open
    issue count, and clone URLs. Read-only — does not modify the repository.
    """
    return json.dumps({"stub": True, "tool": "get_repository"})


async def _handle_list_repositories(
    username: str,
    type: str = "owner",
    sort: str = "updated",
    direction: str = "desc",
    page: int = 1,
    perPage: int = 30,
) -> str:
    """List repositories for a GitHub user.

    Returns a list of repositories accessible to the specified GitHub user.
    Filterable by type (all/owner/member), sort field, and direction. Returns
    repository records for an existing user — does not create or modify anything.
    """
    return json.dumps({"stub": True, "tool": "list_repositories", "username": username})


async def _handle_create_repository(
    name: str,
    description: str = "",
    private: bool = False,
    autoInit: bool = False,
    org: str = "",
) -> str:
    """Create a new GitHub repository.

    Creates a NEW repository under the authenticated user or a specified
    organization. Configures name, description, visibility, and initialization.
    CREATES a permanent repository — the repository persists until explicitly
    deleted. This is a write operation with lasting side-effects.
    """
    return json.dumps({"stub": True, "tool": "create_repository", "name": name})


async def _handle_fork_repository(
    owner: str, repo: str, organization: str = "", name: str = ""
) -> str:
    """Fork a GitHub repository to your account or specified organization.

    Creates a fork of an existing repository under the authenticated user or a
    specified organization. The fork is a permanent, independent copy of the
    source repository. CREATES a new repository with lasting side-effects.
    The fork persists until explicitly deleted.
    """
    return json.dumps({"stub": True, "tool": "fork_repository"})


# ── MCP server wiring ──────────────────────────────────────────────────────────

_DISPATCH: dict[str, object] = {
    "get_pull_request": _handle_get_pull_request,
    "get_pull_request_diff": _handle_get_pull_request_diff,
    "get_pull_request_files": _handle_get_pull_request_files,
    "get_pull_request_reviews": _handle_get_pull_request_reviews,
    "get_pull_request_comments": _handle_get_pull_request_comments,
    "merge_pull_request": _handle_merge_pull_request,
    "search_repositories": _handle_search_repositories,
    "search_code": _handle_search_code,
    "search_issues": _handle_search_issues,
    "search_users": _handle_search_users,
    "get_file_contents": _handle_get_file_contents,
    "create_or_update_file": _handle_create_or_update_file,
    "push_files": _handle_push_files,
    "list_pull_requests": _handle_list_pull_requests,
    "list_issues": _handle_list_issues,
    "list_commits": _handle_list_commits,
    "list_branches": _handle_list_branches,
    "get_repository": _handle_get_repository,
    "list_repositories": _handle_list_repositories,
    "create_repository": _handle_create_repository,
    "fork_repository": _handle_fork_repository,
}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=name, description=GITHUB_DOCSTRINGS[name], inputSchema=TOOL_SCHEMAS[name])
        for name in _DISPATCH
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    handler = _DISPATCH.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    result = await handler(**{k: v for k, v in arguments.items()})  # type: ignore[operator]
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="rw1-github-mirror",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

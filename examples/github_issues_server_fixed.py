from __future__ import annotations

# GitHub Issues call-correctness fixture — Arm F (same schemas as Arm A, real
# descriptions restored).
#
# Same 4 tools as github_issues_server.py. inputSchema is IDENTICAL to the Arm
# A variant (still type-only — no enum, no pattern keywords) so the only
# difference under test is whether the agent can construct correct calls from
# the Tool.description text alone.
#
# Constraint mix (2 tools per type):
#   FORMAT : create_issue (repo, "owner/repo" shape), add_assignee (assignee,
#            GitHub username shape)
#   ENUM   : update_issue_state (state, state_reason), add_label (label, one
#            of GitHub's standard default repository labels)
#
# Server always echoes success — validation is done by the run script comparing
# result.constructed_args against TASK_CONSTRAINTS, NOT by checking result.success.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("github-issues-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format-constrained tools ─────────────────────────────────────────
        types.Tool(
            name="create_issue",
            description=(
                "Creates a new issue in the specified GitHub repository. Requires repo "
                "(the full repository identifier in 'owner/repo' format, e.g. "
                "'octocat/Hello-World') and title (the issue's short summary). Optionally "
                "accepts body (a Markdown-formatted issue description), labels (a list of "
                "label names to apply), and assignee (the GitHub username of the person to "
                "assign). Unlike add_assignee or add_label, this tool creates a brand-new "
                "issue rather than modifying one that already exists."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "labels": {"type": "array"},
                    "assignee": {"type": "string"},
                },
                "required": ["title", "repo"],
            },
        ),
        types.Tool(
            name="add_assignee",
            description=(
                "Adds a single assignee to an existing GitHub issue. Requires repo (the "
                "repository in 'owner/repo' format), issue_number (the issue's number within "
                "that repository), and assignee (the GitHub username to assign — usernames "
                "contain only alphanumeric characters and hyphens, and cannot start or end "
                "with a hyphen). Unlike create_issue, this tool only updates the assignee of "
                "an issue that already exists; it does not create a new one."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                    "assignee": {"type": "string"},
                },
                "required": ["assignee", "repo", "issue_number"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="update_issue_state",
            description=(
                "Updates the open/closed state of an existing GitHub issue. Requires repo, "
                "issue_number, and state ('open' or 'closed'). Optionally accepts "
                "state_reason to record why the state changed: 'completed' (the underlying "
                "work was finished), 'not_planned' (the issue was closed without being "
                "addressed), 'duplicate' (the issue already exists elsewhere), or "
                "'reopened' (the issue was reopened after previously being closed). Unlike "
                "add_label, this tool changes the issue's lifecycle status rather than its "
                "categorization."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                    "state": {"type": "string"},
                    "state_reason": {"type": "string"},
                },
                "required": ["state", "repo", "issue_number"],
            },
        ),
        types.Tool(
            name="add_label",
            description=(
                "Applies a label to an existing GitHub issue for categorization. Requires "
                "repo, issue_number, and label — one of the repository's standard default "
                "labels: 'bug' (something isn't working), 'documentation' (improvements or "
                "additions to documentation), 'duplicate' (this issue already exists), "
                "'enhancement' (new feature or request), 'good first issue' (good for "
                "newcomers), 'help wanted' (extra attention is needed), 'invalid' (this "
                "doesn't seem right), 'question' (further information is requested), or "
                "'wontfix' (this will not be worked on). Unlike update_issue_state, this "
                "tool categorizes the issue rather than changing whether it is open or "
                "closed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                    "label": {"type": "string"},
                },
                "required": ["label", "repo", "issue_number"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    # Always echo success — correctness scoring happens in the run script via constructed_args.
    result = json.dumps({"tool": name, "args": arguments})
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="github-issues-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

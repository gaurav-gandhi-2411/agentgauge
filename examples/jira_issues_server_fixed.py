from __future__ import annotations

# Jira Issues call-correctness fixture — Arm F (same schemas as Arm A, real
# descriptions restored).
#
# Same 4 tools as jira_issues_server.py. inputSchema is IDENTICAL to the Arm
# A variant (still type-only — no enum, no pattern keywords) so the only
# difference under test is whether the agent can construct correct calls from
# the Tool.description text alone.
#
# Constraint mix:
#   FORMAT : create_issue (project_key, 2-10 uppercase-letter Jira project key
#            shape), add_issue_comment (issue_key, "PROJ-123" issue-key shape)
#   ENUM   : create_issue (issue_type, one of Jira's default issue types),
#            transition_issue (transition, one of a default Jira workflow's
#            status names), set_issue_priority (priority, Jira's default
#            priority scheme)
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

server = Server("jira-issues-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format + enum constrained tool ───────────────────────────────────
        types.Tool(
            name="create_issue",
            description=(
                "Creates a new issue in a Jira project. Requires project_key (the "
                "project's key — 2 to 10 uppercase letters, e.g. 'PROJ' or 'ENGTEAM' — "
                "identifying which project the issue belongs to), issue_type (one of "
                "Jira's default issue types: 'Bug' for a defect in existing "
                "functionality, 'Task' for a piece of work that needs doing, 'Story' for "
                "a user-facing feature or requirement, or 'Epic' for a large body of "
                "work that groups several stories/tasks/bugs together), and summary (a "
                "short one-line title for the issue). Optionally accepts description (a "
                "longer free-text explanation of the issue). Unlike transition_issue or "
                "set_issue_priority, this tool creates a brand-new issue rather than "
                "modifying one that already exists."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                    "issue_type": {"type": "string"},
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["summary", "project_key", "issue_type"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="transition_issue",
            description=(
                "Moves an existing Jira issue to a new status along its workflow. "
                "Requires issue_key (the issue's key, e.g. 'PROJ-123') and transition "
                "(the target status — one of 'To Do' for work not yet started, "
                "'In Progress' for work currently underway, or 'Done' for work that has "
                "been completed). Unlike set_issue_priority, this tool changes the "
                "issue's workflow status rather than its urgency ranking."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "transition": {"type": "string"},
                },
                "required": ["transition", "issue_key"],
            },
        ),
        types.Tool(
            name="set_issue_priority",
            description=(
                "Sets the priority of an existing Jira issue. Requires issue_key (the "
                "issue's key, e.g. 'PROJ-123') and priority — one of Jira's default "
                "priority scheme values, from most to least urgent: 'Highest' (blocks "
                "progress and must be fixed immediately), 'High' (should be resolved as "
                "soon as possible), 'Medium' (should be resolved in a normal timeframe), "
                "'Low' (minor, can be resolved when convenient), or 'Lowest' (trivial, "
                "little to no impact). Unlike transition_issue, this tool changes how "
                "urgently the issue should be worked on, not its workflow status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "priority": {"type": "string"},
                },
                "required": ["priority", "issue_key"],
            },
        ),
        # ── Format-constrained tool ───────────────────────────────────────────
        types.Tool(
            name="add_issue_comment",
            description=(
                "Adds a comment to an existing Jira issue. Requires issue_key (the "
                "issue's key — a project key followed by a hyphen and a number, e.g. "
                "'PROJ-123') and comment_body (the free-text content of the comment). "
                "Unlike create_issue, this tool only adds a comment to an issue that "
                "already exists; it does not create a new one."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "comment_body": {"type": "string"},
                },
                "required": ["comment_body", "issue_key"],
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
                server_name="jira-issues-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

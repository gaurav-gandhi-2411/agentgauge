from __future__ import annotations

# T16 held-out fixture — arm A (original / degraded).
# DO NOT tune these degradations against the fixer's behavior.
# Each degradation is documented with the pre-registered expected direction.
#
# Degradations applied (pre-registered):
#
# 1. create_task:
#    - Description "Create a task item." — vague, no param guidance
#    - Parameters have no `type` or `description` fields (bare `{}`)
#    - No `required` array — agent has no signal that `title` is mandatory
#    PRE-REGISTERED: arm A agent may omit `title` (required) or pass `priority` as
#    a string "3" instead of integer 3, or pass `due_date` in a non-ISO format.
#    All these trigger server-side validation failures → success=False.
#
# 2. get_task:
#    - Description "Get." — extremely vague
#    - `task_id` has no `type` or `description`; no `required` array
#    PRE-REGISTERED: agent may pass task_id as "1" (string) instead of 1 (integer).
#    Server strictly checks isinstance(task_id, int) → failure.
#
# 3. list_tasks:
#    - Description "List." — vague, no status/limit guidance
#    - `status` and `limit` have no `type` or `description`
#    PRE-REGISTERED: agent may pass status="incomplete" (not a valid enum value) or
#    limit="10" (string instead of integer).
#
# 4. complete_task:
#    - Description "Done." — ambiguous (could mean close, archive, finish)
#    - `task_id` and `note` have no `type` or `description`; no `required` array
#    PRE-REGISTERED: same as get_task.
#
# Fixed version (arm B): apply `agentgauge fix` on this file with qwen3:8b generator.
# The fixer adds types, descriptions, and `required` arrays to all parameters.
# Behavior is identical; only tool metadata changes.

import asyncio

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("tasktracker-mediocre")

# In-memory task store: {task_id: {title, priority, due_date, status, note}}
_tasks: dict[int, dict] = {}
_next_id = 1


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="create_task",
            description="Create a task item.",  # DEGRADED: vague, no param guidance
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {},  # DEGRADED: no type, no description
                    "priority": {},  # DEGRADED: no type, no description (should be int 1-5)
                    "due_date": {},  # DEGRADED: no type, no description (should be YYYY-MM-DD)
                },
                # DEGRADED: missing required — agent has no signal title is mandatory
            },
        ),
        types.Tool(
            name="get_task",
            description="Get.",  # DEGRADED: extremely vague
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {},  # DEGRADED: no type, no description (should be integer)
                },
                # DEGRADED: missing required
            },
        ),
        types.Tool(
            name="list_tasks",
            description="List.",  # DEGRADED: vague
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {},  # DEGRADED: no type, no description (should be 'open'|'done'|'all')
                    "limit": {},  # DEGRADED: no type, no description (should be integer)
                },
            },
        ),
        types.Tool(
            name="complete_task",
            description="Done.",  # DEGRADED: ambiguous — close? archive? finish?
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {},  # DEGRADED: no type, no description (should be integer)
                    "note": {},  # DEGRADED: no type, no description (optional completion note)
                },
                # DEGRADED: missing required
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    global _next_id

    if name == "create_task":
        title = arguments.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(
                "Required parameter 'title' must be a non-empty string. "
                'Example: {"title": "Write tests"}'
            )
        priority = arguments.get("priority", 3)
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise TypeError(
                f"Parameter 'priority' must be an integer 1-5, got {type(priority).__name__!r}. "
                'Example: {"priority": 2}'
            )
        if not 1 <= priority <= 5:
            raise ValueError(
                f"Parameter 'priority' must be 1-5 (got {priority}). "
                "1=highest priority, 5=lowest."
            )
        due_date = arguments.get("due_date")
        if due_date is not None:
            import re

            if not isinstance(due_date, str) or not re.match(
                r"^\d{4}-\d{2}-\d{2}$", due_date
            ):
                raise ValueError(
                    f"Parameter 'due_date' must be YYYY-MM-DD format (got {due_date!r}). "
                    'Example: {"due_date": "2026-06-30"}'
                )
        task_id = _next_id
        _next_id += 1
        _tasks[task_id] = {
            "title": title,
            "priority": priority,
            "due_date": due_date,
            "status": "open",
            "note": None,
        }
        return [types.TextContent(type="text", text=f"Created task {task_id}: {title!r}")]

    if name == "get_task":
        task_id = arguments.get("task_id")
        if task_id is None:
            raise ValueError(
                "Required parameter 'task_id' is missing. "
                'Example: {"task_id": 1}'
            )
        if not isinstance(task_id, int) or isinstance(task_id, bool):
            raise TypeError(
                f"Parameter 'task_id' must be an integer, got {type(task_id).__name__!r}. "
                'Example: {"task_id": 1}'
            )
        task = _tasks.get(task_id)
        if task is None:
            return [types.TextContent(type="text", text=f"No task with id={task_id}")]
        return [types.TextContent(type="text", text=str(task))]

    if name == "list_tasks":
        status = arguments.get("status", "all")
        if status not in ("open", "done", "all"):
            raise ValueError(
                f"Parameter 'status' must be 'open', 'done', or 'all' (got {status!r}). "
                "Omit to get all tasks."
            )
        limit = arguments.get("limit", 50)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError(
                f"Parameter 'limit' must be an integer (got {type(limit).__name__!r}). "
                'Example: {"limit": 10}'
            )
        if not 1 <= limit <= 100:
            raise ValueError(f"Parameter 'limit' must be 1-100 (got {limit}).")
        filtered = [
            {"id": tid, **t}
            for tid, t in _tasks.items()
            if status == "all" or t["status"] == status
        ]
        return [types.TextContent(type="text", text=str(filtered[:limit]))]

    if name == "complete_task":
        task_id = arguments.get("task_id")
        if task_id is None:
            raise ValueError(
                "Required parameter 'task_id' is missing. "
                'Example: {"task_id": 1}'
            )
        if not isinstance(task_id, int) or isinstance(task_id, bool):
            raise TypeError(
                f"Parameter 'task_id' must be an integer, got {type(task_id).__name__!r}. "
                'Example: {"task_id": 1}'
            )
        note = arguments.get("note")
        if note is not None and not isinstance(note, str):
            raise TypeError("Parameter 'note' must be a string if provided.")
        task = _tasks.get(task_id)
        if task is None:
            return [types.TextContent(type="text", text=f"No task with id={task_id}")]
        task["status"] = "done"
        task["note"] = note
        return [types.TextContent(type="text", text=f"Task {task_id} marked complete.")]

    raise ValueError(f"Unknown tool: {name!r}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="tasktracker-mediocre",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

# T17 selection-limited fixture — Arm B, ORACLE descriptions (pre-registered).
# Identical to confusable_server.py except descriptions are the oracle.
# Used for Q1: does a best-possible description improve selection vs Arm A (empty)?

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("confusable-v1-oracle")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # C1: search_documents / query_records
        types.Tool(
            name="search_documents",
            description=(
                "Performs full-text search across all document content. Use when you have a word "
                "or phrase to match against document bodies. NOT for field-based filtering."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="query_records",
            description=(
                "Executes a structured filter query using field conditions (e.g. field='value'). "
                "Use when you know which field to filter on. NOT for body text or keyword search."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["field", "value"],
            },
        ),
        # C2: send_message / dispatch_event
        types.Tool(
            name="send_message",
            description=(
                "Delivers a text message to a specific user by their user_id. Message is placed "
                "in the user's inbox. Use for human-facing notifications only."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["user_id", "body"],
            },
        ),
        types.Tool(
            name="dispatch_event",
            description=(
                "Publishes a typed event to the internal event bus for downstream service "
                "consumption. NOT for user-facing messages — use send_message for that."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "event_type": {"type": "string"},
                    "payload": {"type": "string"},
                },
                "required": ["event_type", "payload"],
            },
        ),
        # C3: list_items / enumerate_all
        types.Tool(
            name="list_items",
            description=(
                "Returns a paginated window of items using offset and limit. Use when you need "
                "a specific range or page of results."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "offset": {"type": "integer", "default": 0},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="enumerate_all",
            description=(
                "Returns the complete set of all items in a collection with no pagination. "
                "Use only when you need every item at once."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                },
                "required": ["collection"],
            },
        ),
        # C4: create_record / register_user
        types.Tool(
            name="create_record",
            description=(
                "Creates a new structured data record (order, product, note, etc.) with a "
                "system-assigned ID. NOT for user account creation — use register_user for that."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "data": {"type": "string"},
                },
                "required": ["type", "data"],
            },
        ),
        types.Tool(
            name="register_user",
            description=(
                "Creates a new user account with authentication credentials. Takes email and "
                "password. Use only when onboarding a new user to the platform."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                    "password": {"type": "string"},
                },
                "required": ["email", "password"],
            },
        ),
        # C5: update_record / patch_fields
        types.Tool(
            name="update_record",
            description=(
                "Replaces the entire record with the provided data. All required fields must be "
                "supplied; omitted optional fields are cleared or reset to defaults."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "data": {"type": "string"},
                },
                "required": ["id", "data"],
            },
        ),
        types.Tool(
            name="patch_fields",
            description=(
                "Updates only the specific fields you supply. Any field not included in the "
                "request remains unchanged. Use for partial edits."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "fields": {"type": "string"},
                },
                "required": ["id", "fields"],
            },
        ),
        # C6: delete_record / archive_record
        types.Tool(
            name="delete_record",
            description="Permanently and irreversibly removes a record. Cannot be undone.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
                "required": ["id"],
            },
        ),
        types.Tool(
            name="archive_record",
            description=(
                "Soft-deletes a record by marking it inactive. The record is hidden from normal "
                "views but remains in storage and can be restored."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
                "required": ["id"],
            },
        ),
        # C7: get_record / fetch_latest
        types.Tool(
            name="get_record",
            description=(
                "Retrieves a single record by its exact identifier. Requires an id. Returns an "
                "error if the id does not exist."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
                "required": ["id"],
            },
        ),
        types.Tool(
            name="fetch_latest",
            description=(
                "Returns the most recently added or updated item of a given type. Does not "
                "require an id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                },
                "required": ["type"],
            },
        ),
        # C8: export_report / extract_data
        types.Tool(
            name="export_report",
            description=(
                "Generates a formatted report file (PDF or CSV) from stored data and returns a "
                "download URL. Use when you need a shareable file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["pdf", "csv"]},
                    "dataset": {"type": "string"},
                },
                "required": ["format", "dataset"],
            },
        ),
        types.Tool(
            name="extract_data",
            description=(
                "Returns raw structured data inline in the response body as JSON/CSV. No file "
                "is created. Use when you need data to process programmatically."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dataset": {"type": "string"},
                },
                "required": ["dataset"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    result = json.dumps({"tool": name, "args": arguments})
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="confusable-v1-oracle",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

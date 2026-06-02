from __future__ import annotations

# T17 selection-limited fixture — Arm A (empty descriptions).
#
# 8 confusable clusters (2 tools each). Each cluster contains tools whose names
# are plausible and ambiguous between candidates; the disambiguating signal lives
# only in the description (absent here).
#
# CLUSTER HEADROOM MECHANISMS (pre-registered):
# C1 search_documents / query_records — names both suggest "get data"; only desc reveals
#    full-text keyword vs structured field filter.
# C2 send_message / dispatch_event — both suggest "push something"; only desc reveals
#    user inbox vs inter-service event bus.
# C3 list_items / enumerate_all — both suggest "get items"; only desc reveals
#    paginated window vs full collection.
# C4 create_record / register_user — both suggest "make new thing"; only desc reveals
#    generic entity vs user account with credentials.
# C5 update_record / patch_fields — both suggest "change data"; only desc reveals
#    full-replace vs partial update.
# C6 delete_record / archive_record — both suggest "make go away"; only desc reveals
#    permanent removal vs reversible soft-delete.
# C7 get_record / fetch_latest — "get" and "fetch" are synonymous prefixes; only desc
#    reveals ID-required lookup vs newest-item-no-ID.
# C8 export_report / extract_data — both suggest "get data out"; only desc reveals
#    file-generation-with-URL vs inline raw payload.
#
# Pre-registered expected direction: Arm B (oracle) > Arm A on selection_accuracy
# for ALL clusters when descriptions resolve the ambiguity.

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("confusable-v1")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # C1: search_documents / query_records
        types.Tool(
            name="search_documents",
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
            description="",
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
                server_name="confusable-v1",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

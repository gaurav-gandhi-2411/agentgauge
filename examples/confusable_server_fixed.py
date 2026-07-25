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
            description='Searches through a collection of documents to find relevant information based on the provided query. Key parameter: query (string) - the search term or question used to find relevant documents, distinguishing it from general-purpose search tools by focusing on document-specific content retrieval.',
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
            description="The query_records tool filters records by matching the specified field to a given value. It requires 'field' (the attribute to search) and 'value' (the exact value to match).",
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
            description='Sends a message to a specified user, with user_id identifying the recipient and body containing the message text. Intended for direct communication, distinct from broadcast or group messaging tools.',
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["body", "user_id"],
            },
        ),
        types.Tool(
            name="dispatch_event",
            description="The dispatch_event tool triggers specified events in a system by sending an event type and associated payload data. It requires 'event_type' (string, the event's category) and 'payload' (string, event-specific data), distinguishing it from tools that merely log events by enabling direct action initiation via structured data.",
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
            description='The list_items tool retrieves items with optional pagination parameters: offset (starting index, default 0) and limit (number of items, default 10).',
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
            description="Enumerates all items in a specified collection. The 'collection' parameter specifies the name of the collection to enumerate.",
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
            description="The create_record tool generates a structured record by specifying its type and data content, with 'type' defining the record category and 'data' containing the serialized payload, distinguishing it from generic data entry tools by enforcing schema-based record creation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "data": {"type": "string"},
                },
                "required": ["data", "type"],
            },
        ),
        types.Tool(
            name="register_user",
            description="Registers a new user with the provided email and password. Requires email (user's email address) and password (account password).",
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
            description="Updates an existing record by its ID with the provided data. Requires 'id' (record identifier) and 'data' (new information to replace existing content).",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "data": {"type": "string"},
                },
                "required": ["data", "id"],
            },
        ),
        types.Tool(
            name="patch_fields",
            description="Updates specified fields of an object by its ID, using a string-formatted 'fields' parameter (e.g., 'field1=value1,field2=value2') for partial updates, differing from full-replacement tools.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "fields": {"type": "string"},
                },
                "required": ["fields", "id"],
            },
        ),
        # C6: delete_record / archive_record
        types.Tool(
            name="delete_record",
            description="The delete_record tool deletes a record by its unique ID. The 'id' parameter is a string representing the record's unique identifier.",
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
            description='The `archive_record` tool archives a record by its unique identifier, using the `id` parameter to specify which record to archive. Unlike deletion tools, it moves records to an archive state rather than permanently removing them.',
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
            description="The get_record tool retrieves a specific record by its unique ID. It requires the 'id' parameter, which identifies the record, and is designed for exact matches, unlike tools that use filters or queries.",
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
            description="The fetch_latest tool retrieves the most recent data entries based on the specified type. It requires a 'type' parameter (string) to define the category of data to fetch.",
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
            description='Exports a dataset into a specified format (PDF or CSV) using the provided dataset identifier. Parameters: format (pdf/csv) defines the output type, dataset (string) specifies the source dataset.',
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["pdf", "csv"]},
                    "dataset": {"type": "string"},
                },
                "required": ["dataset", "format"],
            },
        ),
        types.Tool(
            name="extract_data",
            description='The extract_data tool retrieves structured data from a specified dataset. The dataset parameter identifies the source dataset, while the tool focuses on direct extraction rather than transformation or analysis.',
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

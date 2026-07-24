from __future__ import annotations

# AWS S3 call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools modeled on real AWS S3 API operations. Arm A schemas show type-only
# ({"type": "string"} / {"type": "integer"}) — no enum, no pattern, no
# description. The agent must rely solely on param names and task text to
# construct valid calls.
#
# Constraint mix (2 tools per type, plus one dual-constraint tool):
#   FORMAT : create_bucket (region, AWS region shape), put_object (bucket,
#            S3 bucket-naming shape)
#   ENUM   : put_object (storage_class, one of S3's real storage classes),
#            set_bucket_versioning (status), set_object_acl (acl, one of
#            S3's real canned ACLs)
#
# Server always echoes success — validation is done by the run script comparing
# result.constructed_args against TASK_CONSTRAINTS, NOT by checking result.success.
#
# See evals/fixtures/v2_4_corpus/aws_s3_NOTES.md for which real S3 operations
# these tools paraphrase.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("aws-s3-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format-constrained tool ───────────────────────────────────────────
        types.Tool(
            name="create_bucket",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {"type": "string"},
                    "region": {"type": "string"},
                },
                "required": ["bucket", "region"],
            },
        ),
        # ── Format + enum constrained tool ────────────────────────────────────
        types.Tool(
            name="put_object",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {"type": "string"},
                    "key": {"type": "string"},
                    "body": {"type": "string"},
                    "storage_class": {"type": "string"},
                },
                "required": ["bucket", "key", "body"],
            },
        ),
        # ── Enum-constrained tools ─────────────────────────────────────────────
        types.Tool(
            name="set_bucket_versioning",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["bucket", "status"],
            },
        ),
        types.Tool(
            name="set_object_acl",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {"type": "string"},
                    "key": {"type": "string"},
                    "acl": {"type": "string"},
                },
                "required": ["bucket", "key", "acl"],
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
                server_name="aws-s3-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

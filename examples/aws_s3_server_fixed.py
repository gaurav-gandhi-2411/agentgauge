from __future__ import annotations

# AWS S3 call-correctness fixture — Arm A (vague schemas, no constraints).
#
# Same 4 tools as aws_s3_server.py. inputSchema is IDENTICAL to the Arm A
# variant (still type-only — no enum, no pattern keywords) so the only
# difference under test is whether the agent can construct correct calls from
# the Tool.description text alone.
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
            description=(
                "Creates a new S3 bucket in the specified AWS region. Requires bucket (the "
                "globally unique bucket name — lowercase letters, digits, hyphens, and dots "
                "only, 3-63 characters, must start and end with a letter or digit) and region "
                "(the AWS region code where the bucket's data will physically reside, e.g. "
                "'us-east-1', 'us-west-2', 'eu-west-1', 'eu-central-1', 'ap-southeast-2'). "
                "Unlike put_object, this tool only creates the empty bucket container itself; "
                "it does not upload any object into it."
            ),
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
            description=(
                "Uploads an object (file) into an existing S3 bucket. Requires bucket (the "
                "target bucket's name, following the same lowercase/hyphen/dot naming shape as "
                "create_bucket's bucket parameter), key (the object's path/name within the "
                "bucket, e.g. 'reports/2026/q1.pdf'), and body (the object's content). "
                "Optionally accepts storage_class — the S3 storage class to store the object "
                "under, one of 'STANDARD' (the default; for frequently accessed data needing "
                "low-latency, high-throughput retrieval), 'STANDARD_IA' (cheaper per-GB storage "
                "for data accessed infrequently but that must still be retrievable immediately, "
                "not after a delay, when it is needed), 'GLACIER' (the cheapest option, for "
                "archival data that is rarely if ever retrieved, where an asynchronous retrieval "
                "delay of minutes to hours is acceptable), or 'INTELLIGENT_TIERING' (automatically "
                "moves the object between frequent- and infrequent-access tiers as its actual "
                "access pattern changes over time, ideal when that pattern is not known in "
                "advance). Unlike create_bucket, this tool adds an object to a bucket that must "
                "already exist."
            ),
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
            description=(
                "Turns object versioning on or off for an existing bucket. Requires bucket and "
                "status, one of 'Enabled' (every future upload to the bucket keeps a recoverable "
                "prior copy of any object it overwrites or deletes) or 'Suspended' (new uploads "
                "stop creating additional versions, but any versions the bucket has already "
                "accumulated are kept, not deleted — S3 has no 'fully disable' state once "
                "versioning has been enabled). Unlike set_object_acl, this tool controls whether "
                "prior copies of objects are retained, not who can access them."
            ),
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
            description=(
                "Sets a canned access-control policy on an existing object. Requires bucket, "
                "key, and acl, one of 'private' (only this AWS account can read or write the "
                "object; the default), 'public-read' (anyone on the internet, with no login "
                "required, can read the object), 'public-read-write' (anyone on the internet can "
                "both read and overwrite the object — rarely appropriate, since it allows "
                "anonymous uploads), or 'authenticated-read' (any logged-in AWS user, from any "
                "AWS account, can read the object, but anonymous internet visitors cannot). "
                "Unlike set_bucket_versioning, this tool controls who can access a single object, "
                "not whether prior versions of it are retained."
            ),
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

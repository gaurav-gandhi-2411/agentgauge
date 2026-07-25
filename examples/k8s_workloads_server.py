from __future__ import annotations

# Kubernetes workloads call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools modeled on real Kubernetes API operations. Arm A schemas show type-only
# ({"type": "string"} / {"type": "integer"} / {"type": "object"}) — no enum, no
# pattern, no minimum/maximum, no description. The agent must rely solely on param
# names and task text to construct valid calls.
#
# Constraint mix:
#   FORMAT + ENUM : create_pod (namespace, DNS-1123 label shape; restart_policy,
#                   one of Always/OnFailure/Never)
#   RANGE         : scale_deployment (replicas)
#   ENUM          : set_pod_image_pull_policy (pull_policy, one of
#                   Always/IfNotPresent/Never)
#   FORMAT        : create_namespace (name, DNS-1123 label shape)
#
# Server always echoes success — validation is done by the run script comparing
# result.constructed_args against TASK_CONSTRAINTS, NOT by checking result.success.
#
# See evals/fixtures/v2_4_corpus/k8s_workloads_NOTES.md for which real Kubernetes
# operations these tools paraphrase.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("k8s-workloads-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format + enum constrained tool ───────────────────────────────────
        types.Tool(
            name="create_pod",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "namespace": {"type": "string"},
                    "image": {"type": "string"},
                    "restart_policy": {"type": "string"},
                },
                "required": ["name", "namespace", "image"],
            },
        ),
        # ── Range-constrained tool ────────────────────────────────────────────
        types.Tool(
            name="scale_deployment",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "namespace": {"type": "string"},
                    "replicas": {"type": "integer"},
                },
                "required": ["name", "namespace", "replicas"],
            },
        ),
        # ── Enum-constrained tool ─────────────────────────────────────────────
        types.Tool(
            name="set_pod_image_pull_policy",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "pod_name": {"type": "string"},
                    "namespace": {"type": "string"},
                    "container_name": {"type": "string"},
                    "pull_policy": {"type": "string"},
                },
                "required": ["pod_name", "namespace", "container_name", "pull_policy"],
            },
        ),
        # ── Format-constrained tool ────────────────────────────────────────────
        types.Tool(
            name="create_namespace",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "labels": {"type": "object"},
                },
                "required": ["name"],
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
                server_name="k8s-workloads-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

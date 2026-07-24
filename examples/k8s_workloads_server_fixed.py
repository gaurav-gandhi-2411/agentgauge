from __future__ import annotations

# Kubernetes workloads call-correctness fixture — Arm A (vague schemas, no constraints).
#
# Same 4 tools as k8s_workloads_server.py. inputSchema is IDENTICAL to the Arm A
# variant (still type-only — no enum, no pattern, no minimum/maximum keywords) so
# the only difference under test is whether the agent can construct correct calls
# from the Tool.description text alone.
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
            description=(
                "Creates a new Pod running one container. Parameters: name (string) — the "
                "Pod's name; namespace (string) — the namespace to create the Pod in, which "
                "must be a valid DNS-1123 label (lowercase alphanumeric characters or '-', "
                "starting with a lowercase letter and ending with an alphanumeric "
                "character, e.g. 'staging' or "
                "'ml-training'); image (string) — the container image reference to run (e.g. "
                "'nginx:1.25'); restart_policy (string, optional) — what to do when the Pod's "
                "container exits, one of 'Always' (the default; always restart the container "
                "regardless of exit status, appropriate for long-running services), "
                "'OnFailure' (only restart if the container exits with a non-zero/error status; "
                "appropriate for batch or retryable jobs), or 'Never' (never restart the "
                "container after it exits, appropriate for one-shot/run-once jobs). Unlike "
                "scale_deployment, this tool creates a single standalone Pod rather than "
                "managing a set of replicated Pods."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "namespace": {"type": "string"},
                    "image": {"type": "string"},
                    "restart_policy": {"type": "string"},
                },
                "required": ["image", "name", "namespace"],
            },
        ),
        # ── Range-constrained tool ────────────────────────────────────────────
        types.Tool(
            name="scale_deployment",
            description=(
                "Changes the number of running Pod replicas for an existing Deployment by "
                "updating its scale subresource. Parameters: name (string) — the Deployment's "
                "name; namespace (string) — the namespace the Deployment lives in; replicas "
                "(integer) — the desired total number of Pod replicas to run, from 0 (scales "
                "the Deployment down to zero running Pods without deleting it) up to whatever "
                "count is needed to meet demand. Unlike create_pod, this tool does not create "
                "individual Pods directly — it adjusts how many Pods the Deployment's "
                "controller keeps running on its behalf."
            ),
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
            description=(
                "Updates how a container inside an existing Pod decides whether to pull its "
                "image from a registry before starting. Parameters: pod_name (string) — the "
                "Pod's name; namespace (string) — the namespace the Pod lives in; "
                "container_name (string) — the name of the container within the Pod to update; "
                "pull_policy (string) — one of 'Always' (always pull the image from the "
                "registry before starting, even if a matching image is already cached on the "
                "node — useful for mutable tags like a floating build tag), 'IfNotPresent' "
                "(only pull if the image isn't already present on the node — avoids "
                "unnecessary registry calls for version-pinned, immutable images), or 'Never' "
                "(never pull from a registry; the image must already exist on the node, as in "
                "local development clusters or air-gapped environments with no registry "
                "access). Unlike create_pod, this tool modifies a container setting on a Pod "
                "that already exists rather than creating a new one."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pod_name": {"type": "string"},
                    "namespace": {"type": "string"},
                    "container_name": {"type": "string"},
                    "pull_policy": {"type": "string"},
                },
                "required": ["container_name", "namespace", "pod_name", "pull_policy"],
            },
        ),
        # ── Format-constrained tool ────────────────────────────────────────────
        types.Tool(
            name="create_namespace",
            description=(
                "Creates a new, empty Namespace to logically isolate a group of resources "
                "within the cluster. Parameters: name (string) — the Namespace's name, which "
                "must be a valid DNS-1123 label (lowercase alphanumeric characters or '-', "
                "starting with a lowercase letter and ending with an alphanumeric "
                "character, e.g. 'qa-integration' or "
                "'ml-experiments'); labels (object, optional) — arbitrary key/value metadata "
                "labels to attach to the Namespace for later selection or organization. Unlike "
                "create_pod or scale_deployment, this tool provisions a cluster-scoped "
                "isolation boundary rather than any workload running inside one."
            ),
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

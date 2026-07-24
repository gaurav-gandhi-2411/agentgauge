from __future__ import annotations

# Docker Engine API call-correctness fixture — Arm F (same schemas as Arm A, real
# descriptions restored).
#
# Same 4 tools as docker_containers_server.py. inputSchema is IDENTICAL to the
# Arm A variant (still type-only — no enum, no pattern keywords) so the only
# difference under test is whether the agent can construct correct calls from
# the Tool.description text alone.
#
# Constraint mix:
#   FORMAT : create_container (image, "name:tag" shape), tag_image (tag, Docker
#            tag-name shape)
#   ENUM   : create_container (restart_policy, Docker's real RestartPolicy.Name
#            values), create_network (driver, a subset of Docker's real
#            built-in network drivers)
#   RANGE  : stop_container (timeout_seconds, graceful-shutdown grace period)
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

server = Server("docker-containers-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format + enum constrained tool ───────────────────────────────────
        types.Tool(
            name="create_container",
            description=(
                "Creates and starts a new Docker container from an image. Requires image "
                "(the image reference to run, in 'name:tag' format, e.g. 'nginx:1.25' or "
                "'redis:7-alpine' — if no tag is given Docker defaults to 'latest') and "
                "restart_policy (what Docker should do if the container exits: 'no' — never "
                "restart automatically, 'always' — always restart regardless of exit status, "
                "'on-failure' — only restart if the container exits with a non-zero status, "
                "or 'unless-stopped' — always restart unless the container was explicitly "
                "stopped by the user). Optionally accepts name (a human-readable name for the "
                "container) and env (a list of 'KEY=VALUE' environment variable strings to set "
                "inside the container). Unlike stop_container or tag_image, this tool "
                "provisions a brand-new container rather than acting on one that already "
                "exists."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image": {"type": "string"},
                    "name": {"type": "string"},
                    "restart_policy": {"type": "string"},
                    "env": {"type": "array"},
                },
                "required": ["restart_policy", "image"],
            },
        ),
        # ── Range-constrained tool ────────────────────────────────────────────
        types.Tool(
            name="stop_container",
            description=(
                "Stops a running Docker container by sending it a graceful termination "
                "signal. Requires container_id (the ID or name of the running container to "
                "stop) and timeout_seconds (how many seconds to wait for the container to shut "
                "down gracefully before Docker force-kills it — a short value gives the "
                "process almost no time to clean up, while a long value gives it much more "
                "room to finish in-flight work before being killed). Unlike create_container, "
                "this tool acts on a container that already exists and is currently running; "
                "it does not create or start anything new."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "container_id": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                },
                "required": ["timeout_seconds", "container_id"],
            },
        ),
        # ── Enum-constrained tool ─────────────────────────────────────────────
        types.Tool(
            name="create_network",
            description=(
                "Creates a new Docker network that containers can be attached to. Requires "
                "name (the network's name) and driver (which networking driver to use: "
                "'bridge' — an isolated private network on a single host, Docker's default "
                "for standalone containers; 'host' — removes network isolation and lets the "
                "container share the host machine's own networking stack directly; 'overlay' "
                "— a network spanning multiple Docker hosts, used for multi-host Swarm "
                "services; or 'none' — disables networking for the container entirely). "
                "Optionally accepts internal (a boolean; when true, the network has no "
                "external connectivity outside the Docker host). Unlike create_container, this "
                "tool provisions a network resource, not a container."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "driver": {"type": "string"},
                    "internal": {"type": "boolean"},
                },
                "required": ["driver", "name"],
            },
        ),
        # ── Format-constrained tool ───────────────────────────────────────────
        types.Tool(
            name="tag_image",
            description=(
                "Creates a new tag that refers to an existing local Docker image, without "
                "duplicating the image's underlying layers. Requires source_image (the "
                "existing local image to tag, in 'name:tag' format), repo (the target "
                "repository name the new tag should belong to, e.g. 'myuser/myapp'), and tag "
                "(the new tag name to assign within that repository — Docker tag names must "
                "start with a letter, digit, or underscore, and may otherwise contain letters, "
                "digits, underscores, periods, and hyphens, up to 128 characters). Unlike "
                "create_container, this tool does not run anything; it only creates an "
                "additional named reference to an image that already exists locally."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source_image": {"type": "string"},
                    "repo": {"type": "string"},
                    "tag": {"type": "string"},
                },
                "required": ["tag", "repo", "source_image"],
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
                server_name="docker-containers-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

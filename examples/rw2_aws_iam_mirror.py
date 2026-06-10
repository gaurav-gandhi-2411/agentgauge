from __future__ import annotations

# RW2 AWS IAM MCP server — LOCAL MIRROR with real docstrings, stub bodies.
#
# Tool names, JSON schemas, and Arm A descriptions are derived from the PUBLIC source of
# awslabs/mcp (src/iam-mcp-server/awslabs/iam_mcp_server/server.py). Bodies are stubs
# that return canned JSON — NO live AWS API, NO credentials, NO write operations.
#
# This file is the "source" input for the Guard-B fixer (Phase 1).
# _extract_scoped_function() extracts each _handle_<tool>() body + docstring.
# Independence signals in each docstring are verified by test_rw2_aws_iam.py.
#
# 29 tools across 10 families. See evals/fixtures/rw2_aws_iam_catalog.py.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from evals.fixtures.rw2_aws_iam_catalog import AWS_IAM_DOCSTRINGS, TOOL_SCHEMAS

server = Server("rw2-aws-iam-mirror")


# ── attach_detach_family ────────────────────────────────────────────────────────


async def _handle_attach_user_policy(
    user_name: str, policy_arn: str, confirmed: bool = False
) -> str:
    """Attach a managed policy to an IAM user.

    Assigns the managed policy identified by policy_arn to the specified individual user.
    This targets an individual user — not any group the user belongs to.
    Use attach_group_policy when the target is an IAM group rather than an individual user.
    The policy must be a managed policy ARN (not an inline policy document).
    """
    return json.dumps({"stub": True, "tool": "attach_user_policy", "user_name": user_name})


async def _handle_attach_group_policy(
    group_name: str, policy_arn: str, confirmed: bool = False
) -> str:
    """Attach a managed policy to an IAM group.

    Assigns the managed policy identified by policy_arn to the specified IAM group.
    All current and future members of the group inherit the permissions from this policy.
    Use attach_user_policy when the target is an individual user rather than a group.
    """
    return json.dumps({"stub": True, "tool": "attach_group_policy", "group_name": group_name})


async def _handle_detach_user_policy(
    user_name: str, policy_arn: str, confirmed: bool = False
) -> str:
    """Detach a managed policy from an IAM user.

    Removes the managed policy identified by policy_arn from the individual IAM user.
    The policy itself is NOT deleted — it is only disassociated from this user.
    Affects only this user; does not affect not any group the user belongs to.
    Use detach_group_policy when the target is a group.
    This removes a MANAGED policy; use delete_user_policy to permanently destroy an INLINE policy.
    """
    return json.dumps({"stub": True, "tool": "detach_user_policy", "user_name": user_name})


async def _handle_detach_group_policy(
    group_name: str, policy_arn: str, confirmed: bool = False
) -> str:
    """Detach a managed policy from an IAM group.

    Removes the managed policy from the specified IAM group.
    All members of the group lose the permissions granted by this policy.
    The policy itself is NOT deleted.
    Use detach_user_policy when the target is an individual user rather than a group.
    """
    return json.dumps({"stub": True, "tool": "detach_group_policy", "group_name": group_name})


# ── list_policies_family ────────────────────────────────────────────────────────


async def _handle_list_policies(
    scope: str = "Local",
    only_attached: bool = False,
    path_prefix: str | None = None,
    max_items: int = 100,
) -> str:
    """List managed IAM policies in the account.

    Returns AWS-managed or customer-managed policies at the account level.
    Does NOT return inline policies embedded inside users or roles.
    To list inline policies for a specific user, use list_user_policies.
    To list inline policies for a specific role, use list_role_policies.
    """
    return json.dumps({"stub": True, "tool": "list_policies", "scope": scope})


async def _handle_list_user_policies(user_name: str) -> str:
    """List inline policies for an IAM user.

    Returns the names of inline policies embedded directly inside the specified user.
    These are inline policies embedded in the user, NOT standalone managed policies.
    Use list_role_policies for roles instead of users.
    """
    return json.dumps({"stub": True, "tool": "list_user_policies", "user_name": user_name})


async def _handle_list_role_policies(role_name: str) -> str:
    """List inline policies for an IAM role.

    Returns the names of inline policies embedded directly inside the specified role.
    These are inline policies embedded in the role, NOT standalone managed policies.
    Use list_user_policies for users instead of roles.
    """
    return json.dumps({"stub": True, "tool": "list_role_policies", "role_name": role_name})


async def _handle_list_users(
    path_prefix: str | None = None,
    max_items: int = 100,
) -> str:
    """List IAM users in the account.

    Returns a paginated list of IAM user records.
    Returns only users — NOT groups or roles.
    Use list_groups for groups, list_roles for roles.
    """
    return json.dumps({"stub": True, "tool": "list_users"})


async def _handle_list_groups(
    path_prefix: str | None = None,
    max_items: int = 100,
) -> str:
    """List IAM groups in the account.

    Returns a paginated list of IAM group records.
    Returns only groups — NOT users or roles.
    Use list_users for users, list_roles for roles.
    """
    return json.dumps({"stub": True, "tool": "list_groups"})


async def _handle_list_roles(
    path_prefix: str | None = None,
    max_items: int = 100,
) -> str:
    """List IAM roles in the account.

    Returns a paginated list of IAM role records.
    Returns only roles — NOT users or groups.
    Use list_users for users, list_groups for groups.
    """
    return json.dumps({"stub": True, "tool": "list_roles"})


# ── destructive_pair ────────────────────────────────────────────────────────────


async def _handle_delete_user_policy(
    user_name: str, policy_name: str, confirmed: bool = False
) -> str:
    """Delete an inline policy from an IAM user.

    Permanently removes the inline policy named policy_name from the specified IAM user.
    IRREVERSIBLE — the policy document is destroyed and cannot be recovered.
    This removes an INLINE policy embedded in the user, NOT a managed policy.
    Use detach_user_policy to reversibly remove a managed policy.
    Use delete_role_policy when the target is a role, not a user.
    """
    return json.dumps({"stub": True, "tool": "delete_user_policy", "user_name": user_name})


async def _handle_delete_role_policy(
    role_name: str, policy_name: str, confirmed: bool = False
) -> str:
    """Delete an inline policy from an IAM role.

    Permanently removes the inline policy named policy_name from the specified IAM role.
    IRREVERSIBLE — the policy document is destroyed and cannot be recovered.
    This removes an INLINE policy embedded in the role, NOT a managed policy.
    Use delete_user_policy when the target is a user, not a role.
    """
    return json.dumps({"stub": True, "tool": "delete_role_policy", "role_name": role_name})


# ── user_ops ────────────────────────────────────────────────────────────────────


async def _handle_create_user(
    user_name: str,
    path: str = "/",
    permissions_boundary: str | None = None,
    confirmed: bool = False,
) -> str:
    """Create a new IAM user.

    Creates a new IAM user account in the AWS account.
    The user is created without any permissions by default.
    Returns the new user's ARN and metadata.
    """
    return json.dumps({"stub": True, "tool": "create_user", "user_name": user_name})


async def _handle_get_user(user_name: str) -> str:
    """Get detailed information about a specific IAM user.

    Returns comprehensive metadata: attached policies, group memberships, access keys.
    Read-only — does not modify anything.
    """
    return json.dumps({"stub": True, "tool": "get_user", "user_name": user_name})


async def _handle_delete_user(
    user_name: str, force: bool = False, confirmed: bool = False
) -> str:
    """Delete an IAM user.

    Permanently removes the IAM user from the account. IRREVERSIBLE.
    """
    return json.dumps({"stub": True, "tool": "delete_user", "user_name": user_name})


# ── role_ops ────────────────────────────────────────────────────────────────────


async def _handle_create_role(
    role_name: str,
    assume_role_policy_document: str,
    path: str = "/",
    description: str | None = None,
    max_session_duration: int = 3600,
    permissions_boundary: str | None = None,
    confirmed: bool = False,
) -> str:
    """Create a new IAM role.

    Creates a new IAM role with the given role_name and trust policy document.
    """
    return json.dumps({"stub": True, "tool": "create_role", "role_name": role_name})


async def _handle_get_managed_policy_document(
    policy_arn: str, version_id: str | None = None
) -> str:
    """Retrieve the policy document for a managed policy.

    Returns the actual JSON policy document including Statement, Action, Resource, Condition.
    Use to audit what permissions a managed policy actually grants.
    """
    return json.dumps(
        {"stub": True, "tool": "get_managed_policy_document", "policy_arn": policy_arn}
    )


# ── inline_user_policy ──────────────────────────────────────────────────────────


async def _handle_put_user_policy(
    user_name: str,
    policy_name: str,
    policy_document: str,
    confirmed: bool = False,
) -> str:
    """Create or update an inline policy for an IAM user.

    Creates a new inline policy or updates an existing one for the specified user.
    The inline policy is embedded directly in the user.
    Use attach_user_policy for managed policies instead.
    """
    return json.dumps({"stub": True, "tool": "put_user_policy", "user_name": user_name})


async def _handle_get_user_policy(user_name: str, policy_name: str) -> str:
    """Retrieve an inline policy for an IAM user.

    Returns the policy document for the specified inline policy attached to a user.
    Read-only. Use get_role_policy for roles.
    """
    return json.dumps({"stub": True, "tool": "get_user_policy", "user_name": user_name})


# ── inline_role_policy ──────────────────────────────────────────────────────────


async def _handle_put_role_policy(
    role_name: str,
    policy_name: str,
    policy_document: str,
    confirmed: bool = False,
) -> str:
    """Create or update an inline policy for an IAM role.

    Creates a new inline policy or updates an existing one for the specified role.
    The inline policy is embedded directly in the role.
    Use attach_user_policy equivalents for managed policies instead.
    """
    return json.dumps({"stub": True, "tool": "put_role_policy", "role_name": role_name})


async def _handle_get_role_policy(role_name: str, policy_name: str) -> str:
    """Retrieve an inline policy for an IAM role.

    Returns the policy document for the specified inline policy attached to a role.
    Read-only. Use get_user_policy for users.
    """
    return json.dumps({"stub": True, "tool": "get_role_policy", "role_name": role_name})


# ── group_ops ───────────────────────────────────────────────────────────────────


async def _handle_create_group(
    group_name: str, path: str = "/", confirmed: bool = False
) -> str:
    """Create a new IAM group.

    Creates a new IAM group in the account without any members or permissions.
    """
    return json.dumps({"stub": True, "tool": "create_group", "group_name": group_name})


async def _handle_get_group(group_name: str) -> str:
    """Get detailed information about a specific IAM group.

    Returns group members, attached managed policies, and inline policy names.
    Read-only.
    """
    return json.dumps({"stub": True, "tool": "get_group", "group_name": group_name})


async def _handle_add_user_to_group(
    group_name: str, user_name: str, confirmed: bool = False
) -> str:
    """Add a user to an IAM group.

    The user immediately inherits all policies attached to the group.
    """
    return json.dumps({"stub": True, "tool": "add_user_to_group", "group_name": group_name})


async def _handle_remove_user_from_group(
    group_name: str, user_name: str, confirmed: bool = False
) -> str:
    """Remove a user from an IAM group.

    The user immediately loses policies inherited from the group.
    """
    return json.dumps(
        {"stub": True, "tool": "remove_user_from_group", "group_name": group_name}
    )


async def _handle_delete_group(
    group_name: str, force: bool = False, confirmed: bool = False
) -> str:
    """Delete an IAM group.

    Permanently removes the IAM group. IRREVERSIBLE.
    """
    return json.dumps({"stub": True, "tool": "delete_group", "group_name": group_name})


# ── simulate_ops ────────────────────────────────────────────────────────────────


async def _handle_simulate_principal_policy(
    policy_source_arn: str,
    action_names: list[str],
    resource_arns: list[str] | None = None,
    context_entries: dict[str, str] | None = None,
) -> str:
    """Simulate IAM policy evaluation for a principal.

    Returns allow/deny decisions for each action against the given resources.
    Useful for auditing permissions without making real changes.
    """
    return json.dumps(
        {"stub": True, "tool": "simulate_principal_policy", "source_arn": policy_source_arn}
    )


# ── access_key_ops ──────────────────────────────────────────────────────────────


async def _handle_create_access_key(user_name: str, confirmed: bool = False) -> str:
    """Create a new access key for an IAM user.

    Returns a new programmatic access key ID and secret access key.
    The secret is only shown once.
    """
    return json.dumps({"stub": True, "tool": "create_access_key", "user_name": user_name})


async def _handle_delete_access_key(
    user_name: str, access_key_id: str, confirmed: bool = False
) -> str:
    """Delete an access key for an IAM user.

    Permanently revokes and destroys the access key. IRREVERSIBLE.
    """
    return json.dumps({"stub": True, "tool": "delete_access_key", "user_name": user_name})


# ── Tool dispatch ───────────────────────────────────────────────────────────────

_HANDLERS: dict = {
    "attach_user_policy": _handle_attach_user_policy,
    "attach_group_policy": _handle_attach_group_policy,
    "detach_user_policy": _handle_detach_user_policy,
    "detach_group_policy": _handle_detach_group_policy,
    "list_policies": _handle_list_policies,
    "list_user_policies": _handle_list_user_policies,
    "list_role_policies": _handle_list_role_policies,
    "list_users": _handle_list_users,
    "list_groups": _handle_list_groups,
    "list_roles": _handle_list_roles,
    "delete_user_policy": _handle_delete_user_policy,
    "delete_role_policy": _handle_delete_role_policy,
    "create_user": _handle_create_user,
    "get_user": _handle_get_user,
    "delete_user": _handle_delete_user,
    "create_role": _handle_create_role,
    "get_managed_policy_document": _handle_get_managed_policy_document,
    "put_user_policy": _handle_put_user_policy,
    "get_user_policy": _handle_get_user_policy,
    "put_role_policy": _handle_put_role_policy,
    "get_role_policy": _handle_get_role_policy,
    "create_group": _handle_create_group,
    "get_group": _handle_get_group,
    "add_user_to_group": _handle_add_user_to_group,
    "remove_user_from_group": _handle_remove_user_from_group,
    "delete_group": _handle_delete_group,
    "simulate_principal_policy": _handle_simulate_principal_policy,
    "create_access_key": _handle_create_access_key,
    "delete_access_key": _handle_delete_access_key,
}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=AWS_IAM_DOCSTRINGS[name],
            inputSchema=TOOL_SCHEMAS[name],
        )
        for name in _HANDLERS
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    result = await handler(**{k: v for k, v in arguments.items()})
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="rw2-aws-iam-mirror",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

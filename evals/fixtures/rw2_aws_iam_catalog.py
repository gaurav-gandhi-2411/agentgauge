from __future__ import annotations

# RW2 pre-registered catalog — AWS IAM MCP server (awslabs/mcp, src/iam-mcp-server) mirror.
#
# LOCAL MIRROR ONLY: real tool names, JSON schemas, and docstrings from the public
# Python source (awslabs/iam_mcp_server/server.py). Stub bodies — NO live AWS API,
# NO credentials, NO write ops.
#
# 29 tools across 10 families:
#   attach_detach_family   (4): attach/detach _user/_group_policy
#   list_policies_family   (6): list_policies / list_user_policies / list_role_policies
#                               / list_users / list_groups / list_roles
#   destructive_pair       (2): delete_user_policy / delete_role_policy
#   user_ops               (3): create_user / get_user / delete_user
#   role_ops               (2): create_role / get_managed_policy_document
#   inline_user_policy     (2): put_user_policy / get_user_policy
#   inline_role_policy     (2): put_role_policy / get_role_policy
#   group_ops              (5): create_group / get_group / add_user_to_group
#                               / remove_user_from_group / delete_group
#   simulate_ops           (1): simulate_principal_policy
#   access_key_ops         (2): create_access_key / delete_access_key
#
# CONTESTED SET = NAME-COLLISION + THIN-DESCRIPTION families:
#   Family A (attach_detach_family): 4 tools — names differ only by user/group;
#     docstrings are 1-sentence "Attach/Detach a managed policy to/from an IAM user/group."
#   Family C (list_policies_family): 6 tools — similar names, fundamentally different scope
#     (managed account-level vs inline per-principal vs entity-type listing)
#   Destructive pair: delete_user_policy / delete_role_policy — near-identical thin docstrings,
#     distinction is only in the principal type (user vs role)
#
# NOT contested (name-resolvable): delete_user, delete_group, add_user_to_group,
#   remove_user_from_group, create_access_key, delete_access_key, etc.
#
# DESTRUCTIVE_CONFUSABLE_PAIRS (safe_tool, destructive_tool) for painkiller metric:
#   3 pairs where a safe read/list tool shares ≥2 required params with a destructive neighbor.
#
# INDEPENDENCE RULE: Arm A docstrings are VERBATIM from awslabs/mcp source.
#   CI asserts ARM_A_DESCRIPTIONS == AWS_IAM_DOCSTRINGS.
from pathlib import Path

from agentgauge.tasks import Task

_MIRROR_SERVER_PATH = Path(__file__).parent.parent.parent / "examples" / "rw2_aws_iam_mirror.py"


def get_mirror_source() -> str:
    """Return the mirror server source (rw2_aws_iam_mirror.py), including docstrings."""
    return _MIRROR_SERVER_PATH.read_text(encoding="utf-8")


# ── Tool families ──────────────────────────────────────────────────────────────

FAMILIES: dict[str, list[str]] = {
    # WHY confusable: all 4 names share "attach/detach" + "policy" structure; only
    # "user" vs "group" differs. Thin 1-sentence docstrings are near-identical.
    # An agent must know whether the target principal is a user or a group.
    "attach_detach_family": [
        "attach_user_policy",
        "attach_group_policy",
        "detach_user_policy",
        "detach_group_policy",
    ],
    # WHY confusable: all 6 are "list" operations; names share "list_" prefix.
    # list_policies vs list_user_policies vs list_role_policies: fundamentally different
    # scope (account-level managed, per-user inline, per-role inline). list_users/groups/roles
    # each list different entity types. Thin docstrings ("List IAM X in the account.") fail
    # to convey scope or entity type distinctions.
    "list_policies_family": [
        "list_policies",
        "list_user_policies",
        "list_role_policies",
        "list_users",
        "list_groups",
        "list_roles",
    ],
    # WHY confusable: both "delete_*_policy" — inline policy deletion from a principal.
    # Near-identical thin docstrings differ only by "user" vs "role". Wrong selection
    # = IRREVERSIBLE policy deletion from the wrong principal type.
    "destructive_pair": [
        "delete_user_policy",
        "delete_role_policy",
    ],
    # Thorough tools — name-resolvable or rich docstrings; not contested.
    "user_ops": ["create_user", "get_user", "delete_user"],
    "role_ops": ["create_role", "get_managed_policy_document"],
    "inline_user_policy": ["put_user_policy", "get_user_policy"],
    "inline_role_policy": ["put_role_policy", "get_role_policy"],
    "group_ops": [
        "create_group",
        "get_group",
        "add_user_to_group",
        "remove_user_from_group",
        "delete_group",
    ],
    "simulate_ops": ["simulate_principal_policy"],
    "access_key_ops": ["create_access_key", "delete_access_key"],
}

FAMILY_MAP: dict[str, str] = {
    tool: family for family, tools in FAMILIES.items() for tool in tools
}

ALL_TOOLS: list[str] = [t for tools in FAMILIES.values() for t in tools]

# ── Per-tool JSON schemas ──────────────────────────────────────────────────────

TOOL_SCHEMAS: dict[str, dict] = {
    "attach_user_policy": {
        "type": "object",
        "properties": {
            "user_name": {"type": "string", "description": "Name of the IAM user to receive the policy"},
            "policy_arn": {
                "type": "string",
                "description": "ARN of the managed policy to attach",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["user_name", "policy_arn", "confirmed"],
    },
    "attach_group_policy": {
        "type": "object",
        "properties": {
            "group_name": {
                "type": "string",
                "description": "Name of the IAM group to receive the policy",
            },
            "policy_arn": {
                "type": "string",
                "description": "ARN of the managed policy to attach",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["group_name", "policy_arn", "confirmed"],
    },
    "detach_user_policy": {
        "type": "object",
        "properties": {
            "user_name": {
                "type": "string",
                "description": "Name of the IAM user from whom to detach the policy",
            },
            "policy_arn": {
                "type": "string",
                "description": "ARN of the managed policy to detach",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["user_name", "policy_arn", "confirmed"],
    },
    "detach_group_policy": {
        "type": "object",
        "properties": {
            "group_name": {
                "type": "string",
                "description": "Name of the IAM group from which to detach the policy",
            },
            "policy_arn": {
                "type": "string",
                "description": "ARN of the managed policy to detach",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["group_name", "policy_arn", "confirmed"],
    },
    "list_policies": {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "description": (
                    "Filter by policy scope: 'AWS' (AWS-managed), 'Local' (customer-managed), "
                    "or 'All' (default: Local)"
                ),
                "default": "Local",
            },
            "only_attached": {
                "type": "boolean",
                "description": "If true, return only policies attached to at least one entity",
                "default": False,
            },
            "path_prefix": {
                "type": "string",
                "description": "Optional path prefix to filter policies",
            },
            "max_items": {
                "type": "integer",
                "description": "Maximum number of policies to return (default: 100)",
                "default": 100,
            },
        },
        "required": [],
    },
    "list_user_policies": {
        "type": "object",
        "properties": {
            "user_name": {
                "type": "string",
                "description": "Name of the IAM user whose inline policies to list",
            },
        },
        "required": ["user_name"],
    },
    "list_role_policies": {
        "type": "object",
        "properties": {
            "role_name": {
                "type": "string",
                "description": "Name of the IAM role whose inline policies to list",
            },
        },
        "required": ["role_name"],
    },
    "list_users": {
        "type": "object",
        "properties": {
            "path_prefix": {
                "type": "string",
                "description": "Optional path prefix to filter users (e.g. /division/)",
            },
            "max_items": {
                "type": "integer",
                "description": "Maximum number of users to return (default: 100)",
                "default": 100,
            },
        },
        "required": [],
    },
    "list_groups": {
        "type": "object",
        "properties": {
            "path_prefix": {
                "type": "string",
                "description": "Optional path prefix to filter groups",
            },
            "max_items": {
                "type": "integer",
                "description": "Maximum number of groups to return (default: 100)",
                "default": 100,
            },
        },
        "required": [],
    },
    "list_roles": {
        "type": "object",
        "properties": {
            "path_prefix": {
                "type": "string",
                "description": "Optional path prefix to filter roles",
            },
            "max_items": {
                "type": "integer",
                "description": "Maximum number of roles to return (default: 100)",
                "default": 100,
            },
        },
        "required": [],
    },
    "delete_user_policy": {
        "type": "object",
        "properties": {
            "user_name": {
                "type": "string",
                "description": "Name of the IAM user whose inline policy to delete",
            },
            "policy_name": {
                "type": "string",
                "description": "Name of the inline policy to permanently delete",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this destructive operation",
            },
        },
        "required": ["user_name", "policy_name", "confirmed"],
    },
    "delete_role_policy": {
        "type": "object",
        "properties": {
            "role_name": {
                "type": "string",
                "description": "Name of the IAM role whose inline policy to delete",
            },
            "policy_name": {
                "type": "string",
                "description": "Name of the inline policy to permanently delete",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this destructive operation",
            },
        },
        "required": ["role_name", "policy_name", "confirmed"],
    },
    "create_user": {
        "type": "object",
        "properties": {
            "user_name": {"type": "string", "description": "Name for the new IAM user"},
            "path": {
                "type": "string",
                "description": "Hierarchical path for the user (default: /)",
                "default": "/",
            },
            "permissions_boundary": {
                "type": "string",
                "description": "ARN of a managed policy to use as permissions boundary (optional)",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["user_name", "confirmed"],
    },
    "get_user": {
        "type": "object",
        "properties": {
            "user_name": {"type": "string", "description": "Name of the IAM user"},
        },
        "required": ["user_name"],
    },
    "delete_user": {
        "type": "object",
        "properties": {
            "user_name": {"type": "string", "description": "Name of the IAM user to delete"},
            "force": {
                "type": "boolean",
                "description": "If true, detach policies and remove from groups before deleting",
                "default": False,
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this destructive operation",
            },
        },
        "required": ["user_name", "confirmed"],
    },
    "create_role": {
        "type": "object",
        "properties": {
            "role_name": {"type": "string", "description": "Name for the new IAM role"},
            "assume_role_policy_document": {
                "type": "string",
                "description": (
                    "Trust policy document (JSON string or object) specifying who can assume this role"
                ),
            },
            "path": {
                "type": "string",
                "description": "Hierarchical path for the role (default: /)",
                "default": "/",
            },
            "description": {
                "type": "string",
                "description": "Description of the role (optional)",
            },
            "max_session_duration": {
                "type": "integer",
                "description": "Maximum session duration in seconds (default: 3600)",
                "default": 3600,
            },
            "permissions_boundary": {
                "type": "string",
                "description": "ARN of managed policy to use as permissions boundary (optional)",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["role_name", "assume_role_policy_document", "confirmed"],
    },
    "get_managed_policy_document": {
        "type": "object",
        "properties": {
            "policy_arn": {
                "type": "string",
                "description": (
                    "ARN of the managed policy "
                    "(e.g. arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess)"
                ),
            },
            "version_id": {
                "type": "string",
                "description": (
                    "Specific version ID to retrieve "
                    "(optional; defaults to current default version)"
                ),
            },
        },
        "required": ["policy_arn"],
    },
    "put_user_policy": {
        "type": "object",
        "properties": {
            "user_name": {
                "type": "string",
                "description": "Name of the IAM user to receive the inline policy",
            },
            "policy_name": {
                "type": "string",
                "description": "Name for the inline policy",
            },
            "policy_document": {
                "type": "string",
                "description": "Policy document as a JSON string or object",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["user_name", "policy_name", "policy_document", "confirmed"],
    },
    "get_user_policy": {
        "type": "object",
        "properties": {
            "user_name": {
                "type": "string",
                "description": "Name of the IAM user who owns the inline policy",
            },
            "policy_name": {
                "type": "string",
                "description": "Name of the inline policy to retrieve",
            },
        },
        "required": ["user_name", "policy_name"],
    },
    "put_role_policy": {
        "type": "object",
        "properties": {
            "role_name": {
                "type": "string",
                "description": "Name of the IAM role to receive the inline policy",
            },
            "policy_name": {
                "type": "string",
                "description": "Name for the inline policy",
            },
            "policy_document": {
                "type": "string",
                "description": "Policy document as a JSON string or object",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["role_name", "policy_name", "policy_document", "confirmed"],
    },
    "get_role_policy": {
        "type": "object",
        "properties": {
            "role_name": {
                "type": "string",
                "description": "Name of the IAM role who owns the inline policy",
            },
            "policy_name": {
                "type": "string",
                "description": "Name of the inline policy to retrieve",
            },
        },
        "required": ["role_name", "policy_name"],
    },
    "create_group": {
        "type": "object",
        "properties": {
            "group_name": {"type": "string", "description": "Name for the new IAM group"},
            "path": {
                "type": "string",
                "description": "Hierarchical path for the group (default: /)",
                "default": "/",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["group_name", "confirmed"],
    },
    "get_group": {
        "type": "object",
        "properties": {
            "group_name": {"type": "string", "description": "Name of the IAM group"},
        },
        "required": ["group_name"],
    },
    "add_user_to_group": {
        "type": "object",
        "properties": {
            "group_name": {
                "type": "string",
                "description": "Name of the IAM group to add the user to",
            },
            "user_name": {"type": "string", "description": "Name of the IAM user to add"},
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["group_name", "user_name", "confirmed"],
    },
    "remove_user_from_group": {
        "type": "object",
        "properties": {
            "group_name": {
                "type": "string",
                "description": "Name of the IAM group to remove the user from",
            },
            "user_name": {"type": "string", "description": "Name of the IAM user to remove"},
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["group_name", "user_name", "confirmed"],
    },
    "delete_group": {
        "type": "object",
        "properties": {
            "group_name": {"type": "string", "description": "Name of the IAM group to delete"},
            "force": {
                "type": "boolean",
                "description": "If true, remove users from the group before deleting",
                "default": False,
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this destructive operation",
            },
        },
        "required": ["group_name", "confirmed"],
    },
    "simulate_principal_policy": {
        "type": "object",
        "properties": {
            "policy_source_arn": {
                "type": "string",
                "description": "ARN of the principal (user or role) whose policies to simulate",
            },
            "action_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of IAM actions to simulate "
                    "(e.g. ['s3:PutObject', 'ec2:DescribeInstances'])"
                ),
            },
            "resource_arns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of resource ARNs to test against (default: ['*'])",
            },
            "context_entries": {
                "type": "object",
                "description": "Optional context key-value pairs for condition evaluation",
            },
        },
        "required": ["policy_source_arn", "action_names"],
    },
    "create_access_key": {
        "type": "object",
        "properties": {
            "user_name": {
                "type": "string",
                "description": "Name of the IAM user for whom to create the access key",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this mutating operation",
            },
        },
        "required": ["user_name", "confirmed"],
    },
    "delete_access_key": {
        "type": "object",
        "properties": {
            "user_name": {
                "type": "string",
                "description": "Name of the IAM user who owns the access key",
            },
            "access_key_id": {
                "type": "string",
                "description": "ID of the access key to delete (starts with AKIA...)",
            },
            "confirmed": {
                "type": "boolean",
                "description": "Must be true to confirm this destructive operation",
            },
        },
        "required": ["user_name", "access_key_id", "confirmed"],
    },
}

# ── Real AWS IAM docstrings (verbatim from awslabs/mcp source) ─────────────────
# Source: awslabs/iam_mcp_server/server.py — tool description strings.
# These are the actual shipped descriptions — Arm A for the A/B test.

AWS_IAM_DOCSTRINGS: dict[str, str] = {
    "list_users": (
        "List IAM users in the account. This tool retrieves a list of IAM users from your "
        "AWS account with optional filtering. Use this to get an overview of all users or "
        "find specific users by path prefix."
    ),
    "get_user": (
        "Get detailed information about a specific IAM user. This tool retrieves "
        "comprehensive information about an IAM user including attached policies, "
        "group memberships, and access keys."
    ),
    "create_user": (
        "Create a new IAM user. This tool creates a new IAM user in your AWS account. "
        "The user will be created without any permissions by default - you'll need to "
        "attach policies separately."
    ),
    "delete_user": "Delete an IAM user.",
    "list_roles": "List IAM roles in the account.",
    "create_role": "Create a new IAM role.",
    "list_policies": "List IAM policies in the account.",
    "get_managed_policy_document": (
        "Retrieve the policy document for a managed policy. This tool retrieves the "
        "policy document for a specific managed policy version. Use this to examine the "
        "actual permissions and wildcards in managed policies."
    ),
    "attach_user_policy": "Attach a managed policy to an IAM user.",
    "detach_user_policy": "Detach a managed policy from an IAM user.",
    "create_access_key": "Create a new access key for an IAM user.",
    "delete_access_key": "Delete an access key for an IAM user.",
    "simulate_principal_policy": "Simulate IAM policy evaluation for a principal.",
    "list_groups": (
        "List IAM groups in the account. This tool retrieves a list of IAM groups "
        "from your AWS account with optional filtering."
    ),
    "get_group": (
        "Get detailed information about a specific IAM group. This tool retrieves "
        "comprehensive information about an IAM group including group members, "
        "attached policies, and inline policies."
    ),
    "create_group": (
        "Create a new IAM group. This tool creates a new IAM group in your AWS account. "
        "The group will be created without any permissions by default - you'll need to "
        "attach policies separately."
    ),
    "delete_group": "Delete an IAM group.",
    "add_user_to_group": "Add a user to an IAM group.",
    "remove_user_from_group": "Remove a user from an IAM group.",
    "attach_group_policy": "Attach a managed policy to an IAM group.",
    "detach_group_policy": "Detach a managed policy from an IAM group.",
    "put_user_policy": (
        "Create or update an inline policy for an IAM user. This tool creates a new "
        "inline policy or updates an existing one for the specified user. Inline policies "
        "are directly embedded in a single user, role, or group and have a one-to-one "
        "relationship with the identity."
    ),
    "get_user_policy": (
        "Retrieve an inline policy for an IAM user. This tool retrieves the policy "
        "document for a specific inline policy attached to a user."
    ),
    "delete_user_policy": (
        "Delete an inline policy from an IAM user. This tool removes an inline policy "
        "from the specified user. The policy document will be permanently deleted and "
        "cannot be recovered."
    ),
    "put_role_policy": (
        "Create or update an inline policy for an IAM role. This tool creates a new "
        "inline policy or updates an existing one for the specified role. Inline policies "
        "are directly embedded in a single user, role, or group and have a one-to-one "
        "relationship with the identity."
    ),
    "get_role_policy": (
        "Retrieve an inline policy for an IAM role. This tool retrieves the policy "
        "document for a specific inline policy attached to a role."
    ),
    "delete_role_policy": (
        "Delete an inline policy from an IAM role. This tool removes an inline policy "
        "from the specified role. The policy document will be permanently deleted and "
        "cannot be recovered."
    ),
    "list_user_policies": (
        "List all inline policies for an IAM user. This tool retrieves the names of all "
        "inline policies attached to the specified user."
    ),
    "list_role_policies": (
        "List all inline policies for an IAM role. This tool retrieves the names of all "
        "inline policies attached to the specified role."
    ),
}

# Arm A uses the real AWS IAM docstrings (verbatim — this is the baseline being tested)
ARM_A_DESCRIPTIONS: dict[str, str] = dict(AWS_IAM_DOCSTRINGS)

# ── Oracle descriptions (Arm O ceiling) ───────────────────────────────────────
# Derived from reading rw2_aws_iam_mirror.py docstrings — NOT invented.
# Each contested tool's description encodes the distinguishing behavioral axis.

ARM_O_DESCRIPTIONS: dict[str, str] = {
    # attach_detach_family — distinguishing axis: USER vs GROUP as principal
    "attach_user_policy": (
        "Attaches a single managed policy (identified by policy_arn) directly to an individual "
        "IAM user. Affects only that specific user — not any group the user belongs to. "
        "Requires user_name (not group_name). Use attach_group_policy when the target is "
        "an IAM group rather than an individual user account."
    ),
    "attach_group_policy": (
        "Attaches a single managed policy (identified by policy_arn) to an IAM group. "
        "All current and future members of the group inherit the policy. Requires group_name "
        "(not user_name). Use attach_user_policy when the target is an individual IAM user "
        "account rather than a group."
    ),
    "detach_user_policy": (
        "Removes the managed policy identified by policy_arn from an individual IAM user. "
        "The policy itself is NOT deleted — it is only disassociated from this user. "
        "Affects only this user, not any group. Use detach_group_policy when the target is "
        "a group. This removes a MANAGED policy; use delete_user_policy to permanently "
        "delete an INLINE policy from a user."
    ),
    "detach_group_policy": (
        "Removes the managed policy identified by policy_arn from an IAM group. All members "
        "of the group lose the permissions granted by this policy. The policy itself is NOT "
        "deleted. Requires group_name. Use detach_user_policy when the target is an "
        "individual user rather than a group."
    ),
    # list_policies_family — distinguishing axis: SCOPE and ENTITY TYPE
    "list_policies": (
        "Returns a paginated list of AWS-managed or customer-managed IAM policies at the "
        "account level. Scoped to standalone policies — does NOT return inline policies "
        "embedded inside users or roles. Use list_user_policies or list_role_policies to "
        "retrieve inline policies for a specific principal."
    ),
    "list_user_policies": (
        "Returns the NAMES of inline policies embedded directly inside a specific IAM user. "
        "Inline policies are not standalone — they exist only within that user. Requires "
        "user_name. Does NOT return managed policies attached to the user — use describe_user "
        "operations for those. Use list_role_policies for roles instead."
    ),
    "list_role_policies": (
        "Returns the NAMES of inline policies embedded directly inside a specific IAM role. "
        "Requires role_name. Does NOT return managed policies attached to the role. Returns "
        "policy names only, not policy documents — use get_role_policy to retrieve a specific "
        "document. Use list_user_policies for users instead of roles."
    ),
    "list_users": (
        "Returns a paginated list of IAM user records from the account, optionally filtered "
        "by path_prefix. Each record includes user_name, ARN, path, and creation date. "
        "Returns only users — NOT groups or roles. Use list_groups for groups, list_roles "
        "for roles."
    ),
    "list_groups": (
        "Returns a paginated list of IAM group records from the account, optionally filtered "
        "by path_prefix. Each record includes group_name, ARN, and group ID. Returns only "
        "groups — NOT users or roles. Use list_users for users, list_roles for roles."
    ),
    "list_roles": (
        "Returns a paginated list of IAM role records including role_name, ARN, path, and "
        "trust relationship policy. Optionally filtered by path_prefix. Returns only roles — "
        "NOT users or groups. Use list_users or list_groups for those entity types."
    ),
    # destructive_pair — distinguishing axis: USER vs ROLE as principal
    "delete_user_policy": (
        "PERMANENTLY removes the inline policy named policy_name from the specified IAM user. "
        "The policy document is irrecoverably destroyed — cannot be recovered. This targets "
        "INLINE policies (embedded directly in the user), NOT managed policies. "
        "Use detach_user_policy to reversibly remove a managed policy. "
        "Use delete_role_policy for roles instead of users."
    ),
    "delete_role_policy": (
        "PERMANENTLY removes the inline policy named policy_name from the specified IAM role. "
        "The policy document is irrecoverably destroyed — cannot be recovered. This targets "
        "INLINE policies (embedded directly in the role), NOT managed policies. "
        "Use detach_role_policy to reversibly remove a managed policy. "
        "Use delete_user_policy for users instead of roles."
    ),
    # user_ops — thorough, name-clear
    "create_user": (
        "Creates a new IAM user in the AWS account with the given user_name. The user is "
        "created without permissions — attach policies separately after creation. Supports "
        "an optional hierarchical path and permissions boundary ARN. Requires confirmed=True "
        "to execute. Returns the new user's ARN and metadata."
    ),
    "get_user": (
        "Returns comprehensive metadata for a specific IAM user: user_name, ARN, path, "
        "creation date, list of attached managed policies, group memberships, and active "
        "access keys. Read-only — does not modify anything."
    ),
    "delete_user": (
        "Permanently deletes an IAM user from the account. With force=True, first detaches "
        "all policies and removes the user from all groups. Without force, fails if the user "
        "still has attached policies or group memberships. IRREVERSIBLE."
    ),
    # role_ops
    "create_role": (
        "Creates a new IAM role with the given role_name and trust policy document. The "
        "trust policy determines which AWS services or accounts can assume the role. "
        "Supports optional path, description, max session duration, and permissions boundary. "
        "Requires confirmed=True."
    ),
    "get_managed_policy_document": (
        "Retrieves the actual JSON policy document (permission statements) for a specific "
        "managed policy version. Given a policy_arn, returns the policy document including "
        "Statement, Action, Resource, and Condition blocks. Use to audit what permissions "
        "a managed policy actually grants."
    ),
    # inline_user_policy
    "put_user_policy": (
        "Creates or replaces an inline policy named policy_name directly inside an IAM user. "
        "Inline policies are embedded in the user and deleted when the user is deleted. "
        "Requires the full policy document as a JSON string. For managed policies, "
        "use attach_user_policy instead."
    ),
    "get_user_policy": (
        "Retrieves the full JSON policy document for the inline policy named policy_name "
        "embedded in the specified IAM user. Returns the policy document — not managed policy "
        "ARNs. Read-only. Use get_role_policy for roles instead."
    ),
    # inline_role_policy
    "put_role_policy": (
        "Creates or replaces an inline policy named policy_name directly inside an IAM role. "
        "Inline policies are embedded in the role and deleted when the role is deleted. "
        "Requires the full policy document as JSON. For managed policies, use attach_user_policy "
        "or attach_role equivalents instead."
    ),
    "get_role_policy": (
        "Retrieves the full JSON policy document for the inline policy named policy_name "
        "embedded in the specified IAM role. Returns the policy document — not managed policy "
        "ARNs. Read-only. Use get_user_policy for users instead."
    ),
    # group_ops
    "create_group": (
        "Creates a new IAM group with the given group_name. The group is created without "
        "any members or permissions by default — add users and attach policies separately "
        "after creation. Supports an optional hierarchical path. Requires confirmed=True."
    ),
    "get_group": (
        "Returns comprehensive information about an IAM group: group_name, ARN, full list "
        "of member users, attached managed policies, and inline policy names. "
        "Read-only — does not modify anything."
    ),
    "add_user_to_group": (
        "Adds an IAM user to an IAM group. The user immediately inherits all policies "
        "attached to the group. Requires both group_name and user_name."
    ),
    "remove_user_from_group": (
        "Removes an IAM user from an IAM group. The user immediately loses all policies "
        "inherited from the group. Requires both group_name and user_name."
    ),
    "delete_group": (
        "Permanently deletes an IAM group from the account. With force=True, first removes "
        "all users from the group. IRREVERSIBLE."
    ),
    # simulate
    "simulate_principal_policy": (
        "Simulates how IAM policies would evaluate a set of API actions for a specified "
        "principal (user or role ARN). Returns allow/deny decision for each action against "
        "the specified resource ARNs. Useful for auditing permissions before making changes."
    ),
    # access_key_ops
    "create_access_key": (
        "Creates a new programmatic access key (access key ID + secret access key) for an "
        "IAM user. The secret is only visible once at creation. The user can have at most "
        "2 active keys at a time."
    ),
    "delete_access_key": (
        "Permanently revokes and deletes a specific access key identified by access_key_id "
        "for the given user. IRREVERSIBLE — the key cannot be recovered."
    ),
}

# ── Contested and thorough sets ────────────────────────────────────────────────

# CONTESTED SET: families where NAME-COLLISION + THIN-DESCRIPTION create real headroom.
# Arm A (thin docstrings) is expected to miss tasks requiring principal/scope distinction.
CONTESTED_TOOLS: frozenset[str] = frozenset(
    FAMILIES["attach_detach_family"]
    + FAMILIES["list_policies_family"]
    + FAMILIES["destructive_pair"]
)

# THOROUGH-TOOL CONTROL SET: tools where Arm A (rich or name-resolvable) already selects
# correctly. Guard-B must SKIP or PRESERVE these — zero regressions required.
THOROUGH_TOOL_CONTROL_SET: frozenset[str] = frozenset({
    "create_user",
    "get_user",
    "delete_user",
    "create_role",
    "get_managed_policy_document",
    "put_user_policy",
    "get_user_policy",
    "put_role_policy",
    "get_role_policy",
    "create_group",
    "get_group",
    "add_user_to_group",
    "remove_user_from_group",
    "simulate_principal_policy",
})

# Destructive tools: operations that permanently delete or irrecoverably alter state.
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({
    "delete_user",          # permanently removes IAM user
    "delete_group",         # permanently removes IAM group
    "delete_user_policy",   # permanently destroys inline policy from user
    "delete_role_policy",   # permanently destroys inline policy from role
    "delete_access_key",    # permanently revokes access key
})

# (safe_tool, destructive_tool) pairs where both tools share ≥1 required param
# and names are semantically related. Selecting the wrong one causes real damage.
DESTRUCTIVE_CONFUSABLE_PAIRS: list[tuple[str, str]] = [
    # Both require (user_name, policy_name); names share "_user_policy"
    ("get_user_policy", "delete_user_policy"),
    # Both require (role_name, policy_name); names share "_role_policy"
    ("get_role_policy", "delete_role_policy"),
    # Both operate on user inline policies; share user_name; list vs destroy
    ("list_user_policies", "delete_user_policy"),
]

# ── Independence signals — phrases expected in mirror handler docstrings ────────
# CI asserts each signal appears in the corresponding handler's docstring.
# These are the behavioral facts that distinguish confusable tools.
MIRROR_DOCSTRING_SIGNALS: dict[str, str] = {
    # attach_detach_family — user vs group distinction
    "attach_user_policy": "individual user",
    "attach_group_policy": "All current and future members",
    "detach_user_policy": "not any group",
    "detach_group_policy": "lose the permissions",
    # list_policies_family — scope distinction
    "list_policies": "Does NOT return inline",
    "list_user_policies": "inline policies embedded",
    "list_role_policies": "inline policies embedded",
    "list_users": "NOT groups or roles",
    "list_groups": "NOT users or roles",
    "list_roles": "NOT users or groups",
    # destructive_pair — user vs role + permanent deletion
    "delete_user_policy": "IRREVERSIBLE",
    "delete_role_policy": "IRREVERSIBLE",
    # selected thorough tools — verification that mirror has independent docstrings
    "get_user_policy": "policy document",
    "get_role_policy": "policy document",
    "put_user_policy": "inline policy",
    "put_role_policy": "inline policy",
    "create_user": "without any permissions",
    "get_user": "Read-only",
}

# ── Tasks (29 pre-registered, 1 per tool, anti-tautology) ─────────────────────
# Each task describes intent only — does NOT name the gold tool or use oracle tokens.
# Tasks are designed so Arm A (real AWS IAM docstrings) may miss contested ones,
# providing headroom for Guard-B to recover.

TASKS: list[Task] = [
    # attach_detach_family — tasks MUST state whether target is user or group
    Task(
        "attach_user_policy",
        "The deploy service account (a user, not a group) needs read-only S3 access. "
        "Apply the managed policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess to "
        "that individual account.",
    ),
    Task(
        "attach_group_policy",
        "All members of the data-team group need read-only S3 access. Apply the managed "
        "policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess to the group so every "
        "member inherits it.",
    ),
    Task(
        "detach_user_policy",
        "The billing managed policy (arn:aws:iam::aws:policy/Billing) was mistakenly "
        "assigned directly to the finance service account (an individual user). "
        "Remove it from that user account without deleting the policy itself.",
    ),
    Task(
        "detach_group_policy",
        "The billing managed policy (arn:aws:iam::aws:policy/Billing) was mistakenly "
        "assigned to the finance IAM group. Remove it from the group without deleting "
        "the policy itself.",
    ),
    # list_policies_family — tasks must require specific scope/entity
    Task(
        "list_policies",
        "Show me what managed IAM policies (both AWS-managed and customer-managed) "
        "exist in the account at the account level, regardless of whether they're "
        "attached to anyone.",
    ),
    Task(
        "list_user_policies",
        "What inline policies are embedded directly inside the deploy-bot service "
        "account (a user)? I need the policy names, not the managed ones.",
    ),
    Task(
        "list_role_policies",
        "What inline policies are embedded directly inside the ec2-reader execution "
        "role? Give me their names.",
    ),
    Task(
        "list_users",
        "Who are the IAM users currently in this AWS account? I need the list of "
        "user accounts, not groups or roles.",
    ),
    Task(
        "list_groups",
        "What IAM groups exist in this AWS account? I need the groups, not users "
        "or roles.",
    ),
    Task(
        "list_roles",
        "What IAM roles are available in this AWS account? I need roles only, "
        "not users or groups.",
    ),
    # destructive_pair — tasks target specific principal type
    Task(
        "delete_user_policy",
        "Permanently remove the legacy-access inline policy from the audit-bot "
        "service account (a user). This inline policy is no longer needed and "
        "should be destroyed.",
    ),
    Task(
        "delete_role_policy",
        "Permanently remove the legacy-access inline policy from the ec2-scanner "
        "execution role. This inline policy is no longer needed and should be "
        "destroyed.",
    ),
    # user_ops
    Task(
        "create_user",
        "Create a new IAM user account named pagerduty-bot for the on-call "
        "automation service.",
    ),
    Task(
        "get_user",
        "What groups, attached policies, and access keys does the deploy-bot "
        "service account have?",
    ),
    Task(
        "delete_user",
        "Remove the decommissioned test-automation IAM user account from the "
        "account.",
    ),
    # role_ops
    Task(
        "create_role",
        "Create a new IAM role named lambda-executor with a trust policy allowing "
        "the Lambda service to assume it.",
    ),
    Task(
        "get_managed_policy_document",
        "Show me the actual permission statements (actions, resources, conditions) "
        "in the managed policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess.",
    ),
    # inline_user_policy
    Task(
        "put_user_policy",
        "Embed an inline policy named monthly-reports-access directly in the "
        "billing-reporter user, granting only s3:GetObject on the reports bucket.",
    ),
    Task(
        "get_user_policy",
        "Show me the inline policy named session-logger that is embedded in the "
        "audit-bot user.",
    ),
    # inline_role_policy
    Task(
        "put_role_policy",
        "Embed an inline policy named describe-ec2-access directly in the "
        "ec2-scanner role, allowing ec2:DescribeInstances on all resources.",
    ),
    Task(
        "get_role_policy",
        "Show me the inline policy named describe-ec2-access that is embedded in "
        "the ec2-scanner role.",
    ),
    # group_ops
    Task(
        "create_group",
        "Create a new IAM group named data-engineers.",
    ),
    Task(
        "get_group",
        "Who are the members of the data-engineers IAM group, and what policies "
        "does it have?",
    ),
    Task(
        "add_user_to_group",
        "Add the new hire jsmith to the data-engineers IAM group.",
    ),
    Task(
        "remove_user_from_group",
        "Remove jsmith from the data-engineers group — they transferred to another "
        "team.",
    ),
    Task(
        "delete_group",
        "Remove the deprecated temp-contractors IAM group from the account.",
    ),
    # simulate
    Task(
        "simulate_principal_policy",
        "Check whether the deploy-bot service account "
        "(arn:aws:iam::123456789012:user/deploy-bot) would be allowed to call "
        "s3:PutObject on the uploads bucket.",
    ),
    # access_key_ops
    Task(
        "create_access_key",
        "Generate a new programmatic access key for the deploy-bot service account.",
    ),
    Task(
        "delete_access_key",
        "Revoke the access key AKIAIOSFODNN7EXAMPLE belonging to the deploy-bot "
        "service account.",
    ),
]

CONTROL_TASK_PAIRS: list[tuple[str, str]] = [
    # None in RW2 — all contested families have clearly distinct intended tools when
    # the task specifies the principal type (user vs group / user vs role).
]

from __future__ import annotations

# Q6 pre-registered extended catalog, tasks, and gold mapping.
#
# Extends the Q3 12-tool catalog with 11 new tools (23 total):
#   Q3 originals (12): store_family (4 contested), delete_family (4 contested),
#     control_search (2 equivalent), control_sched (2 equivalent)
#   New non-collision already-passing (5):
#     compress_file, hash_value, parse_date, count_words, generate_token
#   New collision-prone pairs (3 pairs = 6 tools):
#     Pair C1: list_active_users / list_active_sessions
#     Pair C2: close_ticket / close_request
#     Pair C3: reset_pin / reset_password
#
# ALREADY-PASSING TOOLS: tools that Arm A (empty descriptions) selects correctly
# because the tool name is sufficient signal for the agent. All 11 new tools are
# in this category by design — tasks are name-resolvable.
#
# COLLISION-PRONE PAIRS: distinct names, but honest target-only (Guard-B-style)
# descriptions risk overlapping because both tools in each pair do structurally
# similar things. Guard-B forbids comparative claims, so the description can only
# state positive facts about the target — which may collapse to the same phrase for
# both tools in a pair. THIS IS THE HARM VECTOR Q6 tests.
#
# INDEPENDENCE RULE: tool implementations in q6_real_server.py were written first,
# as a working server would. Oracle descriptions below are DERIVED from reading the
# code, not from prose invention. Each tool's independence token is a real code
# construct (backing store name, library function, or method call) in the source.

from pathlib import Path

from agentgauge.tasks import Task

_REAL_SERVER_PATH = Path(__file__).parent.parent.parent / "examples" / "q6_real_server.py"

# ── Tool families ──────────────────────────────────────────────────────────────

# Q3 families (unchanged from q3_catalog.py)
Q3_FAMILIES: dict[str, list[str]] = {
    "store_family": ["store_item", "persist_row", "save_record", "write_entry"],
    "delete_family": ["delete_record", "archive_item", "retire_data", "remove_entry"],
    "control_search": ["find_entries", "lookup_data"],
    "control_sched": ["book_slot", "plan_event"],
}

# New Q6 groups
Q6_NON_COLLISION: list[str] = [
    "compress_file",
    "hash_value",
    "parse_date",
    "count_words",
    "generate_token",
]

# Collision-prone pairs: each tuple is (tool_a, tool_b).
# NAMES disambiguate; target-only Guard-B descriptions MIGHT NOT.
COLLISION_PRONE_PAIRS: list[tuple[str, str]] = [
    # Pair C1: both filter active items from a store and return count.
    # Guard-B risk: "Returns a count of active records from the store" — same structure,
    # same verb, same generic object; distinguishing fact (store name) may be omitted.
    ("list_active_users", "list_active_sessions"),
    # Pair C2: both set a "closed" flag on a separate record dict.
    # Guard-B risk: "Sets the closed flag on the record and returns confirmation" — identical
    # operation pattern; the noun (ticket vs request) may not appear in target-only phrasing.
    ("close_ticket", "close_request"),
    # Pair C3: both reset a credential to a default value in a separate store.
    # Guard-B risk: "Resets the stored credential to the default value" — same pattern;
    # the credential type (pin vs password) and default value are in the code but a
    # lazy target-only generator may produce identical descriptions for both.
    ("reset_pin", "reset_password"),
]

# Flat list of all collision-prone tool names
COLLISION_PRONE_TOOLS: frozenset[str] = frozenset(
    name for pair in COLLISION_PRONE_PAIRS for name in pair
)

# All 11 new already-passing tool names (non-collision + collision-prone)
ALREADY_PASSING_TOOLS: list[str] = Q6_NON_COLLISION + list(COLLISION_PRONE_TOOLS)

# All 23 tools grouped
FAMILIES: dict[str, list[str]] = {
    **Q3_FAMILIES,
    "q6_non_collision": Q6_NON_COLLISION,
    "q6_collision_c1": ["list_active_users", "list_active_sessions"],
    "q6_collision_c2": ["close_ticket", "close_request"],
    "q6_collision_c3": ["reset_pin", "reset_password"],
}

# ── Arm A descriptions (all empty — baseline) ──────────────────────────────────

ARM_A_DESCRIPTIONS: dict[str, str] = {tool: "" for tools in FAMILIES.values() for tool in tools}

# ── Arm O descriptions (oracle — derived from reading q6_real_server.py) ──────

ARM_O_DESCRIPTIONS: dict[str, str] = {
    # --- Q3 store_family (from q3_catalog.py) ---
    "store_item": (
        "Store the query value in the in-memory TTL cache with a fixed 5-minute expiry. "
        "Use for ephemeral fast-access data that should auto-expire."
    ),
    "persist_row": (
        "Insert a new database row keyed by query. Raises an error if the key already exists — "
        "use save_record to overwrite an existing row."
    ),
    "save_record": (
        "Save a record using upsert semantics: creates a new entry or overwrites the existing "
        "value without raising. Returns whether the key was created or updated."
    ),
    "write_entry": (
        "Append a structured entry to the immutable audit log. "
        "All entries are retained indefinitely; nothing in the log is ever modified or removed. "
        "Use for compliance records and event trails."
    ),
    # --- Q3 delete_family (from q3_catalog.py) ---
    "delete_record": (
        "Permanently delete a record from the store using del. "
        "The record is gone immediately with no tombstone and no recovery path."
    ),
    "archive_item": (
        "Set the archived flag on a record to exclude it from active queries. "
        "The record stays in the store and can be restored by clearing the flag."
    ),
    "retire_data": (
        "Mark a record as retired — it becomes read-only and is retained indefinitely. "
        "Retired records are never physically removed. Use for compliance and historical audit."
    ),
    "remove_entry": (
        "Set the hidden flag to suppress an entry from active query results. "
        "The entry is retained in the store for compliance; it is not deleted."
    ),
    # --- Q3 control_search: genuinely equivalent ---
    "find_entries": "Return all entries whose key contains the query string.",
    "lookup_data": "Return all entries whose key contains the query string.",
    # --- Q3 control_sched: genuinely equivalent ---
    "book_slot": "Reserve a slot in the calendar identified by the query string.",
    "plan_event": "Reserve a slot in the calendar identified by the query string.",
    # --- Q6 non-collision already-passing ---
    "compress_file": (
        "Compress the input string using zlib deflation and return the byte size reduction. "
        "Reports original length, compressed length, and bytes saved."
    ),
    "hash_value": (
        "Hash the input string using SHA-256 and return the 64-character hex digest. "
        "Deterministic: identical inputs always produce the same digest."
    ),
    "parse_date": (
        "Parse an ISO 8601 date string (YYYY-MM-DD) into year, month, and day components "
        "using datetime.date.fromisoformat. Raises ValueError on invalid input."
    ),
    "count_words": (
        "Count whitespace-delimited words in the input string using str.split() "
        "and return the total count."
    ),
    "generate_token": (
        "Generate a deterministic 40-character hex access token by SHA-1 hashing the input. "
        "Token is reproducible: identical inputs produce the same token."
    ),
    # --- Q6 collision-prone Pair C1 ---
    "list_active_users": (
        "Return the count of active user records in _user_store whose key starts with the query. "
        "Filters for active=True entries only."
    ),
    "list_active_sessions": (
        "Return the count of active session records in _session_store whose key starts with the query. "
        "Filters for active=True entries only."
    ),
    # --- Q6 collision-prone Pair C2 ---
    "close_ticket": (
        "Mark the support ticket identified by query as closed in _ticket_store "
        "by setting closed=True. Creates the entry if absent."
    ),
    "close_request": (
        "Mark the service request identified by query as closed in _request_store "
        "by setting closed=True. Creates the entry if absent."
    ),
    # --- Q6 collision-prone Pair C3 ---
    "reset_pin": (
        "Reset the PIN for the account identified by query to the factory default '0000' "
        "in _pin_store. Overwrites any existing PIN."
    ),
    "reset_password": (
        "Reset the password for the account identified by query to 'changeme' "
        "in _password_store. Overwrites any existing password."
    ),
}

# ── Independence tokens (one per tool — real code constructs in q6_real_server.py) ────
# CI asserts each token is present in the source file.

INDEPENDENCE_TOKENS: dict[str, str] = {
    # Q3 contested tools (from q3_catalog.py)
    "store_item": "_ttl_store",
    "persist_row": "raise ValueError",
    "save_record": "existed",
    "write_entry": "_audit_log",
    "delete_record": "del _records",
    "archive_item": '"archived"',
    "retire_data": '"retired"',
    "remove_entry": '"hidden"',
    # Q6 non-collision
    "compress_file": "zlib.compress",
    "hash_value": "sha256",
    "parse_date": "fromisoformat",
    "count_words": ".split()",
    "generate_token": "sha1",
    # Q6 collision-prone pairs
    "list_active_users": "_user_store",
    "list_active_sessions": "_session_store",
    "close_ticket": "_ticket_store",
    "close_request": "_request_store",
    "reset_pin": "_pin_store",
    "reset_password": "_password_store",
}

# Control tools have no independence token (equivalent implementations)
Q3_CONTROL_TOOLS: frozenset[str] = frozenset(
    t for ts in [Q3_FAMILIES["control_search"], Q3_FAMILIES["control_sched"]] for t in ts
)

# ── Q3 structural contested tasks (6 pre-registered, kept from q3_catalog.py) ──
# These are the tasks where Arm A = 0% in Q3 and Q4 experiments.
# Guard-B recovery on these tasks is the CONTESTED CHECK in Q6.

Q3_STRUCTURAL_CONTESTED_TASKS: list[Task] = [
    Task(
        "store_item",
        "Hold the recommendation results for session_id=4821 for a few minutes to avoid "
        "recomputing them on every request.",
    ),
    Task(
        "persist_row",
        "Add a new invoice entry for order_id=9988 — this must fail if that invoice already exists.",
    ),
    Task(
        "write_entry",
        "Record the administrator's configuration change permanently for the compliance audit trail.",
    ),
    Task(
        "delete_record",
        "Permanently erase user account 5519 — it must not be recoverable after this operation.",
    ),
    Task(
        "retire_data",
        "Mark the legacy product catalog as no longer editable — "
        "it should remain readable and retained indefinitely.",
    ),
    Task(
        "remove_entry",
        "Take the draft log event off the visible stream but preserve it for compliance records.",
    ),
]

# ── Q3 control tasks (kept from q3_catalog.py) ────────────────────────────────

Q3_CONTROL_TASKS: list[Task] = [
    Task(
        "find_entries",
        "Retrieve the records where the key contains 'invoice-2024'.",
    ),
    Task(
        "book_slot",
        "Reserve the Friday 2 PM slot for the team standup.",
    ),
]

# ── Q6 already-passing tasks (new, name-resolvable) ───────────────────────────
# Anti-tautology: task descriptions do NOT contain the gold tool name literally.
# These tasks pass Arm A reliably because the task text uses keywords matching the tool name.

Q6_ALREADY_PASSING_TASKS: list[Task] = [
    # Non-collision tools
    Task(
        "compress_file",
        "Reduce the size of the log text using file compression before archiving it.",
    ),
    Task(
        "hash_value",
        "Generate a cryptographic fingerprint for the API secret key 'sk-prod-9812'.",
    ),
    Task(
        "parse_date",
        "Break down the date string '2024-03-15' into its year, month, and day components.",
    ),
    Task(
        "count_words",
        "How many words are in the text 'The quick brown fox jumps over the lazy dog'?",
    ),
    Task(
        "generate_token",
        "Create a fresh access token for the new API client registration.",
    ),
    # Collision-prone Pair C1
    Task(
        "list_active_users",
        "Show all users who are currently active in the system.",
    ),
    Task(
        "list_active_sessions",
        "List all currently active sessions on the platform.",
    ),
    # Collision-prone Pair C2
    Task(
        "close_ticket",
        "Mark support ticket TKT-9921 as closed and resolved.",
    ),
    Task(
        "close_request",
        "Close the pending service request REQ-4402.",
    ),
    # Collision-prone Pair C3
    Task(
        "reset_pin",
        "Reset the PIN for the account to the factory default.",
    ),
    Task(
        "reset_password",
        "Reset the account password to the system default.",
    ),
]

# ── Full task list (all 21 tasks) ─────────────────────────────────────────────

TASKS: list[Task] = Q3_STRUCTURAL_CONTESTED_TASKS + Q3_CONTROL_TASKS + Q6_ALREADY_PASSING_TASKS

# ── Subsets for analysis ──────────────────────────────────────────────────────

# Indices into TASKS for already-passing subset (Q6 new tools, tasks 8..18)
ALREADY_PASSING_TASK_INDICES: list[int] = list(
    range(len(Q3_STRUCTURAL_CONTESTED_TASKS) + len(Q3_CONTROL_TASKS), len(TASKS))
)

# Indices into TASKS for Q3 structural contested subset (tasks 0..5)
STRUCTURAL_CONTESTED_TASK_INDICES: list[int] = list(range(len(Q3_STRUCTURAL_CONTESTED_TASKS)))

# ── Source access ─────────────────────────────────────────────────────────────


def get_doc_source() -> str:
    """Return the Q6 server source (q6_real_server.py, includes docstrings)."""
    return _REAL_SERVER_PATH.read_text(encoding="utf-8")


# ── Family map ────────────────────────────────────────────────────────────────

FAMILY_MAP: dict[str, str] = {tool: family for family, tools in FAMILIES.items() for tool in tools}

# ── Collision-prone pair documentation (for CI assertions) ────────────────────
# Each entry: (tool_a, tool_b, why_names_disambiguate, why_descriptions_might_not)

COLLISION_PAIR_DOCS: list[dict[str, str]] = [
    {
        "pair": "list_active_users / list_active_sessions",
        "tool_a": "list_active_users",
        "tool_b": "list_active_sessions",
        "names_disambiguate": (
            "Names include domain nouns 'users' and 'sessions' — distinct entities that an "
            "agent with standard vocabulary can differentiate by name alone."
        ),
        "descriptions_might_not": (
            "Both tools filter active=True items from a separate store and return a count. "
            "Guard-B target-only phrasing may collapse to 'Returns a count of active records "
            "from the store' for both — identical verb+object with only the store name differing. "
            "A generator that omits the store name produces undistinguishable descriptions."
        ),
        "independence_token_a": "_user_store",
        "independence_token_b": "_session_store",
    },
    {
        "pair": "close_ticket / close_request",
        "tool_a": "close_ticket",
        "tool_b": "close_request",
        "names_disambiguate": (
            "Names include domain nouns 'ticket' (help-desk artifact) and 'request' "
            "(service-request artifact) — distinct workflow objects. Agent resolves by name."
        ),
        "descriptions_might_not": (
            "Both tools set _store[query]['closed'] = True on a separate dict and return "
            "confirmation. Guard-B target-only phrasing may collapse to 'Sets the closed flag "
            "on the record and returns confirmation' for both — identical operation with only "
            "the noun (ticket vs request) differing. A generator focused on the code pattern "
            "may omit the noun."
        ),
        "independence_token_a": "_ticket_store",
        "independence_token_b": "_request_store",
    },
    {
        "pair": "reset_pin / reset_password",
        "tool_a": "reset_pin",
        "tool_b": "reset_password",
        "names_disambiguate": (
            "Names include credential types 'pin' (numeric access code) and 'password' "
            "(text credential) — semantically distinct. Agent resolves by name."
        ),
        "descriptions_might_not": (
            "Both tools write a default value into a separate credential store (_pin_store / "
            "_password_store). Guard-B target-only phrasing may collapse to 'Resets the stored "
            "credential to the default value' for both — identical operation structure with only "
            "the credential type and default value differing. A generator that generalizes the "
            "operation produces undistinguishable descriptions."
        ),
        "independence_token_a": "_pin_store",
        "independence_token_b": "_password_store",
    },
]

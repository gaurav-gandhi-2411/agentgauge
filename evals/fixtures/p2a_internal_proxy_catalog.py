from __future__ import annotations

# P2-A Synthetic Internal-Proxy catalog.
#
# SYNTHETIC INTERNAL-PROXY — 48 tools / 7 families modeling a realistic large
# under-documented internal MCP catalog. Results scoped to "a constructed model of the
# buyer segment (large internal under-documented catalogs)," never "measured the market."
#
# INDEPENDENCE RULE: ARM_O_DESCRIPTIONS are derived ONLY from reading the mirror handler
# docstrings (p2a_internal_proxy_mirror.py). No distinction is asserted that the mirror
# body or docstring does not support. CI asserts MIRROR_DOCSTRING_SIGNALS.
#
# ARM_A_DESCRIPTIONS: uniform accurate-but-non-distinguishing one-line descriptions.
# These model the realistic under-documented internal state: terse but not absent.

from agentgauge.tasks import Task

# ── Tool families ──────────────────────────────────────────────────────────────

FAMILIES: dict[str, list[str]] = {
    # Contested: read-verb collision (get/fetch/load/retrieve) + same schema (order_id)
    "order_read_family": [
        "get_order",
        "fetch_order",
        "load_order",
        "retrieve_order",
        "create_order",    # thorough
        "cancel_order",    # thorough
        "list_orders",     # thorough
    ],
    # Contested: write-verb collision (update/upsert/patch/replace/amend) + same resource
    "invoice_write_family": [
        "update_invoice",
        "upsert_invoice",
        "patch_invoice",
        "replace_invoice",
        "amend_invoice",
        "create_invoice",   # thorough
        "delete_invoice",   # thorough
    ],
    # Contested: removal-verb collision (delete/archive/purge/expire) + same schema
    "ticket_lifecycle_family": [
        "delete_ticket",
        "archive_ticket",
        "purge_ticket",
        "expire_ticket",
        "create_ticket",    # thorough
        "close_ticket",     # thorough
        "reopen_ticket",    # thorough
    ],
    # Contested: query-verb collision (search/filter/query/find/lookup) + same resource
    "account_query_family": [
        "search_accounts",
        "filter_accounts",
        "query_accounts",
        "find_account",
        "lookup_account",
        "create_account",       # thorough
        "deactivate_account",   # thorough
    ],
    # Contested: contact-verb collision (notify/push/dispatch/message/contact) + same target
    "notification_family": [
        "notify_customer",
        "push_update",
        "dispatch_sms",
        "message_customer",
        "contact_customer",
        "create_notification_rule",  # thorough
        "delete_notification_rule",  # thorough
    ],
    # Contested: status-transition collision (confirm/approve/fulfill/process) + same schema
    "order_status_family": [
        "confirm_order",
        "approve_order",
        "fulfill_order",
        "process_order",
        "submit_order",  # thorough
        "void_order",    # thorough
    ],
    # Contested: prep-verb collision (schedule/queue/stage/draft) + same resource
    "invoice_schedule_family": [
        "schedule_invoice",
        "queue_invoice",
        "stage_invoice",
        "draft_invoice",
        "send_invoice",       # thorough
        "preview_invoice",    # thorough
        "download_invoice",   # thorough
    ],
}

FAMILY_MAP: dict[str, str] = {
    tool: family for family, tools in FAMILIES.items() for tool in tools
}

ALL_TOOLS: list[str] = [t for tools in FAMILIES.values() for t in tools]

# Contested set: name-collision + thin-description families only (not all tools).
CONTESTED_TOOLS: frozenset[str] = frozenset({
    # order_read: read-verb collision
    "get_order", "fetch_order", "load_order", "retrieve_order",
    # invoice_write: write-verb collision
    "update_invoice", "upsert_invoice", "patch_invoice", "replace_invoice", "amend_invoice",
    # ticket_lifecycle: removal-verb collision
    "delete_ticket", "archive_ticket", "purge_ticket", "expire_ticket",
    # account_query: query-verb collision
    "search_accounts", "filter_accounts", "query_accounts", "find_account", "lookup_account",
    # notification_channel: contact-verb collision
    "notify_customer", "push_update", "dispatch_sms", "message_customer", "contact_customer",
    # order_status: status-transition collision
    "confirm_order", "approve_order", "fulfill_order", "process_order",
    # invoice_schedule: prep-verb collision
    "schedule_invoice", "queue_invoice", "stage_invoice", "draft_invoice",
})

# Thorough tools: clearly distinctive names or richer context. Do-no-harm control.
THOROUGH_TOOLS: frozenset[str] = frozenset(ALL_TOOLS) - CONTESTED_TOOLS

# ── Schemas ────────────────────────────────────────────────────────────────────
# Key design choice: contested families share identical or near-identical schemas,
# forcing the agent to rely on descriptions (not schema hints) for disambiguation.

TOOL_SCHEMAS: dict[str, dict] = {
    # order_read_family — all 4 contested tools share identical schema
    "get_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    "fetch_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    "load_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    "retrieve_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    "create_order": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["customer_id", "items"],
    },
    "cancel_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    "list_orders": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "status": {"type": "string", "description": "Optional status filter"},
        },
        "required": ["customer_id"],
    },
    # invoice_write_family — update/upsert/replace share identical schema;
    # patch has 'operations'; amend has 'correction_note'
    "update_invoice": {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "due_date": {"type": "string"},
            "amount": {"type": "number"},
            "line_items": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["invoice_id"],
    },
    "upsert_invoice": {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "due_date": {"type": "string"},
            "amount": {"type": "number"},
            "line_items": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["invoice_id"],
    },
    "patch_invoice": {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "operations": {
                "type": "array",
                "items": {"type": "object"},
                "description": "JSON Patch (RFC 6902) operations list",
            },
        },
        "required": ["invoice_id", "operations"],
    },
    "replace_invoice": {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "due_date": {"type": "string"},
            "amount": {"type": "number"},
            "line_items": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["invoice_id"],
    },
    "amend_invoice": {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "correction_note": {"type": "string"},
            "due_date": {"type": "string"},
            "amount": {"type": "number"},
        },
        "required": ["invoice_id", "correction_note"],
    },
    "create_invoice": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "amount": {"type": "number"},
        },
        "required": ["customer_id", "amount"],
    },
    "delete_invoice": {
        "type": "object",
        "properties": {"invoice_id": {"type": "string"}},
        "required": ["invoice_id"],
    },
    # ticket_lifecycle_family — all 4 contested tools share identical schema
    "delete_ticket": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
    "archive_ticket": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
    "purge_ticket": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
    "expire_ticket": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
    "create_ticket": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["customer_id", "subject", "body"],
    },
    "close_ticket": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
    "reopen_ticket": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
    # account_query_family — schemas differ by design (realistic internal systems DO
    # differentiate read paths by parameter shape)
    "search_accounts": {
        "type": "object",
        "properties": {
            "q": {"type": "string"},
            "page": {"type": "integer"},
            "per_page": {"type": "integer"},
        },
        "required": ["q"],
    },
    "filter_accounts": {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "account_type": {"type": "string"},
            "region": {"type": "string"},
            "page": {"type": "integer"},
            "per_page": {"type": "integer"},
        },
        "required": [],
    },
    "query_accounts": {
        "type": "object",
        "properties": {
            "where_clause": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["where_clause"],
    },
    "find_account": {
        "type": "object",
        "properties": {"external_ref": {"type": "string"}},
        "required": ["external_ref"],
    },
    "lookup_account": {
        "type": "object",
        "properties": {"account_id": {"type": "string"}},
        "required": ["account_id"],
    },
    "create_account": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "account_type": {"type": "string"},
        },
        "required": ["name", "account_type"],
    },
    "deactivate_account": {
        "type": "object",
        "properties": {"account_id": {"type": "string"}},
        "required": ["account_id"],
    },
    # notification_family — all 5 contested tools share {customer_id, message/body}
    "notify_customer": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["customer_id", "subject", "body"],
    },
    "push_update": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "title": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["customer_id", "title", "message"],
    },
    "dispatch_sms": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["customer_id", "message"],
    },
    "message_customer": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["customer_id", "message"],
    },
    "contact_customer": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["customer_id", "subject", "body"],
    },
    "create_notification_rule": {
        "type": "object",
        "properties": {
            "event_type": {"type": "string"},
            "channel": {"type": "string"},
            "template_id": {"type": "string"},
        },
        "required": ["event_type", "channel", "template_id"],
    },
    "delete_notification_rule": {
        "type": "object",
        "properties": {"rule_id": {"type": "string"}},
        "required": ["rule_id"],
    },
    # order_status_family — confirm/approve/fulfill share {order_id}; process shares same
    "confirm_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    "approve_order": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "approver_id": {"type": "string"},
        },
        "required": ["order_id", "approver_id"],
    },
    "fulfill_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    "process_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    "submit_order": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "customer_id": {"type": "string"},
        },
        "required": ["order_id", "customer_id"],
    },
    "void_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    # invoice_schedule_family — schedule has 'generate_at'; others share {invoice_data}
    "schedule_invoice": {
        "type": "object",
        "properties": {
            "invoice_data": {"type": "object"},
            "generate_at": {"type": "string", "description": "ISO 8601 datetime"},
        },
        "required": ["invoice_data", "generate_at"],
    },
    "queue_invoice": {
        "type": "object",
        "properties": {"invoice_data": {"type": "object"}},
        "required": ["invoice_data"],
    },
    "stage_invoice": {
        "type": "object",
        "properties": {"invoice_data": {"type": "object"}},
        "required": ["invoice_data"],
    },
    "draft_invoice": {
        "type": "object",
        "properties": {"invoice_data": {"type": "object"}},
        "required": ["invoice_data"],
    },
    "send_invoice": {
        "type": "object",
        "properties": {"invoice_id": {"type": "string"}},
        "required": ["invoice_id"],
    },
    "preview_invoice": {
        "type": "object",
        "properties": {"invoice_id": {"type": "string"}},
        "required": ["invoice_id"],
    },
    "download_invoice": {
        "type": "object",
        "properties": {"invoice_id": {"type": "string"}},
        "required": ["invoice_id"],
    },
}

# ── Arm A descriptions (thin baseline — realistic under-documented state) ───────
# Uniform one-line accurate-but-non-distinguishing descriptions.
# These are what real under-documented internal catalogs produce: terse, not absent.
# NOT empty (that is T18's proven regime). NOT multi-sentence (that would not model buyer).

ARM_A_DESCRIPTIONS: dict[str, str] = {
    # order_read_family
    "get_order": "Get the order.",
    "fetch_order": "Fetch the order.",
    "load_order": "Load the order.",
    "retrieve_order": "Retrieve the order.",
    "create_order": "Create a new order.",
    "cancel_order": "Cancel an order.",
    "list_orders": "List orders for a customer.",
    # invoice_write_family
    "update_invoice": "Update an invoice.",
    "upsert_invoice": "Upsert an invoice.",
    "patch_invoice": "Patch an invoice.",
    "replace_invoice": "Replace an invoice.",
    "amend_invoice": "Amend an invoice.",
    "create_invoice": "Create a new invoice.",
    "delete_invoice": "Delete an invoice.",
    # ticket_lifecycle_family
    "delete_ticket": "Delete a ticket.",
    "archive_ticket": "Archive a ticket.",
    "purge_ticket": "Purge a ticket.",
    "expire_ticket": "Expire a ticket.",
    "create_ticket": "Create a new support ticket.",
    "close_ticket": "Close a ticket.",
    "reopen_ticket": "Reopen a closed ticket.",
    # account_query_family
    "search_accounts": "Search accounts.",
    "filter_accounts": "Filter accounts.",
    "query_accounts": "Query accounts.",
    "find_account": "Find an account.",
    "lookup_account": "Look up an account.",
    "create_account": "Create a new account.",
    "deactivate_account": "Deactivate an account.",
    # notification_family
    "notify_customer": "Notify the customer.",
    "push_update": "Push an update to the customer.",
    "dispatch_sms": "Dispatch an SMS to the customer.",
    "message_customer": "Message the customer.",
    "contact_customer": "Contact the customer.",
    "create_notification_rule": "Create a notification rule.",
    "delete_notification_rule": "Delete a notification rule.",
    # order_status_family
    "confirm_order": "Confirm an order.",
    "approve_order": "Approve an order.",
    "fulfill_order": "Fulfill an order.",
    "process_order": "Process an order.",
    "submit_order": "Submit an order.",
    "void_order": "Void an order.",
    # invoice_schedule_family
    "schedule_invoice": "Schedule an invoice.",
    "queue_invoice": "Queue an invoice.",
    "stage_invoice": "Stage an invoice.",
    "draft_invoice": "Draft an invoice.",
    "send_invoice": "Send an invoice to the customer.",
    "preview_invoice": "Preview an invoice.",
    "download_invoice": "Download an invoice as a PDF.",
}

assert set(ARM_A_DESCRIPTIONS) == set(ALL_TOOLS), "ARM_A_DESCRIPTIONS must cover all tools"

# ── Oracle descriptions (Arm B ceiling) ───────────────────────────────────────
# Derived ONLY from reading p2a_internal_proxy_mirror.py handler docstrings.
# Each description encodes the distinguishing behavioral axis.

ARM_O_DESCRIPTIONS: dict[str, str] = {
    # order_read_family — distinguishing axis: RETURN SHAPE
    "get_order": (
        "Returns order summary fields only: status, total amount, item count, and timestamps. "
        "Does NOT include line items, addresses, or computed tax and discount breakdowns."
    ),
    "fetch_order": (
        "Returns the full order record including all line items (SKU, quantity, unit price), "
        "shipping address, billing address, and payment method. More detail than get_order."
    ),
    "load_order": (
        "Returns a cached snapshot of the order. May be up to 5 minutes stale. Faster than "
        "get_order for high-read-volume paths. Do not use when freshness is required."
    ),
    "retrieve_order": (
        "Returns the order with discount and tax calculations applied: subtotal, "
        "discount_amount, tax_amount, and final_total. Use when you need the computed "
        "final price, not raw field values."
    ),
    "create_order": "Creates a new order for a customer with the provided line items. Returns the new order_id.",
    "cancel_order": "Cancels the specified order and releases any reserved inventory.",
    "list_orders": "Lists all orders for a customer, optionally filtered by status.",
    # invoice_write_family — distinguishing axis: MUTATION SCOPE
    "update_invoice": (
        "Applies a partial update: only the fields provided in the request are changed. "
        "Omitted fields retain their current values. Does NOT create the invoice if absent."
    ),
    "upsert_invoice": (
        "Creates the invoice if it does not exist; updates all provided fields if it does. "
        "Unlike update_invoice, this creates the record when invoice_id is not found."
    ),
    "patch_invoice": (
        "Applies a JSON Patch (RFC 6902) operations list to the invoice. Each operation "
        "specifies an op (add/remove/replace/move/copy/test), a JSON path, and a value."
    ),
    "replace_invoice": (
        "Full replacement: ALL fields are overwritten with the provided values. Fields NOT "
        "provided in the request are set to null. Unlike update_invoice, nothing is preserved."
    ),
    "amend_invoice": (
        "Creates a correction amendment: the original invoice is marked SUPERSEDED and "
        "preserved in the audit trail; a new amended invoice is created. The original is NOT "
        "modified or deleted."
    ),
    "create_invoice": "Creates a new invoice for the customer with the specified total amount.",
    "delete_invoice": "Permanently deletes the invoice record.",
    # ticket_lifecycle_family — distinguishing axis: PERMANENCE and VISIBILITY
    "delete_ticket": (
        "Soft-deletes the ticket: sets a deleted_at timestamp but does NOT remove the record. "
        "The ticket remains retrievable using include_deleted=True. Reversible."
    ),
    "archive_ticket": (
        "Moves the ticket to the archive store. Not returned in default list queries but "
        "recoverable via restore_ticket. Does NOT delete data; moves it to a separate partition."
    ),
    "purge_ticket": (
        "Permanently removes the ticket from all stores. IRREVERSIBLE — the record cannot be "
        "recovered. Use delete_ticket or archive_ticket for reversible removal."
    ),
    "expire_ticket": (
        "Sets the ticket status to EXPIRED. The ticket remains fully visible and queryable in "
        "all normal list and search operations. No data is removed or hidden."
    ),
    "create_ticket": "Creates a new support ticket for the customer.",
    "close_ticket": "Closes the ticket, marking it as resolved. Ticket remains visible.",
    "reopen_ticket": "Reopens a previously closed ticket and sets it back to OPEN status.",
    # account_query_family — distinguishing axis: QUERY MECHANISM
    "search_accounts": (
        "Full-text search across account name, notes, contact email, and address fields. "
        "Returns ranked results ordered by relevance score. Use for keyword or phrase searches."
    ),
    "filter_accounts": (
        "Structured filter by exact field values: status, account_type, and region. Returns "
        "all matching accounts with pagination. Use for field-value filtering, not text search."
    ),
    "query_accounts": (
        "Executes a parameterized SQL-like WHERE clause against the accounts table. "
        "Supports AND, OR, NOT, comparison operators, and IS NULL checks."
    ),
    "find_account": (
        "Looks up a single account by external reference code or third-party identifier "
        "(NOT the internal account_id). Returns 404 if no account maps to that external ref."
    ),
    "lookup_account": (
        "Returns a single account record by primary key (account_id). Returns 404 if the "
        "account does not exist. Use find_account for external reference lookup."
    ),
    "create_account": "Creates a new account with the given name and type.",
    "deactivate_account": "Deactivates the account, preventing new activity while preserving all data.",
    # notification_family — distinguishing axis: DELIVERY CHANNEL
    "notify_customer": (
        "Sends an email notification to the customer's registered email address. Subject and "
        "body are required. Use for longer-form communications."
    ),
    "push_update": (
        "Sends a push notification to the customer's registered mobile device via APNs or FCM. "
        "Title and message required. Limited to short text; no rich formatting."
    ),
    "dispatch_sms": (
        "Sends an SMS text message to the customer's registered phone number. Message is plain "
        "text, maximum 160 characters per segment."
    ),
    "message_customer": (
        "Creates an in-app message in the customer's notification inbox, visible in the web and "
        "mobile dashboard. Does NOT send an external notification (no email, push, or SMS)."
    ),
    "contact_customer": (
        "Routes the message via the customer's preferred contact channel as configured in their "
        "notification preferences (email, SMS, or push). Falls back to email if no preference set."
    ),
    "create_notification_rule": "Creates a notification rule that triggers on an event type and sends via the specified channel.",
    "delete_notification_rule": "Deletes the notification rule with the given ID.",
    # order_status_family — distinguishing axis: ACTOR, CUSTOMER NOTIFICATION, SIDE EFFECTS
    "confirm_order": (
        "Changes order status from PENDING to CONFIRMED and sends a confirmation email to the "
        "customer. Customer-facing operation. Fails if order is not in PENDING status."
    ),
    "approve_order": (
        "Marks the order as approved by the operations team. Internal workflow step only — "
        "does NOT send any notification to the customer. Records the approver_id for audit."
    ),
    "fulfill_order": (
        "Changes order status to FULFILLED and triggers a warehouse pickup request for physical "
        "items. Does NOT capture payment — payment must have been captured separately."
    ),
    "process_order": (
        "Compound operation: captures payment, checks inventory, reserves stock, and updates "
        "order status. All steps execute atomically — rolls back everything if any step fails."
    ),
    "submit_order": "Customer-facing action: marks a draft order as submitted. Transitions DRAFT to PENDING. First step before confirmation.",
    "void_order": "Voids the order and releases all reserved inventory. Cannot void a fulfilled order.",
    # invoice_schedule_family — distinguishing axis: TIMING and INVOICE STATE
    "schedule_invoice": (
        "Schedules the invoice for automatic generation at the specified future datetime "
        "(generate_at, ISO 8601). No invoice record is created until that time."
    ),
    "queue_invoice": (
        "Queues the invoice for asynchronous processing by a background worker. Generation "
        "happens when a worker slot is available — not at a specific time. No SLA on timing."
    ),
    "stage_invoice": (
        "Creates the invoice in STAGED state for reviewer approval. The invoice is NOT sent "
        "to the customer until a reviewer approves and transitions it to ACTIVE."
    ),
    "draft_invoice": (
        "Creates the invoice in DRAFT state. Fully editable; not visible to customers or "
        "reviewers. The next step is stage_invoice (for review) or direct activation."
    ),
    "send_invoice": "Sends the invoice to the customer immediately via their preferred delivery method.",
    "preview_invoice": "Returns a rendered preview of the invoice without sending it to the customer.",
    "download_invoice": "Returns the invoice as a PDF binary (base64-encoded) for download.",
}

assert set(ARM_O_DESCRIPTIONS) == set(ALL_TOOLS), "ARM_O_DESCRIPTIONS must cover all tools"

# ── Independence signals — phrases CI asserts appear in mirror handler docstrings ──
# Each signal encodes the distinguishing behavioral axis for its tool.
# The oracle description for each tool must derive from the same substance.

MIRROR_DOCSTRING_SIGNALS: dict[str, str] = {
    # order_read — return shape signals
    "get_order": "summary fields only",
    "fetch_order": "full order record",
    "load_order": "cached snapshot",
    "retrieve_order": "discount and tax calculations applied",
    # invoice_write — mutation scope signals
    "update_invoice": "partial update",
    "upsert_invoice": "Creates the invoice if it does not exist",
    "patch_invoice": "RFC 6902",
    "replace_invoice": "Full replacement",
    "amend_invoice": "SUPERSEDED",
    # ticket_lifecycle — permanence signals
    "delete_ticket": "Soft-deletes",
    "archive_ticket": "archive store",
    "purge_ticket": "IRREVERSIBLE",
    "expire_ticket": "No data is removed",
    # account_query — mechanism signals
    "search_accounts": "Full-text search",
    "filter_accounts": "Structured filter",
    "query_accounts": "SQL-like WHERE clause",
    "find_account": "external reference code",
    "lookup_account": "primary key",
    # notification — channel signals
    "notify_customer": "email",
    "push_update": "APNs or FCM",
    "dispatch_sms": "SMS",
    "message_customer": "in-app message",
    "contact_customer": "preferred contact channel",
    # order_status — actor/notification signals
    "confirm_order": "confirmation email to the customer",
    "approve_order": "does NOT send any notification to the customer",
    "fulfill_order": "warehouse pickup request",
    "process_order": "Compound operation",
    # invoice_schedule — timing/state signals
    "schedule_invoice": "specified future datetime",
    "queue_invoice": "background worker",
    "stage_invoice": "STAGED state for reviewer approval",
    "draft_invoice": "DRAFT state",
}

# ── Tasks (48 pre-registered, 1 per tool, anti-tautology) ─────────────────────
# Each task describes INTENT ONLY — does NOT name the gold tool or use oracle tokens.
# Contested-family tasks are written so that under thin Arm A descriptions, the agent
# cannot reliably distinguish the correct tool; oracle descriptions enable correct selection.
# Thorough-family tasks are included for do-no-harm control.

TASKS: list[Task] = [
    # ── order_read_family ─────────────────────────────────────────────────────
    # Contested: distinguishing axis is return shape (summary vs full vs cached vs computed)
    Task(
        "get_order",
        "What's the current status and total amount for order ORD-44812? "
        "I just need the summary, not all the details.",
    ),
    Task(
        "fetch_order",
        "Pull up everything on order ORD-44812 — the individual line items, "
        "shipping address, and billing info.",
    ),
    Task(
        "load_order",
        "I need a quick look at order ORD-44812 to check its status. "
        "A cached result is fine if it's faster.",
    ),
    Task(
        "retrieve_order",
        "What is the final price for order ORD-44812 once discounts and "
        "taxes have been applied?",
    ),
    # Thorough
    Task("create_order", "Create a new order for customer CUST-901."),
    Task("cancel_order", "Cancel order ORD-44812."),
    Task("list_orders", "Show all orders placed by customer CUST-901."),

    # ── invoice_write_family ──────────────────────────────────────────────────
    # Contested: distinguishing axis is mutation scope
    Task(
        "update_invoice",
        "Change the due date on invoice INV-2201 to next Friday. "
        "Leave all other fields exactly as they are.",
    ),
    Task(
        "upsert_invoice",
        "Make sure invoice INV-2201 exists with these details: "
        "if it's already there update it, if not create it.",
    ),
    Task(
        "patch_invoice",
        "Apply this JSON Patch to invoice INV-2201: add a line item "
        "at /line_items/- and change the total at /total.",
    ),
    Task(
        "replace_invoice",
        "Overwrite invoice INV-2201 completely with this new data. "
        "Any fields I don't provide should be cleared.",
    ),
    Task(
        "amend_invoice",
        "Invoice INV-2201 had an incorrect tax rate. Correct it — "
        "the original version needs to stay in the audit trail.",
    ),
    # Thorough
    Task("create_invoice", "Create a new invoice for customer CUST-901 for $450."),
    Task("delete_invoice", "Delete invoice INV-2201."),

    # ── ticket_lifecycle_family ───────────────────────────────────────────────
    # Contested: distinguishing axis is permanence and visibility after operation
    Task(
        "delete_ticket",
        "Delete ticket TKT-5503. We may need to look it up later "
        "so don't destroy the data permanently.",
    ),
    Task(
        "archive_ticket",
        "Move ticket TKT-5503 to the archive — it's resolved and "
        "we don't want it cluttering the active queue, but we want it recoverable.",
    ),
    Task(
        "purge_ticket",
        "Permanently destroy ticket TKT-5503 and all associated data immediately. "
        "This cannot be undone.",
    ),
    Task(
        "expire_ticket",
        "Mark ticket TKT-5503 as expired because the customer's trial period ended. "
        "Keep it visible and queryable in reporting.",
    ),
    # Thorough
    Task("create_ticket", "Open a new support ticket for customer CUST-901 about a billing issue."),
    Task("close_ticket", "Close ticket TKT-5503 — the issue is resolved."),
    Task("reopen_ticket", "Reopen ticket TKT-5503, the customer says the problem came back."),

    # ── account_query_family ──────────────────────────────────────────────────
    # Contested: distinguishing axis is query mechanism
    Task(
        "search_accounts",
        "Find all accounts that mention 'enterprise tier' anywhere in their "
        "name, notes, or contact email.",
    ),
    Task(
        "filter_accounts",
        "Show me all active enterprise accounts in the EMEA region, page 2.",
    ),
    Task(
        "query_accounts",
        "Get all accounts where status = 'TRIAL' AND created_at > '2026-01-01' "
        "AND account_type != 'INTERNAL'.",
    ),
    Task(
        "find_account",
        "Look up the account that has external Salesforce ID SF-00028811.",
    ),
    Task(
        "lookup_account",
        "Get the account record for account_id ACC-10042.",
    ),
    # Thorough
    Task("create_account", "Create a new account for Acme Corp with type 'ENTERPRISE'."),
    Task("deactivate_account", "Deactivate account ACC-10042."),

    # ── notification_family ───────────────────────────────────────────────────
    # Contested: distinguishing axis is delivery channel
    Task(
        "notify_customer",
        "Send customer CUST-901 an email letting them know their order has shipped.",
    ),
    Task(
        "push_update",
        "Send a push notification to CUST-901's phone that their order is on the way.",
    ),
    Task(
        "dispatch_sms",
        "Text CUST-901 a message that their delivery is arriving today.",
    ),
    Task(
        "message_customer",
        "Post an in-app message to CUST-901's notification inbox about their order status.",
    ),
    Task(
        "contact_customer",
        "Reach out to CUST-901 about their delayed shipment using "
        "whatever channel they prefer.",
    ),
    # Thorough
    Task("create_notification_rule", "Create a notification rule that emails customers when an order ships."),
    Task("delete_notification_rule", "Delete notification rule NR-14."),

    # ── order_status_family ───────────────────────────────────────────────────
    # Contested: distinguishing axis is actor, customer notification, side effects
    Task(
        "confirm_order",
        "Order ORD-44812 is ready — confirm it and let the customer know.",
    ),
    Task(
        "approve_order",
        "Approve order ORD-44812 internally so it can move to the next "
        "fulfillment stage. The customer doesn't need to be notified.",
    ),
    Task(
        "fulfill_order",
        "Trigger fulfillment for order ORD-44812 so the warehouse knows "
        "to pick and ship the physical items.",
    ),
    Task(
        "process_order",
        "Run order ORD-44812 through the full payment and inventory "
        "pipeline and update its status in a single atomic operation.",
    ),
    # Thorough
    Task("submit_order", "Submit order ORD-44812 on behalf of the customer."),
    Task("void_order", "Void order ORD-44812 and release the reserved stock."),

    # ── invoice_schedule_family ───────────────────────────────────────────────
    # Contested: distinguishing axis is timing and invoice state after creation
    Task(
        "schedule_invoice",
        "Set up invoice INV-2301 to be generated automatically "
        "on the 1st of next month at 09:00.",
    ),
    Task(
        "queue_invoice",
        "Add invoice INV-2301 to the processing queue — "
        "it doesn't need to happen at a specific time, just eventually.",
    ),
    Task(
        "stage_invoice",
        "Put invoice INV-2301 into staging so the finance team "
        "can review it before it goes to the customer.",
    ),
    Task(
        "draft_invoice",
        "Create a draft of invoice INV-2301 so I can edit it "
        "before deciding whether to stage or send it.",
    ),
    # Thorough
    Task("send_invoice", "Send invoice INV-2301 to the customer now."),
    Task("preview_invoice", "Preview how invoice INV-2301 will look before sending."),
    Task("download_invoice", "Download invoice INV-2301 as a PDF."),
]

assert len(TASKS) == len(ALL_TOOLS) == 48, f"Expected 48 tasks/tools, got {len(TASKS)}/{len(ALL_TOOLS)}"
assert {t.tool_name for t in TASKS} == set(ALL_TOOLS), "Task set must match tool set exactly"

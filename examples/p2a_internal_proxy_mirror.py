from __future__ import annotations

# P2-A Synthetic Internal-Proxy mirror server.
#
# SYNTHETIC INTERNAL-PROXY — models a realistic large (48-tool) under-documented
# internal MCP catalog. Real-behavior-bearing stubs with meaningful docstrings.
# Stub bodies — NO live API, NO database, NO external dependencies.
#
# INDEPENDENCE RULE: oracle descriptions are derived from these docstrings and
# return structures — not invented separately. CI asserts independence signals.
#
# 48 tools across 7 confusable families:
#   order_read_family     (4 contested + 3 thorough = 7)  — get/fetch/load/retrieve
#   invoice_write_family  (5 contested + 2 thorough = 7)  — update/upsert/patch/replace/amend
#   ticket_lifecycle_fam  (4 contested + 3 thorough = 7)  — delete/archive/purge/expire
#   account_query_family  (5 contested + 2 thorough = 7)  — search/filter/query/find/lookup
#   notification_family   (5 contested + 2 thorough = 7)  — notify/push/dispatch/message/contact
#   order_status_family   (4 contested + 2 thorough = 6)  — confirm/approve/fulfill/process
#   invoice_schedule_fam  (4 contested + 3 thorough = 7)  — schedule/queue/stage/draft

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from evals.fixtures.p2a_internal_proxy_catalog import ARM_A_DESCRIPTIONS, TOOL_SCHEMAS

server = Server("p2a-internal-proxy-mirror")

# ── Family 1: order_read ──────────────────────────────────────────────────────
# WHY confusable: all 4 names start with a common read-verb (get/fetch/load/retrieve)
# and take the same input (order_id). Thin descriptions collapse to "Verb the order."
# The distinguishing axis is RETURN SHAPE: summary vs full vs cached vs computed.


def _handle_get_order(order_id: str) -> dict:
    """Returns order summary fields only: status, total amount, item count, and timestamps.
    Does NOT include line items, addresses, or computed tax and discount breakdowns."""
    return {
        "order_id": order_id,
        "status": "CONFIRMED",
        "total": 0.0,
        "item_count": 0,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


def _handle_fetch_order(order_id: str) -> dict:
    """Returns the full order record including all line items (SKU, quantity, unit price),
    shipping address, billing address, and payment method. More data than get_order."""
    return {
        "order_id": order_id,
        "status": "CONFIRMED",
        "line_items": [{"sku": "SKU-001", "qty": 1, "unit_price": 0.0}],
        "shipping_address": {"street": "", "city": "", "country": ""},
        "billing_address": {"street": "", "city": "", "country": ""},
        "payment_method": "CARD",
    }


def _handle_load_order(order_id: str) -> dict:
    """Returns a cached snapshot of the order. May be up to 5 minutes stale.
    Faster than get_order for high-read-volume paths. Do not use when freshness is required."""
    return {
        "order_id": order_id,
        "status": "CONFIRMED",
        "total": 0.0,
        "item_count": 0,
        "_cached_at": "2026-01-01T00:00:00Z",
        "_cache_ttl_seconds": 300,
    }


def _handle_retrieve_order(order_id: str) -> dict:
    """Returns the order with discount and tax calculations applied: subtotal, discount_amount,
    tax_amount, and final_total. Use when you need the computed final price, not raw field values."""
    return {
        "order_id": order_id,
        "subtotal": 0.0,
        "discount_amount": 0.0,
        "tax_amount": 0.0,
        "final_total": 0.0,
        "discounts_applied": [],
    }


def _handle_create_order(customer_id: str, items: list) -> dict:
    """Creates a new order for a customer with the provided line items. Returns the new order_id."""
    return {"order_id": "ORD-NEW", "customer_id": customer_id, "status": "PENDING"}


def _handle_cancel_order(order_id: str) -> dict:
    """Cancels the specified order and releases any reserved inventory."""
    return {"order_id": order_id, "status": "CANCELLED"}


def _handle_list_orders(customer_id: str, status: str | None = None) -> dict:
    """Lists all orders for a customer, optionally filtered by status."""
    return {"customer_id": customer_id, "orders": [], "total": 0}


# ── Family 2: invoice_write ───────────────────────────────────────────────────
# WHY confusable: all 5 contested names start with an action verb targeting the same
# resource (invoice). Thin descriptions collapse to "Verb an invoice." The distinguishing
# axis is MUTATION SCOPE: partial vs create-or-update vs JSON-patch vs full-replace vs
# audit-preserving amendment.


def _handle_update_invoice(invoice_id: str, **fields: object) -> dict:
    """Applies a partial update: only the fields provided in the request are changed.
    Omitted fields retain their current values. Does NOT create the invoice if absent."""
    return {"invoice_id": invoice_id, "updated_fields": list(fields.keys())}


def _handle_upsert_invoice(invoice_id: str, **fields: object) -> dict:
    """Creates the invoice if it does not exist; updates all provided fields if it does.
    Unlike update_invoice, this creates the record when invoice_id is not found."""
    return {"invoice_id": invoice_id, "created": False, "updated_fields": list(fields.keys())}


def _handle_patch_invoice(invoice_id: str, operations: list) -> dict:
    """Applies a JSON Patch (RFC 6902) operations list to the invoice. Each operation
    specifies an op (add/remove/replace/move/copy/test), a JSON path, and an optional value."""
    return {"invoice_id": invoice_id, "operations_applied": len(operations)}


def _handle_replace_invoice(invoice_id: str, **fields: object) -> dict:
    """Full replacement: ALL fields are overwritten with the provided values.
    Fields NOT provided in the request are set to null. Unlike update_invoice, nothing is preserved."""
    return {"invoice_id": invoice_id, "replaced": True}


def _handle_amend_invoice(invoice_id: str, correction_note: str, **fields: object) -> dict:
    """Creates a correction amendment: the original invoice is marked SUPERSEDED and preserved
    in the audit trail; a new amended invoice is created. The original is NOT modified or deleted."""
    return {
        "original_invoice_id": invoice_id,
        "amended_invoice_id": "INV-AMEND",
        "original_status": "SUPERSEDED",
        "correction_note": correction_note,
    }


def _handle_create_invoice(customer_id: str, amount: float) -> dict:
    """Creates a new invoice for the customer with the specified total amount."""
    return {"invoice_id": "INV-NEW", "customer_id": customer_id, "amount": amount}


def _handle_delete_invoice(invoice_id: str) -> dict:
    """Permanently deletes the invoice record."""
    return {"invoice_id": invoice_id, "deleted": True}


# ── Family 3: ticket_lifecycle ────────────────────────────────────────────────
# WHY confusable: all 4 contested names imply "removal" of a ticket but the recoverability
# and visibility semantics differ. Thin descriptions collapse to "Verb a ticket."
# Distinguishing axis: PERMANENCE and VISIBILITY after the operation.


def _handle_delete_ticket(ticket_id: str) -> dict:
    """Soft-deletes the ticket: sets a deleted_at timestamp but does NOT remove the record.
    The ticket remains retrievable using include_deleted=True. Reversible."""
    return {"ticket_id": ticket_id, "deleted_at": "2026-01-01T00:00:00Z", "recoverable": True}


def _handle_archive_ticket(ticket_id: str) -> dict:
    """Moves the ticket to the archive store. Not returned in default list queries but
    recoverable via restore_ticket. Does NOT delete data; moves it to a separate partition."""
    return {"ticket_id": ticket_id, "archived": True, "recoverable": True}


def _handle_purge_ticket(ticket_id: str) -> dict:
    """Permanently removes the ticket from all stores. IRREVERSIBLE — the record cannot
    be recovered after purging. Use delete_ticket or archive_ticket for reversible removal."""
    return {"ticket_id": ticket_id, "purged": True, "recoverable": False}


def _handle_expire_ticket(ticket_id: str) -> dict:
    """Sets the ticket status to EXPIRED. The ticket remains fully visible and queryable in
    all normal list and search operations. No data is removed or hidden."""
    return {"ticket_id": ticket_id, "status": "EXPIRED", "data_removed": False}


def _handle_create_ticket(customer_id: str, subject: str, body: str) -> dict:
    """Creates a new support ticket for the customer."""
    return {"ticket_id": "TKT-NEW", "customer_id": customer_id, "status": "OPEN"}


def _handle_close_ticket(ticket_id: str) -> dict:
    """Closes the ticket, marking it as resolved. Ticket remains visible."""
    return {"ticket_id": ticket_id, "status": "CLOSED"}


def _handle_reopen_ticket(ticket_id: str) -> dict:
    """Reopens a previously closed ticket and sets it back to OPEN status."""
    return {"ticket_id": ticket_id, "status": "OPEN"}


# ── Family 4: account_query ───────────────────────────────────────────────────
# WHY confusable: all 5 contested names imply "retrieve matching accounts" but the
# query mechanism differs. Thin descriptions collapse to "Verb accounts / an account."
# Distinguishing axis: QUERY MECHANISM (full-text vs structured vs SQL vs external-ref vs PK).


def _handle_search_accounts(q: str, page: int = 1, per_page: int = 20) -> dict:
    """Full-text search across account name, notes, contact email, and address fields.
    Returns ranked results ordered by relevance score. Use for keyword or phrase searches."""
    return {"q": q, "results": [], "total": 0, "page": page}


def _handle_filter_accounts(
    status: str | None = None,
    account_type: str | None = None,
    region: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Structured filter by exact field values: status, account_type, and region.
    Returns all matching accounts with pagination. Use for field-value filtering, not text search."""
    return {"filters_applied": {"status": status, "account_type": account_type, "region": region}, "results": [], "total": 0}


def _handle_query_accounts(where_clause: str, params: dict | None = None) -> dict:
    """Executes a parameterized SQL-like WHERE clause against the accounts table.
    Supports AND, OR, NOT, comparison operators (=, !=, >, <), and IS NULL checks."""
    return {"where_clause": where_clause, "params": params or {}, "results": [], "total": 0}


def _handle_find_account(external_ref: str) -> dict:
    """Looks up a single account by external reference code or third-party identifier
    (NOT the internal account_id). Returns 404 if no account maps to that external reference."""
    return {"external_ref": external_ref, "account": None}


def _handle_lookup_account(account_id: str) -> dict:
    """Returns a single account record by primary key (account_id).
    Returns 404 if the account does not exist. Use find_account for external reference lookup."""
    return {"account_id": account_id, "account": None}


def _handle_create_account(name: str, account_type: str) -> dict:
    """Creates a new account with the given name and type."""
    return {"account_id": "ACC-NEW", "name": name, "account_type": account_type}


def _handle_deactivate_account(account_id: str) -> dict:
    """Deactivates the account, preventing new activity while preserving all data."""
    return {"account_id": account_id, "status": "INACTIVE"}


# ── Family 5: notification_channel ────────────────────────────────────────────
# WHY confusable: all 5 contested names imply "contact the customer" but the delivery
# CHANNEL differs. Thin descriptions collapse to "Verb the customer."
# Distinguishing axis: CHANNEL (email vs push vs SMS vs in-app vs preferred-routing).


def _handle_notify_customer(customer_id: str, subject: str, body: str) -> dict:
    """Sends an email notification to the customer's registered email address.
    Subject and body are required. Use for longer-form communications."""
    return {"customer_id": customer_id, "channel": "EMAIL", "delivered": True}


def _handle_push_update(customer_id: str, title: str, message: str) -> dict:
    """Sends a push notification to the customer's registered mobile device via APNs or FCM.
    Title and message are required. Limited to short text; no rich formatting."""
    return {"customer_id": customer_id, "channel": "PUSH", "delivered": True}


def _handle_dispatch_sms(customer_id: str, message: str) -> dict:
    """Sends an SMS text message to the customer's registered phone number.
    Message is plain text, maximum 160 characters per segment."""
    return {"customer_id": customer_id, "channel": "SMS", "delivered": True}


def _handle_message_customer(customer_id: str, message: str) -> dict:
    """Creates an in-app message in the customer's notification inbox, visible in the
    web and mobile dashboard. Does NOT send an external notification (no email, push, or SMS)."""
    return {"customer_id": customer_id, "channel": "IN_APP", "message_id": "MSG-NEW"}


def _handle_contact_customer(customer_id: str, subject: str, body: str) -> dict:
    """Routes the message via the customer's preferred contact channel as configured in their
    notification preferences (email, SMS, or push). Falls back to email if no preference is set."""
    return {"customer_id": customer_id, "channel": "PREFERRED", "resolved_channel": "EMAIL"}


def _handle_create_notification_rule(event_type: str, channel: str, template_id: str) -> dict:
    """Creates a notification rule that triggers on an event type and sends via the specified channel."""
    return {"rule_id": "NR-NEW", "event_type": event_type, "channel": channel}


def _handle_delete_notification_rule(rule_id: str) -> dict:
    """Deletes the notification rule with the given ID."""
    return {"rule_id": rule_id, "deleted": True}


# ── Family 6: order_status ────────────────────────────────────────────────────
# WHY confusable: all 4 contested names imply "advance the order" but the ACTOR,
# customer notification, and side effects differ. Thin descriptions collapse to
# "Verb an order." Distinguishing axis: WHO ACTS, WHAT NOTIFICATION FIRES, WHAT SIDE EFFECT.


def _handle_confirm_order(order_id: str) -> dict:
    """Changes order status from PENDING to CONFIRMED and sends a confirmation email to the
    customer. Customer-facing operation. Fails if order is not in PENDING status."""
    return {"order_id": order_id, "status": "CONFIRMED", "customer_email_sent": True}


def _handle_approve_order(order_id: str, approver_id: str) -> dict:
    """Marks the order as approved by the operations team. Internal workflow step only —
    does NOT send any notification to the customer. Records the approver_id for audit."""
    return {"order_id": order_id, "status": "APPROVED", "approver_id": approver_id, "customer_notified": False}


def _handle_fulfill_order(order_id: str) -> dict:
    """Changes order status to FULFILLED and triggers a warehouse pickup request for the
    physical items. Does NOT capture payment — payment must have been captured separately."""
    return {"order_id": order_id, "status": "FULFILLED", "warehouse_request_id": "WR-NEW"}


def _handle_process_order(order_id: str) -> dict:
    """Compound operation: captures payment, checks inventory availability, reserves stock,
    and updates order status. All steps execute atomically — rolls back everything if any step fails."""
    return {
        "order_id": order_id,
        "payment_captured": True,
        "inventory_reserved": True,
        "status": "PROCESSING",
    }


def _handle_submit_order(order_id: str, customer_id: str) -> dict:
    """Customer-facing action: marks a draft order as submitted for processing.
    Transitions order from DRAFT to PENDING status. First step before confirmation."""
    return {"order_id": order_id, "status": "PENDING", "customer_id": customer_id}


def _handle_void_order(order_id: str) -> dict:
    """Voids the order and releases all reserved inventory. Cannot void a fulfilled order."""
    return {"order_id": order_id, "status": "VOIDED", "inventory_released": True}


# ── Family 7: invoice_schedule ────────────────────────────────────────────────
# WHY confusable: all 4 contested names imply "prepare/defer invoice generation" but
# the TIMING and STATE differ. Thin descriptions collapse to "Verb an invoice."
# Distinguishing axis: WHEN it executes (scheduled datetime vs async-queue vs review-gate)
# and WHAT STATE the invoice enters (scheduled vs queued vs staged vs draft).


def _handle_schedule_invoice(invoice_data: dict, generate_at: str) -> dict:
    """Schedules the invoice for automatic generation at the specified future datetime (ISO 8601).
    No invoice record is created until that time. Use for recurring billing or deferred invoicing."""
    return {"schedule_id": "SCHED-NEW", "generate_at": generate_at, "status": "SCHEDULED"}


def _handle_queue_invoice(invoice_data: dict) -> dict:
    """Queues the invoice for asynchronous processing by a background worker.
    Generation happens when a worker slot is available — not at a specific time. No SLA on timing."""
    return {"queue_job_id": "JOB-NEW", "status": "QUEUED", "estimated_wait_seconds": 30}


def _handle_stage_invoice(invoice_data: dict) -> dict:
    """Creates the invoice in STAGED state for reviewer approval. The invoice is NOT sent to
    the customer until a reviewer approves and transitions it to ACTIVE. Use for pre-send review."""
    return {"invoice_id": "INV-STAGED", "status": "STAGED", "requires_approval": True}


def _handle_draft_invoice(invoice_data: dict) -> dict:
    """Creates the invoice in DRAFT state. Fully editable by the creator; not visible to customers
    or reviewers. The next step is stage_invoice (for review) or direct activation."""
    return {"invoice_id": "INV-DRAFT", "status": "DRAFT", "editable": True}


def _handle_send_invoice(invoice_id: str) -> dict:
    """Sends the invoice to the customer immediately via their preferred delivery method."""
    return {"invoice_id": invoice_id, "sent": True, "sent_at": "2026-01-01T00:00:00Z"}


def _handle_preview_invoice(invoice_id: str) -> dict:
    """Returns a rendered preview of the invoice without sending it to the customer."""
    return {"invoice_id": invoice_id, "preview_html": "<html>...</html>"}


def _handle_download_invoice(invoice_id: str) -> dict:
    """Returns the invoice as a PDF binary (base64-encoded) for download."""
    return {"invoice_id": invoice_id, "pdf_base64": "JVBERi0...", "filename": f"{invoice_id}.pdf"}


# ── Dispatch table ────────────────────────────────────────────────────────────

_HANDLERS: dict[str, object] = {
    "get_order": _handle_get_order,
    "fetch_order": _handle_fetch_order,
    "load_order": _handle_load_order,
    "retrieve_order": _handle_retrieve_order,
    "create_order": _handle_create_order,
    "cancel_order": _handle_cancel_order,
    "list_orders": _handle_list_orders,
    "update_invoice": _handle_update_invoice,
    "upsert_invoice": _handle_upsert_invoice,
    "patch_invoice": _handle_patch_invoice,
    "replace_invoice": _handle_replace_invoice,
    "amend_invoice": _handle_amend_invoice,
    "create_invoice": _handle_create_invoice,
    "delete_invoice": _handle_delete_invoice,
    "delete_ticket": _handle_delete_ticket,
    "archive_ticket": _handle_archive_ticket,
    "purge_ticket": _handle_purge_ticket,
    "expire_ticket": _handle_expire_ticket,
    "create_ticket": _handle_create_ticket,
    "close_ticket": _handle_close_ticket,
    "reopen_ticket": _handle_reopen_ticket,
    "search_accounts": _handle_search_accounts,
    "filter_accounts": _handle_filter_accounts,
    "query_accounts": _handle_query_accounts,
    "find_account": _handle_find_account,
    "lookup_account": _handle_lookup_account,
    "create_account": _handle_create_account,
    "deactivate_account": _handle_deactivate_account,
    "notify_customer": _handle_notify_customer,
    "push_update": _handle_push_update,
    "dispatch_sms": _handle_dispatch_sms,
    "message_customer": _handle_message_customer,
    "contact_customer": _handle_contact_customer,
    "create_notification_rule": _handle_create_notification_rule,
    "delete_notification_rule": _handle_delete_notification_rule,
    "confirm_order": _handle_confirm_order,
    "approve_order": _handle_approve_order,
    "fulfill_order": _handle_fulfill_order,
    "process_order": _handle_process_order,
    "submit_order": _handle_submit_order,
    "void_order": _handle_void_order,
    "schedule_invoice": _handle_schedule_invoice,
    "queue_invoice": _handle_queue_invoice,
    "stage_invoice": _handle_stage_invoice,
    "draft_invoice": _handle_draft_invoice,
    "send_invoice": _handle_send_invoice,
    "preview_invoice": _handle_preview_invoice,
    "download_invoice": _handle_download_invoice,
}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=ARM_A_DESCRIPTIONS[name],
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
        raise ValueError(f"Unknown tool: {name}")
    # Call with only the args the handler accepts
    import inspect
    sig = inspect.signature(handler)  # type: ignore[arg-type]
    valid_params = set(sig.parameters)
    has_var_kw = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if has_var_kw:
        filtered = arguments
    else:
        filtered = {k: v for k, v in arguments.items() if k in valid_params}
    result = handler(**filtered)  # type: ignore[operator]
    return [types.TextContent(type="text", text=json.dumps(result))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="p2a-internal-proxy-mirror",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())

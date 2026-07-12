from __future__ import annotations

# T18 pre-registered catalog, tasks, and gold mapping.
# 60-tool catalog in 10 families of 6 near-neighbors each.
# Oracle A/B: Arm A = empty descriptions; Arm B = discriminating oracle descriptions.
from agentgauge.tasks import Task

# ── Catalog ────────────────────────────────────────────────────────────────────

FAMILIES: dict[str, list[str]] = {
    "data_fetch": [
        "get_record",
        "fetch_record",
        "read_entry",
        "load_item",
        "retrieve_row",
        "pull_document",
    ],
    "data_write": [
        "save_record",
        "write_entry",
        "store_item",
        "persist_row",
        "commit_data",
        "insert_document",
    ],
    "data_update": [
        "update_record",
        "modify_entry",
        "patch_item",
        "edit_row",
        "revise_document",
        "amend_data",
    ],
    "data_delete": [
        "delete_record",
        "remove_entry",
        "archive_item",
        "purge_row",
        "trash_document",
        "retire_data",
    ],
    "search": [
        "search_items",
        "query_records",
        "find_entries",
        "filter_list",
        "lookup_data",
        "scan_table",
    ],
    "export": [
        "export_data",
        "send_report",
        "publish_entry",
        "forward_record",
        "stream_document",
        "transmit_file",
    ],
    "notify": [
        "notify_user",
        "alert_contact",
        "send_notification",
        "trigger_event",
        "broadcast_message",
        "ping_service",
    ],
    "validate": [
        "validate_schema",
        "check_permission",
        "verify_token",
        "validate_format",
        "check_quota",
        "verify_signature",
    ],
    "schedule": [
        "schedule_task",
        "queue_job",
        "defer_action",
        "plan_event",
        "book_slot",
        "register_run",
    ],
    "analyze": [
        "analyze_data",
        "compute_metric",
        "calculate_stats",
        "aggregate_records",
        "summarize_entries",
        "evaluate_expression",
    ],
}

# ── Arm A descriptions (all empty) ────────────────────────────────────────────

ARM_A_DESCRIPTIONS: dict[str, str] = {tool: "" for tools in FAMILIES.values() for tool in tools}

# ── Arm B descriptions (oracle — each distinguishes within-family) ─────────────

ARM_B_DESCRIPTIONS: dict[str, str] = {
    # F1: data_fetch — source dimension
    "get_record": (
        "Retrieve a single database record by its primary key. Use for direct key-based DB lookups."
    ),
    "fetch_record": (
        "Download a record from a remote REST API by endpoint URL. "
        "Use for HTTP-based retrieval from external services."
    ),
    "read_entry": (
        "Read an entry from a configuration or text file at a local filesystem path. "
        "Use for file-based data."
    ),
    "load_item": (
        "Load an item from the in-memory cache or session store. "
        "Use for fast reads without hitting the database."
    ),
    "retrieve_row": (
        "Retrieve a row from a SQL table using a WHERE clause predicate. "
        "Use for relational query-based reads."
    ),
    "pull_document": (
        "Pull a document from a NoSQL document store (e.g., MongoDB). "
        "Use for document-collection reads."
    ),
    # F2: data_write — destination/semantics dimension
    "save_record": (
        "Save a database record using upsert semantics — inserts if new, "
        "updates if existing key found."
    ),
    "write_entry": (
        "Write a structured log entry to the application log file. "
        "Use for audit trails and event logging."
    ),
    "store_item": (
        "Store an item in the in-memory cache with a configurable TTL. "
        "Use for ephemeral fast-access data."
    ),
    "persist_row": (
        "Persist a new row to a SQL table via an INSERT statement. "
        "Use only for net-new rows — fails if row exists."
    ),
    "commit_data": (
        "Commit a pending transaction batch to the database, flushing all staged writes atomically."
    ),
    "insert_document": (
        "Insert a new document into a NoSQL collection. "
        "Fails if a document with the same _id already exists."
    ),
    # F3: data_update — scope dimension
    "update_record": (
        "Replace all fields of a database record with the new payload. "
        "All existing fields are overwritten."
    ),
    "modify_entry": (
        "Modify a single named field in an existing log entry, leaving all other fields unchanged."
    ),
    "patch_item": (
        "Apply a partial update to a cached item — merges new fields into the existing object "
        "without replacing it."
    ),
    "edit_row": (
        "Edit one or more columns in a SQL table row using an UPDATE SET statement. "
        "Only named columns change."
    ),
    "revise_document": (
        "Revise a subset of fields in a NoSQL document using a partial update "
        "(does not replace the full document)."
    ),
    "amend_data": (
        "Amend the most recently committed transaction by undoing it and re-applying "
        "with the corrected values."
    ),
    # F4: data_delete — permanence/recoverability dimension
    "delete_record": (
        "Hard-delete a database record permanently. "
        "The record is immediately gone and not recoverable."
    ),
    "remove_entry": (
        "Remove an entry from a queue or event stream (soft delete — entry is hidden from queries "
        "but retained for compliance)."
    ),
    "archive_item": (
        "Move a cache item to cold storage. The item remains accessible via a restore operation "
        "but is removed from hot storage."
    ),
    "purge_row": (
        "Permanently purge a SQL row and all child rows via CASCADE DELETE. Cannot be undone."
    ),
    "trash_document": (
        "Move a NoSQL document to the trash collection. "
        "Restorable within 30 days; auto-deleted after."
    ),
    "retire_data": (
        "Mark data records as retired. Records become read-only and are retained indefinitely "
        "for audit; never physically deleted."
    ),
    # F5: search — query mechanism dimension
    "search_items": (
        "Full-text search across item descriptions and content using an inverted index. "
        "Returns ranked results by relevance."
    ),
    "query_records": (
        "Execute a structured query against records using field-value predicates "
        "(equality, range, IN). Returns exact matches."
    ),
    "find_entries": (
        "Find entries by exact unique identifier match (primary key or UUID). "
        "Returns at most one result."
    ),
    "filter_list": (
        "Filter an in-memory list by applying a predicate function to each element. "
        "Use for client-side filtering of already-loaded data."
    ),
    "lookup_data": (
        "Look up a value in a key-value store by its exact key. "
        "Returns the stored value or null if absent."
    ),
    "scan_table": (
        "Perform a full sequential scan of a SQL table without using any index. "
        "Use when no indexed column is available."
    ),
    # F6: export — destination/format dimension
    "export_data": (
        "Export data to a CSV or JSON file on the local filesystem. "
        "Use for offline analysis or file-based reporting."
    ),
    "send_report": (
        "Send a formatted report to a user via email. "
        "Use for automated email delivery of summaries."
    ),
    "publish_entry": (
        "Publish an entry to a message queue or pub/sub topic. "
        "Use for asynchronous downstream consumption."
    ),
    "forward_record": (
        "Forward a record to an external webhook URL via HTTP POST. "
        "Use for real-time push to third-party systems."
    ),
    "stream_document": (
        "Stream a document in chunks to a WebSocket client. Use for real-time incremental delivery."
    ),
    "transmit_file": (
        "Transmit a file to a remote SFTP or FTP server. "
        "Use for file-protocol transfers to legacy systems."
    ),
    # F7: notify — channel/trigger dimension
    "notify_user": (
        "Send an in-app notification to a specific user by user ID. "
        "Appears in the user's in-app notification inbox."
    ),
    "alert_contact": (
        "Send an SMS alert to a contact's registered phone number. "
        "Use for urgent out-of-band text messages."
    ),
    "send_notification": (
        "Send a push notification to a user's mobile device via the push gateway. "
        "Use for mobile app alerts."
    ),
    "trigger_event": (
        "Emit a named event into the event-sourcing log. "
        "Use to signal state transitions to downstream event handlers."
    ),
    "broadcast_message": (
        "Broadcast a message to all active subscribers of a named channel simultaneously."
    ),
    "ping_service": (
        "Ping a downstream service's health check endpoint and return its availability status."
    ),
    # F8: validate — what is checked dimension
    "validate_schema": (
        "Validate that a JSON object conforms to a registered JSON Schema definition. "
        "Returns validation errors if any."
    ),
    "check_permission": (
        "Check whether a user has a named permission in the RBAC policy store. Returns true/false."
    ),
    "verify_token": (
        "Verify that an OAuth2 or JWT access token is syntactically valid and has not expired."
    ),
    "validate_format": (
        "Validate that a string value matches a required format pattern (regular expression). "
        "Returns match status."
    ),
    "check_quota": (
        "Check whether a resource quota limit has been reached for an account. "
        "Returns current usage vs limit."
    ),
    "verify_signature": (
        "Verify a cryptographic HMAC or RSA signature against a public key or shared secret."
    ),
    # F9: schedule — timing semantics dimension
    "schedule_task": (
        "Schedule a recurring task using a cron expression (e.g., '0 2 * * 1-5'). "
        "Runs repeatedly on schedule."
    ),
    "queue_job": (
        "Add a job to the async task queue for immediate background processing. "
        "Starts as soon as a worker is free."
    ),
    "defer_action": (
        "Defer an action to run after a specified delay in seconds. "
        "Runs once, after the delay elapses."
    ),
    "plan_event": (
        "Plan a calendar event with a start datetime and end datetime. "
        "Visible on the team calendar."
    ),
    "book_slot": (
        "Reserve a specific time slot in an availability calendar. "
        "Prevents double-booking of that slot."
    ),
    "register_run": (
        "Register a one-time future run at an exact UNIX timestamp. "
        "Runs once at that precise moment."
    ),
    # F10: analyze — computation type dimension
    "analyze_data": (
        "Run a predefined analytics pipeline on a dataset and return structured insight objects."
    ),
    "compute_metric": (
        "Compute a single named business metric (e.g., churn_rate, MRR) from raw event data."
    ),
    "calculate_stats": (
        "Calculate descriptive statistics (mean, median, stddev, min, max) for a numeric column."
    ),
    "aggregate_records": (
        "Aggregate records by a grouping field and apply a reduction function "
        "(sum, count, avg) per group."
    ),
    "summarize_entries": (
        "Summarize a set of text entries into a concise human-readable digest "
        "using NLP compression."
    ),
    "evaluate_expression": (
        "Evaluate a mathematical or logical expression string and return the computed numeric result."
    ),
}

# ── Tasks (40 pre-registered, 4 per family) ────────────────────────────────────
# Anti-tautology: task descriptions do NOT contain gold tool names or oracle description tokens.

TASKS: list[Task] = [
    # F1: data_fetch
    Task(
        "get_record",
        "The inventory service needs the warehouse product with item_id=9812 from the primary database.",
    ),
    Task(
        "fetch_record",
        "Retrieve order status for #TX-991 by calling the fulfilment partner's external HTTP endpoint.",
    ),
    Task(
        "read_entry",
        "The startup routine needs the server's settings from disk at /etc/app/settings.ini.",
    ),
    Task(
        "load_item",
        "The checkout flow needs the cart contents for the active session without touching the database.",
    ),
    # F2: data_write
    Task(
        "save_record",
        "Upsert a customer profile: create it if new, overwrite it if found by key.",
    ),
    Task(
        "write_entry",
        "Record the user login event in the application audit trail.",
    ),
    Task(
        "store_item",
        "Hold the API response for this user in fast temporary storage for 5 minutes.",
    ),
    Task(
        "persist_row",
        "Add a new invoice line item to the orders table as a brand-new row.",
    ),
    # F3: data_update
    Task(
        "update_record",
        "Overwrite every field of the customer record for account_id=4492 with the new payload.",
    ),
    Task(
        "modify_entry",
        "Correct only the severity field in the most recent log line, leaving all other fields intact.",
    ),
    Task(
        "patch_item",
        "Update only the TTL on the cached session object without replacing the session payload.",
    ),
    Task(
        "edit_row",
        "Change the price and stock columns for product row 8812 in the catalog table.",
    ),
    # F4: data_delete
    Task(
        "delete_record",
        "Permanently erase the account for user_id=2241 — it must not be recoverable.",
    ),
    Task(
        "remove_entry",
        "Hide the log event from the active stream but keep it for compliance auditing.",
    ),
    Task(
        "archive_item",
        "Transfer the infrequently-accessed session file to cold storage (still restorable later).",
    ),
    Task(
        "purge_row",
        "Remove the order row and all its child line-item rows from the SQL tables — no recovery possible.",
    ),
    # F5: search
    Task(
        "search_items",
        "Find all product listings whose text mentions 'organic' or 'natural' anywhere.",
    ),
    Task(
        "query_records",
        "Get all invoices where status='overdue' AND amount > 500.",
    ),
    Task(
        "find_entries",
        "Locate the session whose identifier is exactly 'sess-abc-8871'.",
    ),
    Task(
        "filter_list",
        "From the in-memory product list already loaded, keep only items with price below 20.",
    ),
    # F6: export
    Task(
        "export_data",
        "Save the quarterly sales data to a spreadsheet file for offline analysis.",
    ),
    Task(
        "send_report",
        "Email the weekly summary report to the finance team.",
    ),
    Task(
        "publish_entry",
        "Put the new order event on the queue so downstream services can process it.",
    ),
    Task(
        "forward_record",
        "Push the payment confirmation to the external payment provider's endpoint via HTTP.",
    ),
    # F7: notify
    Task(
        "notify_user",
        "Show an alert inside the application interface to user_id=1002.",
    ),
    Task(
        "alert_contact",
        "Dispatch an urgent text message to the on-call engineer's mobile number.",
    ),
    Task(
        "send_notification",
        "Push a pop-up reminder to the user's phone for their upcoming appointment.",
    ),
    Task(
        "trigger_event",
        "Fire the 'order_shipped' signal into the event log so handlers can react.",
    ),
    # F8: validate
    Task(
        "validate_schema",
        "Confirm the incoming request body matches the required data contract structure.",
    ),
    Task(
        "check_permission",
        "Verify whether user_id=5501 is allowed to perform the 'report:export' action.",
    ),
    Task(
        "verify_token",
        "Confirm the credential in the Authorization header has not expired.",
    ),
    Task(
        "validate_format",
        "Ensure the submitted phone number string matches the E.164 pattern.",
    ),
    # F9: schedule
    Task(
        "schedule_task",
        "Configure a nightly cleanup routine to run at 2 AM every weekday using a cron expression.",
    ),
    Task(
        "queue_job",
        "Submit the image-resizing job for immediate background processing.",
    ),
    Task(
        "defer_action",
        "Delay the email send by 10 minutes so the user can cancel if needed.",
    ),
    Task(
        # Fixed 2026-06-14: original wording ("Reserve the ... slot") described book_slot's
        # distinction, leaving gold=plan_event unresolvable even with the oracle (Ty-style
        # mislabel surfaced by FRONTIER-T18 STEP 2). Reworded to plan_event's actual niche — a
        # visible, start/end-bounded shared-calendar entry — without book_slot tokens
        # (reserve/slot) or plan_event's oracle first token ("plan"). Pre-registration intact.
        "plan_event",
        "Add the Thursday team sync to the shared calendar as a 3:00-4:00 PM entry everyone can see.",
    ),
    # F10: analyze
    Task(
        "analyze_data",
        "Run the end-of-quarter analytics pipeline on the transactions dataset.",
    ),
    Task(
        "compute_metric",
        "Calculate the churn rate for the paid tier over the last 30 days.",
    ),
    Task(
        "calculate_stats",
        "Get the mean, median, and standard deviation for the response_time_ms column.",
    ),
    Task(
        "aggregate_records",
        "Group the sales records by region and sum the revenue in each group.",
    ),
]

# ── Family map ─────────────────────────────────────────────────────────────────

FAMILY_MAP: dict[str, str] = {tool: family for family, tools in FAMILIES.items() for tool in tools}

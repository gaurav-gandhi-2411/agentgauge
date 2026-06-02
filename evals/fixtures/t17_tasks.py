from __future__ import annotations

from agentgauge.tasks import Task

# T17 pre-registered tasks and cluster map.
# 32 tasks, 4 per cluster, 2 per tool.
# Task descriptions are phrased by user intent — NOT echoing oracle description vocabulary.

TASKS: list[Task] = [
    # C1: search_documents / query_records
    Task("search_documents", "Find all documents that mention the word 'overdue'"),
    Task("search_documents", "Locate entries whose content includes the phrase 'budget exceeded'"),
    Task("query_records", "Get all orders where the status field is set to 'pending'"),
    Task("query_records", "Retrieve customers from the enterprise tier"),
    # C2: send_message / dispatch_event
    Task("send_message", "Tell user #102 that their subscription renewal went through"),
    Task("send_message", "Let the customer with ID 55 know their refund has been approved"),
    Task("dispatch_event", "Trigger the fulfillment pipeline after a new order is placed"),
    Task("dispatch_event", "Signal downstream services that a batch upload has finished"),
    # C3: list_items / enumerate_all
    Task("list_items", "Show me the third page of results with 10 items per page"),
    Task("list_items", "Get items 21 through 40 from the product catalog"),
    Task("enumerate_all", "Retrieve every country code available for the address form dropdown"),
    Task("enumerate_all", "Pull the complete list of supported currencies for the settings page"),
    # C4: create_record / register_user
    Task("create_record", "Add a new product to the catalog with its price and SKU"),
    Task("create_record", "Store a new support ticket with a subject and description"),
    Task("register_user", "Set up an account for a new team member joining the platform"),
    Task("register_user", "Onboard a new customer who just signed up on the website"),
    # C5: update_record / patch_fields
    Task("update_record", "Replace the full configuration of project #3 with a new complete spec"),
    Task("update_record", "Overwrite the product record with the fully corrected version"),
    Task("patch_fields", "Change only the shipping address on order #882 without touching other fields"),
    Task("patch_fields", "Update just the expiry date on a credential, leaving everything else alone"),
    # C6: delete_record / archive_record
    Task("delete_record", "Permanently erase a user account that was created by mistake"),
    Task("delete_record", "Remove a duplicate product entry so it can never appear again"),
    Task("archive_record", "Take an old campaign offline but keep it accessible for reporting"),
    Task("archive_record", "Disable a user's access while preserving their history in the system"),
    # C7: get_record / fetch_latest
    Task("get_record", "Pull up the order whose ID is ord-77231"),
    Task("get_record", "Look up the user profile with identifier usr-00991"),
    Task("fetch_latest", "Get whichever log entry was written most recently"),
    Task("fetch_latest", "Show me the last notification that came in"),
    # C8: export_report / extract_data
    Task("export_report", "Produce a PDF summary of last month's invoices for the accounting team"),
    Task("export_report", "Generate a CSV file of all active users for an external audit"),
    Task("extract_data", "Pull the raw transaction records as structured data for my ETL script"),
    Task("extract_data", "Get the underlying data so I can run my own aggregations on it"),
]

CLUSTER_MAP: dict[str, str] = {
    "search_documents": "C1_search_query",
    "query_records": "C1_search_query",
    "send_message": "C2_send_dispatch",
    "dispatch_event": "C2_send_dispatch",
    "list_items": "C3_list_enumerate",
    "enumerate_all": "C3_list_enumerate",
    "create_record": "C4_create_register",
    "register_user": "C4_create_register",
    "update_record": "C5_update_patch",
    "patch_fields": "C5_update_patch",
    "delete_record": "C6_delete_archive",
    "archive_record": "C6_delete_archive",
    "get_record": "C7_get_fetch",
    "fetch_latest": "C7_get_fetch",
    "export_report": "C8_export_extract",
    "extract_data": "C8_export_extract",
}

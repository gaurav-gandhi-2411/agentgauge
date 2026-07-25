from __future__ import annotations

# Twilio Messaging/Voice call-correctness fixture — pre-registered tasks and gold constraints.
#
# Corpus-expansion pilot (v2_4_corpus): a real-domain sibling to the synthetic
# call_constraints_v2 fixture (evals/fixtures/ty2_tasks.py) and the other
# v2_4_corpus real-API fixtures, modeled on Twilio's real Programmable
# Messaging/Voice REST API instead of an invented domain.
#
# 4 tools, all constrained — 5 tasks each = 20 tasks.
# Constraint mix (2 tools per type):
#   FORMAT : send_sms (to, E.164 phone number shape)
#            lookup_phone_number (country_code, ISO 3166-1 alpha-2 shape)
#   ENUM   : make_call (method, HTTP method Twilio uses to request the TwiML
#            webhook — "GET"/"POST")
#            set_call_status_callback (status_event, call lifecycle stage —
#            "initiated"/"ringing"/"answered"/"completed")
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only. They must NOT
# contain the literal enum value (e.g. "GET", "ringing") or the literal format
# shape (e.g. an actual E.164 digit string or a two-letter country-code token)
# that the agent is meant to construct. Referencing a real city/company whose
# country is merely implied is fine — the literal answer token itself must not
# appear. The agent must derive the correct value from the tool's
# SCHEMA/description (fixed variant) or fail correctly (bad variant), not from
# the task text.
#
# See twilio_messaging_NOTES.md for provenance of the real Twilio API fields used.
from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

TASKS: list[Task] = [
    # send_sms (format constraint on `to`, E.164 shape) — 5 tasks
    Task(
        "send_sms",
        "Send a text message to our on-call engineer letting them know the production "
        "database failover completed successfully.",
    ),
    Task(
        "send_sms",
        "Text the customer who just abandoned their cart a reminder that their items "
        "are still waiting, along with a 10% discount code.",
    ),
    Task(
        "send_sms",
        "Send an SMS to the delivery driver confirming the package was left at the front porch.",
    ),
    Task(
        "send_sms",
        "Message our support lead in the London office to let them know the incident "
        "bridge is starting in five minutes.",
    ),
    Task(
        "send_sms",
        "Send a one-time passcode via text to the user who just requested a login on a new device.",
    ),
    # lookup_phone_number (format constraint on `country_code`, ISO alpha-2 shape) — 5 tasks
    Task(
        "lookup_phone_number",
        "A new supplier in Tokyo gave us their phone number in local format — check "
        "it's a valid line before adding them to the vendor directory.",
    ),
    Task(
        "lookup_phone_number",
        "Our onboarding contact in Berlin only gave us the local-format version of "
        "their number — verify it before we save it to their profile.",
    ),
    Task(
        "lookup_phone_number",
        "The reseller's contact in Toronto shared a phone number without the country "
        "prefix — confirm it's a legitimate mobile line.",
    ),
    Task(
        "lookup_phone_number",
        "Our distributor in Sydney gave us their number in national format — validate "
        "it before we add it to the CRM.",
    ),
    Task(
        "lookup_phone_number",
        "The support rep working out of Sao Paulo shared her number in local format — "
        "confirm the line type before we register it.",
    ),
    # make_call (enum constraint on `method`) — 5 tasks
    Task(
        "make_call",
        "Place a call to the customer and have Twilio simply fetch the static, "
        "read-only TwiML script we host on our CDN — no server-side data processing "
        "is involved.",
    ),
    Task(
        "make_call",
        "Call the loan applicant and have Twilio submit the full set of call "
        "parameters as form-encoded data to our backend so it can log every detail "
        "server-side.",
    ),
    Task(
        "make_call",
        "Dial our support hotline and pull the instructions from the plain, "
        "unchanging XML file sitting in our public static-assets bucket.",
    ),
    Task(
        "make_call",
        "Ring the vendor's line and have Twilio hand off the complete call payload to "
        "our webhook so our server can pick the right greeting based on caller ID.",
    ),
    Task(
        "make_call",
        "Call the survey participant and load the lightweight, cacheable TwiML "
        "snippet from our static hosting — our endpoint never needs to parse a "
        "request body.",
    ),
    # set_call_status_callback (enum constraint on `status_event`) — 5 tasks
    Task(
        "set_call_status_callback",
        "Configure the webhook to fire the instant an outbound call is first placed "
        "by our dialer, before the recipient's phone even starts alerting them.",
    ),
    Task(
        "set_call_status_callback",
        "Notify our webhook the instant the recipient's device starts alerting them "
        "to an incoming call, but before they've picked up.",
    ),
    Task(
        "set_call_status_callback",
        "Trigger the callback the moment the person on the other end actually picks "
        "up and starts talking.",
    ),
    Task(
        "set_call_status_callback",
        "Fire the callback once the call has fully wrapped up and the line has been "
        "disconnected on both ends.",
    ),
    Task(
        "set_call_status_callback",
        "Have our webhook alert us the moment the callee's line starts alerting them "
        "but they haven't picked up yet, so we can start a countdown timer for a "
        "no-answer failover.",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
# Format tasks: no gold value — any value matching the pattern counts.
# Enum tasks: gold_value is the specific expected enum member.
TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # send_sms — format: E.164 phone number (leading '+', non-zero first digit, 7-15 digits)
    (
        "send_sms",
        "Send a text message to our on-call engineer letting them know the production "
        "database failover completed successfully.",
    ): [Constraint("to", "format", pattern=r"\+[1-9]\d{6,14}")],
    (
        "send_sms",
        "Text the customer who just abandoned their cart a reminder that their items "
        "are still waiting, along with a 10% discount code.",
    ): [Constraint("to", "format", pattern=r"\+[1-9]\d{6,14}")],
    (
        "send_sms",
        "Send an SMS to the delivery driver confirming the package was left at the front porch.",
    ): [Constraint("to", "format", pattern=r"\+[1-9]\d{6,14}")],
    (
        "send_sms",
        "Message our support lead in the London office to let them know the incident "
        "bridge is starting in five minutes.",
    ): [Constraint("to", "format", pattern=r"\+[1-9]\d{6,14}")],
    (
        "send_sms",
        "Send a one-time passcode via text to the user who just requested a login on a new device.",
    ): [Constraint("to", "format", pattern=r"\+[1-9]\d{6,14}")],
    # lookup_phone_number — format: ISO 3166-1 alpha-2 country code (simplified, letters only)
    (
        "lookup_phone_number",
        "A new supplier in Tokyo gave us their phone number in local format — check "
        "it's a valid line before adding them to the vendor directory.",
    ): [Constraint("country_code", "format", pattern=r"[A-Z]{2}")],
    (
        "lookup_phone_number",
        "Our onboarding contact in Berlin only gave us the local-format version of "
        "their number — verify it before we save it to their profile.",
    ): [Constraint("country_code", "format", pattern=r"[A-Z]{2}")],
    (
        "lookup_phone_number",
        "The reseller's contact in Toronto shared a phone number without the country "
        "prefix — confirm it's a legitimate mobile line.",
    ): [Constraint("country_code", "format", pattern=r"[A-Z]{2}")],
    (
        "lookup_phone_number",
        "Our distributor in Sydney gave us their number in national format — validate "
        "it before we add it to the CRM.",
    ): [Constraint("country_code", "format", pattern=r"[A-Z]{2}")],
    (
        "lookup_phone_number",
        "The support rep working out of Sao Paulo shared her number in local format — "
        "confirm the line type before we register it.",
    ): [Constraint("country_code", "format", pattern=r"[A-Z]{2}")],
    # make_call — enum: method ("GET"/"POST")
    (
        "make_call",
        "Place a call to the customer and have Twilio simply fetch the static, "
        "read-only TwiML script we host on our CDN — no server-side data processing "
        "is involved.",
    ): [Constraint("method", "enum", gold_value="GET")],
    (
        "make_call",
        "Call the loan applicant and have Twilio submit the full set of call "
        "parameters as form-encoded data to our backend so it can log every detail "
        "server-side.",
    ): [Constraint("method", "enum", gold_value="POST")],
    (
        "make_call",
        "Dial our support hotline and pull the instructions from the plain, "
        "unchanging XML file sitting in our public static-assets bucket.",
    ): [Constraint("method", "enum", gold_value="GET")],
    (
        "make_call",
        "Ring the vendor's line and have Twilio hand off the complete call payload to "
        "our webhook so our server can pick the right greeting based on caller ID.",
    ): [Constraint("method", "enum", gold_value="POST")],
    (
        "make_call",
        "Call the survey participant and load the lightweight, cacheable TwiML "
        "snippet from our static hosting — our endpoint never needs to parse a "
        "request body.",
    ): [Constraint("method", "enum", gold_value="GET")],
    # set_call_status_callback — enum: status_event
    (
        "set_call_status_callback",
        "Configure the webhook to fire the instant an outbound call is first placed "
        "by our dialer, before the recipient's phone even starts alerting them.",
    ): [Constraint("status_event", "enum", gold_value="initiated")],
    (
        "set_call_status_callback",
        "Notify our webhook the instant the recipient's device starts alerting them "
        "to an incoming call, but before they've picked up.",
    ): [Constraint("status_event", "enum", gold_value="ringing")],
    (
        "set_call_status_callback",
        "Trigger the callback the moment the person on the other end actually picks "
        "up and starts talking.",
    ): [Constraint("status_event", "enum", gold_value="answered")],
    (
        "set_call_status_callback",
        "Fire the callback once the call has fully wrapped up and the line has been "
        "disconnected on both ends.",
    ): [Constraint("status_event", "enum", gold_value="completed")],
    (
        "set_call_status_callback",
        "Have our webhook alert us the moment the callee's line starts alerting them "
        "but they haven't picked up yet, so we can start a countdown timer for a "
        "no-answer failover.",
    ): [Constraint("status_event", "enum", gold_value="ringing")],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    ["send_sms", "lookup_phone_number", "make_call", "set_call_status_callback"]
)
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["send_sms", "lookup_phone_number"])
ENUM_TOOL_NAMES: frozenset[str] = frozenset(["make_call", "set_call_status_callback"])

# Enum gold values referenced in tasks (for inferability tests)
ENUM_GOLD_VALUES: list[str] = [
    "GET",
    "POST",
    "initiated",
    "ringing",
    "answered",
    "completed",
]
# Format patterns (for inferability tests — these should not appear verbatim in task text)
FORMAT_PATTERNS_SAMPLE: list[str] = [
    r"\+[1-9]\d{6,14}",
    r"[A-Z]{2}",
    "+14155552671",
    "US",
]

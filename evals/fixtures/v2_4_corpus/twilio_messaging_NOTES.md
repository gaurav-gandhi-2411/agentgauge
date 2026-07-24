# Twilio Messaging/Voice fixture — provenance notes

## Real Twilio API operations modeled

Four tools, each a simplified wrapper around a real Twilio REST API operation:

| Tool                        | Modeled on real Twilio REST API operation |
|------------------------------|--------------------------------------------|
| `send_sms`                   | `POST /2010-04-01/Accounts/{AccountSid}/Messages.json` (Programmable Messaging). Real fields `To`, `From`, `Body`, `MediaUrl` — simplified to lower_snake_case (`to`, `from_number`, `body`, `media_url`) and a single `MediaUrl` value instead of the real API's repeatable field. |
| `lookup_phone_number`         | `GET /v2/PhoneNumbers/{PhoneNumber}` (Lookup API v2). Real query params `CountryCode` and `Fields` (a comma-separated list of data packages such as `line_type_intelligence`). |
| `make_call`                   | `POST /2010-04-01/Accounts/{AccountSid}/Calls.json` (Programmable Voice). Real fields `To`, `From`, `Url`, `Method` (the HTTP method Twilio uses to request `Url`; real default is `POST`, real alternative is `GET`). |
| `set_call_status_callback`    | Not a standalone real endpoint — modeled on the real `StatusCallback` and `StatusCallbackEvent` parameters that Twilio's Calls resource accepts (at call creation or update). Presented here as its own conceptual tool for a clean single-purpose fixture, rather than folded into `make_call`'s already-large parameter set. |

## Constraint provenance

- **`to` format** (`send_sms`, also present but untested on `make_call`): Twilio's
  Messaging/Voice APIs require phone numbers in E.164 format — a leading `+`,
  followed by the country code and subscriber number, digits only, no spaces
  or punctuation (e.g. `+14155552671`). The regex used here
  (`\+[1-9]\d{6,14}`) is a simplification of the real E.164 spec (which allows
  up to 15 digits total and does not itself forbid all invalid country-code
  prefixes) — it captures the leading-`+`/non-zero-first-digit/digit-run
  shape, not the full ITU numbering-plan validity rules.
- **`country_code` format** (`lookup_phone_number`): Twilio's Lookup API v2
  accepts an optional `CountryCode` query parameter — the ISO 3166-1 alpha-2
  country code (e.g. `US`, `GB`) — used when `phone_number` is supplied in
  national/local format rather than full E.164, so Twilio knows which
  country's numbering plan applies. The regex used here (`[A-Z]{2}`) is a
  simplified shape check (two uppercase letters); it does not validate
  against the real, finite list of ISO 3166-1 alpha-2 codes.
- **`method` enum** (`make_call`): Twilio's Calls resource accepts a `Method`
  parameter controlling the HTTP method used to request the `Url` webhook,
  with two real, documented values: `GET` and `POST` (default `POST`). `GET`
  is the natural choice for a static/unchanging TwiML document; `POST` is
  the natural choice when the receiving endpoint needs the call's parameters
  submitted as form-encoded data.
- **`status_event` enum** (`set_call_status_callback`): Twilio's real
  `StatusCallbackEvent` parameter accepts one or more of `initiated`,
  `ringing`, `answered`, `completed` describing the call lifecycle stage that
  should trigger the callback. The real API accepts an array of these values
  in a single request; this fixture simplifies it to a single value per call
  for a clean per-task gold value, following the same array-to-scalar
  simplification pattern used elsewhere in this corpus (e.g. the GitHub
  Issues fixture's `add_assignee`/`add_label`).

## Honesty about sourcing

This fixture was authored from the author's existing knowledge of Twilio's
Programmable Messaging, Programmable Voice, and Lookup REST APIs — there was
no live internet access available to verify field names, parameter defaults,
or enum values against Twilio's current published API reference at authoring
time. All descriptions and schema shapes are the author's own paraphrase, not
copied verbatim from any Twilio document. The specific field names (`To`,
`From`, `Body`, `MediaUrl`, `CountryCode`, `Fields`, `Url`, `Method`,
`StatusCallback`, `StatusCallbackEvent`), the E.164 phone number format, and
the `Method` (`GET`/`POST`) and `StatusCallbackEvent`
(`initiated`/`ringing`/`answered`/`completed`) enum values are believed
accurate to the real Twilio product as of recent memory, but were not
re-verified against a live source before committing. If a byte-exact match to
Twilio's current API reference matters for downstream use, re-verify against
`https://www.twilio.com/docs/messaging/api` and
`https://www.twilio.com/docs/voice/api` before relying on this fixture for
anything beyond fixture-internal self-consistency (which is fully verified —
see the import/lint checks in the corresponding commit).

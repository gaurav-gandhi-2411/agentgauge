# Google Calendar gold-constraint fixture — notes

Pilot fixture pair for the v2.4 corpus-expansion effort (Task 4). Domain: Google
Calendar API v3. Mirrors the structure and rigor of
`examples/call_constraints_v2_server.py` / `_fixed.py` and
`evals/fixtures/ty2_tasks.py`.

## Real Google Calendar API operations modeled

| Tool (this fixture)             | Real Calendar API v3 basis                                                  | Constraint type |
|----------------------------------|-------------------------------------------------------------------------------|-----------------|
| `create_event`                   | `events.insert` — `start.dateTime` / `end.dateTime` (RFC 3339), `visibility`   | FORMAT (`start_time`) |
| `create_calendar`                 | `calendars.insert` — `summary`, `timeZone` (IANA Time Zone Database name)      | FORMAT (`time_zone`) |
| `update_event_response_status`   | `events.patch` on `attendees[].responseStatus`                                 | ENUM (`response_status`) |
| `set_event_recurrence`           | `events.recurrence` — RFC 5545 `RRULE:FREQ=...` line                          | ENUM (`frequency`) |

All 4 tools have a genuine constrained parameter, so all 4 are "hard" tools
(no inert/unconstrained tools), matching the v2 fixture's design of using only
constrained tools.

Constraint mix is 2 FORMAT / 2 ENUM, matching the "2 tools per constraint
type" design of `evals/fixtures/ty2_tasks.py`.

## Field naming

Tool parameter names in this fixture (`start_time`, `time_zone`,
`response_status`, `frequency`, `calendar_id`, `event_id`, `attendee_email`)
are snake_case, following the convention used elsewhere in this repo's
constraint fixtures (`sensor_id`, `channel_ref`, etc.) and consistent with how
an MCP tool wrapper typically re-cases a REST API's camelCase JSON keys
(`timeZone`, `responseStatus`) for a tool-call interface. These map 1:1 to the
real Calendar API v3 field *semantics* described above, but the wrapper-layer
paraphrase is not casing-only: the real API nests `dateTime`/`timeZone` inside
a `start`/`end` object (`{"start": {"dateTime": "...", "timeZone": "..."}}`),
which this fixture additionally flattens to standalone `start_time`/
`time_zone` string fields for a simpler tool-call interface — a deliberate
structural simplification on top of the casing convention, not an invented
field.

## Accuracy and honesty about sourcing

This agent does not have live internet access. The tool semantics above
(field names, enum values, RFC 3339 datetime format, IANA time zone identifier
format, RFC 5545 `RRULE` `FREQ` values) are drawn from the author's trained
knowledge of the public Google Calendar API v3 and are believed accurate, but
they are the author's own paraphrase and were not verified against a live
`https://developers.google.com/calendar/api` fetch or the API's OpenAPI
discovery document at the time of writing. In particular:

- `response_status` enum values (`accepted`, `declined`, `tentative`,
  `needsAction`) and `visibility` enum values (`default`, `public`,
  `private`) are recalled directly from the `Events` resource schema.
- The real API does not expose `update_event_response_status` or
  `set_event_recurrence` as standalone endpoints — both are modeled here as
  simplified single-purpose wrappers around fields that are actually part of
  the broader `events.patch` / `events.insert` request bodies
  (`attendees[].responseStatus` and `recurrence[]` respectively). This
  simplification is intentional (matches the fixture's need for one tool per
  constrained parameter) and does not change the real field semantics being
  tested.
- `RRULE:FREQ` only supports `SECONDLY`/`MINUTELY`/`HOURLY`/`DAILY`/`WEEKLY`/
  `MONTHLY`/`YEARLY` per RFC 5545; this fixture restricts `frequency` to the
  four values named in the task brief (`DAILY`/`WEEKLY`/`MONTHLY`/`YEARLY`),
  omitting the three sub-daily values that are real but not useful for a
  calendar-event recurrence tool.

## Format-constraint checking discipline

Consistent with `evals/fixtures/ty2_tasks.py`'s `register_channel` /
`log_fault` tools: FORMAT-constrained tasks (`create_event.start_time`,
`create_calendar.time_zone`) check only that the constructed argument matches
the expected *syntax* (RFC 3339 datetime shape, `Area/Location` time-zone
shape). They do not check that the value semantically matches the task's
natural-language time or city reference (e.g. that "next Tuesday at 2pm
Pacific" resolves to the *correct* UTC offset, or that "our New York office"
resolves to exactly `America/New_York` rather than another valid IANA zone).
This is a real, stated limitation of the format-constraint check, not hidden.

# Slack messaging fixture — provenance notes

## Real Slack Web API operations modeled

Corpus-expansion entry (v2_4_corpus, Task 4): a real-domain sibling to
`github_issues_fixture.py` / `stripe_payments_fixture.py`, modeled on Slack's
real Web API instead of an invented domain. Four tools, each a simplified
wrapper around a real Slack Web API operation:

| Tool                 | Modeled on real Slack Web API operation                              |
|-----------------------|------------------------------------------------------------------------|
| `post_message`        | `chat.postMessage` — `channel`, `text`, `thread_ts` are genuinely real fields (`thread_ts` is the real name for the parent-message timestamp used to reply in a thread). |
| `invite_to_channel`    | `conversations.invite` — the real endpoint takes a `users` field as a comma-separated list of Slack user IDs; simplified here to a single `user` string for a clean one-parameter format constraint (mirrors `github_issues_fixture.py`'s `add_assignee` simplification of GitHub's real `assignees` array). |
| `set_user_presence`   | `users.setPresence` — the real endpoint's only meaningful field, `presence`, taking exactly `auto` or `away`. |
| `set_channel_topic`   | `conversations.setTopic` — `channel`, `topic` are the real field names. |

## Constraint provenance

- **`channel` format** (`post_message`): Slack's real `chat.postMessage`
  accepts either a channel name prefixed with `#` (e.g. `#general`) or Slack's
  internal encoded conversation ID — a `C` (public channel), `G` (private
  channel/group), or `D` (direct message) prefix followed by 8-10 uppercase
  alphanumeric characters (e.g. `C0G9QF9GZ`). The regex used here
  (`#[a-z0-9_-]+|[CGD][A-Z0-9]{8,10}`) is a simplification of the real
  constraint (real channel-ID lengths and character sets are not published as
  a strict spec by Slack; this pattern captures the well-known shape, not an
  exhaustively verified one), matching the discipline documented in
  `github_issues_NOTES.md` and `gcal_NOTES.md` for their own format patterns.
- **`user` format** (`invite_to_channel`): Slack's real internal user IDs are a
  `U` prefix followed by 8-10 uppercase alphanumeric characters (e.g.
  `U012AB3CDE`), structurally identical in shape to the channel-ID convention
  above. Unlike GitHub's human-chosen username slugs (which a model can
  plausibly infer from a person's name, e.g. "Ryan Dahl" -> "ryandahl"), a
  Slack user ID is an opaque, server-assigned token with no human-readable
  relationship to the person's name — there is no way for an agent to guess
  the *correct* ID for "Wei Zhang" from context alone. This fixture's
  format constraint (like all format constraints in this repo, per
  `evals/fixtures/predictive_validity/constraints.py`'s `_check_constraint`)
  only checks the *shape* of whatever value the agent constructs, not whether
  it is the real, correct ID for that person — the intended signal is purely
  "did the agent learn from the schema/description that Slack user references
  take this specific opaque shape, rather than writing a plain display name or
  email address." This is a deliberately starker bad-vs-fixed contrast than
  GitHub's username fixture: an agent with no schema guidance (Arm A) has
  essentially no reason to produce a `U`-prefixed token at all, while an agent
  given the fixed description is told the exact shape explicitly.
- **`presence` enum** (`set_user_presence`): Slack's real `users.setPresence`
  endpoint takes exactly one of two values — `auto` (the default; Slack infers
  active/away from real client activity) or `away` (force the status to away
  regardless of activity). These are real, exact Slack API enum values, used
  verbatim as gold values. Because both values are common English words, task
  text was written to imply the correct value through scenario/intent (e.g.
  "stepped out from my desk", "let Slack track my real activity again")
  without literally using the words "away" or "auto" as tokens — see the
  Task design section below.
- **`set_channel_topic`** (inert): Slack's real `conversations.setTopic` takes
  only `channel` and a free-text `topic` string — there is no enum, format, or
  range constraint anywhere in the real API for this field, so forcing a task
  onto it would either be trivially inert or require inventing a constraint
  Slack does not actually have. Included in both servers as a realistic 4th
  operation (a Slack messaging server would obviously support setting a
  channel's topic) but deliberately excluded from `TASKS`/`TASK_CONSTRAINTS`,
  mirroring `stripe_payments_fixture.py`'s `create_customer` precedent.

## Task design

- 15 tasks total: 5 per constrained tool x 3 constrained tools
  (`post_message`, `invite_to_channel`, `set_user_presence`).
- Anti-tautology: task text never states a literal `#channel-name` or encoded
  channel/user ID, and never uses the literal enum tokens `auto`/`away`.
  `post_message`/`invite_to_channel` tasks name channels and people only in
  natural prose ("the engineering team's channel", "Wei Zhang"), requiring the
  agent to construct the correctly-shaped identifier itself from the
  schema/description rather than copying it out of the task text.
  `set_user_presence` tasks describe the underlying scenario (stepping out,
  an all-day offsite, wanting Slack to resume tracking real activity) rather
  than naming the enum value directly.

## Honesty about sourcing

This fixture was authored from the author's existing knowledge of the Slack
Web API — there was no live internet access available to verify field names,
enum values, or ID conventions against Slack's current published API
reference (`https://api.slack.com/methods`) at authoring time. All
descriptions and schema shapes are the author's own paraphrase, not copied
verbatim from any Slack document. The field names (`channel`, `text`,
`thread_ts`, `user`, `presence`, `topic`), the `auto`/`away` enum values, and
the `C`/`G`/`D`/`U`-prefixed ID conventions are believed accurate to the real
Slack product as of recent memory, but were not re-verified against a live
source before committing. If a byte-exact match to Slack's current API
reference matters for downstream use, re-verify against
`https://api.slack.com/methods` before relying on this fixture for anything
beyond fixture-internal self-consistency (which is fully verified — see the
import/lint checks in the corresponding commit).

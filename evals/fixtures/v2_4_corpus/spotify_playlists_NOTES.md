# Spotify Playlists fixture — provenance notes

## Real Spotify Web API operations modeled

Four tools, each a simplified wrapper around a real Spotify Web API operation:

| Tool                        | Modeled on real Spotify Web API operation                                     |
|------------------------------|--------------------------------------------------------------------------------|
| `create_playlist`            | `POST /users/{user_id}/playlists` — create a playlist. `name` is genuinely required by the real API; `public`, `collaborative`, and `description` are genuinely optional there. `collaborative` is omitted here to keep a clean single-constraint tool. |
| `add_tracks_to_playlist`     | `POST /playlists/{playlist_id}/tracks` — the real endpoint takes `uris` (a list of Spotify track URIs, `spotify:track:{id}`) and an optional `position`. |
| `set_playback_repeat_mode`   | `PUT /me/player/repeat` — the real endpoint's `state` query parameter, one of `track` / `context` / `off`, plus an optional `device_id`. |
| `follow_playlist`            | `PUT /playlists/{playlist_id}/followers` — the real endpoint's optional request body `{"public": bool}`. |

## Constraint provenance

- **`public` enum** (`create_playlist`, `follow_playlist`): the real Spotify API
  represents this field as a JSON **boolean**, not a string. This fixture
  simplifies it to a string enum (`"true"` / `"false"`) so the schema can carry
  a clean, testable enum constraint using this repo's existing
  `Constraint(kind="enum")` machinery (which compares string equality) rather
  than adding a new boolean-constraint kind. This mirrors `add_assignee` in the
  GitHub Issues fixture simplifying a real array field (`assignees`) to a
  single string for the same reason — a deliberate, documented simplification
  of a real field's shape, not an invented field. Only `create_playlist`'s
  `public` is exercised in `TASKS`/`TASK_CONSTRAINTS`; `follow_playlist`'s
  `public` is present in the schema (it is a real, optional field on the real
  endpoint) but not constrained in tasks, since `follow_playlist`'s
  constrained field for this fixture is its `playlist_id` (format).
- **`state` enum** (`set_playback_repeat_mode`): these are real Spotify API
  values, used verbatim as gold values. `track` repeats the single currently
  playing track, `context` repeats the current album/playlist/artist context,
  and `off` disables repeat.
- **`playlist_id` format** (`add_tracks_to_playlist`, `follow_playlist`):
  Spotify's real playlist (and most other resource) IDs are 22-character
  base62 strings (`[A-Za-z0-9]{22}`), e.g. `3cEYpjA9oz9GiPac4AsH4n`. Both
  tools take a real playlist ID in this same shape, so the identical pattern
  is reused across both tools deliberately (it is the same genuine ID format
  in both places), similar to how the GitHub Issues fixture reuses the
  `owner/repo` shape conceptually across format-constrained tools in that
  domain — here the reuse is exact because both operations key off the exact
  same resource type (a playlist).

## Honesty about sourcing

This fixture was authored from the author's existing knowledge of the Spotify
Web API (Playlists and Player resources) — there was no live internet access
available to verify field names, enum values, or endpoint shapes against
Spotify's current published API reference at authoring time. All descriptions
and schema shapes are the author's own paraphrase, not copied verbatim from
any Spotify document. The field names (`user_id`, `name`, `public`,
`description`, `playlist_id`, `uris`, `position`, `state`, `device_id`), the
`state` enum values (`track`/`context`/`off`), and the base62/22-character ID
shape are believed accurate to the real Spotify Web API as of recent memory,
but were not re-verified against a live source before committing. If a
byte-exact match to Spotify's current API reference matters for downstream
use, re-verify against `https://developer.spotify.com/documentation/web-api`
before relying on this fixture for anything beyond fixture-internal
self-consistency (which is fully verified — see the import/lint checks in the
corresponding commit).

## Task design

- 20 tasks total: 5 per tool x 4 tools, all constrained (no inert tool — all
  four chosen operations have a genuine constrained parameter, unlike the
  Stripe Payments fixture's `create_customer`).
- Anti-tautology: task text never states `"true"`/`"false"`, `"track"`/
  `"context"`/`"off"`, or a literal 22-character playlist ID. `create_playlist`
  tasks imply `public` via a scenario about who should be able to find the
  playlist (e.g. "anyone browsing his profile can find and listen to it" ->
  `true`; "just for her own listening, not shown to anyone else" -> `false`).
  `set_playback_repeat_mode` tasks imply `state` via a scenario about what
  should loop (a single song -> `track`, an album/playlist as a whole ->
  `context`, or a request to stop looping -> `off`). `add_tracks_to_playlist`
  and `follow_playlist` tasks never mention an ID at all — they name a
  playlist and a person/context, requiring the agent to have already resolved
  or be given the corresponding `playlist_id` in the correct shape.

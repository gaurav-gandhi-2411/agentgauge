# Docker Containers fixture — provenance notes

## Real Docker Engine API operations modeled

Four tools, each a simplified wrapper around a real Docker Engine API
operation:

| Tool               | Modeled on real Docker Engine API operation |
|---------------------|----------------------------------------------|
| `create_container`  | `POST /containers/create` — create (and, for this fixture, implicitly start) a container. The real request body's `Image` field and `HostConfig.RestartPolicy.Name` field are flattened here to top-level `image` and `restart_policy` for a clean two-constraint tool, matching this repo's existing simplification style (see `github_issues_NOTES.md`). |
| `stop_container`    | `POST /containers/{id}/stop?t=<seconds>` — stop a running container. The real `t` query parameter (seconds to wait before force-killing) is renamed `timeout_seconds` here for clarity; `container_id` maps to the real `{id}` path parameter. |
| `create_network`    | `POST /networks/create` — create a network. The real request body's `Name` and `Driver` fields map directly to `name` and `driver`; `internal` maps to the real `Internal` boolean field. |
| `tag_image`         | `POST /images/{name}/tag?repo=<repo>&tag=<tag>` — tag an existing local image into a repository without duplicating its layers. The real `{name}` path parameter (the existing image reference) is renamed `source_image` here; `repo` and `tag` map directly to the real query parameters. |

## Constraint provenance

- **`image` format** (`create_container`): Docker image references follow a
  `name[:tag]` (or full `registry/repo/path:tag`) shape. The regex used here
  (`[A-Za-z0-9][A-Za-z0-9/_.-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*`) is a
  simplification requiring at least one path segment, a colon, and a tag
  segment — it does not enforce Docker's full reference grammar (registry
  hostnames with ports, digests, case restrictions on repository names), only
  the basic "name:tag" shape, matching this repo's existing simplified-regex
  convention (e.g. `github_issues_NOTES.md`'s `owner/repo` pattern).
- **`restart_policy` enum** (`create_container`): `no`, `always`,
  `on-failure`, and `unless-stopped` are the real, complete set of values
  accepted by Docker's `HostConfig.RestartPolicy.Name` field. This is the
  full real enum, not a subset.
- **`timeout_seconds` range** (`stop_container`): Docker's real `t` query
  parameter on `/containers/{id}/stop` is an unbounded integer (seconds to
  wait before force-killing); the API itself does not enforce a min/max. The
  per-task ranges used here (e.g. 0-1s for "immediately", 240-600s for "let
  it fully flush for several minutes") are the fixture author's own
  real-world judgment about what grace period each described urgency level
  plausibly implies, not a value drawn from Docker's API reference — this
  mirrors `stripe_payments_NOTES.md`'s `amount` range, which is likewise a
  fixture-author judgment call rather than an API-enforced bound.
- **`driver` enum** (`create_network`): `bridge`, `host`, `overlay`, and
  `none` are four of Docker's real built-in network drivers. Docker also
  ships `macvlan` and `ipvlan` as built-in drivers, and additional drivers
  can be supplied by third-party plugins; those are deliberately omitted here
  to keep a clean four-member enum, following this task's explicit guidance
  to use this exact subset.
- **`tag` format** (`tag_image`): Docker's real tag-name grammar (from the
  `distribution/reference` package) is `[\w][\w.-]{0,127}` — starts with a
  word character (letter, digit, or underscore), followed by up to 127
  further word characters, periods, or hyphens. The regex used here
  (`[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}`) is a direct ASCII-only rendering of
  that real grammar.

## Simplifications from the real API

- `create_container`'s real request body accepts many more fields (`Cmd`,
  `WorkingDir`, `HostConfig.PortBindings`, etc.); only `image`, `name`,
  `restart_policy`, and `env` are modeled, matching this fixture's need for
  one clean format-constrained param and one clean enum-constrained param.
- `create_container` and `create_network` both make `restart_policy` /
  `driver` required parameters in this fixture's schema even though the real
  Docker API treats them as optional (defaulting to `"no"` and `"bridge"`
  respectively) — this is deliberate, so every task in this fixture has a
  real constraint to test rather than an omittable one.
- `tag_image`'s real endpoint defaults `tag` to `"latest"` if the query
  parameter is omitted; this fixture makes `tag` required so every task
  exercises the format constraint directly.

## Honesty about sourcing

This fixture was authored from the author's existing knowledge of the Docker
Engine API (Containers, Networks, and Images resources) — there was no live
internet access available to verify field names, enum values, or the tag-name
regex against Docker's current published Engine API reference at authoring
time. All descriptions and schema shapes are the author's own paraphrase, not
copied verbatim from any Docker document. The specific field names
(`Image`, `HostConfig.RestartPolicy.Name`, the `t` stop-timeout query
parameter, `Driver`, and the `repo`/`tag` tag-endpoint query parameters), the
four `RestartPolicy.Name` enum values, and the tag-name grammar are believed
accurate to the real Docker Engine API as of recent memory, but were not
re-verified against a live source before committing. If a byte-exact match to
Docker's current API reference matters for downstream use, re-verify against
`https://docs.docker.com/engine/api/latest/` before relying on this fixture
for anything beyond fixture-internal self-consistency (which is fully
verified — see the import/lint checks in the corresponding commit).

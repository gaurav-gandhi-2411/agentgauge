# Provenance of the bundled demo recording

`agentgauge demo` replays `replay_before.json` / `replay_after.json`: real trial outcomes recorded
once from a local model. Nothing here is simulated, tuned or cherry-picked.

## What it is (and is not)

- A tiny, **illustrative** before/after MCP server pair (`before_server.py`, `after_server.py`):
  six `ticket_*` tools, identical names and parameters, only the descriptions differ. In BEFORE,
  three pairs of tools share the same vague description text; in AFTER, every description says
  what the tool does, when to use it and when not to.
- `tasks.json`: 24 tasks (4 per tool), written as user intents that never contain a gold tool
  name, each with one argument constraint.
- The pair was **designed to show a large gap. It is not a benchmark** and says nothing about how
  real servers behave. Its purpose is to show the shape of the output.

## Recording

| Item | Value |
|---|---|
| Date (UTC) | 2026-10-11, 05:24-05:26 |
| Command | `python scripts/record_demo_replays.py --model gemma2:9b --max-calls 120` |
| Collection path | `agentgauge.cli._collect_trials` -> `runner.run_tasks` -> `OllamaProvider` |
| Trials per task | 1 |
| Base seed | 42 (per-(task, trial) seeds derived by `runner.trial_seed`; the seed is sent to Ollama as `options.seed`) |
| Model | `gemma2:9b`, Q4_0, 9.2B parameters, Ollama image ID `ff02c3702f32` (`ollama list`) |
| Ollama | 0.33.3 |
| Decoding | Ollama defaults apart from the seed (no temperature override), so the exact trial outcomes depend on Ollama/model build and hardware |
| Model calls | 96 (24 tasks x 2 prompts x 2 arms) |
| Sampling | one pass, one seed; no seed search, no re-runs of the final recording |

## Result of the recording

Selection accuracy / joint success: BEFORE 0.667 / 0.667, AFTER 1.000 / 1.000 (n = 24 tasks per
arm). `agentgauge diff` at its default 0.05 threshold gives **INSUFFICIENT_SENSITIVITY**
(delta +0.333, 95% CI [+0.125, +0.500]): the point estimate is large but 24 tasks cannot narrow the
interval below 2x the threshold. That is the harness working as designed, and is kept as-is; the
demo prints it and explains it. A reliable gate needs roughly 100 tasks per arm.

## History: one earlier design, discarded

The first pair (REST-style names `ticket_post` / `ticket_get` / `ticket_list` / `ticket_patch` /
`ticket_put` / `ticket_delete`, vague BEFORE descriptions) was recorded the same way on the same
day (05:20-05:22 UTC, 96 calls) and gave selection accuracy 1.000 in **both** arms (joint 0.958 vs
1.000, delta +0.042, INSUFFICIENT_SENSITIVITY): `gemma2:9b` inferred the right tool from the tool
names and parameter names alone, so there was no description effect to show. The pair was
redesigned once, with near-synonym names whose difference lives only in the descriptions, and
re-recorded once. The files shipped here are that second recording. The first recording is not
included.

## Regenerating

Needs a running local Ollama with `gemma2:9b`:

```
python scripts/record_demo_replays.py --model gemma2:9b
```

The outcome will differ if the Ollama/model build or hardware differs. Any re-recording must
update this file.

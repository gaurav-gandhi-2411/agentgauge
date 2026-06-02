# spec.md — T14: Non-destructive schema merge (fixer data-loss bug)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ d35d935 ·
**Branch:** `claude/t14-nondestructive-merge`
**Routing:** DRAFT PR. Touches `fixer.py` merge logic only — does NOT touch scorer.py, judge,
rubrics, or calibration, so NOT draft-forcing #1. Merge correctness is fully CI-provable;
the real-generator run is confirmation. NOT in `AUTO_MERGE_TASKS`.

---

## Problem (found by the greet diagnostic)

The fixer's schema merge is destructive. At the merge site (`fixer.py`, ~L399):

    merged_props = {**existing_props, **new_props}

For any param the generator returns, `new_props[param]` REPLACES the entire existing param schema.
The generator prompt (~L92) constrains output to exactly `{type, description}`, so every other
JSON Schema keyword on a touched param is erased — `default`, `enum`, `minimum`/`maximum`,
`format`, `items`, nested `properties`, etc.

`greet.prefix` lost its `default: "Hello"`. Visible symptom: 83.3 (the scorer's third sub-point
needs `param in required OR default is not None`, and both are now false). Real harm: the emitted
"fix" deletes the default, so the schema now misrepresents an optional param as if it had no
default. The fixer is DEGRADING the interface it claims to improve.

This is a fixer bug, not a scorer ceiling. scorer.py (L81–82) explicitly rewards defaulted params;
it has no structural cap.

## Why this jumps the queue

Ahead of T13 (real-server cost pre-filter) and the runner ground-truth work: the fixer currently
strips constraints from any schema it touches. Pointing it at a real third-party server would
silently delete `enum`/`min`/`max`/`default` — the opposite of the product's premise. Must land
before anything runs against a real server, and before "improves schema_completeness" is claimed
for optional-param tools.

---

## Scope

**IN:** replace the destructive merge with a non-destructive deep merge that PRESERVES existing
per-param keywords the generator didn't return, while letting the generator override the fields it
did return (type, description). Recursive for dict-valued keywords. Schema fixes only.

**OUT:** pruning/removing existing keywords (generator may override values, not delete keys);
new dimensions; the cost pre-filter (T13).

## Design

- Param level: for a param present in both, `deep_merge(existing[param], new[param])` — generator
  output overlays existing — instead of replacement. Params only in `existing` are untouched;
  params only in `new` are added.
- `deep_merge` semantics: dict values merge recursively (so nested `properties` / `items` survive);
  scalar and list values from the generator win; existing keys absent from generator output are kept.
- Over-marking guard is unchanged and stays correct: a preserved `default` keeps the param optional
  and out of `required`; the scorer's `default is not None` branch then legitimately awards the
  third point.

---

## Acceptance criteria

1. **CI (deterministic, MockProvider, seed 42, no network) — the core proof:**
   - Param with existing `{default, enum, minimum, format, items, nested properties}` + generator
     returning only `{type, description}` → merged param keeps ALL existing keywords AND takes the
     generator's type/description.
   - Param only in existing: unchanged. Param only in generator: added.
   - Over-marking guard still strips defaulted params from `required`.
   - Deterministic re-score: `greet.schema_completeness` reaches 100 with a mock generator returning
     the realistic two-field `prefix` output (proves the merge, not the model).
2. **Real-generator (manual, in PR description):** run on `echo_server` with qwen3:8b. Confirm
   `greet` → 100 AND the emitted diff for `prefix` still contains `default: "Hello"`. `mystery`
   still 100; `add`/`echo` unchanged. PRINT the emitted `prefix` schema so the reviewer can SEE the
   default survived.
3. scorer.py untouched; `generator_model != judge_model` still asserted; verify.sh green;
   coverage ≥ 60%; committed tests mock the generator.

## Housekeeping

- TASKS.md: add T14 (TODO → IN-REVIEW on completion). T13 stays in FUTURE/DEFERRED.
- STATUS.md: once landed, note schema fixes are non-destructive (preserve existing constraints).
  Only then is "improves schema_completeness" safe to state for optional-param tools.

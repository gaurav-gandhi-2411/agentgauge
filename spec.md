# spec.md — UX1: make AgentGauge feel like tracegauge (one command, nothing destructive)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 8cb679b ·
**Branch:** `claude/ux1-onecommand`
**Routing:** DRAFT PR. CLI/UX changes only — NO scoring/judge/generator/rubric/calibration changes.
NOT condition #1. Pure presentation + safety-of-defaults layer over the existing scan/fix logic.

**Pre-registration:** lighter than an experiment, but commit the spec; this is product polish, not a
measurement. No fixtures, no GPU run required for acceptance (CI + a manual smoke-test only).

## Why

CC's runbook showed the product takes ~8 commands + a manual file-copy + a JSON one-liner to
experience, and `fix --apply` silently rewrites the target file. tracegauge proved the winning
pattern: one install, one command, instant readable local result, nothing destructive. Port that
*pattern* (not the code) to AgentGauge. The underlying scan/fix engine is unchanged and correct;
this is the wrapper that makes first-touch frictionless and safe.

## Scope — THREE changes only (resist scope creep)

### 1. Non-destructive by default (the one real footgun)
- `agentgauge fix <server>` with NO `--apply` already previews — keep that, make it the obvious path.
- When `--apply` IS passed: ALWAYS write a `<file>.bak` backup before rewriting in place. Print the
  backup path. (Today a user can clobber their server file by running the obvious command; this ends
  that.)
- If `--apply` would overwrite and a `.bak` already exists, write `.bak.N` (don't silently stomp the
  prior backup).

### 2. Inline before/after (kill the "Get-Content fix.patch" step)
- In the fix PREVIEW path, render each accepted change INLINE in the console: tool name, dimension,
  delta, and a compact before -> after of the description/schema (colorized: red old / green new,
  degrade gracefully to +/- markers if no TTY color).
- Keep `--out-diff PATH` as an option for those who want the patch file; it's no longer REQUIRED to
  see what changed.

### 3. One convenience command: `agentgauge try <server>`
- New verb that orchestrates the existing scan + fix-preview in ONE read-only command:
  a. run scan (default judge), print the score table + prioritized fixes,
  b. run fix in PREVIEW mode (no writes), print the inline before/after from change #2,
  c. print a one-line next-step hint ("run `agentgauge fix <server> --apply` to apply these").
- `try` NEVER writes anything (no --apply path). It's the "feel the product" command — the tes-serve
  analog: one command, full read-only picture.
- `try` is a thin wrapper over existing scan/fix code paths — NO new scoring/generation logic.

## Explicitly OUT of scope (do NOT build)
- Env-var model config, remote-Ollama host flags, HTML report polish, web dashboard, progress
  spinners, config files. Defaults already work (llama3.1:8b judge / qwen3:8b generator). Anything
  beyond the three changes above is a separate PR.

## Acceptance criteria

1. **CI (deterministic, --mock, no Ollama/network):**
   - `agentgauge try <server> --mock` runs end-to-end, exits 0, prints score table + inline
     before/after, writes NOTHING (assert target file unchanged, no .bak created).
   - `agentgauge fix <server> --mock --apply` writes a `.bak` (assert it exists and matches the
     pre-apply content); a second `--apply` produces `.bak.1` not a stomped `.bak`.
   - `agentgauge fix <server> --mock` (no --apply) writes nothing (assert unchanged).
   - Inline before/after renders for an accepted mock fix (assert the old + new strings both appear
     in stdout); no-TTY path uses +/- markers.
   - All existing scan/fix/ci tests still pass unchanged (this is a wrapper, not a rewrite).
2. **Manual smoke (in PR description, Ollama):**
   - `agentgauge try examples/echo_server.py` — paste the full single-command output; confirm it
     shows score + inline before/after for mystery/greet and wrote nothing.
   - `agentgauge fix examples/echo_server.py --apply` on a COPY — confirm `.bak` created.
3. No scoring/judge/generator/rubric/calibration changes; verify.sh green; coverage >= 60%.

## Housekeeping
- TASKS.md: UX1 (TODO -> IN-REVIEW). STATUS.md: note the UX pass (non-destructive default + inline
  diff + `try`), explicitly scoped as presentation-only, engine unchanged. README/quickstart: replace
  the multi-step walkthrough with the single `agentgauge try <server>` command.

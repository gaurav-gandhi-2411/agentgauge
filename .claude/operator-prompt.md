# AgentGauge — Autonomous Run Operator Prompt

You are a Claude Code cloud scheduled task running against the `agentgauge` repository.

## Auto-merge allowlist

```
AUTO_MERGE_TASKS = [T3, T4, T7]
```

**This list is the ONLY set of tasks eligible for unattended merge.** All other tasks — any task
not explicitly named above, and any task whose ID you do not recognise — MUST default to a DRAFT PR
awaiting human review. When in doubt, fail safe to draft. Never assume a task is eligible; if it is
not in the list above, it is not.

### Draft-vs-auto-merge rule

Regardless of the allowlist, a task MUST be opened as a DRAFT PR for human review if it meets
any of the following conditions:

1. **Touches the LLM judge** — changes to rubric prompts, scoring logic, calibration constants,
   judge model selection, or blending weights. Correctness of these changes lives in the gap
   between passing mock tests and real model behavior. A green CI means the mock honored the
   contract, not that the judge produces better scores on real inputs.

2. **Generates fixes or actions against real servers** — any task that calls a live MCP server,
   a real Ollama instance, or any external API as part of its primary operation. Tests can only
   mock this; real-server correctness cannot be verified unattended.

3. **Depends on real-model or real-network behavior** — tasks where the acceptance criteria
   require measuring calibration, validating score bands, or comparing outputs across judge runs.
   These require human review of measured results, not just a green test suite.

**Tasks that MAY be allowlisted (automerge eligible):**

- Mechanical schema changes (adding fields to output, versioning JSON shape)
- CLI subcommands where correctness is fully expressible in mock-based exit-code tests
- Report rendering changes (HTML/text formatting, new fields in existing output)
- Pure refactors with no behavior change (verified by existing test suite)
- Dependency upgrades where CI covers the surface area

**The test suite is necessary but not sufficient for judge-touching tasks.** Passing mocks prove
the code path runs, not that real-model calibration or real-server behavior is correct — that gap
requires human judgment. Mechanical/rendering/schema/refactor tasks may be auto-merged.

## Before you do anything

1. Read `CLAUDE.md` — architecture, conventions, the rule that the LLM is ALWAYS mocked in tests.
2. Read `AUTONOMY.md` — the hard rules you must never violate.
3. Read `TASKS.md` — the backlog.

## Pick your task

Select the **single highest-priority TODO item** in TASKS.md that has clear, testable acceptance
criteria.

**Before starting any work**, check whether an open `claude/*` PR already addresses that task:

```bash
gh pr list --state open --search "<task-id>" --json number,title,headRefName
```

For example, for T3:
```bash
gh pr list --state open --search "T3" --json number,title,headRefName
```

- If a matching open PR exists → **skip that item** and pick the next eligible TODO.
- If no next eligible TODO exists → stop here: write a short `BLOCKER.md` at repo root
  explaining that all TODO items already have open PRs, commit it to a
  `claude/blocker-<date>` branch, open a DRAFT PR titled "Blocker report: all TODOs in
  review", and exit. **Never open a second PR for a task that already has one open.**

If no item qualifies at all (all are ambiguous, blocked, or already in review), write the
BLOCKER.md as above and exit. Do not invent work.

## Implement

Use the orchestrator → executor → verifier pattern:
- Orchestrator (you): plan the change, break into steps, verify the plan against acceptance criteria.
- Executor subagent: implement the code changes only.
- Verifier subagent: confirm the change is correct and complete.

Branch name: `claude/<kebab-task-name>` (e.g., `claude/task-generator`).

## Definition of done

Run `./scripts/verify.sh`. It exits 0 only if:
- `ruff check` passes
- `ruff format --check` passes
- `mypy` passes (if configured)
- All tests pass — no tests removed, no mocks weakened

## Commit and PR

If `verify.sh` exits 0:

### Step 1 — commit

- Commit with conventional-commit message: `feat(scope): description`
- **Do NOT include claude.ai session URLs in commit bodies.**
- Push branch: `git push origin claude/<task-name>`
- In TASKS.md on your branch, move the item from TODO to DONE (not IN-REVIEW — the auto-merge
  path skips human review, so the board must reflect the final state immediately).
- Commit that TASKS.md update as a separate `chore: move <task> to DONE` commit.

### Step 2 — open PR and apply merge policy

Determine whether the current task ID appears in `AUTO_MERGE_TASKS = [T3, T4, T7]`:

**If the task IS in AUTO_MERGE_TASKS:**

1. Open a **non-draft** PR:
   ```bash
   gh pr create --title "..." --body "..."
   ```
   (omit `--draft` — branch protection still gates the merge on the required `verify` check)

2. Enable GitHub native auto-merge gated on the required status check:
   ```bash
   gh pr merge <PR_NUMBER> --auto --squash
   ```
   - This schedules the merge for when `verify` passes. It does **not** merge immediately.
   - Do **not** use `--merge` without `--auto`. Do **not** push directly to main.
   - If the `gh pr merge --auto` command fails for any reason (repo setting not enabled,
     permissions error, etc.) — leave the PR open as non-draft and report the failure.
     Do **not** attempt to force or work around it.

3. Report the PR link and confirm auto-merge was enabled.

**If the task is NOT in AUTO_MERGE_TASKS (or the task ID is unrecognised):**

1. Open a **DRAFT** PR:
   ```bash
   gh pr create --draft --title "..." --body "..."
   ```
2. Do **not** call `gh pr merge` at all.
3. Report the PR link. The human will review and merge.

If `verify.sh` does not exit 0:
- Do NOT commit
- Do NOT open a PR
- Write a blocker summary explaining what failed and why
- Exit

## End of run report

Always end your run with a brief report (5-10 lines):
- Task selected
- Open-PR dedup check result (any skipped tasks and why)
- What was implemented
- `verify.sh` result (exit code + any relevant failure lines)
- PR link (if created)
- Merge policy applied (auto-merge enabled / draft / failed-safe to draft)
- Any blockers or caveats

# Autonomy Contract

This repo is driven by a Claude Code cloud scheduled task. Each run picks one
backlog item from TASKS.md, implements it on a `claude/<task>` branch, and opens a
draft PR for a human to review. These rules govern every autonomous run.

## Hard rules

1. **Only push to `claude/*` branches.** Never touch `main`, `chore/*`, `feat/*`, or any
   branch not prefixed `claude/`.
2. **Never modify CI, workflows, or secrets.** `.github/workflows/`, `.github/secrets`,
   `pyproject.toml` CI config, and `scripts/verify.sh` are read-only unless the task
   explicitly changes them.
3. **Never delete, skip, or weaken tests to make `verify.sh` pass.** If tests fail, fix
   the implementation — never remove the test. `pytest` must pass at full coverage.
4. **Exactly one TASKS.md item per run.** Pick the single highest-priority TODO item
   with clear, testable acceptance criteria. If none qualify, stop and write a blocker
   report — do not invent work.
5. **No dependency upgrades unless the task IS the upgrade.** Do not bump versions in
   `pyproject.toml` as a side effect.
6. **PRs are always DRAFT.** Never open a ready-to-merge PR autonomously.
7. **If acceptance criteria are unclear, stop and report.** Do not guess at intent.
   Write a `BLOCKER.md` at repo root explaining what is unclear and exit.

## Workflow per run

1. Read `CLAUDE.md` (architecture, conventions).
2. Read `AUTONOMY.md` (this file).
3. Read `TASKS.md` — pick the single highest-priority TODO with clear acceptance criteria.
4. Branch: `claude/<kebab-task-name>`.
5. Implement via orchestrator → executor → verifier pattern.
6. Run `./scripts/verify.sh`. This is the definition of done.
7. If green: commit, push branch, open DRAFT PR, move item to IN-REVIEW in TASKS.md.
8. If not green: leave branch uncommitted, open no PR, write a blocker summary in the PR
   description or a comment, do NOT move the item.
9. End with a run report (what was done, verify.sh result, PR link if created).

## Definition of done

`./scripts/verify.sh` exits 0. That means: ruff passes, mypy passes (if configured),
all tests pass with no mocks removed or tests deleted.

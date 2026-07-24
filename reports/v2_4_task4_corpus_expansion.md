# AgentGauge v2.4 — Task 4: fixture corpus expansion

Deferred from v2.3, executed after Tasks 1-3. Builds >=10 additional gold-constraint
fixtures at the same rigor as the existing two (`call_constraints_server`,
`call_constraints_v2_server`), sourced from real public APIs, to close the
sample-size ceiling that left the argument-degradation cross-model question
inconclusive at n=62 (`reports/v2_2_task_a_reallocation.md`).

## What was built

10 new bad/fixed fixture pairs, each modeling real operations from a distinct,
well-known public API — same design as the existing two: type-only ("bad")
schemas vs. real descriptions ("fixed"), a mix of FORMAT/ENUM/RANGE-constrained
tools, and hand-authored anti-tautology tasks with gold `Constraint` entries
(`agentgauge.constraints.Constraint`, the product class — not a separate
research-only type).

| Domain | Tools (constrained) | Tasks | Constraint mix |
|---|---|---|---|
| GitHub Issues | 4 (4) | 20 | 2 FORMAT / 2 ENUM |
| Stripe Payments | 4 (3, 1 inert) | 15 | RANGE+ENUM / ENUM / ENUM |
| Google Calendar | 4 (4) | 20 | 2 FORMAT / 2 ENUM |
| Jira Issues | 4 (4) | 20 | FORMAT+ENUM / ENUM / ENUM / FORMAT |
| Slack Messaging | 4 (3, 1 inert) | 15 | 2 FORMAT / 1 ENUM |
| Docker Containers | 4 (4) | 20 | FORMAT+ENUM / RANGE / ENUM / FORMAT |
| Kubernetes Workloads | 4 (4) | 20 | FORMAT+ENUM / RANGE / ENUM / FORMAT |
| Twilio Messaging | 4 (4) | 20 | 2 FORMAT / 2 ENUM |
| AWS S3 | 4 (4) | 20 | FORMAT / FORMAT+ENUM / ENUM / ENUM |
| Spotify Playlists | 4 (4) | 20 | 2 ENUM / 2 FORMAT |
| **Total** | **40 tools (37 constrained)** | **190** | |

**190 new anti-tautology tasks, 0 missing gold-constraint entries** (verified by
direct import: every task's `(tool_name, description)` key resolves in its
fixture's `TASK_CONSTRAINTS`). Combined with the existing 62 (`call_constraints_server`
32 + `call_constraints_v2_server` 30), the real, non-fabricated task pool for
the argument-degradation question is now **252 tasks**.

## Methodology — no fabrication, no pooling of unrelated fixtures

Each fixture was built by an independent executor agent, working from a
detailed brief specifying: read the exact structure of the existing fixtures
first (`call_constraints_v2_server.py` + `ty2_tasks.py`); model a real,
well-known public API (GitHub, Stripe, Google Calendar, Jira, Slack, Docker,
Kubernetes, Twilio, AWS S3, Spotify) using genuinely-known field names and
semantics, not invented ones; enforce the anti-tautology rule (task text
expresses user intent only, never quotes the literal gold enum/format/value);
disclose in a `*_NOTES.md` file that descriptions are the agent's own
paraphrase without live-internet verification this session (an honest,
stated limitation, not hidden).

**Independent verification, not self-report alone:**
- All 10 fixtures re-imported directly by the orchestrator: 190 tasks total,
  0 missing constraint entries, confirmed a second time.
- 3 of the 10 new "fixed" servers smoke-tested as genuinely running MCP
  servers (not just syntactically valid Python) via real `connect_stdio` +
  `introspect()` calls: `github_issues_server_fixed.py` →
  `['create_issue', 'add_assignee', 'update_issue_state', 'add_label']`;
  `k8s_workloads_server.py` → `['create_pod', 'scale_deployment',
  'set_pod_image_pull_policy', 'create_namespace']`;
  `twilio_messaging_server_fixed.py` → `['send_sms', 'lookup_phone_number',
  'make_call', 'set_call_status_callback']`.
- `ruff check`/`ruff format --check` clean on all 40 new example-server files
  and all 10 fixture modules.
- Full test suite (864 tests) re-run after the expansion: unchanged pass
  count — the new fixtures are additive and don't touch any shared registry
  (`blind_tasks.py`, `constraints.py`, `manifest.py` were deliberately left
  untouched by every executor agent, per instruction, to avoid merge
  conflicts across concurrent authoring).

## Disclosed limitation: a git-index race produced two mislabeled commits

Ten executor agents authored and committed concurrently in the same working
tree. Git has no locking between separate `git add`/`git commit` invocations
racing in the same index, and two commits ended up with a commit MESSAGE that
does not match their actual DIFF CONTENT:

- `b0b4393`, titled "feat(evals): add Docker containers gold-constraint
  fixture pair" — its actual diff contains the **Kubernetes** fixture files
  (`k8s_workloads_*`).
- `b1587f9`, titled "feat(evals): add Spotify playlists gold-constraint
  fixture pair" — its actual diff contains the **Docker** fixture files
  (`docker_containers_*`).

**No data was lost and no content is incorrect** — confirmed directly
(`git show --stat` on both commits, cross-checked against every agent's own
independent report of what it authored). The Docker agent's real content is
present and correct, just under the Spotify commit; the Kubernetes agent's
real content is present and correct, just under the Docker commit. Every
other commit (`c9a48ba` Google Calendar, `1f95af2` GitHub Issues, `e6537a9`
Stripe, `6d8a997` Jira, `3f499f7` Twilio, `0161d5d` Slack, `704b348` AWS S3,
`0e8e1f1` Spotify) has correctly-matched message/content, including the two
newly-recommitted fixtures (AWS S3 and the real Spotify content) that the
race had knocked loose from any commit entirely (they were re-committed
cleanly as untracked-file recoveries, verified byte-identical to what their
authoring agent produced).

**Not fixed via rebase in this pass**: correcting the two commit messages
would require rewriting shared branch history that later commits are already
built on top of — exactly the kind of operation that needs explicit
confirmation and a backup per this project's standing history-rewrite
discipline. Content correctness was prioritized over commit-message
cosmetics; the mismatch is disclosed here rather than silently left
unexplained in `git log`.

**Addendum (v2.5 Task 4):** fixed. `b0b4393`/`b1587f9` (the hashes above) no
longer exist on `feat/agentgauge-v2` — a backed-up, non-interactive rebase
corrected only the two messages, verified byte-identical by tree hash
against the pre-rebase state (preserved at branch `backup/pre-rebase-v2-4`).
See `reports/v2_5_task4_rebase.md` for the full record and the new,
correctly-labeled hashes.

**Lesson for future multi-agent corpus-authoring waves:** concurrent
executor agents must not share one working directory's git index for
committing. Each concurrent agent should get its own `git worktree`, or the
commit step should be serialized (one agent commits at a time, coordinated
by the orchestrator), not left to race.

## Achieved MDE at the new corpus size

`agentgauge.harness.simulate_mde_task_level`, calibrated constants
(`CALIBRATED_BASELINE_RATE`/`CALIBRATED_SIGMA_TASK`/`CALIBRATED_RESID_SD`/
`CALIBRATED_RHO`), `trials_per_task=1` (Task 1's optimal allocation),
80% power, `n_simulations=2000`:

| n_tasks | MDE (80% power) |
|---|---|
| 62 (real ceiling before this expansion) | **0.1061** — above the 0.10 ship target |
| 100 | **0.0848** — clears the ship target |
| 150 | **0.0689** |
| 200 (not directly measured this pass) | Between 0.0689 and the n=150 value, monotonically decreasing — not computed to exact precision, disclosed as an estimate range, not a measured point |
| 252 (full new pool) | Below the n=150 value; not computed to exact precision this pass for the same reason |

**The power gap Task A (v2.2) / v2.3 left open is now closed.** At n=100 — a
subset of the 252-task pool now available, not a hypothetical — MDE=0.0848
clears the 0.10 ship target, the same allocation already validated for the
causal-chain measurement (`reports/v2_2_optimal_allocation.md`). The
argument-degradation cross-model question can now be re-run with real
statistical power, using real tasks, without needing more compute or more
fixture authoring — a live-inference re-run of that specific question (not
performed in this pass; this task's deliverable is the corpus and the MDE it
enables, not a new live measurement) is the natural next step.

**Precision note on n=200/252**: those two grid cells were still computing
when this report was finalized; rather than block on marginal additional
precision past the point the headline claim (gap closed at n=100) was
already decisively established, the report proceeds with the 3 confirmed
values (62/100/150) plus the qualitative fact that MDE decreases
monotonically with n_tasks (established in `reports/v2_2_optimal_allocation.md`
1a's full grid) — not an assumption, a previously-measured property of this
exact estimator.

## Independent verification

A separate verifier agent re-imported all 10 fixture modules directly,
recomputed the total task count and missing-constraint count from scratch
(190 total, 0 missing — matches exactly), independently confirmed the
mislabeled-commit finding by reading both commits' diffs itself (`b0b4393`
actually contains `k8s_workloads_*`, `b1587f9` actually contains
`docker_containers_*` — confirmed, not taken on the reporting agents'
self-report), spot-checked 2 of the 10 `NOTES.md` files for the honest
no-live-verification disclosure (present in both), and re-ran
`ruff check`/`ruff format --check` on all 10 fixture files (clean). **All
four items: CONFIRMED, no discrepancies.**

## What this does and does not establish

- **Established:** a 252-task real, non-fabricated corpus now exists for the
  argument-degradation question; at the already-validated 100-task
  allocation, MDE clears the ship target — the sample-size ceiling that
  made this question "inconclusive-underpowered" (not "no effect") is
  removed.
- **Not established:** what the argument-degradation effect size actually
  IS at this new allocation — that requires a live-inference re-run across
  the 3 model families, out of scope for this corpus-building task and not
  performed here. The corpus and its achievable MDE are the deliverable;
  the measurement itself is the natural next task.

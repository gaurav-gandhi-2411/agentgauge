# AgentGauge — Roadmap

## v1 — CLI scanner (COMPLETE)

`agentgauge scan <target>` connects to an MCP server, introspects its tools, runs an LLM agent
against generated tasks, and prints a scored report. All eight scoring dimensions are implemented.
JSON and HTML output are supported. `agentgauge ci` provides an exit-code gate for CI pipelines.

---

## v2 — Fix + monitor (not started)

### Auto-fix loop (the differentiator)

Generate improved tool descriptions, parameter schemas, and examples, and open them as a PR against
the target server repo. This is the primary v2 goal and the main thing that separates AgentGauge from
a test runner — it closes the loop from diagnosis to fix.

**Why it needs human review per PR (all three draft-forcing conditions apply):**
- It touches live servers (real MCP calls to understand the server's actual behavior).
- Correctness of the generated fix depends on real-model output, not mock-verifiable logic.
- Acceptance criteria require validating that the fix actually improves the score on real inputs.

Any auto-fix task must ship with designed acceptance criteria and a human-review gate. The autonomy
infrastructure's DRAFT-PR default is the right policy here — do not add auto-fix tasks to
`AUTO_MERGE_TASKS`.

### CI action

A GitHub Actions action (published to the marketplace) that installs AgentGauge inside a user's
own workflow and fails the build if the score regresses below a threshold. The `agentgauge ci`
subcommand already provides the exit-code primitive; this packages it for easy adoption.

### Hosted dashboard (recurring revenue core)

Per-server score history, regression alerts, and trend graphs. Subscription-based; one score per
scheduled scan run per server. Stripe integration deferred until people are actively asking to pay.

---

## v3 — Expand surface + flywheel (not started)

- Same harness against **OpenAPI / REST** endpoints and **CLIs**.
- **Public scanner + leaderboard**: scan a public MCP server, publish the score. The leaderboard
  itself is the marketing — publishing numbers draws attention without an ad budget.
- **"Certified agent-ready" badge / directory**: servers that pass a quality threshold get a badge
  and a listing. This is the distribution flywheel.

---

## Deferred / backlog

- **≥30B judge re-calibration.** Swap `CALIBRATED_JUDGE_MODEL` in `cli.py` to `llama3.3:70b` (or
  equivalent), re-run the three-tier calibration cases, and update the band tables in CLAUDE.md.
  No rebuild required — this is a config change + measurement exercise. Blocked on a ≥64 GB host.
  Tracked in TASKS.md under FUTURE/DEFERRED.

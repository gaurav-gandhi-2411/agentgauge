> DRAFT. NOT POSTED. PREREQUISITE: merge `docs/gw-truncation-correction` before posting. Links below point at
> the paths as they will be on main after that merge. See [README.md](README.md) in this folder.
> Show HN renders plain text only: sources are bare URLs in a reference list at the end.

# Show HN

**Title:** Show HN: AgentGauge, did your MCP tool-description change move agent success?

**URL:** https://github.com/gaurav-gandhi-2411/agentgauge

**Body:**

I built AgentGauge because I wanted a measurement, not a score, for one question: when I rewrite the
tool descriptions on an MCP server, does an agent actually succeed more often? It is a regression
harness that runs an agent model (a local Ollama model by default) against two variants of a server
and reports the change in task success with a confidence interval (README).

Try it (the lint step needs no LLM):

    pip install agentgauge-harness
    agentgauge lint examples/call_constraints_server_fixed.py
    agentgauge diff before_server.py after_server.py --tasks agentgauge_tasks.json

before_server.py and after_server.py stand for your own two versions of a server, and the tasks file
is yours to write; `agentgauge init` scaffolds a starter one. The install name and the CLI are
documented in the README. `diff` needs a model (Ollama, default gemma2:9b) or a mock/replay run (README).

What I measured, and what I did not:

- At 100 tasks per arm and 1 trial per task the minimum detectable effect is 8.5 percentage points
  at 80% power, assuming you supply about 100 tasks of your own (README, allocation report). Below
  that, the harness can answer "insufficient sensitivity" instead of a verdict. The 21.6% abstention
  rate in the README is from an earlier version of the estimator, before the move to 100 tasks per arm,
  on 44 historical tool sets and 2200 bootstrap null comparisons (estimator report). It is not a
  measurement at 100 tasks per arm.
- Only one lint rule has a validated effect on task success; the README says so in a
  per-rule table that includes the nulls (README). That rule flags a contradiction
  between a type and its enum, and it cost 13.3 to 28.9 points of task success across three small models
  (README).
- In a pilot of ten public Python MCP servers, 7 had a testable confusable family. Counting 2 earlier anchor
  servers, 0 of those 9 showed the regime where better descriptions help. "In the regime" means the
  server's shipped descriptions fail at least one contested task and a hand-written oracle description
  recovers it. This is a lower bound from a small sample, not a population estimate: the sampled public
  servers are more often documented than internal or custom servers (paper).
- Scope of the numbers. Rubric scores from `agentgauge scan`, the legacy v1 interface, depend on its
  judge model: the judge is pinned to llama3.1:8b and scores from different judges are not
  comparable (CLAUDE.md). The effects `diff` reports are task success measured on the specific agent
  models I tested (gemma2:9b, llama3.1:8b, qwen2.5:7b) and may differ on other models.

One of my own published results was wrong. The paper reported 0%/0% for the google_workspace server
(116 tools). It was Ollama silently truncating the tool listing at its default 4096-token window;
rerun with the window sized, both arms score 65% (13/20) in a small pilot of 4 tasks x 5 trials on
gemma2:9b (STATUS.md). I corrected the paper in place with a dated correction note and kept the raw
fixtures. The fix that sizes the window, plus a guard that raises when Ollama truncates a prompt, is on
the unmerged branch fix/ollama-num-ctx; it is not on main yet, so the shipped tool does not size the
window itself (branch).

Feedback on the statistics is the most useful thing to me. Apache-2.0 (README).

References:

README: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md
Allocation report: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/reports/v2_2_optimal_allocation.md
Estimator report: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/reports/v2_1_estimator_rebuild.md
Paper: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md
STATUS.md: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md
CLAUDE.md: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/CLAUDE.md
Branch: https://github.com/gaurav-gandhi-2411/agentgauge/blob/fix/ollama-num-ctx/agentgauge/providers.py

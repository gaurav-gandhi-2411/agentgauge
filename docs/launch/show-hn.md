> DRAFT. NOT POSTED. PREREQUISITE: merge `docs/gw-truncation-correction` before posting. Links below point at
> the paths as they will be on main after that merge. See [README.md](README.md) in this folder.

# Show HN

**Title:** Show HN: AgentGauge, did your MCP tool-description change move agent success?

**URL:** https://github.com/gaurav-gandhi-2411/agentgauge

**Body:**

I built AgentGauge because I wanted a measurement, not a score, for one question: when I rewrite the
tool descriptions on an MCP server, does an agent actually succeed more often? It is a regression
harness that runs a local agent model against two variants of a server and reports the change in
task success with a confidence interval ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

Try it (the lint step needs no LLM):

    pip install agentgauge-harness
    agentgauge lint examples/call_constraints_server_fixed.py
    agentgauge diff before_server.py after_server.py --tasks agentgauge_tasks.json

The install name and the CLI are documented in the [README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md). `diff` needs a model
(Ollama, default gemma2:9b) or a mock/replay run ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

What I measured, and what I did not:

- At 100 tasks per arm and 1 trial per task the minimum detectable effect is 8.5 percentage points
  at 80% power ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). Below that, the harness can answer "insufficient
  sensitivity" instead of a verdict; that happened in 21.6% of null runs ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).
- Only one lint rule has a validated effect on task success; the README says so in a
  per-rule table that includes the nulls ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). That rule flags a contradiction
  between a type and its enum, and it cost 13.3 to 28.9 points of task success across three small models
  ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).
- Across a pilot of ten public MCP servers, 0 of 9 with a testable confusable family showed the
  regime where better descriptions help. This is a lower bound from a small sample, not a
  population estimate ([paper](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md)).
- Scores depend on the judge model. The judge is pinned to llama3.1:8b and scores from different
  judges are not comparable ([CLAUDE.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/CLAUDE.md)).

One of my own published results was wrong. The paper reported 0%/0% for the google_workspace server
(116 tools). It was Ollama silently truncating the tool listing at its default 4096-token window;
with the window sized, both arms score 65% ([STATUS.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md)). I wrote up what happened
in the repo rather than quietly editing it.

Feedback on the statistics is the most useful thing to me. Apache-2.0 ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

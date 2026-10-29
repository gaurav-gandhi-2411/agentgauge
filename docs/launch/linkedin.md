> DRAFT. NOT POSTED. PREREQUISITE: merge `docs/gw-truncation-correction` before posting. Links point at paths
> as they will be on main after that merge.

Most advice about writing MCP tool descriptions is untested. I built AgentGauge to test it.

AgentGauge is an open-source harness that compares two versions of an MCP server and reports whether
the change moved real agent task success, with a confidence interval
([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). At 100 tasks per arm and one trial per task, the smallest effect it can
detect at 80% power is 8.5 percentage points; below that it says "insufficient sensitivity" rather
than guessing ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

What the measurements showed, including the unflattering parts:

- Only one lint rule has a validated effect on task success: the one that flags a
  type/enum contradiction cost 13.3 to 28.9 points across three small models
  ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).
- In a pilot of ten public servers, 0 of 9 with a testable confusable family were in the regime
  where better descriptions help. A small sample, so a lower bound
  ([paper](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md)).
- Scores depend on the judge model, which is pinned to llama3.1:8b, so they are not comparable
  across judges ([CLAUDE.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/CLAUDE.md)).

I also had to correct one of my own published results: a 0%/0% reading on a 116-tool server was
Ollama truncating the prompt at its default window, not a property of the model. With the window
sized, both arms score 65% ([STATUS.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md)).

Code, reports and the paper are in the repository: https://github.com/gaurav-gandhi-2411/agentgauge

#MCP #LLMEvaluation

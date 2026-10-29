> DRAFT. NOT POSTED. PREREQUISITE: merge `docs/gw-truncation-correction` before posting. Links point at paths
> as they will be on main after that merge.
> LinkedIn renders plain text only: sources are bare URLs in a reference list at the end.

I used to assume that rewriting MCP tool descriptions made agents better. I built AgentGauge to test
that assumption on my own servers.

AgentGauge is an open-source harness that compares two versions of an MCP server and reports whether
the change moved real agent task success, with a confidence interval (README). At 100 tasks per arm and
one trial per task, the smallest effect it can detect at 80% power is 8.5 percentage points, assuming
you write about 100 tasks of your own; below that it says "insufficient sensitivity" rather than
guessing (README, allocation report).

What the measurements showed, including the unflattering parts:

- Only one lint rule has a validated effect on task success: the one that flags a
  type/enum contradiction cost 13.3 to 28.9 points across three small models (README).
- In a pilot of ten public servers, 7 had a testable confusable family. Counting 2 earlier anchor
  servers, 0 of those 9 were in the regime where better descriptions help: the shipped descriptions
  fail a task and a hand-written oracle description recovers it. A small sample, so a lower bound; the
  sampled public servers skew toward documented ones (paper).
- Scores from the legacy `agentgauge scan` rubric depend on a judge model pinned to llama3.1:8b, so
  they are not comparable across judges (CLAUDE.md). Effects from `diff` are task success on the agent
  models I tested (gemma2:9b, llama3.1:8b, qwen2.5:7b) and may differ on other models.

I also had to correct one of my own published results: a 0%/0% reading on a 116-tool server was
Ollama truncating the prompt at its default window, not a property of the model. Rerunning with the
window sized, both arms gave 65% (13/20) in a small pilot of 4 tasks x 5 trials on gemma2:9b
(STATUS.md). I corrected the paper in place with a dated note and kept the raw fixtures. The window fix
is on the unmerged branch fix/ollama-num-ctx and is not on main yet (branch).

Code, reports and the paper are in the repository: https://github.com/gaurav-gandhi-2411/agentgauge

References:

README: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md
Allocation report: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/reports/v2_2_optimal_allocation.md
Paper: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md
STATUS.md: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md
CLAUDE.md: https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/CLAUDE.md
Branch: https://github.com/gaurav-gandhi-2411/agentgauge/blob/fix/ollama-num-ctx/agentgauge/providers.py

#MCP #LLMEvaluation

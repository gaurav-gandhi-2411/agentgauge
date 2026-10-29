> DRAFT. NOT POSTED. PREREQUISITE: merge `docs/gw-truncation-correction` before posting. Links point at paths
> as they will be on main after that merge.

# Did your tool-description change help? Measuring it, and one measurement I got wrong

<!-- BODY-START -->
If you maintain an MCP server, you eventually rewrite tool descriptions and hope an agent does better.
AgentGauge is an open-source harness that checks that hope. It runs a local agent model against two
variants of your server on the same tasks and reports the change in task success
([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

## What it measures

The primary command is `agentgauge diff`, a comparison of real task success between two variants
([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). A secondary command, `agentgauge lint`, is a deterministic defect linter
that needs no LLM ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). The two are separated on purpose: only one lint rule has
a validated causal effect on task success, so the linter alone cannot tell you a change helped
([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

## How the statistics work

Repeating a trial within a task carries almost no independent information (ICC=0.793), so the
harness allocates its budget to more tasks, not more repeats ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). At 100 tasks per
arm and 1 trial per task, the minimum detectable effect is 8.5 percentage points at 80% power
([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). When a change is smaller than that, the harness is built to say
`INSUFFICIENT_SENSITIVITY` rather than declare a winner ([harness](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/agentgauge/harness.py)).
Under the null that happens 21.6% of the time ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

## A worked example

The lint step runs with no model. On a bundled fixture the default view is clean, because its only
defects are rules measured to have no effect on task success ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)):

    pip install agentgauge-harness
    agentgauge lint examples/call_constraints_server_fixed.py
    No violations found.

For a real comparison you author tasks that never quote the gold tool name, then run
`agentgauge diff before_server.py after_server.py --tasks agentgauge_tasks.json`
([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). That needs a local Ollama model or a mock/replay run
([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

## What the audit gate catches

Every `diff` and `eval` run passes through `agentgauge audit` first, and a failing check blocks the result from being reported ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). Each check was seeded from a real artifact found while building the harness. One example: a scoring bug had inflated one effect to -76.7 to -80.0pp before it was corrected to a null ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). Null results are kept too: an argument-degradation study over 253 tasks found no practically significant effect in any of three models, and the README reports it as a null ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

## Limitations

Scores depend on the judge model. The judge is pinned to llama3.1:8b, and scores from a different
judge are not comparable ([CLAUDE.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/CLAUDE.md)). The agents under test are small local models.
In a pilot of ten public servers, 0 of 9 with a testable confusable family showed the regime where
better descriptions help; that is a lower bound from a small sample, not a population estimate
([paper](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md)). A failure-attribution feature exists but costs 1.01x to 20.24x a
full re-evaluation, so it is gated behind `--experimental` ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

## The google_workspace truncation lesson

The paper's pilot table reported 0% and 0% for a Google Workspace server with 116 tools, and read it
as a "catalog overwhelm" failure mode ([STATUS.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md)). That reading was wrong. Ollama was
silently truncating the roughly 7k-token tool listing at its default 4096-token window; a control
run at that window reproduced the 0%/0% ([STATUS.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md)). Rerunning with the window sized
gave 65% (13/20) in both arms, a difference of +0pp ([paper](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md)). The one
remaining failure is a genuine wrong-tool pick that the oracle description does not fix
([STATUS.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md)). The out-of-regime label stands, now for the reason of no recovery, and
the catalog-overwhelm claim is withdrawn ([paper](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md)).

The raw trial fixtures were left
untouched as the record of what was run ([STATUS.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md)). A guard that raises an error when
Ollama truncates a prompt is written on the branch
[fix/ollama-num-ctx](https://github.com/gaurav-gandhi-2411/agentgauge/blob/fix/ollama-num-ctx/agentgauge/providers.py)
but is not on main as of this draft.

The lesson is that a silent truncation looks exactly like a model failure. If a result is a clean
zero, check what the model actually saw before explaining it.

Code, reports and the paper: https://github.com/gaurav-gandhi-2411/agentgauge
<!-- BODY-END -->

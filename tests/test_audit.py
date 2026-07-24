"""Tests for agentgauge.audit (v2.4, Task 2) -- the standing pre-report
measurement-validity gate.

One test class per historical artifact class this project has actually hit,
each seeded with the real case (not a synthetic stand-in), per the task
brief's "a regression test per artifact class, seeded with the actual
historical case" instruction:

  1. Task/answer leakage -- reports/predictive_validity_study.md: early tasks
     were generated as f"Call '{tool.name}': {tool.description}", quoting the
     gold tool name verbatim.
  2. Tool-name ceiling -- reports/predictive_validity_study.md: the RW1 family
     (get_pull_request/get_pull_request_diff/get_pull_request_files) showed
     task_success_rate 0.95-1.00 across every description-quality arm.
  3. Zero-vector/empty-input degeneracy -- reports/predictive_validity_study.md:
     5 of 6 "before" fixer-pair fixtures have literally empty tool descriptions.
  4. RW1 self-descriptive-name confound -- same RW1 family; real, self-
     explanatory API tool names make description quality irrelevant.
  5. T18 subset-vs-catalog mismatch -- reports/v2_linter_evaluation.md: linting
     the 12-tool T18 subset instead of the full 60-tool catalog swung
     t18_q2b_server from 11 HIGH violations to 0.
  6. LCG index saturation -- already covered by
     tests/test_harness.py::TestBootstrapDeltaCI (not duplicated here).
  7. Pre/post-mutation scoring-key mismatch (artifact #7) -- the
     confusable_server_oracle::query_records param_renamed case
     (evals/fixtures/v2_3_advisory_audit.json / reports/v2_3_task1_advisory_audit.md):
     'field' renamed to 'field_v2' in the schema.
"""

from __future__ import annotations

from types import SimpleNamespace

from agentgauge.audit import (
    check_catalog_subset_mismatch,
    check_ceiling_floor,
    check_degenerate_metrics,
    check_empty_schema,
    check_empty_tasks,
    check_scoring_reference_consistency,
    check_task_leakage,
    run_audit,
)
from agentgauge.constraints import BlindTask, Constraint
from agentgauge.harness import DecomposedRate, TrialOutcome


def _tool(name: str, description: str, properties: dict) -> SimpleNamespace:
    return SimpleNamespace(
        name=name, description=description, inputSchema={"type": "object", "properties": properties}
    )


class TestTaskLeakage:
    """Historical case: agentgauge.tasks.generate_tasks() originally built task
    text as f"Call '{tool.name}': {tool.description}" -- quoting the gold tool
    name verbatim made selection trivial regardless of description quality."""

    def test_gold_tool_name_quoted_in_task_flagged(self) -> None:
        tasks = [
            BlindTask(
                tool_name="get_pull_request", description="Call 'get_pull_request': fetch a PR."
            )
        ]
        findings = check_task_leakage(tasks)
        assert len(findings) == 1
        assert findings[0].severity == "block"
        assert findings[0].check == "task_leakage"

    def test_anti_tautology_task_not_flagged(self) -> None:
        tasks = [
            BlindTask(
                tool_name="get_pull_request",
                description="Fetch details for pull request #42 in the payments repo.",
            )
        ]
        assert check_task_leakage(tasks) == []


class TestToolNameCeiling:
    """Historical case: the RW1 family (get_pull_request/get_pull_request_diff/
    get_pull_request_files) showed task_success_rate clustered at 0.95-1.00
    across every description-quality arm -- selection was solved by tool name
    alone, leaving no room to show a real description-quality effect."""

    def test_near_ceiling_rate_flagged(self) -> None:
        # 20/20 correct joint success, mirroring the RW1 family's measured 1.0.
        trials = [TrialOutcome("get_pull_request", "get_pull_request", 1.0) for _ in range(20)]
        rate = DecomposedRate.from_trials(trials)
        findings = check_ceiling_floor(rate, variant_label="rw1_arm_oracle")
        assert len(findings) == 1
        assert findings[0].severity == "warn"
        assert "ceiling" in findings[0].detail

    def test_mid_range_rate_not_flagged(self) -> None:
        # confusable_server's real measured spread (0.64 bad / 0.80 oracle) --
        # genuine room to show an effect, must not be flagged.
        trials = [TrialOutcome("query_records", "query_records", 1.0) for _ in range(16)] + [
            TrialOutcome("query_records", "query_records", 0.0) for _ in range(9)
        ]
        rate = DecomposedRate.from_trials(trials)
        assert check_ceiling_floor(rate, variant_label="confusable_server") == []


class TestEmptyInputDegeneracy:
    """Historical case: 5 of 6 'before' fixer-pair fixtures have literally
    empty tool descriptions by design -- embedding an empty string produced a
    zero-length vector, not a zero vector or an error, corrupting a
    similarity measurement. The general class: any empty description/schema
    makes whatever it touches meaningless to score."""

    def test_empty_tool_description_flagged(self) -> None:
        tools = [_tool("grounded_server_tool", "", {"value": {"type": "string"}})]
        tasks = [BlindTask(tool_name="grounded_server_tool", description="Do the thing.")]
        findings = check_empty_schema(tools, tasks, variant_label="before")
        assert any("empty description" in f.detail for f in findings)

    def test_empty_task_description_flagged(self) -> None:
        findings = check_empty_tasks([BlindTask(tool_name="some_tool", description="   ")])
        assert len(findings) == 1
        assert findings[0].severity == "block"

    def test_nonempty_description_not_flagged(self) -> None:
        tools = [_tool("t", "Does a real thing with real params.", {"x": {"type": "string"}})]
        tasks = [BlindTask(tool_name="t", description="Do the real thing with value x=5.")]
        assert check_empty_schema(tools, tasks, variant_label="before") == []
        assert check_empty_tasks(tasks) == []


class TestSelfDescriptiveNameConfound:
    """Historical case: RW1's real GitHub-mirror names (get_pull_request,
    get_pull_request_diff) are self-explanatory enough that selection is
    solved regardless of description quality -- same underlying mechanism as
    the ceiling check, exercised here via the full run_audit() entry point
    across a before/after pair to confirm the ceiling fires on BOTH sides
    when a name-driven ceiling is real (not just one arm)."""

    def test_ceiling_on_both_before_and_after(self) -> None:
        # Mirrors the real measured RW1 rates (1.0/1.0/0.9524/1.0 across arms,
        # not a literal uniform 1.0) across 3 real tool names from the family
        # (get_pull_request/_diff/_files) -- near-ceiling with genuine (if
        # small) variance, not a degenerate zero-variance corpus.
        tasks = [
            BlindTask(tool_name="get_pull_request", description="Fetch PR #7."),
            BlindTask(tool_name="get_pull_request_diff", description="Fetch the diff for PR #7."),
            BlindTask(
                tool_name="get_pull_request_files", description="List files changed in PR #7."
            ),
        ]
        before_trials = [
            TrialOutcome("get_pull_request", "get_pull_request", 1.0),
            TrialOutcome("get_pull_request_diff", "get_pull_request_diff", 1.0),
            TrialOutcome("get_pull_request_files", "get_pull_request_files", 1.0),
        ] * 7 + [
            TrialOutcome("get_pull_request_files", "get_pull_request_files", 0.0)
        ]  # 22 trials, 21/22 correct (0.955) -- near ceiling, not degenerate
        after_trials = before_trials
        report = run_audit(tasks, before_trials=before_trials, after_trials=after_trials)
        ceiling_labels = {
            f.detail.split("]")[0][1:] for f in report.findings if f.check == "ceiling_floor"
        }
        assert ceiling_labels == {"before", "after"}
        assert report.passed  # WARN only -- a real near-ceiling doesn't block, it just limits power


class TestCatalogSubsetMismatch:
    """Historical case: linting the predictive-validity study's cost-bounded
    12-tool T18 subset instead of the full 60-tool catalog swung
    t18_q2b_server from 11 HIGH violations to 0 -- legitimate sibling tool
    names from outside the filtered subset looked like unknown identifiers."""

    def test_subset_vs_full_catalog_flagged(self) -> None:
        before_tools = [_tool(f"t{i}", "d", {}) for i in range(12)]  # the 12-tool subset
        after_tools = [_tool(f"t{i}", "d", {}) for i in range(60)]  # the full catalog
        findings = check_catalog_subset_mismatch(before_tools, after_tools)
        assert len(findings) == 1
        assert findings[0].severity == "warn"
        assert findings[0].check == "catalog_subset_mismatch"

    def test_similar_sized_catalogs_not_flagged(self) -> None:
        before_tools = [_tool(f"t{i}", "d", {}) for i in range(58)]
        after_tools = [_tool(f"t{i}", "d", {}) for i in range(60)]
        assert check_catalog_subset_mismatch(before_tools, after_tools) == []


class TestDegenerateMetrics:
    """Zero variance across every trial in a corpus suggests the scoring
    function itself is constant, not that the server is uniformly good/bad."""

    def test_all_identical_scores_flagged(self) -> None:
        trials = [TrialOutcome("t", "t", 0.5) for _ in range(10)]
        findings = check_degenerate_metrics(trials, variant_label="after")
        assert len(findings) == 1
        assert findings[0].severity == "block"

    def test_varied_scores_not_flagged(self) -> None:
        trials = [TrialOutcome("t", "t", 1.0 if i % 2 == 0 else 0.0) for i in range(10)]
        assert check_degenerate_metrics(trials, variant_label="after") == []


class TestScoringReferenceConsistency:
    """Artifact #7, the seventh and most consequential artifact: a gold
    constraint's `param` name must exist in the schema of the variant it's
    actually scored against. Seeded with the real historical case --
    confusable_server_oracle's query_records tool, 'field' renamed to
    'field_v2' (evals/fixtures/v2_3_advisory_audit.json), which silently
    scored every correct agent response as a failure."""

    def test_renamed_property_flagged(self) -> None:
        tasks = [
            BlindTask(
                tool_name="query_records",
                description="Get all orders where the status field is set to 'pending'",
                constraints=[
                    Constraint(param="field", kind="contains", gold_value="status"),
                    Constraint(param="value", kind="contains", gold_value="pending"),
                ],
            )
        ]
        # the AFTER (mutated) schema: 'field' renamed to 'field_v2', matching
        # the real inject_param_renamed output for this exact instance.
        schema_by_tool = {
            "query_records": {"value": {"type": "string"}, "field_v2": {"type": "string"}}
        }
        findings = check_scoring_reference_consistency(tasks, schema_by_tool, variant_label="after")
        assert len(findings) == 1
        assert findings[0].severity == "block"
        assert "field" in findings[0].detail
        assert "field_v2" in findings[0].detail

    def test_matching_schema_not_flagged(self) -> None:
        tasks = [
            BlindTask(
                tool_name="query_records",
                description="Get all orders where the status field is set to 'pending'",
                constraints=[Constraint(param="field", kind="contains", gold_value="status")],
            )
        ]
        schema_by_tool = {
            "query_records": {"field": {"type": "string"}, "value": {"type": "string"}}
        }
        assert (
            check_scoring_reference_consistency(tasks, schema_by_tool, variant_label="before") == []
        )

    def test_wired_through_run_audit_blocks(self) -> None:
        tasks = [
            BlindTask(
                tool_name="query_records",
                description="Get all orders where the status field is set to 'pending'",
                constraints=[Constraint(param="field", kind="contains", gold_value="status")],
            )
        ]
        after_tools = [_tool("query_records", "d", {"field_v2": {"type": "string"}})]
        report = run_audit(tasks, after_tools=after_tools)
        assert not report.passed
        assert any(f.check == "scoring_reference_consistency" for f in report.blocking)


class TestAuditReport:
    def test_passed_true_with_only_warnings(self) -> None:
        from agentgauge.audit import AuditFinding, AuditReport

        report = AuditReport(findings=[AuditFinding("ceiling_floor", "warn", "d")])
        assert report.passed
        assert report.warnings and not report.blocking

    def test_passed_false_with_any_blocking_finding(self) -> None:
        from agentgauge.audit import AuditFinding, AuditReport

        report = AuditReport(
            findings=[
                AuditFinding("ceiling_floor", "warn", "d1"),
                AuditFinding("task_leakage", "block", "d2"),
            ]
        )
        assert not report.passed
        assert len(report.blocking) == 1

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
  8. Hallucinated fixture-authoring facts (artifact #8) -- the GitHub Issues
     fixture's update_issue_state::state_reason enum, originally missing
     GitHub's real 4th value 'duplicate' (reports/v2_5_task2_fixture_validation.md).
  9. Benchmark-construction diff-size confound (artifact #9) -- v0.5 Wave 1's
     injected-culprit attribution benchmark (agentgauge/attribution_benchmark.py):
     the true culprit's fixed-length defect sentence was smaller than 2 of 3
     decoy tiers by construction, giving a mean fractional rank ~0.66-0.73
     instead of the 0.5 a role-independent generator would produce
     (reports/v0_5_attribution_benchmark.md).
"""

from __future__ import annotations

from types import SimpleNamespace

from agentgauge.audit import (
    check_benchmark_construction_diffsize_bias,
    check_catalog_subset_mismatch,
    check_ceiling_floor,
    check_degenerate_metrics,
    check_empty_schema,
    check_empty_tasks,
    check_enum_schema_fidelity,
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


class TestEnumSchemaFidelity:
    """Artifact #8, the eighth artifact: an `enum` constraint's `gold_value`
    is only as trustworthy as whoever authored it, and nothing in a
    type-only schema can verify it. Seeded with the real historical case --
    the GitHub Issues fixture's `update_issue_state` tool
    (evals/fixtures/v2_4_corpus/github_issues_fixture.py): its `state_reason`
    enum constraints originally covered only 'completed'/'not_planned'/
    'reopened', omitting GitHub's real 4th value 'duplicate' -- an
    LLM-authoring gap the schema itself (type-only, no declared `enum` list)
    gave no way to catch (reports/v2_5_task2_fixture_validation.md)."""

    def test_enum_constraint_on_type_only_schema_flagged(self) -> None:
        tasks = [
            BlindTask(
                tool_name="update_issue_state",
                description="Close issue #45 since the reported bug has been fixed.",
                constraints=[Constraint(param="state_reason", kind="enum", gold_value="completed")],
            )
        ]
        schema_by_tool = {"update_issue_state": {"state_reason": {"type": "string"}}}
        findings = check_enum_schema_fidelity(tasks, schema_by_tool, variant_label="after")
        assert len(findings) == 1
        assert findings[0].severity == "warn"
        assert findings[0].check == "enum_schema_fidelity"
        assert "state_reason" in findings[0].detail
        assert "completed" in findings[0].detail

    def test_enum_constraint_with_declared_schema_enum_not_flagged(self) -> None:
        tasks = [
            BlindTask(
                tool_name="update_issue_state",
                description="Close issue #45 since the reported bug has been fixed.",
                constraints=[Constraint(param="state_reason", kind="enum", gold_value="completed")],
            )
        ]
        schema_by_tool = {
            "update_issue_state": {
                "state_reason": {
                    "type": "string",
                    "enum": ["completed", "not_planned", "duplicate", "reopened"],
                }
            }
        }
        assert check_enum_schema_fidelity(tasks, schema_by_tool, variant_label="after") == []

    def test_non_enum_constraint_not_flagged(self) -> None:
        tasks = [
            BlindTask(
                tool_name="query_records",
                description="Get all orders where the status field is set to 'pending'",
                constraints=[Constraint(param="field", kind="contains", gold_value="status")],
            )
        ]
        schema_by_tool = {"query_records": {"field": {"type": "string"}}}
        assert check_enum_schema_fidelity(tasks, schema_by_tool, variant_label="after") == []

    def test_wired_through_run_audit_warns_without_blocking(self) -> None:
        tasks = [
            BlindTask(
                tool_name="update_issue_state",
                description="Close issue #45 since the reported bug has been fixed.",
                constraints=[Constraint(param="state_reason", kind="enum", gold_value="completed")],
            )
        ]
        after_tools = [_tool("update_issue_state", "d", {"state_reason": {"type": "string"}})]
        report = run_audit(tasks, after_tools=after_tools)
        assert report.passed  # WARN only, never blocks a measurement
        assert any(f.check == "enum_schema_fidelity" for f in report.warnings)


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


class TestBenchmarkConstructionDiffsizeBias:
    """Artifact #9, the ninth artifact: `agentgauge.attribution_benchmark`'s ORIGINAL
    injected-culprit generator satisfied the two weaker confound-guard edge conditions (culprit
    not always positioned first; culprit not always the single largest-diff tool) while still
    having a real, systematic DISTRIBUTIONAL correlation between diff size and culprit-vs-decoy
    role -- the culprit's fixed-length defect sentence (~32-47 chars) was smaller than 2 of 3
    decoy tiers (medium ~65, large ~230) by construction, giving a mean fractional rank of
    ~0.66-0.73 (measured, `reports/v0_5_attribution_benchmark.md`) instead of the 0.5 a
    role-independent generator would produce. This check catches that class of bias directly, via
    a case's `.diff_chars`/`.true_culprit` shape, independent of any specific generator module."""

    def _biased_case(
        self, case_id: str, culprit_diff: int, decoy_diffs: list[int]
    ) -> SimpleNamespace:
        diff_chars = {"culprit": culprit_diff}
        diff_chars.update({f"decoy_{i}": d for i, d in enumerate(decoy_diffs)})
        return SimpleNamespace(case_id=case_id, true_culprit="culprit", diff_chars=diff_chars)

    def test_deliberately_biased_fixture_fires(self) -> None:
        """Mirrors the real pre-fix generator's characteristic shape: a small, near-constant
        culprit diff (~40 chars) against a decoy pool spanning small/medium/large tiers
        (6/65/230 chars) -- every case has the SAME three decoy diffs, so the culprit sits at
        fractional rank 2/3 ~= 0.667 in every one of 30 cases (matching the real measured
        ~0.66-0.73 pre-fix regime), well outside the [0.35, 0.65] pass band."""
        cases = [self._biased_case(f"c{i}", 40, [65, 230, 6]) for i in range(30)]
        findings = check_benchmark_construction_diffsize_bias(cases)
        assert len(findings) == 1
        assert findings[0].severity == "block"
        assert findings[0].check == "benchmark_construction_diffsize_bias"

    def test_unbiased_fixture_does_not_fire(self) -> None:
        """A generator where the culprit's diff is drawn from the SAME distribution as the
        decoys' (no structural correlation with role) must not fire -- the culprit rotates
        through each rank position evenly across cases."""
        pools = [[40, 65, 230], [230, 40, 65], [65, 230, 40], [40, 6, 65], [6, 40, 65]]
        cases = [self._biased_case(f"c{i}", pool[0], pool[1:]) for i, pool in enumerate(pools * 6)]
        findings = check_benchmark_construction_diffsize_bias(cases)
        assert findings == []

    def test_corrected_generate_benchmark_output_does_not_fire(self) -> None:
        """The real, fixed generator's actual output (n=50, seed=42) must not trip this check --
        the direct regression test that the artifact #9 fix in `agentgauge.attribution_benchmark`
        actually holds, using the check that would have caught it before this task, not just the
        module-local test in `tests/test_attribution_benchmark.py`."""
        from agentgauge.attribution_benchmark import generate_benchmark

        cases = generate_benchmark(n_cases=50, seed=42)
        findings = check_benchmark_construction_diffsize_bias(cases)
        assert findings == [], f"expected no finding on the corrected generator, got: {findings}"

    def test_insufficient_cases_returns_no_finding(self) -> None:
        """Fewer than `min_cases` valid (culprit + >=1 decoy) cases means there isn't enough data
        to assess the distribution -- returns [] (not enough data), not a false pass or block."""
        cases = [self._biased_case(f"c{i}", 40, [65, 230, 6]) for i in range(5)]
        assert check_benchmark_construction_diffsize_bias(cases, min_cases=20) == []


class TestRunAuditBenchmarkCases:
    """v0.5 Wave 1 Task 5a: `run_audit`'s optional `benchmark_cases` parameter wires
    `check_benchmark_construction_diffsize_bias` into the standing pre-report gate,
    for callers (`scripts/attribution_benchmark_report.py`) auditing injected-culprit
    benchmark cases rather than `BlindTask`/tool-based `diff`/`eval` inputs. `tasks=[]`
    and every other `run_audit` input defaulting to `None` must not itself produce any
    finding -- only the benchmark-case check should fire (or not) here."""

    def _biased_case(
        self, case_id: str, culprit_diff: int, decoy_diffs: list[int]
    ) -> SimpleNamespace:
        diff_chars = {"culprit": culprit_diff}
        diff_chars.update({f"decoy_{i}": d for i, d in enumerate(decoy_diffs)})
        return SimpleNamespace(case_id=case_id, true_culprit="culprit", diff_chars=diff_chars)

    def test_deliberately_biased_cases_fail_the_gate(self) -> None:
        """Same characteristic pre-fix shape as
        TestBenchmarkConstructionDiffsizeBias.test_deliberately_biased_fixture_fires, run through
        the full `run_audit` dispatcher rather than the standalone check function directly."""
        cases = [self._biased_case(f"c{i}", 40, [65, 230, 6]) for i in range(30)]
        report = run_audit(tasks=[], benchmark_cases=cases)
        assert report.passed is False
        assert any(
            f.check == "benchmark_construction_diffsize_bias" and f.severity == "block"
            for f in report.findings
        )

    def test_real_corrected_generator_output_passes_the_gate(self) -> None:
        """The real, fixed `agentgauge.attribution_benchmark.generate_benchmark()` output
        (n=50, seed=42) must clear `run_audit` cleanly -- this is the actual pipeline
        `scripts/attribution_benchmark_report.py` runs before reporting accuracy."""
        from agentgauge.attribution_benchmark import generate_benchmark

        cases = generate_benchmark(n_cases=50, seed=42)
        report = run_audit(tasks=[], benchmark_cases=cases)
        assert report.passed is True, f"expected a clean pass, got findings: {report.findings}"

    def test_benchmark_cases_none_by_default_is_unaffected(self) -> None:
        """Existing `BlindTask`/tool-based callers that never pass `benchmark_cases` see
        identical behavior to before this parameter existed -- no diffsize-bias finding
        appears when `benchmark_cases` is omitted."""
        tasks = [BlindTask(tool_name="get_item", description="Fetch the item.")]
        report = run_audit(tasks)
        assert not any(f.check == "benchmark_construction_diffsize_bias" for f in report.findings)

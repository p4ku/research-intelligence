"""
Comprehensive Tests for Reprocessed Pipeline Runs across Models, REST API, and FastMCP Tools.
Guarantees that reprocessed papers (linked via reprocessed_runs M2M) are correctly discovered,
counted, and returned across all endpoints and tools, preventing the '0 papers' bug.
"""

import json
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    ComponentRun,
    Paper,
    PaperMetric,
    ExtractionDefinition,
    Extraction,
    ResearchAgentProcess,
)
from mcp_server.tools.pipeline_runs.status import get_pipeline_run_status_logic
from mcp_server.tools.extractions.matrix import get_paper_extractions_matrix_logic, list_extractions_logic
from mcp_server.tools.agents.processes import get_research_agent_status_logic
from research_intelligence.tasks.step_7_reporting.narrative import generate_executive_narrative_report


class ReprocessedRunsAPIMCPTests(TestCase):
    """
    Validates that whenever a paper is reprocessed by a subsequent PipelineRun,
    both the REST API and FastMCP tools return the paper and its extractions accurately.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="test_lead",
            email="lead@schwarz.de",
            password="lead_password_123!"
        )
        self.workspace = Workspace.objects.create(
            name="Quantum Intelligence Hub",
            screening_llm_model="google/gemini-3.8-flash",
            signal_score_code="score = 0.5 * fit_score + 0.5 * 8.0\nreturn round(score * 10.0, 2)"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )

        # Extraction Definition
        self.extraction_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fidelity Benchmark",
            system_prompt="Extract benchmark fidelity metrics.",
            user_prompt_template="Analyze: {paper_text}",
            response_schema={"type": "object", "properties": {"metric": {"type": "string"}}},
            exit_metric="metric",
            is_active=True
        )

        # 1. Run 1: Initial Discovery
        self.run_1 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            current_stage="reporting",
            reprocess_existing=False,
            triggered_by=self.user,
            total_papers_fetched=1,
            total_papers_passed_screening=1,
            usd_cost=Decimal("0.0250"),
            tokens_consumed=15000,
        )

        # Paper 1: Initially discovered in Run 1
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run_1,
            hash_id="sha256_quantum_topological_paper",
            title="Fault-Tolerant Topological Quantum Computation",
            authors="Kitaev et al.",
            source_database="arxiv"
        )

        # PaperMetric for Run 1 (original score)
        self.metric_run_1 = PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.run_1,
            workspace=self.workspace,
            screening_status="full_text_passed",
            screening_reasoning="Breakthrough topological error threshold.",
            signal_score=80.0,
            signal_score_details={"formula": "base"}
        )

        self.extraction = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.extraction_def,
            category="metrics",
            fields_data={"metric": "Gate Fidelity", "value": "99.98%"},
            confidence_score=0.98,
        )

        # 2. Run 2: Reprocess Existing Corpus
        self.run_2 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            current_stage="reporting",
            reprocess_existing=True,
            triggered_by=self.user,
            total_papers_fetched=1,
            total_papers_passed_screening=1,
            usd_cost=Decimal("0.0150"),
            tokens_consumed=10000,
        )

        # Link Paper 1 as reprocessed in Run 2
        self.paper.reprocessed_runs.add(self.run_2)

        # PaperMetric for Run 2 (reprocessed higher score)
        self.metric_run_2 = PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.run_2,
            workspace=self.workspace,
            screening_status="full_text_passed",
            screening_reasoning="Reprocessed with newer topological models.",
            signal_score=94.5,
            signal_score_details={"formula": "reprocessed"}
        )

        # API Client setup
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_model_get_papers_resolves_both_initial_and_reprocessed(self):
        """
        Both run_1 and run_2 associate with the paper via PaperMetric,
        so get_papers() on each run returns the paper.
        """
        papers_run_1 = list(self.run_1.get_papers())
        papers_run_2 = list(self.run_2.get_papers())

        self.assertEqual(len(papers_run_1), 1)
        self.assertEqual(len(papers_run_2), 1)
        self.assertEqual(papers_run_1[0].id, self.paper.id)
        self.assertEqual(papers_run_2[0].id, self.paper.id)

    def test_rest_api_papers_endpoint_filters_reprocessed_run(self):
        """
        GET /api/papers/?pipeline_run={run_2.id} must return the reprocessed paper with run 2's score,
        while GET /api/papers/?pipeline_run={run_1.id} must return run 1's score.
        """
        resp_2 = self.client.get(f"/api/papers/?pipeline_run={self.run_2.id}")
        self.assertEqual(resp_2.status_code, 200)
        data_2 = resp_2.json()
        results_2 = data_2["results"] if isinstance(data_2, dict) and "results" in data_2 else data_2
        self.assertEqual(len(results_2), 1)
        self.assertEqual(results_2[0]["id"], str(self.paper.id))
        self.assertEqual(results_2[0]["signal_score"], 94.5, "Run 2 must see its own reprocessed signal score 94.5")

        resp_1 = self.client.get(f"/api/papers/?pipeline_run={self.run_1.id}")
        self.assertEqual(resp_1.status_code, 200)
        data_1 = resp_1.json()
        results_1 = data_1["results"] if isinstance(data_1, dict) and "results" in data_1 else data_1
        self.assertEqual(len(results_1), 1)
        self.assertEqual(results_1[0]["id"], str(self.paper.id))
        self.assertEqual(results_1[0]["signal_score"], 80.0, "Run 1 must preserve its original signal score 80.0 without corruption")

    def test_rest_api_extractions_endpoint_filters_reprocessed_run(self):
        """
        GET /api/extractions/?pipeline_run={run_2.id} must return extractions of reprocessed papers.
        """
        resp = self.client.get(f"/api/extractions/?pipeline_run={self.run_2.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        self.assertEqual(len(results), 1, "Reprocessed run must return extractions in /api/extractions/")
        self.assertEqual(results[0]["id"], str(self.extraction.id))

    def test_rest_api_pipeline_run_detail_serializer_counts(self):
        """
        GET /api/pipeline-runs/{run_2.id}/ must report papers_count=1 and extractions_count=1.
        """
        resp = self.client.get(f"/api/pipeline-runs/{self.run_2.id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("papers_count"), 1, "PipelineRunDetailSerializer must use get_papers() for papers_count")
        self.assertEqual(data.get("extractions_count"), 1, "PipelineRunDetailSerializer must use get_papers() for extractions_count")

    def test_mcp_tool_pipeline_run_status(self):
        """
        FastMCP get_pipeline_run_status_logic for run_2 must include papers preview and extractions count.
        """
        res_str = get_pipeline_run_status_logic(self.user, str(self.run_2.id))
        status_data = json.loads(res_str)

        self.assertEqual(status_data["total_papers_fetched"], 1)
        self.assertEqual(status_data["extractions_count"], 1)
        self.assertEqual(len(status_data.get("fetched_papers_preview", [])), 1)
        self.assertEqual(status_data["fetched_papers_preview"][0]["id"], str(self.paper.id))

    def test_mcp_tool_extractions_matrix(self):
        """
        FastMCP get_paper_extractions_matrix_logic and list_extractions_logic for run_2
        must return the extractions from reprocessed papers.
        """
        res_str = get_paper_extractions_matrix_logic(self.user, pipeline_run_id=str(self.run_2.id))
        matrix_data = json.loads(res_str)

        self.assertIn("papers", matrix_data)
        self.assertEqual(len(matrix_data["papers"]), 1)
        self.assertEqual(matrix_data["papers"][0]["paper_id"], str(self.paper.id))

        list_str = list_extractions_logic(self.user, pipeline_run_id=str(self.run_2.id))
        list_data = json.loads(list_str)
        self.assertEqual(len(list_data), 1)
        self.assertEqual(list_data[0]["id"], str(self.extraction.id))

    def test_mcp_tool_agent_process_status(self):
        """
        FastMCP get_research_agent_status_logic for an agent driving run_2 must report paper metrics.
        """
        proc = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run_2,
            name="Reprocess Agent",
            status="completed",
            triggered_by=self.user,
        )

        res_str = get_research_agent_status_logic(self.user, str(proc.id))
        proc_data = json.loads(res_str)

        self.assertIn("paper_metrics", proc_data)
        self.assertEqual(proc_data["paper_metrics"]["total_papers_fetched"], 1)
        self.assertEqual(proc_data["paper_metrics"]["extractions_count"], 1)

    def test_executive_narrative_report_includes_reprocessed_papers(self):
        """
        generate_executive_narrative_report for run_2 must include the reprocessed paper in highlights.
        """
        rep_result = generate_executive_narrative_report(self.run_2)
        self.assertTrue(rep_result["success"])

        from research_intelligence.models import NarrativeReport
        report = NarrativeReport.objects.get(pipeline_run=self.run_2)
        self.assertIn("Fault-Tolerant Topological Quantum Computation", report.content_markdown)
        self.assertIn("Signal Score: 94.50", report.content_markdown)

    def test_omitted_and_malformed_query_params_do_not_crash(self):
        """
        Verifies that omitting pipeline_run or passing 'undefined'/'null'/invalid-uuid
        does not crash with 500 error and handles cleanly.
        """
        # 1. Completely omitted:
        resp = self.client.get("/api/papers/")
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/extractions/")
        self.assertEqual(resp.status_code, 200)

        # 2. Frontend unselected states ('undefined', 'null', '') should be gracefully ignored (return all papers):
        for unselected in ["undefined", "null", ""]:
            resp = self.client.get(f"/api/papers/?pipeline_run={unselected}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            results = data["results"] if isinstance(data, dict) and "results" in data else data
            self.assertEqual(len(results), 1)

            resp_ext = self.client.get(f"/api/extractions/?pipeline_run={unselected}")
            self.assertEqual(resp_ext.status_code, 200)

        # 3. Explicit corrupt/invalid UUID string returns 0 results instead of crashing with 500:
        resp_corrupt = self.client.get("/api/papers/?pipeline_run=corrupt-bad-uuid-format")
        self.assertEqual(resp_corrupt.status_code, 200)
        data_corrupt = resp_corrupt.json()
        results_corrupt = data_corrupt["results"] if isinstance(data_corrupt, dict) and "results" in data_corrupt else data_corrupt
        self.assertEqual(len(results_corrupt), 0)

    def test_mcp_tools_with_omitted_or_malformed_parameters(self):
        """
        Verifies that MCP tools handle omitted and invalid parameters gracefully.
        """
        # list_extractions_logic without pipeline_run_id (only workspace_id)
        res_str = list_extractions_logic(self.user, workspace_id=str(self.workspace.id))
        data = json.loads(res_str)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)

        # get_paper_extractions_matrix_logic without pipeline_run_id (only workspace_id)
        res_str = get_paper_extractions_matrix_logic(self.user, workspace_id=str(self.workspace.id))
        data = json.loads(res_str)
        self.assertIn("papers", data)

        # get_paper_extractions_matrix_logic with invalid pipeline_run_id
        res_str = get_paper_extractions_matrix_logic(self.user, pipeline_run_id="invalid-uuid")
        data = json.loads(res_str)
        self.assertIn("error", data)

    def test_per_run_screening_and_benchmark_evaluations_isolation(self):
        """
        Validates that evaluations (screening_status, reasoning, benchmark flags, and labels)
        are completely isolated per pipeline run on PaperMetric, eliminating run-overwriting.
        """
        # Run 1: Rejected
        self.metric_run_1.screening_status = "rejected"
        self.metric_run_1.screening_reasoning = "Insufficient sample size in trial"
        self.metric_run_1.is_evaluation_benchmark = True
        self.metric_run_1.evaluation_label = "rejected"
        self.metric_run_1.save()

        # Run 2: Full text passed with new benchmark label
        self.metric_run_2.screening_status = "full_text_passed"
        self.metric_run_2.screening_reasoning = "Passed after methodology expansion"
        self.metric_run_2.is_evaluation_benchmark = True
        self.metric_run_2.evaluation_label = "passed"
        self.metric_run_2.save()

        # 1. Query Run 1 API: Must reflect Run 1 evaluations
        resp_1 = self.client.get(f"/api/papers/?pipeline_run={self.run_1.id}")
        self.assertEqual(resp_1.status_code, 200)
        data_1 = resp_1.json()
        results_1 = data_1["results"] if "results" in data_1 else data_1
        self.assertEqual(len(results_1), 1)
        p1 = results_1[0]
        self.assertEqual(p1["screening_status"], "rejected")
        self.assertEqual(p1["screening_reasoning"], "Insufficient sample size in trial")
        self.assertTrue(p1["is_evaluation_benchmark"])
        self.assertEqual(p1["evaluation_label"], "rejected")
        self.assertEqual(p1["signal_score"], 80.0)

        # 2. Query Run 2 API: Must reflect Run 2 evaluations on the SAME paper
        resp_2 = self.client.get(f"/api/papers/?pipeline_run={self.run_2.id}")
        self.assertEqual(resp_2.status_code, 200)
        data_2 = resp_2.json()
        results_2 = data_2["results"] if "results" in data_2 else data_2
        self.assertEqual(len(results_2), 1)
        p2 = results_2[0]
        self.assertEqual(p2["screening_status"], "full_text_passed")
        self.assertEqual(p2["screening_reasoning"], "Passed after methodology expansion")
        self.assertTrue(p2["is_evaluation_benchmark"])
        self.assertEqual(p2["evaluation_label"], "passed")
        self.assertEqual(p2["signal_score"], 94.5)

        # 3. Filter by screening_status per run
        resp_rej_1 = self.client.get(f"/api/papers/?pipeline_run={self.run_1.id}&screening_status=rejected")
        res_rej_1 = resp_rej_1.json()["results"] if "results" in resp_rej_1.json() else resp_rej_1.json()
        self.assertEqual(len(res_rej_1), 1)

        resp_rej_2 = self.client.get(f"/api/papers/?pipeline_run={self.run_2.id}&screening_status=rejected")
        res_rej_2 = resp_rej_2.json()["results"] if "results" in resp_rej_2.json() else resp_rej_2.json()
        self.assertEqual(len(res_rej_2), 0)

        resp_pass_2 = self.client.get(f"/api/papers/?pipeline_run={self.run_2.id}&screening_status=full_text_passed")
        res_pass_2 = resp_pass_2.json()["results"] if "results" in resp_pass_2.json() else resp_pass_2.json()
        self.assertEqual(len(res_pass_2), 1)

        # get_pipeline_run_status_logic with invalid UUID
        err_msg = get_pipeline_run_status_logic(self.user, "bad-uuid")
        self.assertIn("not a valid UUID format", err_msg)

    def test_rest_api_papers_endpoint_includes_run_id_and_supports_run_id_param(self):
        """
        GET /api/papers/?run_id={run_2.id} returns paper with pipeline_run_id and run_id.
        """
        resp = self.client.get(f"/api/papers/?run_id={self.run_2.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data["results"] if "results" in data else data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["pipeline_run_id"], str(self.run_2.id))
        self.assertEqual(results[0]["run_id"], str(self.run_2.id))
        self.assertEqual(results[0]["signal_score"], 94.5)

    def test_rest_api_paper_metrics_dedicated_endpoint(self):
        """
        GET /api/paper-metrics/ exposes standalone PaperMetric items filtered by pipeline_run or run_id.
        """
        resp = self.client.get(f"/api/paper-metrics/?pipeline_run={self.run_2.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data["results"] if "results" in data else data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["paper"], str(self.paper.id))
        self.assertEqual(results[0]["pipeline_run"], str(self.run_2.id))
        self.assertEqual(results[0]["signal_score"], 94.5)
        self.assertEqual(results[0]["screening_status"], "full_text_passed")

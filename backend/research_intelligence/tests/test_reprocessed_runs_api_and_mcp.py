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
            source_database="arxiv",
            screening_status="full_text_passed",
            signal_score=94.5,
            screening_reasoning="Breakthrough topological error threshold."
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

        # API Client setup
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_model_get_papers_resolves_both_initial_and_reprocessed(self):
        """
        Paper.objects.filter(pipeline_run=run_2) must be EMPTY, but
        run_2.get_papers() must return the reprocessed paper.
        """
        raw_filter_count = Paper.objects.filter(pipeline_run=self.run_2).count()
        self.assertEqual(raw_filter_count, 0, "Direct FK filter on run_2 should be 0 because paper was created in run_1")

        papers_run_1 = list(self.run_1.get_papers())
        papers_run_2 = list(self.run_2.get_papers())

        self.assertEqual(len(papers_run_1), 1)
        self.assertEqual(len(papers_run_2), 1)
        self.assertEqual(papers_run_1[0].id, self.paper.id)
        self.assertEqual(papers_run_2[0].id, self.paper.id)

    def test_rest_api_papers_endpoint_filters_reprocessed_run(self):
        """
        GET /api/papers/?pipeline_run={run_2.id} must return the reprocessed paper.
        """
        resp = self.client.get(f"/api/papers/?pipeline_run={self.run_2.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        self.assertEqual(len(results), 1, "Reprocessed run must return its reprocessed papers in /api/papers/")
        self.assertEqual(results[0]["id"], str(self.paper.id))
        self.assertEqual(results[0]["title"], self.paper.title)

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

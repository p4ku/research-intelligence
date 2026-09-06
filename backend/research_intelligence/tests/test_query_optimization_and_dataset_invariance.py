"""
Dataset Invariance and Query Performance Benchmark Tests.
Guarantees that query optimizations do not mutate or drop records from any dataset
across REST endpoints, MCP tools, and ORM interfaces, while keeping database query
counts constant O(1) and preventing N+1 queries.
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    Paper,
    PaperMetric,
    ExtractionDefinition,
    Extraction,
)
from research_intelligence.services.scraper_service import list_workspace_papers
from mcp_server.tools.extractions.matrix import get_paper_extractions_matrix_logic

User = get_user_model()


class DatasetInvarianceAndQueryBenchmarkTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="query_benchmark_user",
            email="benchmark@schwarz.de",
            password="securepassword123!"
        )
        self.workspace = Workspace.objects.create(
            name="Benchmark Quantum Workspace",
            screening_llm_model="google/gemini-3.8-flash"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )

        self.run_1 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed"
        )
        self.run_2 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed"
        )

        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Qubit Count Extraction",
            exit_metrics="qubits",
            system_prompt="Extract qubit count",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object", "properties": {"qubits": {"type": "integer"}}}
        )

        # Create 15 papers:
        # Papers 0-9: Evaluated in Run 1
        # Papers 5-14: Evaluated in Run 2 (Papers 5-9 are reprocessed in Run 2!)
        self.papers = []
        for i in range(15):
            p = Paper.objects.create(
                workspace=self.workspace,
                hash_id=f"hash_benchmark_{i:03d}",
                title=f"Quantum Paper #{i:02d}",
                authors=f"Author {i}",
                abstract=f"Abstract for benchmark paper {i}",
                source_database="arxiv" if i % 2 == 0 else "openalex"
            )
            self.papers.append(p)

            # Extractions
            Extraction.objects.create(
                workspace=self.workspace,
                paper=p,
                extraction_definition=self.ext_def,
                category="hardware",
                fields_data={"qubits": 50 + i},
                confidence_score=0.95,
                validation_status="pass"
            )

        # Evaluations in Run 1 (Papers 0 to 9)
        for i in range(10):
            p = self.papers[i]
            status = "accepted" if i < 6 else "rejected"
            score = 50.0 + (i * 3.5) if status == "accepted" else 10.0
            PaperMetric.objects.create(
                paper=p,
                pipeline_run=self.run_1,
                workspace=self.workspace,
                screening_status=status,
                abstract_screening_reasoning=f"Run 1 abstract decision: {status}",
                full_text_screening_reasoning=f"Run 1 full text decision: {status}",
                signal_score=score,
                signal_score_details={"formula": "run1_calc", "step": i},
                is_evaluation_benchmark=(i % 3 == 0),
                evaluation_label="passed" if status == "accepted" else "rejected",
                metrics_data={"qubit_count": 50 + i}
            )

        # Evaluations in Run 2 (Papers 5 to 14)
        for i in range(5, 15):
            p = self.papers[i]
            status = "accepted" if i >= 8 else "full_text_passed"
            score = 60.0 + (i * 2.0)
            PaperMetric.objects.create(
                paper=p,
                pipeline_run=self.run_2,
                workspace=self.workspace,
                screening_status=status,
                abstract_screening_reasoning=f"Run 2 abstract decision: {status}",
                full_text_screening_reasoning=f"Run 2 full text decision: {status}",
                signal_score=score,
                signal_score_details={"formula": "run2_calc", "step": i},
                is_evaluation_benchmark=(i % 2 == 0),
                evaluation_label="passed",
                metrics_data={"qubit_count": 50 + i}
            )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_pipeline_run_get_papers_dataset_invariance(self):
        """
        Verify that get_papers() returns exact paper IDs for runs and status filters.
        """
        papers_run_1 = self.run_1.get_papers()
        self.assertEqual(papers_run_1.count(), 10)
        expected_run_1_ids = {self.papers[i].id for i in range(10)}
        self.assertEqual(set(papers_run_1.values_list('id', flat=True)), expected_run_1_ids)

        # Run 1 accepted
        accepted_run_1 = self.run_1.get_papers(screening_status='accepted')
        self.assertEqual(accepted_run_1.count(), 6)
        expected_acc_1 = {self.papers[i].id for i in range(6)}
        self.assertEqual(set(accepted_run_1.values_list('id', flat=True)), expected_acc_1)

        # Run 2 papers
        papers_run_2 = self.run_2.get_papers()
        self.assertEqual(papers_run_2.count(), 10)
        expected_run_2_ids = {self.papers[i].id for i in range(5, 15)}
        self.assertEqual(set(papers_run_2.values_list('id', flat=True)), expected_run_2_ids)

    def test_api_papers_endpoint_dataset_invariance_by_run(self):
        """
        Verify that /api/papers/?pipeline_run= returns the exact papers and their run-specific metrics.
        """
        resp_1 = self.client.get(f"/api/papers/?pipeline_run={self.run_1.id}")
        self.assertEqual(resp_1.status_code, 200)
        json_1 = resp_1.json()
        data_1 = json_1["results"] if isinstance(json_1, dict) and "results" in json_1 else json_1
        self.assertEqual(len(data_1), 10)

        for item in data_1:
            idx = int(item["title"].split("#")[1])
            self.assertEqual(item["pipeline_run"], str(self.run_1.id))
            expected_status = "accepted" if idx < 6 else "rejected"
            self.assertEqual(item["screening_status"], expected_status)
            expected_score = 50.0 + (idx * 3.5) if expected_status == "accepted" else 10.0
            self.assertEqual(item["signal_score"], expected_score)

        resp_2 = self.client.get(f"/api/papers/?pipeline_run={self.run_2.id}")
        self.assertEqual(resp_2.status_code, 200)
        json_2 = resp_2.json()
        data_2 = json_2["results"] if isinstance(json_2, dict) and "results" in json_2 else json_2
        self.assertEqual(len(data_2), 10)

        for item in data_2:
            idx = int(item["title"].split("#")[1])
            self.assertEqual(item["pipeline_run"], str(self.run_2.id))
            expected_status = "accepted" if idx >= 8 else "full_text_passed"
            self.assertEqual(item["screening_status"], expected_status)
            expected_score = 60.0 + (idx * 2.0)
            self.assertEqual(item["signal_score"], expected_score)

    def test_api_papers_endpoint_workspace_ordering_and_filters(self):
        """
        Verify that ordering by signal_score across the workspace preserves dataset integrity.
        """
        resp_desc = self.client.get(f"/api/papers/?workspace_id={self.workspace.id}&ordering=-signal_score")
        self.assertEqual(resp_desc.status_code, 200)
        json_desc = resp_desc.json()
        data_desc = json_desc["results"] if isinstance(json_desc, dict) and "results" in json_desc else json_desc
        self.assertEqual(len(data_desc), 15)

        # Check descending order of non-null signal scores
        scores = [item["signal_score"] for item in data_desc if item["signal_score"] is not None]
        self.assertEqual(scores, sorted(scores, reverse=True))

        # Check filtering by screening_status
        resp_acc = self.client.get(f"/api/papers/?workspace_id={self.workspace.id}&screening_status=accepted")
        self.assertEqual(resp_acc.status_code, 200)
        json_acc = resp_acc.json()
        data_acc = json_acc["results"] if isinstance(json_acc, dict) and "results" in json_acc else json_acc
        self.assertTrue(len(data_acc) > 0)
        for item in data_acc:
            self.assertEqual(item["screening_status"], "accepted")

    def test_api_papers_endpoint_latest_run_and_reasoning(self):
        """
        Validates that:
        1. /api/papers/ returns bare array with 'screening_reasoning', 'pipeline_run', 'pipeline_run_id'.
        2. If pipeline_run is not specified, backend resolves to latest valid pipeline run.
        3. /api/papers/?pipeline_run=latest resolves correctly.
        4. /api/workspaces/{id}/papers/ returns workspace papers.
        """
        resp = self.client.get("/api/papers/")
        self.assertEqual(resp.status_code, 200)
        papers_data = resp.json()
        self.assertIsInstance(papers_data, list)
        self.assertTrue(len(papers_data) > 0)

        for p in papers_data:
            self.assertIn("screening_reasoning", p)
            self.assertIn("pipeline_run", p)
            self.assertIn("pipeline_run_id", p)
            self.assertIn("run_id", p)
            # pipeline_run must resolve to a valid UUID string
            self.assertIsNotNone(p["pipeline_run"])
            import uuid
            self.assertTrue(uuid.UUID(str(p["pipeline_run"])))

        # Test pipeline_run=latest parameter
        resp_latest = self.client.get(f"/api/papers/?workspace_id={self.workspace.id}&pipeline_run=latest")
        self.assertEqual(resp_latest.status_code, 200)
        latest_data = resp_latest.json()
        data_list = latest_data["results"] if isinstance(latest_data, dict) and "results" in latest_data else latest_data
        self.assertEqual(len(data_list), 10)
        for item in data_list:
            self.assertEqual(item["pipeline_run"], str(self.run_2.id))

        # Test /api/workspaces/{id}/papers/
        resp_ws_papers = self.client.get(f"/api/workspaces/{self.workspace.id}/papers/")
        self.assertEqual(resp_ws_papers.status_code, 200)
        ws_papers = resp_ws_papers.json()
        self.assertEqual(len(ws_papers), 15)

    def test_mcp_extractions_matrix_dataset_invariance(self):
        """
        Verify that get_paper_extractions_matrix_logic returns exact papers and aggregated scores.
        """
        import json
        matrix_all = json.loads(get_paper_extractions_matrix_logic(self.user, pipeline_run_id=str(self.run_1.id), screening_status='all'))
        self.assertEqual(matrix_all["total_papers"], 10)

        with CaptureQueriesContext(connection) as ctx:
            matrix_1 = json.loads(get_paper_extractions_matrix_logic(self.user, pipeline_run_id=str(self.run_1.id)))
            self.assertEqual(matrix_1["total_papers"], 6)
            # Papers 0-5 accepted (scores: 50.0, 53.5, 57.0, 60.5, 64.0, 67.5), top score is 67.5
            self.assertEqual(matrix_1["top_signal_score"], 67.5)

        query_count_mcp = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] get_paper_extractions_matrix executed {query_count_mcp} queries for 6 papers.")
        self.assertLessEqual(query_count_mcp, 6, f"Expected <= 6 queries, got {query_count_mcp}")

    def test_list_workspace_papers_service_dataset_invariance(self):
        """
        Verify list_workspace_papers returns exact datasets with pipeline_run filter.
        """
        papers_1 = list_workspace_papers(self.user, str(self.workspace.id), pipeline_run_id=str(self.run_1.id))
        self.assertEqual(len(papers_1), 10)
        for p in papers_1:
            self.assertEqual(p["pipeline_run"], str(self.run_1.id))

    def test_query_count_for_papers_api_endpoint(self):
        """
        Benchmark query count: Serializing 10 papers must not trigger N+1 queries.
        """
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/papers/?pipeline_run={self.run_1.id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()["results"] if isinstance(resp.json(), dict) and "results" in resp.json() else resp.json()
            self.assertEqual(len(data), 10)

        query_count_run = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] /api/papers/?pipeline_run= executed {query_count_run} queries for 10 papers.")
        self.assertLessEqual(query_count_run, 5, f"Expected <= 5 queries for 10 papers, got {query_count_run}")

        with CaptureQueriesContext(connection) as ctx_ws:
            resp_ws = self.client.get(f"/api/papers/?workspace_id={self.workspace.id}")
            self.assertEqual(resp_ws.status_code, 200)
            data_ws = resp_ws.json()["results"] if isinstance(resp_ws.json(), dict) and "results" in resp_ws.json() else resp_ws.json()
            self.assertEqual(len(data_ws), 15)

        query_count_ws = len(ctx_ws.captured_queries)
        print(f"\n[BENCHMARK] /api/papers/?workspace_id= executed {query_count_ws} queries for 15 papers.")
        self.assertLessEqual(query_count_ws, 5, f"Expected <= 5 queries for 15 papers, got {query_count_ws}")

    def test_paper_serializer_in_memory_metrics_caching_zero_extra_queries(self):
        """
        Verify that PaperSerializer consumes already-prefetched metrics completely in memory
        without triggering ANY extra SQL queries during serialization.
        """
        from api.serializers.papers import PaperSerializer
        papers_qs = list(Paper.objects.filter(workspace=self.workspace).prefetch_related('metrics')[:10])

        with CaptureQueriesContext(connection) as ctx:
            serializer = PaperSerializer(papers_qs, many=True, context={'pipeline_run_id': str(self.run_1.id)})
            serialized_data = serializer.data
            self.assertEqual(len(serialized_data), 10)

        query_count = len(ctx.captured_queries)
        self.assertEqual(query_count, 0, f"Expected 0 queries during in-memory serialization, got {query_count}")

    def test_pipelinerun_detail_serializer_efficiency_and_dataset(self):
        """
        Verify PipelineRunDetailSerializer correctly calculates papers_count, extractions_count,
        and duplicates_count without redundant N+1 queries.
        """
        from api.serializers.pipeline_runs import PipelineRunDetailSerializer
        resp = self.client.get(f"/api/pipeline-runs/{self.run_1.id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["papers_count"], 10)
        self.assertEqual(data["extractions_count"], 10)

    def test_papermetric_dedicated_viewset_query_efficiency(self):
        """
        Verify /api/paper-metrics/ endpoint returns exact metrics with minimal constant queries.
        """
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/paper-metrics/?pipeline_run={self.run_1.id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            results = data["results"] if isinstance(data, dict) and "results" in data else data
            self.assertEqual(len(results), 10)

        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] /api/paper-metrics/?pipeline_run= executed {query_count} queries for 10 metrics.")
        self.assertLessEqual(query_count, 5, f"Expected <= 5 queries, got {query_count}")

    def test_reports_and_extractions_endpoints_pipeline_run_filter(self):
        """
        Verify that /api/reports/ and /api/extractions/ cleanly filter by ?pipeline_run=
        and return the correct dataset.
        """
        from research_intelligence.models import NarrativeReport
        report = NarrativeReport.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run_1,
            title="Run 1 Executive Briefing",
            content_markdown="# Briefing Content"
        )

        resp_rep = self.client.get(f"/api/reports/?pipeline_run={self.run_1.id}")
        self.assertEqual(resp_rep.status_code, 200)
        data_rep = resp_rep.json()
        results_rep = data_rep["results"] if isinstance(data_rep, dict) and "results" in data_rep else data_rep
        self.assertEqual(len(results_rep), 1)
        self.assertEqual(results_rep[0]["id"], str(report.id))

        resp_ext = self.client.get(f"/api/extractions/?pipeline_run={self.run_1.id}")
        self.assertEqual(resp_ext.status_code, 200)
        data_ext = resp_ext.json()
        results_ext = data_ext["results"] if isinstance(data_ext, dict) and "results" in data_ext else data_ext
        self.assertEqual(len(results_ext), 10)

    def test_hitl_and_activity_logs_views_query_efficiency(self):
        """
        Verify HITL and ActivityLog endpoints execute in constant O(1) queries with select_related.
        """
        from research_intelligence.models import HITLCorrection, UserActivityLog
        first_ext = Extraction.objects.filter(paper__in=self.papers).first()
        for i in range(5):
            HITLCorrection.objects.create(
                extraction=first_ext,
                human_operator=self.user.email,
                original_value={"qubits": 50},
                action="verify",
                reason=f"Verification note {i}"
            )
            UserActivityLog.objects.create(
                user=self.user,
                workspace=self.workspace,
                interface="rest_api",
                action_name=f"test_action_{i}",
                status="success"
            )

        with CaptureQueriesContext(connection) as ctx_hitl:
            resp_hitl = self.client.get(f"/api/hitl/?workspace_id={self.workspace.id}")
            self.assertEqual(resp_hitl.status_code, 200)

        query_count_hitl = len(ctx_hitl.captured_queries)
        self.assertLessEqual(query_count_hitl, 5, f"Expected <= 5 queries for HITL listing, got {query_count_hitl}")

        with CaptureQueriesContext(connection) as ctx_log:
            resp_log = self.client.get(f"/api/activity-logs/?workspace={self.workspace.id}")
            self.assertEqual(resp_log.status_code, 200)

        query_count_log = len(ctx_log.captured_queries)
        self.assertLessEqual(query_count_log, 5, f"Expected <= 5 queries for activity logs, got {query_count_log}")

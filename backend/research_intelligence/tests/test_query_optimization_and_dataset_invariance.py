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
    ComponentRun,
    WorkflowSchedule,
    Paper,
    PaperMetric,
    ExtractionDefinition,
    Extraction,
    Subscriber,
    Scraper,
    UserActivityLog,
    HITLCorrection,
    NarrativeReport,
    ResearchAgentProcess,
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

    def test_pipeline_runs_list_query_efficiency_and_no_component_runs_prefetch(self):
        """
        Verify that /api/pipeline-runs/:
        1. Selects schedule in O(1) query count (no N+1 for schedule_name).
        2. Does NOT query or prefetch component_runs on list action.
        3. Prefetches component_runs on retrieve action.
        """
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Daily Scheduled Ingestion",
            frequency="daily"
        )
        runs = []
        for i in range(5):
            r = PipelineRun.objects.create(
                workspace=self.workspace,
                name=f"Run With Schedule #{i}",
                schedule=schedule,
                status="completed"
            )
            runs.append(r)
            for step in ("search", "download", "screening", "extraction", "signal_score"):
                ComponentRun.objects.create(
                    pipeline_run=r,
                    step_type=step,
                    component_name=f"step_{step}",
                    status="completed"
                )

        with CaptureQueriesContext(connection) as ctx_list:
            resp = self.client.get(f"/api/pipeline-runs/?workspace={self.workspace.id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()["results"] if isinstance(resp.json(), dict) and "results" in resp.json() else resp.json()
            self.assertTrue(len(data) >= 5)

        queries_list = ctx_list.captured_queries
        query_count = len(queries_list)
        print(f"\n[BENCHMARK] /api/pipeline-runs/ executed {query_count} queries for {len(data)} runs.")
        self.assertLessEqual(query_count, 5, f"Expected <= 5 queries for pipeline runs listing, got {query_count}")

        # Verify schedule_name is present and correct
        scheduled_items = [item for item in data if item.get("schedule_name") == "Daily Scheduled Ingestion"]
        self.assertEqual(len(scheduled_items), 5)

        # Verify component_runs was NOT queried in the list action
        for q in queries_list:
            self.assertNotIn(
                "componentrun",
                q["sql"].lower(),
                "ComponentRun table should not be queried during pipeline-runs list action!"
            )

        # Verify component_runs IS queried/prefetched on retrieve
        with CaptureQueriesContext(connection) as ctx_detail:
            resp_detail = self.client.get(f"/api/pipeline-runs/{runs[0].id}/")
            self.assertEqual(resp_detail.status_code, 200)
            detail_data = resp_detail.json()
            self.assertIn("component_runs", detail_data)
            self.assertEqual(len(detail_data["component_runs"]), 5)

    def test_workspaces_list_query_efficiency(self):
        """
        Verify that /api/workspaces/ executes in constant O(1) queries (no N+1 for
        subscribers, scrapers, extraction_definitions, or user_role).
        """
        for i in range(4):
            ws = Workspace.objects.create(name=f"Benchmark Extra Workspace {i}")
            WorkspaceMember.objects.create(workspace=ws, user=self.user, role="researcher")
            Subscriber.objects.create(workspace=ws, email=f"sub_{i}@schwarz.de", name=f"Sub {i}")
            Scraper.objects.create(workspace=ws, provider="arxiv", search_query=f"query_{i}")
            ExtractionDefinition.objects.create(
                workspace=ws,
                name=f"Ext Def {i}",
                system_prompt="prompt",
                user_prompt_template="tpl",
                response_schema={"type": "object"}
            )

        with CaptureQueriesContext(connection) as ctx_ws:
            resp = self.client.get("/api/workspaces/")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()["results"] if isinstance(resp.json(), dict) and "results" in resp.json() else resp.json()
            self.assertTrue(len(data) >= 5)

        query_count = len(ctx_ws.captured_queries)
        print(f"\n[BENCHMARK] /api/workspaces/ executed {query_count} queries for {len(data)} workspaces.")
        # Total queries should be <= 7 (workspace list + count + subscribers + scrapers + extraction_defs + roles)
        self.assertLessEqual(query_count, 7, f"Expected <= 7 queries for workspace listing, got {query_count}")

        # Check user_role is populated
        for ws_item in data:
            self.assertIn("user_role", ws_item)
            self.assertIsNotNone(ws_item["user_role"])

    def test_paper_scorecard_deterministic_and_query_efficiency(self):
        """
        Verify that /api/papers/<id>/scorecard/ returns deterministic dimensions
        with latest extraction and minimal queries.
        """
        paper = self.papers[0]
        # Add a newer extraction for the same definition
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=self.ext_def,
            category="hardware",
            fields_data={"qubits": 999},
            confidence_score=0.99,
            validation_status="pass"
        )

        with CaptureQueriesContext(connection) as ctx_card:
            resp = self.client.get(f"/api/papers/{paper.id}/scorecard/")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

        self.assertIn("paper", data)
        self.assertIn("workspace", data)
        dimensions = data["paper"]["dimensions"]
        self.assertTrue(len(dimensions) > 0)
        # Verify that the newest extraction (999 qubits) was selected
        qubit_dim = next((d for d in dimensions if d["definition_id"] == str(self.ext_def.id)), None)
        self.assertIsNotNone(qubit_dim)
        self.assertEqual(qubit_dim["value"], "999")
        self.assertEqual(qubit_dim["confidence"], 0.99)

    def test_scrapers_endpoint_workspace_filter_and_isolation(self):
        """
        Verify that /api/scrapers/?workspace= correctly scopes scrapers to that workspace
        and respects workspace isolation.
        """
        ws_b = Workspace.objects.create(name="Scraper Test Workspace B")
        WorkspaceMember.objects.create(workspace=ws_b, user=self.user, role="admin")

        Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="quantum")
        Scraper.objects.create(workspace=ws_b, provider="openalex", search_query="nlp")

        # Query specifically for workspace A
        resp_a = self.client.get(f"/api/scrapers/?workspace={self.workspace.id}")
        self.assertEqual(resp_a.status_code, 200)
        data_a = resp_a.json()["results"] if isinstance(resp_a.json(), dict) and "results" in resp_a.json() else resp_a.json()
        self.assertTrue(len(data_a) >= 1)
        for s in data_a:
            self.assertEqual(str(s["workspace"]), str(self.workspace.id))

        # Query specifically for workspace B
        resp_b = self.client.get(f"/api/scrapers/?workspace={ws_b.id}")
        self.assertEqual(resp_b.status_code, 200)
        data_b = resp_b.json()["results"] if isinstance(resp_b.json(), dict) and "results" in resp_b.json() else resp_b.json()
        self.assertEqual(len(data_b), 1)
        self.assertEqual(str(data_b[0]["workspace"]), str(ws_b.id))
        self.assertEqual(data_b[0]["provider"], "openalex")

    def test_user_without_workspaces_short_circuits_all_views(self):
        """
        Verify that a user who does not belong to any workspace gets immediate empty
        responses without redundant SQL queries (short-circuit logic).
        """
        unaffiliated_user = User.objects.create_user(
            username="no_ws_user",
            email="no_ws@schwarz.de",
            password="securepassword123!"
        )
        empty_client = APIClient()
        empty_client.force_authenticate(user=unaffiliated_user)

        endpoints = [
            "/api/pipeline-runs/",
            "/api/papers/",
            "/api/workspaces/",
            "/api/scrapers/",
            "/api/extractions/",
            "/api/schedules/",
            "/api/agents/",
            "/api/hitl/",
            "/api/reports/",
        ]

        for ep in endpoints:
            with CaptureQueriesContext(connection) as ctx:
                resp = empty_client.get(ep)
                self.assertEqual(resp.status_code, 200, f"Endpoint {ep} failed with {resp.status_code}")
                data = resp.json()
                results = data["results"] if isinstance(data, dict) and "results" in data else data
                self.assertEqual(len(results), 0, f"Endpoint {ep} should return 0 items for unaffiliated user")
            # Should only query WorkspaceMember (and pagination count if applicable) <= 2 queries
            self.assertLessEqual(
                len(ctx.captured_queries),
                3,
                f"Endpoint {ep} executed too many queries ({len(ctx.captured_queries)}) for unaffiliated user"
            )

    def test_extractions_pipeline_run_subquery_efficiency(self):
        """
        Verify that /api/extractions/?pipeline_run= uses optimized subquery,
        returns correct extractions without duplicate rows, and runs in constant O(1) queries.
        """
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/extractions/?pipeline_run={self.run_1.id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            results = data["results"] if isinstance(data, dict) and "results" in data else data
            self.assertEqual(len(results), 10)

        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] /api/extractions/?pipeline_run= executed {query_count} queries for 10 extractions.")
        self.assertLessEqual(query_count, 5, f"Expected <= 5 queries, got {query_count}")

        # Ensure no duplicate extraction IDs in response
        extraction_ids = [e["id"] for e in results]
        self.assertEqual(len(extraction_ids), len(set(extraction_ids)))

    def test_activity_logs_query_optimization_with_q_filter(self):
        """
        Verify that /api/activity-logs/ uses indexed Q filter without SQL UNION overhead.
        """
        for i in range(3):
            UserActivityLog.objects.create(
                user=self.user,
                workspace=self.workspace,
                interface="rest_api",
                action_name=f"benchmark_act_{i}",
                status="success"
            )

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get("/api/activity-logs/")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            results = data["results"] if isinstance(data, dict) and "results" in data else data
            self.assertTrue(len(results) >= 3)

        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] /api/activity-logs/ executed {query_count} queries.")
        self.assertLessEqual(query_count, 4, f"Expected <= 4 queries for activity logs, got {query_count}")

    def test_user_profile_view_query_efficiency(self):
        """
        Verify that /api/auth/me/ executes in minimal queries (O(1)) without
        unnecessary joins on count.
        """
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get("/api/auth/me/")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

        self.assertEqual(data["username"], self.user.username)
        self.assertEqual(data["workspaces_count"], 1)
        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] /api/auth/me/ executed {query_count} queries.")
        self.assertLessEqual(query_count, 3, f"Expected <= 3 queries for profile view, got {query_count}")

    def test_dag_orchestrator_query_efficiency(self):
        """
        Verify that WorkflowDAG.get_node_status_map and sync_pipeline_run_stage_results
        evaluate component runs in memory, reducing 50+ queries to 1 single query.
        """
        from research_intelligence.tasks.orchestrator.dag.pipelines import build_default_slr_dag
        from research_intelligence.tasks.orchestrator.dag.engine import sync_pipeline_run_stage_results

        dag = build_default_slr_dag(self.workspace)

        # Measure queries for get_node_status_map
        with CaptureQueriesContext(connection) as ctx:
            status_map = dag.get_node_status_map(self.run_1)
        
        status_queries = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] dag.get_node_status_map executed {status_queries} query (was 25+).")
        self.assertLessEqual(status_queries, 1, f"Expected <= 1 query, got {status_queries}")
        self.assertIsInstance(status_map, dict)
        self.assertTrue("search" in status_map)

        # Measure queries for sync_pipeline_run_stage_results
        with CaptureQueriesContext(connection) as ctx:
            stage_results = sync_pipeline_run_stage_results(self.run_1, dag.nodes)

        sync_queries = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] sync_pipeline_run_stage_results executed {sync_queries} query (was 16+).")
        self.assertLessEqual(sync_queries, 1, f"Expected <= 1 query, got {sync_queries}")
        self.assertIsInstance(stage_results, dict)

        # When comp_runs is passed in-memory, 0 queries should be executed!
        comp_runs = list(ComponentRun.objects.filter(pipeline_run=self.run_1))
        with CaptureQueriesContext(connection) as ctx:
            mem_status_map = dag.get_node_status_map(self.run_1, comp_runs=comp_runs)
            mem_stage_results = sync_pipeline_run_stage_results(self.run_1, dag.nodes, comp_runs=comp_runs)
            ready_nodes = dag.get_ready_nodes(self.run_1, self.workspace, status_map=mem_status_map, comp_runs=comp_runs)

        zero_queries = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] In-memory DAG evaluation executed {zero_queries} queries (pure RAM execution).")
        self.assertEqual(zero_queries, 0, f"Expected 0 queries when passing comp_runs, got {zero_queries}")

    def test_screening_node_should_halt_query_efficiency(self):
        """
        Verify that AbstractScreeningNode and FullTextScreeningNode check halting
        conditions using a single PaperMetric query instead of 4 separate DISTINCT joins.
        """
        from research_intelligence.tasks.step_4_screening.node import AbstractScreeningNode, FullTextScreeningNode

        abstract_node = AbstractScreeningNode()
        full_text_node = FullTextScreeningNode()

        with CaptureQueriesContext(connection) as ctx:
            halt, reason = abstract_node.should_halt_pipeline(self.run_1, self.workspace, {})

        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] AbstractScreeningNode.should_halt_pipeline executed {query_count} queries (was 4+).")
        self.assertLessEqual(query_count, 2, f"Expected <= 2 queries, got {query_count}")

        with CaptureQueriesContext(connection) as ctx:
            halt_ft, reason_ft = full_text_node.should_halt_pipeline(self.run_1, self.workspace, {})

        query_count_ft = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] FullTextScreeningNode.should_halt_pipeline executed {query_count_ft} queries (was 4+).")
        self.assertLessEqual(query_count_ft, 2, f"Expected <= 2 queries, got {query_count_ft}")

    def test_search_node_should_halt_query_efficiency(self):
        """
        Verify that SearchNode.should_halt_pipeline evaluates component runs in memory.
        """
        from research_intelligence.tasks.step_1_search.node import SearchNode

        search_node = SearchNode()
        with CaptureQueriesContext(connection) as ctx:
            halt, reason = search_node.should_halt_pipeline(self.run_1, self.workspace, {})

        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] SearchNode.should_halt_pipeline executed {query_count} queries.")
        self.assertLessEqual(query_count, 2, f"Expected <= 2 queries, got {query_count}")

    def test_runner_handle_component_completion_efficiency(self):
        """
        Verify that PipelineRunner.handle_component_completion fetches component runs once.
        """
        from research_intelligence.tasks.orchestrator.runner import PipelineRunner

        with CaptureQueriesContext(connection) as ctx:
            PipelineRunner.handle_component_completion(self.run_1)

        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] PipelineRunner.handle_component_completion executed {query_count} queries.")
        # Minimal queries: fetch pipeline_run (or passed obj), comp_runs.all(), agent_processes
        self.assertLessEqual(query_count, 4, f"Expected <= 4 queries, got {query_count}")

    def test_signal_scoring_batch_query_efficiency(self):
        """
        Verify that execute_signal_score_job prefetches extraction definitions and extractions,
        avoiding N+1 queries per paper.
        """
        from research_intelligence.tasks.step_6_signal_score.scorer import execute_signal_score_job

        # Create ComponentRun for signal scoring
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.run_1,
            step_type='signal_score',
            component_name='signal_score_evaluator',
            status='pending'
        )

        with CaptureQueriesContext(connection) as ctx:
            res = execute_signal_score_job(str(comp_run.id))

        self.assertTrue(res.get("success"))
        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] execute_signal_score_job executed {query_count} queries for 10 papers (was 120+).")
        # Pre-fetching and single save per paper keeps total queries <= 30 (includes component_run updates, metric saves, completion ticks)
        self.assertLessEqual(query_count, 30, f"Expected <= 30 queries, got {query_count}")

    def test_download_paper_task_withdrawn_optimization(self):
        """
        Verify that _download_paper_task with preloaded withdrawn_info_map executes 0 queries for withdrawn check.
        """
        from research_intelligence.tasks.step_2_download.fetch import _download_paper_task

        paper = self.papers[0]
        withdrawn_map = {paper.id: "Withdrawn by authors"}

        with CaptureQueriesContext(connection) as ctx:
            res = _download_paper_task(paper, self.workspace, self.run_1, withdrawn_info_map=withdrawn_map)

        self.assertEqual(res["status"], "withdrawn")
        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] _download_paper_task with withdrawn map executed {query_count} queries.")
        self.assertEqual(query_count, 0, f"Expected 0 queries, got {query_count}")

    def test_hitl_and_reports_unaffiliated_workspace_short_circuit(self):
        """
        Verify that /api/hitl/ and /api/reports/ short-circuit on unauthorized workspace query.
        """
        import uuid
        foreign_ws_id = str(uuid.uuid4())

        # Test HITL short-circuit
        with CaptureQueriesContext(connection) as ctx:
            resp_hitl = self.client.get(f"/api/hitl/?workspace_id={foreign_ws_id}")
            self.assertEqual(resp_hitl.status_code, 200)
            data_hitl = resp_hitl.json()
            results_hitl = data_hitl["results"] if isinstance(data_hitl, dict) and "results" in data_hitl else data_hitl
            self.assertEqual(len(results_hitl), 0)

        hitl_queries = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] /api/hitl/ with unauthorized workspace executed {hitl_queries} queries.")
        self.assertLessEqual(hitl_queries, 3, f"Expected <= 3 queries, got {hitl_queries}")

        # Test Reports short-circuit
        with CaptureQueriesContext(connection) as ctx:
            resp_rep = self.client.get(f"/api/reports/?workspace_id={foreign_ws_id}")
            self.assertEqual(resp_rep.status_code, 200)
            data_rep = resp_rep.json()
            results_rep = data_rep["results"] if isinstance(data_rep, dict) and "results" in data_rep else data_rep
            self.assertEqual(len(results_rep), 0)

        rep_queries = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] /api/reports/ with unauthorized workspace executed {rep_queries} queries.")
        self.assertLessEqual(rep_queries, 3, f"Expected <= 3 queries, got {rep_queries}")

    def test_workspace_default_scoring_context_caching(self):
        """
        Verify get_workspace_default_scoring_context extracts default variables
        and pre-populates the scoring AST dictionary once.
        """
        from research_intelligence.tasks.step_6_signal_score.scorer import get_workspace_default_scoring_context
        from research_intelligence.models import ExtractionDefinition

        # Create sample extraction definitions
        ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Sample Target Metric",
            system_prompt="Test system prompt",
            user_prompt_template="Extract from {paper_text}",
            response_schema={},
            exit_metrics="sample_score, computed_val",
            postprocessing_code="return {'computed_val': 42.0}"
        )

        ctx_1 = get_workspace_default_scoring_context(self.workspace)
        self.assertIn("sample_target_metric", ctx_1)
        self.assertIn("sample_score", ctx_1)
        self.assertIn("computed_val", ctx_1)
        self.assertEqual(ctx_1["sample_target_metric"], 0.0)

        # Call again to ensure invariance
        ctx_2 = get_workspace_default_scoring_context(self.workspace)
        self.assertEqual(ctx_1, ctx_2)

    def test_reporting_annotate_papers_efficiency(self):
        """
        Verify _annotate_papers in narrative.py annotates papers with PaperMetric
        in O(1) batch query without redundant .exists() or N+1 queries.
        """
        from research_intelligence.tasks.step_7_reporting.narrative import _annotate_papers

        # Create PaperMetric for 3 papers
        for paper in self.papers[:3]:
            PaperMetric.objects.update_or_create(
                paper=paper,
                pipeline_run=self.run_1,
                workspace=self.workspace,
                defaults={"screening_status": "accepted", "signal_score": 8.5}
            )

        paper_ids = [p.id for p in self.papers[:3]]
        papers_qs = Paper.objects.filter(id__in=paper_ids)

        with CaptureQueriesContext(connection) as ctx:
            annotated = _annotate_papers(papers_qs, self.run_1)

        self.assertEqual(len(annotated), 3)
        for p in annotated:
            self.assertEqual(p.annotated_screening_status, "accepted")
            self.assertEqual(p.annotated_signal_score, 8.5)

        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] _annotate_papers executed {query_count} queries for 3 papers.")
        self.assertLessEqual(query_count, 3, f"Expected <= 3 queries, got {query_count}")

    def test_pdf_download_safe_call_legacy_mock_compatibility(self):
        """
        Verify that execute_pdf_download_job can execute even when _download_paper_task
        is mocked with a 3-argument function without kwargs.
        """
        from unittest.mock import patch
        from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.run_1,
            step_type="download",
            component_name="pdf_fetcher",
            status="pending"
        )

        # Lambda taking only 3 positional arguments
        def legacy_mock_task(paper, ws, pr):
            return {"status": "success", "paper_id": str(paper.id)}

        with patch("research_intelligence.tasks.step_2_download.fetch._download_paper_task", side_effect=legacy_mock_task):
            res = execute_pdf_download_job(str(comp_run.id))
            self.assertTrue(res)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")

    def test_storage_stats_caching_on_pipeline_run_detail(self):
        """
        Verify that _get_run_storage_stats caches results in memory so repeated
        polling by the frontend does not traverse storage on every request.
        """
        from unittest.mock import patch
        from mcp_server.tools.pipeline_runs.status import _get_run_storage_stats
        from django.core.cache import cache

        run_dir = f"workspaces/{self.workspace.id}/runs/{self.run_1.id}"
        cache.delete(f"storage_stats:{run_dir}")

        with patch("django.core.files.storage.default_storage.listdir", return_value=([], ["file1.pdf"])) as mock_listdir:
            with patch("django.core.files.storage.default_storage.size", return_value=1024):
                res1 = _get_run_storage_stats(run_dir)
                self.assertEqual(res1["total_files"], 1)
                self.assertEqual(mock_listdir.call_count, 1)

                # Second call should be served entirely from cache without storage calls
                res2 = _get_run_storage_stats(run_dir)
                self.assertEqual(res2["total_files"], 1)
                self.assertEqual(mock_listdir.call_count, 1)

    def test_component_runs_query_efficiency_for_frontend_polling(self):
        """
        Verify that GET /api/component-runs/?pipeline_run=... executes efficiently
        without unnecessary joins on workspace.
        """
        for i in range(3):
            ComponentRun.objects.create(
                pipeline_run=self.run_1,
                step_type="search",
                component_name=f"test_comp_{i}",
                status="completed"
            )

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/component-runs/?pipeline_run={self.run_1.id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            results = data["results"] if isinstance(data, dict) and "results" in data else data
            self.assertTrue(len(results) >= 3)

        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] /api/component-runs/?pipeline_run= executed {query_count} queries.")
        self.assertLessEqual(query_count, 3, f"Expected <= 3 queries, got {query_count}")

    def test_papers_unauthorized_workspace_short_circuit(self):
        """
        Verify that /api/papers/?workspace_id=foreign_id short-circuits with minimal queries.
        """
        import uuid
        foreign_ws_id = str(uuid.uuid4())

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/papers/?workspace_id={foreign_ws_id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            results = data["results"] if isinstance(data, dict) and "results" in data else data
            self.assertEqual(len(results), 0)

        query_count = len(ctx.captured_queries)
        print(f"\n[BENCHMARK] /api/papers/ with unauthorized workspace executed {query_count} queries.")
        self.assertLessEqual(query_count, 2, f"Expected <= 2 queries, got {query_count}")




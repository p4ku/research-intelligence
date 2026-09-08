import uuid
from datetime import datetime, time, timedelta, timezone as dt_timezone
from django.utils import timezone
from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    Paper,
    PaperMetric,
    Extraction,
    ExtractionDefinition,
)
from chat.models import PaperChatSession

User = get_user_model()


class ApiEndpointOptimizationsTestCase(TestCase):
    """
    Validates performance optimizations applied to API endpoints and database models:
    1. Composite B-tree indexes defined on PipelineRun and Extraction models.
    2. /api/workspaces/{id}/editions/ scalar field pruning and date deduplication.
    3. /api/workspaces/{id}/editions/{date}/ single PaperMetric query, range-based timestamp lookups, and descending score order.
    4. /api/chat/sessions/ consolidated WorkspaceMember access query (1 query instead of 2).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="perf_tester",
            email="perf@schwarz.de",
            password="securepassword123!"
        )
        self.workspace = Workspace.objects.create(name="Performance Benchmark Workspace")
        self.membership = WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_model_indexes_configuration(self):
        """
        Verify that PipelineRun and Extraction models define the required
        high-traffic composite B-tree indexes in their Meta options.
        """
        # 1. Verify PipelineRun indexes
        pr_index_fields = [list(idx.fields) for idx in PipelineRun._meta.indexes]
        self.assertIn(['workspace', 'status', '-completed_at'], pr_index_fields)
        self.assertIn(['workspace', '-started_at'], pr_index_fields)
        self.assertIn(['status', '-started_at'], pr_index_fields)
        self.assertIn(['schedule', '-started_at'], pr_index_fields)

        # 2. Verify Extraction indexes
        ext_index_fields = [list(idx.fields) for idx in Extraction._meta.indexes]
        self.assertIn(['paper', '-created_at'], ext_index_fields)

    def test_editions_list_field_pruning_and_deduplication(self):
        """
        Verify GET /api/workspaces/{id}/editions/:
        - Deduplicates multiple runs on the same date (keeps newest).
        - Loads scalar fields correctly and constructs funnel counts.
        """
        now = timezone.now()
        day1 = now - timedelta(days=2)
        day2 = now - timedelta(days=1)

        # Run 1 on day 1 (earlier in the day)
        r1 = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run Day 1 Morning",
            status="completed",
            completed_at=day1,
            total_papers_fetched=10,
            total_papers_passed_screening=3,
            configuration_override={"huge_payload": "x" * 1000},
            step_history=[{"step": "search", "event": "done"}] * 50
        )
        # Run 2 on day 1 (later in the day - should be chosen for day 1)
        r2 = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run Day 1 Evening",
            status="completed",
            completed_at=day1 + timedelta(hours=4),
            total_papers_fetched=12,
            total_papers_passed_screening=5,
            configuration_override={"huge_payload": "y" * 1000},
            step_history=[{"step": "screening", "event": "done"}] * 50
        )
        # Run 3 on day 2
        r3 = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run Day 2",
            status="completed",
            completed_at=day2,
            total_papers_fetched=20,
            total_papers_passed_screening=8,
            configuration_override={"huge_payload": "z" * 1000},
            step_history=[{"step": "completed", "event": "done"}] * 50
        )

        resp = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/?page_size=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Should be deduped to exactly 2 editions (day2 and day1)
        self.assertEqual(data["count"], 2)
        results = data["results"]
        self.assertEqual(len(results), 2)

        # Newest edition first
        day2_str = day2.strftime("%Y-%m-%d")
        day1_str = day1.strftime("%Y-%m-%d")
        self.assertEqual(results[0]["date"], day2_str)
        self.assertEqual(results[0]["run_id"], str(r3.id))
        self.assertEqual(results[0]["funnel"]["fetched"], 20)

        self.assertEqual(results[1]["date"], day1_str)
        self.assertEqual(results[1]["run_id"], str(r2.id))
        self.assertEqual(results[1]["funnel"]["fetched"], 12)

    def test_edition_detail_single_papermetric_query_and_sorting(self):
        """
        Verify GET /api/workspaces/{id}/editions/{date}/:
        1. Executes exactly ONE query against PaperMetric (no separate queries for passed vs excluded).
        2. Uses timestamp range filtering rather than unindexed completed_at__date.
        3. Correctly sorts surfaced papers in descending signal_score order.
        4. Accurately groups exclusions with their screening reason.
        """
        target_date = datetime(2026, 9, 5, 22, 30, 0, tzinfo=dt_timezone.utc)
        target_date_str = "2026-09-05"

        run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Optimization Benchmark Edition Run",
            status="completed",
            completed_at=target_date,
            total_papers_fetched=5,
            total_papers_passed_screening=3
        )

        # 3 Surfaced papers with varied signal scores
        p_high = Paper.objects.create(
            workspace=self.workspace,
            title="High Score Paper",
            authors="Alice Alpha, Bob Beta",
            source_database="arXiv",
            hash_id="opt_hash_high"
        )
        PaperMetric.objects.create(
            paper=p_high,
            pipeline_run=run,
            workspace=self.workspace,
            screening_status="accepted",
            signal_score=95.5
        )

        p_med = Paper.objects.create(
            workspace=self.workspace,
            title="Medium Score Paper",
            authors="Charlie Gamma",
            source_database="arXiv",
            hash_id="opt_hash_med"
        )
        PaperMetric.objects.create(
            paper=p_med,
            pipeline_run=run,
            workspace=self.workspace,
            screening_status="full_text_passed",
            signal_score=82.0
        )

        p_low = Paper.objects.create(
            workspace=self.workspace,
            title="Low Score Paper",
            authors="David Delta",
            source_database="arXiv",
            hash_id="opt_hash_low"
        )
        PaperMetric.objects.create(
            paper=p_low,
            pipeline_run=run,
            workspace=self.workspace,
            screening_status="abstract_passed",
            signal_score=60.0
        )

        # 2 Excluded papers
        p_rej1 = Paper.objects.create(
            workspace=self.workspace,
            title="Abstract Rejected Paper",
            source_database="arXiv",
            hash_id="opt_hash_rej1"
        )
        PaperMetric.objects.create(
            paper=p_rej1,
            pipeline_run=run,
            workspace=self.workspace,
            screening_status="rejected",
            abstract_screening_reasoning="Abstract does not meet clinical benchmark criteria"
        )

        p_rej2 = Paper.objects.create(
            workspace=self.workspace,
            title="Full Text Rejected Paper",
            source_database="arXiv",
            hash_id="opt_hash_rej2"
        )
        PaperMetric.objects.create(
            paper=p_rej2,
            pipeline_run=run,
            workspace=self.workspace,
            screening_status="rejected",
            full_text_screening_reasoning="Failed methodology replication threshold"
        )

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/{target_date_str}/")
            self.assertEqual(resp.status_code, 200)

        # 1. Assert exactly 1 query to PaperMetric
        papermetric_queries = [
            q['sql'] for q in ctx.captured_queries
            if 'research_intelligence_papermetric' in q['sql'].lower()
        ]
        self.assertEqual(len(papermetric_queries), 1, "PaperMetric should be queried exactly once in edition_detail")

        # 2. Assert no DATE(completed_at) full table scan in captured SQL
        for q in ctx.captured_queries:
            sql = q['sql'].lower()
            if 'research_intelligence_pipelinerun' in sql:
                self.assertNotIn('date("research_intelligence_pipelinerun"."completed_at")', sql)
                self.assertNotIn('django_date_trunc', sql)

        # 3. Assert sorting and data completeness
        detail = resp.json()
        self.assertEqual(detail["run_id"], str(run.id))
        self.assertEqual(detail["date"], target_date_str)
        self.assertEqual(len(detail["papers"]), 3)
        self.assertEqual(len(detail["exclusions"]), 2)

        # Verify descending order by signal_score
        scores = [p["signal_score"] for p in detail["papers"]]
        self.assertEqual(scores, [95.5, 82.0, 60.0])
        self.assertEqual(detail["papers"][0]["title"], "High Score Paper")
        self.assertEqual(detail["papers"][1]["title"], "Medium Score Paper")
        self.assertEqual(detail["papers"][2]["title"], "Low Score Paper")

        # Verify exclusions retain their screening reasoning
        rej_reasons = {ex["title"]: ex["reason"] for ex in detail["exclusions"]}
        self.assertIn("Abstract Rejected Paper", rej_reasons)
        self.assertEqual(rej_reasons["Abstract Rejected Paper"], "Abstract does not meet clinical benchmark criteria")
        self.assertIn("Full Text Rejected Paper", rej_reasons)
        self.assertEqual(rej_reasons["Full Text Rejected Paper"], "Failed methodology replication threshold")

    def test_chat_sessions_single_workspacemember_query(self):
        """
        Verify GET /api/chat/sessions/ for a non-superuser:
        Executes at most ONE query to WorkspaceMember table to resolve both admin
        and regular memberships, eliminating redundant access check queries.
        """
        researcher = User.objects.create_user(
            username="researcher_user",
            email="researcher@schwarz.de",
            password="securepassword123!"
        )
        ws_member = Workspace.objects.create(name="Researcher Membership WS")
        ws_admin = Workspace.objects.create(name="Manager Membership WS")

        WorkspaceMember.objects.create(workspace=ws_member, user=researcher, role="researcher")
        WorkspaceMember.objects.create(workspace=ws_admin, user=researcher, role="manager")

        PaperChatSession.objects.create(
            workspace=ws_member,
            user=researcher,
            title="Session in Researcher WS"
        )
        PaperChatSession.objects.create(
            workspace=ws_admin,
            user=researcher,
            title="Session in Manager WS"
        )

        client = APIClient()
        client.force_authenticate(user=researcher)

        with CaptureQueriesContext(connection) as ctx:
            resp = client.get("/api/chat/sessions/")
            self.assertEqual(resp.status_code, 200)

        # Count queries made to WorkspaceMember
        ws_member_queries = [
            q['sql'] for q in ctx.captured_queries
            if 'research_intelligence_workspacemember' in q['sql'].lower()
        ]
        self.assertEqual(len(ws_member_queries), 1, "WorkspaceMember should be queried at most once to evaluate chat session access")
        self.assertEqual(len(resp.json()), 2)

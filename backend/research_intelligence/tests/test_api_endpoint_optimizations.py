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
        - Returns one entry per completed run (preserves same-day runs per #117/#123/#127).
        - Loads scalar fields correctly, constructs funnel counts, and returns workspace_name.
        """
        now = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
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
        # Run 2 on day 1 (later in the day)
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

        # One entry per completed run (3 total: day 2, day 1 evening, day 1 morning)
        self.assertEqual(data["count"], 3)
        results = data["results"]
        self.assertEqual(len(results), 3)

        # Newest edition first
        day2_str = day2.strftime("%Y-%m-%d")
        day1_str = day1.strftime("%Y-%m-%d")

        self.assertEqual(results[0]["date"], day2_str)
        self.assertEqual(results[0]["run_id"], str(r3.id))
        self.assertEqual(results[0]["workspace_name"], self.workspace.name)
        self.assertEqual(results[0]["funnel"]["fetched"], 20)

        self.assertEqual(results[1]["date"], day1_str)
        self.assertEqual(results[1]["run_id"], str(r2.id))
        self.assertEqual(results[1]["workspace_name"], self.workspace.name)
        self.assertEqual(results[1]["funnel"]["fetched"], 12)

        self.assertEqual(results[2]["date"], day1_str)
        self.assertEqual(results[2]["run_id"], str(r1.id))
        self.assertEqual(results[2]["workspace_name"], self.workspace.name)
        self.assertEqual(results[2]["funnel"]["fetched"], 10)

    def test_editions_same_day_pair_and_run_id_selection(self):
        """
        Verify that multiple runs on the same date can be selected by run_id,
        and omitting run_id defaults to the day's newest completed run.
        """
        target_date = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
        target_date_str = target_date.strftime("%Y-%m-%d")

        r_morning = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Morning Run",
            status="completed",
            completed_at=target_date,
            total_papers_fetched=10,
            total_papers_passed_screening=4
        )
        r_evening = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Evening Run",
            status="completed",
            completed_at=target_date + timedelta(hours=6),
            total_papers_fetched=15,
            total_papers_passed_screening=7
        )

        # 1. Omitting run_id returns newest run (evening)
        resp_default = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/{target_date_str}/")
        self.assertEqual(resp_default.status_code, 200)
        self.assertEqual(resp_default.json()["run_id"], str(r_evening.id))
        self.assertEqual(resp_default.json()["funnel"]["fetched"], 15)

        # 2. Specifying morning run_id returns morning run
        resp_morning = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/{target_date_str}/?run_id={r_morning.id}")
        self.assertEqual(resp_morning.status_code, 200)
        self.assertEqual(resp_morning.json()["run_id"], str(r_morning.id))
        self.assertEqual(resp_morning.json()["funnel"]["fetched"], 10)

        # 3. Specifying evening run_id returns evening run
        resp_evening = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/{target_date_str}/?run_id={r_evening.id}")
        self.assertEqual(resp_evening.status_code, 200)
        self.assertEqual(resp_evening.json()["run_id"], str(r_evening.id))
        self.assertEqual(resp_evening.json()["funnel"]["fetched"], 15)

    def test_editions_cross_date_and_unknown_run_fallback(self):
        """
        Verify:
        - When run_id belongs to another date, fallback to the day's newest run (Issue #127).
        - When run_id is an unknown UUID, fallback to the day's newest run.
        - When the requested date has no completed runs, return 404 even if run_id is passed.
        - date and title in the response are derived from the run.
        """
        import uuid
        day1 = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=3)
        day2 = day1 + timedelta(days=1)
        day1_str = day1.strftime("%Y-%m-%d")
        day2_str = day2.strftime("%Y-%m-%d")

        r_day1 = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Day 1 Run",
            status="completed",
            completed_at=day1,
            total_papers_fetched=5,
            total_papers_passed_screening=2
        )
        r_day2 = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Day 2 Run",
            status="completed",
            completed_at=day2,
            total_papers_fetched=8,
            total_papers_passed_screening=4
        )

        # 1. Query day1 with r_day2's run_id -> falls back to r_day1 (not 404!)
        resp_cross = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/{day1_str}/?run_id={r_day2.id}")
        self.assertEqual(resp_cross.status_code, 200)
        cross_data = resp_cross.json()
        self.assertEqual(cross_data["run_id"], str(r_day1.id))
        self.assertEqual(cross_data["date"], day1_str)
        self.assertEqual(cross_data["title"], f"{self.workspace.name} Briefing — {day1_str}")
        self.assertEqual(cross_data["workspace_name"], self.workspace.name)

        # 2. Query day1 with non-existent UUID -> falls back to r_day1
        unknown_id = uuid.uuid4()
        resp_unknown = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/{day1_str}/?run_id={unknown_id}")
        self.assertEqual(resp_unknown.status_code, 200)
        self.assertEqual(resp_unknown.json()["run_id"], str(r_day1.id))

        # 3. Query a date with no runs at all (e.g. 2030-01-01) -> returns 404
        resp_empty_day = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/2030-01-01/?run_id={r_day1.id}")
        self.assertEqual(resp_empty_day.status_code, 404)

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

        # Verify descending order by signal_score and presence of screening_status
        scores = [p["signal_score"] for p in detail["papers"]]
        self.assertEqual(scores, [95.5, 82.0, 60.0])
        self.assertEqual(detail["papers"][0]["title"], "High Score Paper")
        self.assertEqual(detail["papers"][0]["screening_status"], "accepted")
        self.assertEqual(detail["papers"][1]["title"], "Medium Score Paper")
        self.assertEqual(detail["papers"][1]["screening_status"], "full_text_passed")
        self.assertEqual(detail["papers"][2]["title"], "Low Score Paper")
        self.assertEqual(detail["papers"][2]["screening_status"], "abstract_passed")

        # Verify exclusions retain their screening reasoning
        rej_reasons = {ex["title"]: ex["reason"] for ex in detail["exclusions"]}
        self.assertIn("Abstract Rejected Paper", rej_reasons)
        self.assertEqual(rej_reasons["Abstract Rejected Paper"], "Abstract does not meet clinical benchmark criteria")
        self.assertIn("Full Text Rejected Paper", rej_reasons)
        self.assertEqual(rej_reasons["Full Text Rejected Paper"], "Failed methodology replication threshold")

        # Verify explicit ?run_id query param
        resp_run = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/{target_date_str}/?run_id={run.id}")
        self.assertEqual(resp_run.status_code, 200)
        self.assertEqual(resp_run.json()["run_id"], str(run.id))

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

    def test_workspace_scorecard_run_id_filters_papers_and_orders_by_signal_score(self):
        """
        Verify GET /api/workspaces/{id}/scorecard/?run_id={run_id}:
        - Scopes papers strictly to those evaluated in the specified pipeline run.
        - Does NOT leak or serialize papers belonging exclusively to other runs.
        - Orders returned scored papers descending by signal_score.
        """
        run_a = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run Alpha",
            status="completed",
            completed_at=timezone.now()
        )
        run_b = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run Beta",
            status="completed",
            completed_at=timezone.now()
        )

        p_a = Paper.objects.create(
            workspace=self.workspace,
            title="Paper A from Run Alpha",
            source_database="arXiv",
            hash_id="p_a_hash"
        )
        PaperMetric.objects.create(
            paper=p_a,
            workspace=self.workspace,
            pipeline_run=run_a,
            signal_score=50.0,
            screening_status="accepted"
        )

        p_b1 = Paper.objects.create(
            workspace=self.workspace,
            title="Paper B1 from Run Beta (Low Score)",
            source_database="arXiv",
            hash_id="p_b1_hash"
        )
        PaperMetric.objects.create(
            paper=p_b1,
            workspace=self.workspace,
            pipeline_run=run_b,
            signal_score=65.0,
            screening_status="accepted"
        )

        p_b2 = Paper.objects.create(
            workspace=self.workspace,
            title="Paper B2 from Run Beta (High Score)",
            source_database="arXiv",
            hash_id="p_b2_hash"
        )
        PaperMetric.objects.create(
            paper=p_b2,
            workspace=self.workspace,
            pipeline_run=run_b,
            signal_score=92.5,
            screening_status="accepted"
        )

        # Query scorecard scoped to run_b
        resp = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run_b.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        returned_ids = [p["id"] for p in data["papers"]]
        self.assertIn(str(p_b1.id), returned_ids)
        self.assertIn(str(p_b2.id), returned_ids)
        self.assertNotIn(str(p_a.id), returned_ids, "Papers from other runs must not be returned when run_id is scoped")

        # Must be sorted descending by signal_score
        scores = [p["signal_score"] for p in data["papers"]]
        self.assertEqual(scores, [92.5, 65.0])

        # Test search query parameter on scorecard
        resp_search = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run_b.id}&search=High")
        self.assertEqual(resp_search.status_code, 200)
        search_papers = resp_search.json()["papers"]
        self.assertEqual(len(search_papers), 1)
        self.assertEqual(search_papers[0]["id"], str(p_b2.id))

        # Test ordering query parameter on scorecard
        # 1. Ascending signal_score
        resp_asc = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run_b.id}&ordering=signal_score")
        self.assertEqual(resp_asc.status_code, 200)
        self.assertEqual([p["signal_score"] for p in resp_asc.json()["papers"]], [65.0, 92.5])

        # 2. Descending title
        resp_title = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run_b.id}&ordering=-title")
        self.assertEqual(resp_title.status_code, 200)
        titles = [p["title"] for p in resp_title.json()["papers"]]
        self.assertEqual(titles, [p_b2.title, p_b1.title])

    def test_edition_detail_delivers_complete_scored_paper_payload(self):
        """
        Verify GET /api/workspaces/{id}/editions/{date}/:
        Delivers complete ScoredPaper representation (dimensions, abstract, source_url)
        so frontend can render PaperCard without making a second request to scorecard.
        """
        run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Single Stream Run",
            status="completed",
            completed_at=timezone.now(),
            total_papers_fetched=1,
            total_papers_passed_screening=1,
        )
        paper = Paper.objects.create(
            workspace=self.workspace,
            title="Single Stream Paper",
            abstract="Detailed methodology for quantum neural network optimization.",
            authors="John Doe, Jane Smith",
            source_database="arXiv",
            arxiv_id="2609.12345",
            hash_id="single_stream_hash",
        )
        PaperMetric.objects.create(
            paper=paper,
            workspace=self.workspace,
            pipeline_run=run,
            screening_status="accepted",
            signal_score=88.5,
        )
        def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Assessment",
            system_prompt="Extract TRL",
            user_prompt_template="{paper_text}",
            response_schema={},
            exit_metrics="trl_level",
            is_active=True,
        )
        Extraction.objects.create(
            paper=paper,
            workspace=self.workspace,
            extraction_definition=def_trl,
            category="TRL",
            confidence_score=0.92,
            fields_data={"trl_level": 5, "rationale": "Validated in laboratory environment"},
        )

        target_date_str = run.completed_at.strftime('%Y-%m-%d')
        resp = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/{target_date_str}/?run_id={run.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(len(data["papers"]), 1)
        card = data["papers"][0]
        self.assertEqual(card["id"], str(paper.id))
        self.assertEqual(card["title"], "Single Stream Paper")
        self.assertEqual(card["abstract"], "Detailed methodology for quantum neural network optimization.")
        self.assertEqual(card["source_url"], "https://arxiv.org/abs/2609.12345")
        self.assertEqual(card["signal_score"], 88.5)
        self.assertEqual(card["screening_status"], "accepted")
        self.assertIn("dimensions", card)
        self.assertGreaterEqual(len(card["dimensions"]), 1)
        self.assertEqual(card["dimensions"][0]["name"], "TRL Assessment")
        self.assertEqual(card["dimensions"][0]["value"], 5)

    def test_scorecard_advanced_search_across_all_fields(self):
        """
        Verify GET /api/workspaces/{id}/scorecard/?run_id={id}&search={term}:
        Full-text search matches accurately and case-insensitively across:
        - title
        - authors
        - abstract
        - doi
        - arxiv_id
        """
        run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Search Benchmark Run",
            status="completed",
            completed_at=timezone.now(),
        )
        p1 = Paper.objects.create(
            workspace=self.workspace,
            title="DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning",
            authors="DeepSeek-AI, Daya Guo, Dejian Yang",
            abstract="We introduce our first-generation reasoning models.",
            doi="10.1000/182",
            arxiv_id="2501.12948",
            hash_id="search_hash_1",
        )
        PaperMetric.objects.create(
            paper=p1,
            workspace=self.workspace,
            pipeline_run=run,
            signal_score=95.0,
            screening_status="accepted",
        )

        p2 = Paper.objects.create(
            workspace=self.workspace,
            title="Attention Is All You Need",
            authors="Ashish Vaswani, Noam Shazeer, Niki Parmar",
            abstract="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
            doi="10.5555/3295222.3295349",
            arxiv_id="1706.03762",
            hash_id="search_hash_2",
        )
        PaperMetric.objects.create(
            paper=p2,
            workspace=self.workspace,
            pipeline_run=run,
            signal_score=85.0,
            screening_status="accepted",
        )

        # 1. Search by title (case-insensitive)
        resp = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&search=deepseek")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["papers"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(p1.id))

        # 2. Search by author
        resp = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&search=vaswani")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["papers"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(p2.id))

        # 3. Search by abstract keyword
        resp = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&search=transduction")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["papers"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(p2.id))

        # 4. Search by DOI
        resp = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&search=10.1000/182")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["papers"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(p1.id))

        # 5. Search by arXiv ID
        resp = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&search=1706.03762")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["papers"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(p2.id))

        # 6. Search with no matches returns empty list
        resp = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&search=nonexistent_xyz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["papers"]), 0)

    def test_scorecard_comprehensive_ordering(self):
        """
        Verify GET /api/workspaces/{id}/scorecard/?run_id={id}&ordering={field}:
        Validates signal_score, -signal_score, title, -title, created_at, -created_at.
        """
        run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Ordering Benchmark Run",
            status="completed",
            completed_at=timezone.now(),
        )
        p_c = Paper.objects.create(
            workspace=self.workspace,
            title="Charlie Paper",
            source_database="arXiv",
            hash_id="ord_hash_c",
        )
        PaperMetric.objects.create(
            paper=p_c,
            workspace=self.workspace,
            pipeline_run=run,
            signal_score=20.0,
            screening_status="accepted",
        )

        p_a = Paper.objects.create(
            workspace=self.workspace,
            title="Alpha Paper",
            source_database="arXiv",
            hash_id="ord_hash_a",
        )
        PaperMetric.objects.create(
            paper=p_a,
            workspace=self.workspace,
            pipeline_run=run,
            signal_score=90.0,
            screening_status="accepted",
        )

        p_b = Paper.objects.create(
            workspace=self.workspace,
            title="Bravo Paper",
            source_database="arXiv",
            hash_id="ord_hash_b",
        )
        PaperMetric.objects.create(
            paper=p_b,
            workspace=self.workspace,
            pipeline_run=run,
            signal_score=60.0,
            screening_status="accepted",
        )

        # 1. Default ordering for run_id is signal_score descending
        resp_def = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}")
        self.assertEqual(resp_def.status_code, 200)
        self.assertEqual([p["signal_score"] for p in resp_def.json()["papers"]], [90.0, 60.0, 20.0])

        # 2. signal_score ascending
        resp_asc = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&ordering=signal_score")
        self.assertEqual(resp_asc.status_code, 200)
        self.assertEqual([p["signal_score"] for p in resp_asc.json()["papers"]], [20.0, 60.0, 90.0])

        # 3. title ascending
        resp_t_asc = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&ordering=title")
        self.assertEqual(resp_t_asc.status_code, 200)
        self.assertEqual([p["title"] for p in resp_t_asc.json()["papers"]], ["Alpha Paper", "Bravo Paper", "Charlie Paper"])

        # 4. title descending
        resp_t_desc = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&ordering=-title")
        self.assertEqual(resp_t_desc.status_code, 200)
        self.assertEqual([p["title"] for p in resp_t_desc.json()["papers"]], ["Charlie Paper", "Bravo Paper", "Alpha Paper"])

    def test_edition_detail_query_count_constant_scaling(self):
        """
        Verify GET /api/workspaces/{id}/editions/{date}/:
        Scales with O(1) constant SQL query count regardless of paper count.
        Bulk fetches Extractions and PaperMetrics without N+1 regression.
        """
        run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Scaling Benchmark Run",
            status="completed",
            completed_at=timezone.now(),
            total_papers_fetched=10,
            total_papers_passed_screening=5,
        )
        def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Definition",
            system_prompt="Extract TRL",
            user_prompt_template="{paper_text}",
            response_schema={},
            exit_metrics="trl_level",
            is_active=True,
        )
        def_biz = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Commercial Relevance",
            system_prompt="Extract Commercial Value",
            user_prompt_template="{paper_text}",
            response_schema={},
            exit_metrics="market_potential",
            is_active=True,
        )

        # Create 5 passed and 5 rejected papers
        for i in range(5):
            p = Paper.objects.create(
                workspace=self.workspace,
                title=f"Passed Scaled Paper {i}",
                abstract=f"Methodology description {i}",
                source_database="arXiv",
                hash_id=f"pass_scale_{i}",
            )
            PaperMetric.objects.create(
                paper=p,
                workspace=self.workspace,
                pipeline_run=run,
                screening_status="accepted",
                signal_score=50.0 + (i * 10),
            )
            Extraction.objects.create(
                paper=p,
                workspace=self.workspace,
                extraction_definition=def_trl,
                category="TRL",
                fields_data={"trl_level": 5 + i},
            )
            Extraction.objects.create(
                paper=p,
                workspace=self.workspace,
                extraction_definition=def_biz,
                category="Commercial",
                fields_data={"market_potential": 80},
            )

        for j in range(5):
            p_rej = Paper.objects.create(
                workspace=self.workspace,
                title=f"Rejected Scaled Paper {j}",
                source_database="arXiv",
                hash_id=f"rej_scale_{j}",
            )
            PaperMetric.objects.create(
                paper=p_rej,
                workspace=self.workspace,
                pipeline_run=run,
                screening_status="rejected",
                screening_reasoning=f"Exclusion criteria #{j}",
            )

        target_date_str = run.completed_at.strftime('%Y-%m-%d')
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/workspaces/{self.workspace.id}/editions/{target_date_str}/?run_id={run.id}")
            self.assertEqual(resp.status_code, 200)

        # Verify query count bounds: exactly 1 PaperMetric query, exactly 1 Extraction query (bulk-fetched)
        papermetric_queries = [
            q['sql'] for q in ctx.captured_queries
            if 'FROM "research_intelligence_papermetric"' in q['sql'] or 'from "research_intelligence_papermetric"' in q['sql'].lower()
        ]
        extraction_queries = [
            q['sql'] for q in ctx.captured_queries
            if 'FROM "research_intelligence_extraction"' in q['sql'] or 'from "research_intelligence_extraction"' in q['sql'].lower()
        ]
        self.assertEqual(len(papermetric_queries), 1, "PaperMetric must be queried exactly once")
        self.assertEqual(len(extraction_queries), 1, "Extraction must be queried exactly once (bulk-fetched)")

        data = resp.json()
        self.assertEqual(len(data["papers"]), 5)
        self.assertEqual(len(data["exclusions"]), 5)

        # Must be ordered descending by signal_score (90.0 down to 50.0)
        scores = [p["signal_score"] for p in data["papers"]]
        self.assertEqual(scores, [90.0, 80.0, 70.0, 60.0, 50.0])

        # Verify each paper has its dimensions unpacked
        for p in data["papers"]:
            self.assertEqual(len(p["dimensions"]), 2)

    def test_pipeline_runs_list_defers_heavy_json_fields_and_retrieve_includes_them(self):
        """
        Verify GET /api/pipeline-runs/:
        1. List endpoint defers and omits heavy JSON blobs ('step_history', 'stage_results')
           to prevent multi-megabyte payload bloat and high DB serialization cost on /runs and /dashboard.
        2. Detail endpoint GET /api/pipeline-runs/{id}/ continues to deliver full telemetry
           including 'step_history' and 'stage_results'.
        """
        run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Heavy Telemetry Run",
            status="completed",
            completed_at=timezone.now(),
            total_papers_fetched=100,
            total_papers_passed_screening=25,
            step_history=[{"step": "search", "trace": "x" * 500}] * 20,
            stage_results={"screening": {"detail": "y" * 1000}},
        )

        # 1. Test GET /api/pipeline-runs/ (list)
        resp_list = self.client.get("/api/pipeline-runs/")
        self.assertEqual(resp_list.status_code, 200)
        items = resp_list.json()
        target_item = next(item for item in items if item["id"] == str(run.id))

        # Heavy JSON fields must NOT be serialized in list view
        self.assertNotIn("step_history", target_item)
        self.assertNotIn("stage_results", target_item)

        # Required fields for /runs and /dashboard tables must be present
        self.assertEqual(target_item["id"], str(run.id))
        self.assertEqual(target_item["workspace_name"], self.workspace.name)
        self.assertEqual(target_item["status"], "completed")
        self.assertEqual(target_item["total_papers_fetched"], 100)
        self.assertEqual(target_item["total_papers_passed_screening"], 25)

        # 2. Test GET /api/pipeline-runs/{id}/ (detail)
        resp_detail = self.client.get(f"/api/pipeline-runs/{run.id}/")
        self.assertEqual(resp_detail.status_code, 200)
        detail_data = resp_detail.json()

        # Detail endpoint MUST include the full telemetry
        self.assertIn("step_history", detail_data)
        self.assertIn("stage_results", detail_data)
        self.assertEqual(len(detail_data["step_history"]), 20)
        self.assertIn("screening", detail_data["stage_results"])

    def test_edition_detail_handles_undefined_and_invalid_run_id_gracefully(self):
        """
        Verify GET /api/workspaces/{id}/editions/{date}/ safely handles:
        - ?run_id=undefined
        - ?run_id=null
        - ?run_id=invalid-uuid-string
        without raising an unhandled 500 ValidationError, safely falling back to date-based lookup.
        """
        target_date = datetime(2026, 9, 8, 14, 0, 0, tzinfo=dt_timezone.utc)
        run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Edition Test Run",
            status="completed",
            completed_at=target_date,
            total_papers_fetched=5,
            total_papers_passed_screening=2,
        )

        for invalid_param in ["undefined", "null", "not-a-valid-uuid", ""]:
            resp = self.client.get(
                f"/api/workspaces/{self.workspace.id}/editions/2026-09-08/?run_id={invalid_param}"
            )
            self.assertEqual(
                resp.status_code,
                200,
                f"Expected 200 OK fallback for ?run_id={invalid_param}, got {resp.status_code}: {resp.content}"
            )
            data = resp.json()
            self.assertEqual(data["run_id"], str(run.id))
            self.assertEqual(data["date"], "2026-09-08")

    def test_workspace_scorecard_pagination_preserves_global_ordering(self):
        """
        Verify that requesting pagination (page_size=2) with ordering by score (-signal_score)
        properly orders results in the database before slicing, so Page 1 gets the global highest scores.
        """
        # Create 4 papers with varying creation times and scores
        # p1 created first (oldest), but has the HIGHEST score (95)
        p1 = Paper.objects.create(workspace=self.workspace, title="Oldest Highest Score Paper", arxiv_id="2609.0001", hash_id="hash_0001")
        p2 = Paper.objects.create(workspace=self.workspace, title="Mid High Score Paper", arxiv_id="2609.0002", hash_id="hash_0002")
        p3 = Paper.objects.create(workspace=self.workspace, title="Mid Low Score Paper", arxiv_id="2609.0003", hash_id="hash_0003")
        p4 = Paper.objects.create(workspace=self.workspace, title="Newest Lowest Score Paper", arxiv_id="2609.0004", hash_id="hash_0004")

        run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Scorecard Ordering Run",
            status="completed",
            completed_at=timezone.now(),
        )

        PaperMetric.objects.create(workspace=self.workspace, paper=p1, pipeline_run=run, signal_score=95.0, screening_status="accepted")
        PaperMetric.objects.create(workspace=self.workspace, paper=p2, pipeline_run=run, signal_score=80.0, screening_status="accepted")
        PaperMetric.objects.create(workspace=self.workspace, paper=p3, pipeline_run=run, signal_score=50.0, screening_status="accepted")
        PaperMetric.objects.create(workspace=self.workspace, paper=p4, pipeline_run=run, signal_score=20.0, screening_status="accepted")

        # Request Page 1 with page_size=2 and ordering=-signal_score
        resp = self.client.get(
            f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&page=1&page_size=2&ordering=-signal_score"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 4)
        self.assertEqual(len(data["papers"]), 2)

        # Page 1 must contain p1 (95) and p2 (80)
        scores_page_1 = [p["signal_score"] for p in data["papers"]]
        self.assertEqual(scores_page_1, [95.0, 80.0])

        # Request Page 2
        resp2 = self.client.get(
            f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run.id}&page=2&page_size=2&ordering=-signal_score"
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        scores_page_2 = [p["signal_score"] for p in data2["papers"]]
        self.assertEqual(scores_page_2, [50.0, 20.0])

    def test_workspace_scorecard_screening_status_scoped_to_same_metric_join(self):
        """
        Verify that when filtering by run_id AND screening_status=passed, a paper that was
        accepted in Run A but rejected in Run B does NOT show up as passed when querying Run B.
        """
        paper = Paper.objects.create(workspace=self.workspace, title="Multi-Run Paper", arxiv_id="2609.9999", hash_id="hash_multirun")
        run_a = PipelineRun.objects.create(workspace=self.workspace, name="Run A", status="completed")
        run_b = PipelineRun.objects.create(workspace=self.workspace, name="Run B", status="completed")

        # In Run A, paper was accepted with score 90
        PaperMetric.objects.create(workspace=self.workspace, paper=paper, pipeline_run=run_a, signal_score=90.0, screening_status="accepted")
        # In Run B, paper was rejected with score 10
        PaperMetric.objects.create(workspace=self.workspace, paper=paper, pipeline_run=run_b, signal_score=10.0, screening_status="rejected")

        # Query Run B with screening=passed -> should return 0 papers!
        resp_b = self.client.get(
            f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run_b.id}&screening=passed"
        )
        self.assertEqual(resp_b.status_code, 200)
        data_b = resp_b.json()
        self.assertEqual(len(data_b["papers"]), 0, "Paper was rejected in Run B, must not match screening=passed for Run B")

        # Query Run A with screening=passed -> should return 1 paper!
        resp_a = self.client.get(
            f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={run_a.id}&screening=passed"
        )
        self.assertEqual(resp_a.status_code, 200)
        data_a = resp_a.json()
        self.assertEqual(len(data_a["papers"]), 1)
        self.assertEqual(data_a["papers"][0]["id"], str(paper.id))
        self.assertEqual(data_a["papers"][0]["screening_status"], "accepted")







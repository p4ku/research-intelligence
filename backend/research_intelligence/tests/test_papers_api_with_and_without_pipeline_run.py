import uuid
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    Paper,
    PaperMetric,
)
from api.serializers.papers import PaperSerializer

User = get_user_model()


class PapersApiWithAndWithoutPipelineRunTestCase(TestCase):
    """
    Dedicated test suite validating that /api/papers/ works seamlessly:
    1. WITH an explicit pipeline_run UUID.
    2. WITH pipeline_run=latest.
    3. WITHOUT any pipeline_run parameter (workspace-level and global corpus).
    4. When papers have NO metrics attached (freshly scraped or unlinked).
    5. On /api/workspaces/{id}/papers/ endpoint with and without pipeline_run.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="contract_user",
            email="contract@schwarz.de",
            password="securepassword123!"
        )
        self.workspace = Workspace.objects.create(name="Quantum NLP Contract Workspace")
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Create two distinct pipeline runs
        self.older_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Older Run 2026-01",
            status="completed"
        )
        self.newer_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Newer Run 2026-02",
            status="completed"
        )

        # Paper 1: Evaluated in BOTH runs with different metrics
        self.paper_multi = Paper.objects.create(
            workspace=self.workspace,
            title="Quantum Convolutional Networks for Materials",
            hash_id="hash_multi_1",
            doi="10.1000/qcn.1",
            arxiv_id="2601.00001",
            authors="Alice Q., Bob N.",
            abstract="Quantum convolutional networks...",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=self.paper_multi,
            pipeline_run=self.older_run,
            workspace=self.workspace,
            screening_status="borderline",
            abstract_screening_reasoning="Older abstract reasoning: marginal novelty.",
            signal_score=45.0
        )
        PaperMetric.objects.create(
            paper=self.paper_multi,
            pipeline_run=self.newer_run,
            workspace=self.workspace,
            screening_status="accepted",
            abstract_screening_reasoning="Newer abstract reasoning: accepted.",
            full_text_screening_reasoning="Newer full-text reasoning: verified experimental results.",
            signal_score=88.5
        )

        # Paper 2: Only evaluated in older run
        self.paper_older_only = Paper.objects.create(
            workspace=self.workspace,
            title="Superconducting Qubit Scalability Limits",
            hash_id="hash_older_2",
            doi="10.1000/squbit.2",
            authors="Carol T.",
            abstract="Limits of superconducting qubits...",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=self.paper_older_only,
            pipeline_run=self.older_run,
            workspace=self.workspace,
            screening_status="rejected",
            abstract_screening_reasoning="Rejected: does not meet TRL 4.",
            signal_score=15.0
        )

        # Paper 3: Freshly ingested, NO PaperMetric attached at all
        self.paper_unprocessed = Paper.objects.create(
            workspace=self.workspace,
            title="Topological Braiding in Nanowires",
            hash_id="hash_unprocessed_3",
            doi="10.1000/nanowire.3",
            authors="Dave N.",
            abstract="Braiding operations in Majorana wires...",
            source_database="arxiv"
        )

    def test_1_query_with_explicit_pipeline_run(self):
        """
        WITH pipeline_run=<older_run.id>:
        - Returns only papers evaluated in that run (paper_multi and paper_older_only).
        - Excludes papers not in that run (paper_unprocessed).
        - Serializes run-specific scores and reasonings.
        """
        res = self.client.get(f"/api/papers/?pipeline_run={self.older_run.id}")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 2)

        p_multi = next(p for p in items if p["id"] == str(self.paper_multi.id))
        self.assertEqual(p_multi["pipeline_run"], str(self.older_run.id))
        self.assertEqual(p_multi["screening_status"], "borderline")
        self.assertEqual(p_multi["screening_reasoning"], "Older abstract reasoning: marginal novelty.")
        self.assertEqual(p_multi["signal_score"], 45.0)

        # WITH pipeline_run=<newer_run.id>:
        res_newer = self.client.get(f"/api/papers/?pipeline_run={self.newer_run.id}")
        self.assertEqual(res_newer.status_code, 200)
        items_newer = res_newer.json()
        self.assertEqual(len(items_newer), 1)
        p_newer = items_newer[0]
        self.assertEqual(p_newer["id"], str(self.paper_multi.id))
        self.assertEqual(p_newer["pipeline_run"], str(self.newer_run.id))
        self.assertEqual(p_newer["screening_status"], "accepted")
        self.assertEqual(p_newer["screening_reasoning"], "Newer full-text reasoning: verified experimental results.")
        self.assertEqual(p_newer["signal_score"], 88.5)

    def test_2_query_with_pipeline_run_latest(self):
        """
        WITH pipeline_run=latest:
        - Automatically resolves to self.newer_run (the latest completed run).
        - Returns matching papers with metrics for that latest run.
        """
        res = self.client.get(f"/api/papers/?workspace_id={self.workspace.id}&pipeline_run=latest")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertEqual(item["id"], str(self.paper_multi.id))
        self.assertEqual(item["pipeline_run"], str(self.newer_run.id))
        self.assertEqual(item["screening_status"], "accepted")
        self.assertEqual(item["signal_score"], 88.5)

    def test_3_query_without_pipeline_run_resolves_contract(self):
        """
        WITHOUT pipeline_run:
        - Returns ALL workspace papers (3 papers: multi, older_only, unprocessed).
        - Every paper has a non-null, valid UUID string for 'pipeline_run'.
        - 'screening_reasoning' key is always present (string or null, never undefined).
        - Multi-evaluated paper picks up the latest run's metric.
        - Unprocessed paper falls back to the workspace's latest valid run ID.
        """
        res = self.client.get("/api/papers/")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 3)

        for p in items:
            # Crucial frontend contract assertions:
            self.assertIn("pipeline_run", p)
            self.assertIn("pipeline_run_id", p)
            self.assertIn("run_id", p)
            self.assertIn("screening_reasoning", p)

            # pipeline_run must NOT be null or empty; must parse as valid UUID
            pr_val = p["pipeline_run"]
            self.assertIsNotNone(pr_val)
            self.assertNotEqual(pr_val, "")
            parsed_uuid = uuid.UUID(str(pr_val))
            self.assertTrue(parsed_uuid)

            # pipeline_run_id and run_id match pipeline_run
            self.assertEqual(p["pipeline_run_id"], pr_val)
            self.assertEqual(p["run_id"], pr_val)

        # Check paper_multi resolves to newest run's metric
        p_multi = next(p for p in items if p["id"] == str(self.paper_multi.id))
        self.assertEqual(p_multi["pipeline_run"], str(self.newer_run.id))
        self.assertEqual(p_multi["screening_status"], "accepted")
        self.assertEqual(p_multi["signal_score"], 88.5)
        self.assertEqual(p_multi["screening_reasoning"], "Newer full-text reasoning: verified experimental results.")

        # Check paper_unprocessed (no metrics) falls back to latest run ID and status 'pending'
        p_unproc = next(p for p in items if p["id"] == str(self.paper_unprocessed.id))
        self.assertEqual(p_unproc["pipeline_run"], str(self.newer_run.id))
        self.assertEqual(p_unproc["screening_status"], "pending")
        self.assertIsNone(p_unproc["screening_reasoning"])
        self.assertIsNone(p_unproc["signal_score"])

    def test_4_workspace_papers_endpoint_with_and_without_pipeline_run(self):
        """
        Tests the /api/workspaces/{id}/papers/ action:
        - Without ?pipeline_run: returns all 3 papers for this workspace.
        - With ?pipeline_run: returns filtered papers.
        """
        # Without pipeline_run
        res_all = self.client.get(f"/api/workspaces/{self.workspace.id}/papers/")
        self.assertEqual(res_all.status_code, 200)
        items_all = res_all.json()
        self.assertEqual(len(items_all), 3)

        # With pipeline_run
        res_older = self.client.get(f"/api/workspaces/{self.workspace.id}/papers/?pipeline_run={self.older_run.id}")
        self.assertEqual(res_older.status_code, 200)
        items_older = res_older.json()
        self.assertEqual(len(items_older), 2)

    def test_5_scorecard_and_component_runs_filtering(self):
        """
        Tests the /api/papers/{id}/scorecard/ endpoint and component-runs filtering.
        """
        from research_intelligence.models import ComponentRun
        c_run = ComponentRun.objects.create(
            pipeline_run=self.newer_run,
            step_type="search",
            component_name="arXiv Ingest",
            status="completed",
        )

        # Test scorecard endpoint
        res_card = self.client.get(f"/api/papers/{self.paper_multi.id}/scorecard/")
        self.assertEqual(res_card.status_code, 200)
        data = res_card.json()
        self.assertIn("workspace", data)
        self.assertIn("paper", data)
        self.assertEqual(data["paper"]["id"], str(self.paper_multi.id))
        self.assertEqual(data["paper"]["title"], self.paper_multi.title)
        self.assertEqual(data["paper"]["signal_score"], 88.5)

        # Test component-runs with workspace and pipeline_run filters
        res_cr = self.client.get(f"/api/component-runs/?workspace={self.workspace.id}")
        self.assertEqual(res_cr.status_code, 200)
        cr_items = res_cr.json()
        self.assertEqual(len(cr_items), 1)

        # Test component-runs with pipeline_run=latest
        res_cr_latest = self.client.get(f"/api/component-runs/?workspace={self.workspace.id}&pipeline_run=latest")
        self.assertEqual(res_cr_latest.status_code, 200)
        cr_latest_items = res_cr_latest.json()
        self.assertEqual(len(cr_latest_items), 1)


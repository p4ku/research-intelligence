import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    ComponentRun,
    Paper,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
    ResearchAgentProcess,
    Scraper,
)
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
from mcp_server.tools.agents import (
    start_research_agent_logic,
    check_run_status_logic,
    get_research_agent_status_logic,
)
from mcp_server.tools.pipeline_runs import trigger_search_job_logic, get_pipeline_run_status_logic
from mcp_server.tools.pipeline_runs.triggers import start_pipeline_run_logic
from mcp_server.tools.extractions import get_paper_extractions_matrix_logic
from mcp_server.tools.workspaces.crud import list_workspaces_logic, get_workspace_logic, create_workspace_logic, update_workspace_logic
from rest_framework.test import APIClient
from rest_framework import status
from research_intelligence.services.workspace_service import create_workspace_record, serialize_workspace_configuration
from research_intelligence.tasks.orchestrator.runner import ResearchAgentRunner
from research_intelligence.tasks.step_1_search.node import SearchNode
from research_intelligence.tasks.step_4_screening.node import AbstractScreeningNode, FullTextScreeningNode

User = get_user_model()


class ReprocessExistingPipelineE2ETestCase(TestCase):
    """
    End-to-End Test Suite verifying duplicate handling and the 'reprocess_existing' feature:
    1. reprocess_existing=False: Stops gracefully at Step 1 (Search & Ingestion) with halted_zero_papers.
    2. reprocess_existing=True: Re-links existing workspace papers and executes all pipeline steps
       (Search -> Download -> Screening -> Extraction -> Signal Score).
    3. MCP Tool Level verification of reprocess_existing parameter.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="e2e_reprocess_user", email="reprocess@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="Reprocess E2E Workspace",
            screening_llm_model="google/gemini-3.8-flash",
            ocr_provider=None,  # Direct multimodal PDF screening
            skip_abstract_screening=True,  # Direct Full-Text Screening
            full_text_acceptance_criteria="Accept deep tech innovations in quantum machine learning.",
            full_text_rejection_criteria="Reject pure marketing material.",
            signal_score_code="score = 0.5 * trl_level + 0.5 * novelty_score\nreturn round(score, 2)"
        )
        from research_intelligence.models import WorkspaceMember
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role='admin')

        self.scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="quantum neural networks",
            limit=5
        )

        self.ext_def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            system_prompt="Extract technology readiness level 1-9.",
            user_prompt_template="Extract TRL from paper: {paper_text}",
            response_schema={"type": "object", "properties": {"trl": {"type": "integer"}}, "required": ["trl"]},
            exit_metrics="trl"
        )

        self.ext_def_nov = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            system_prompt="Rate novelty 1-10.",
            user_prompt_template="Extract novelty score from paper: {paper_text}",
            response_schema={"type": "object", "properties": {"score": {"type": "number"}}, "required": ["score"]},
            exit_metrics="score"
        )

        self.raw_scraped_items = [
            {
                "hash_id": "arxiv_qml_001",
                "arxiv_id": "2401.00001v1",
                "doi": "10.1000/arxiv.2401.00001",
                "title": "Quantum Neural Network Scalability on Transmon Arrays",
                "authors": "Alice Smith, Bob Jones",
                "abstract": "We demonstrate empirical scaling for parameterized quantum circuits.",
                "source_database": "arxiv",
                "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf"
            },
            {
                "hash_id": "arxiv_qml_002",
                "arxiv_id": "2401.00002v1",
                "doi": "10.1000/arxiv.2401.00002",
                "title": "Error-Resilient Quantum Variational Classifiers",
                "authors": "Carol White, Dave Brown",
                "abstract": "Noise-robust quantum embeddings for supervised classification.",
                "source_database": "arxiv",
                "pdf_url": "https://arxiv.org/pdf/2401.00002.pdf"
            }
        ]

    def _mock_llm_and_pdf(self):
        """Helper to mock PDF downloads and LLM calls (Screening + Extraction)."""
        # Mock requests.get for PDF download
        mock_pdf_resp = MagicMock()
        mock_pdf_resp.status_code = 200
        mock_pdf_resp.content = b"%PDF-1.5 Mock PDF Binary Content for Testing"
        mock_pdf_resp.headers = {"Content-Type": "application/pdf"}

        def mock_llm_generate(*args, **kwargs):
            prompt_str = str(kwargs.get("prompt", "") or (args[0] if len(args) > 0 else ""))
            sys_str = str(kwargs.get("system_instruction", "") or (args[1] if len(args) > 1 else ""))

            if "Screening" in sys_str or "full_text" in prompt_str or "Screening" in prompt_str or "methodology" in prompt_str.lower():
                return {
                    "passed": True,
                    "reasoning": "Strong methodology with quantum experimental results.",
                    "evidence_quotes": ["We demonstrate empirical scaling on 16-qubit array."],
                    "decision_category": "ACCEPTED"
                }
            elif "TRL Level" in sys_str or "TRL" in prompt_str or "readiness" in prompt_str:
                return {"trl": 6}
            elif "Novelty Score" in sys_str or "Novelty" in prompt_str or "novelty" in prompt_str:
                return {"score": 8.5}
            return {"passed": True, "value": 7.0}

        return mock_pdf_resp, mock_llm_generate

    def _drive_agent_to_completion(self, process_id: str, max_ticks: int = 15):
        """Helper to advance the agent process via check_run_status_logic until completion."""
        for _ in range(max_ticks):
            res_str = check_run_status_logic(user=self.user, process_id=process_id)
            res = json.loads(res_str)
            if res.get("is_finished") or res.get("status") in ["completed", "failed", "aborted"]:
                return res
        return json.loads(check_run_status_logic(user=self.user, process_id=process_id))

    def test_reprocess_existing_false_halts_at_step_1_when_all_papers_are_duplicates(self):
        """
        Scenario 1:
        1. Run 1 ingests 2 papers into the workspace.
        2. Run 2 is started with reprocess_existing=False (default).
        3. Scraper returns the exact same 2 papers (100% duplicate).
        4. Verifies Run 2 halts gracefully at Step 1 (halted_zero_papers) and does NOT execute downstream stages.
        """
        mock_pdf_resp, mock_llm_generate = self._mock_llm_and_pdf()

        with patch("requests.get", return_value=mock_pdf_resp), \
             patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_scraper, \
             patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate", side_effect=mock_llm_generate):

            provider_inst = MagicMock()
            provider_inst.search.return_value = self.raw_scraped_items
            mock_scraper.return_value = provider_inst

            # 1. Run 1: Ingests 2 papers through the state engine
            res_str = start_research_agent_logic(
                user=self.user,
                workspace_id=str(self.workspace.id),
                name="Initial Ingestion Run",
                reprocess_existing=False
            )
            run1_info = json.loads(res_str)
            self.assertEqual(run1_info["status"], "success")
            proc1_id = run1_info["process_id"]

            # Drive Run 1 to complete all steps 1-6
            wait_res = self._drive_agent_to_completion(proc1_id)
            self.assertEqual(wait_res["agent_status"], "completed")

            proc1 = ResearchAgentProcess.objects.get(id=proc1_id)
            self.assertEqual(proc1.pipeline_run.papers.count(), 2)
            self.assertEqual(Paper.objects.filter(workspace=self.workspace).count(), 2)

            # 2. Run 2: Start with reprocess_existing=False on the same search query
            res2_str = start_research_agent_logic(
                user=self.user,
                workspace_id=str(self.workspace.id),
                name="Second Run - No Reprocessing",
                reprocess_existing=False
            )
            run2_info = json.loads(res2_str)
            proc2_id = run2_info["process_id"]

            # Drive Run 2 to finish
            wait2_res = self._drive_agent_to_completion(proc2_id)
            self.assertEqual(wait2_res["agent_status"], "completed")

            proc2 = ResearchAgentProcess.objects.get(id=proc2_id)
            self.assertEqual(proc2.status, "completed")
            self.assertEqual(proc2.current_step, "completed")
            self.assertEqual(proc2.pipeline_run.papers.count(), 0)

            # Audit step history contains halted_zero_papers
            history_events = [h.get("event") for h in proc2.step_history]
            self.assertIn("halted_zero_papers", history_events)
            self.assertIn("0 papers were found matching criteria", proc2.step_history[-1]["message"])

            # Verify no downstream component runs were spawned for Run 2
            comp_types_run2 = list(ComponentRun.objects.filter(pipeline_run=proc2.pipeline_run).values_list("step_type", flat=True))
            self.assertEqual(comp_types_run2, ["search"])

    def test_reprocess_existing_true_runs_full_pipeline_on_duplicate_papers(self):
        """
        Scenario 2:
        1. Workspace already contains 2 ingested papers from previous runs.
        2. Run 3 is started with reprocess_existing=True.
        3. Scraper returns the same duplicate papers.
        4. Verifies Run 3 re-links the papers and executes all steps 1-6 to completion (Search -> Download -> Screening -> Extraction -> Signal Score).
        """
        mock_pdf_resp, mock_llm_generate = self._mock_llm_and_pdf()

        # Seed workspace with 2 existing papers attached to an older completed run
        old_run = PipelineRun.objects.create(workspace=self.workspace, status="completed", current_stage="completed")
        p1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=old_run,
            hash_id=self.raw_scraped_items[0]["hash_id"],
            arxiv_id=self.raw_scraped_items[0]["arxiv_id"],
            doi=self.raw_scraped_items[0]["doi"],
            title=self.raw_scraped_items[0]["title"],
            authors=self.raw_scraped_items[0]["authors"],
            abstract=self.raw_scraped_items[0]["abstract"],
            source_database="arxiv"
        )
        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=old_run,
            hash_id=self.raw_scraped_items[1]["hash_id"],
            arxiv_id=self.raw_scraped_items[1]["arxiv_id"],
            doi=self.raw_scraped_items[1]["doi"],
            title=self.raw_scraped_items[1]["title"],
            authors=self.raw_scraped_items[1]["authors"],
            abstract=self.raw_scraped_items[1]["abstract"],
            source_database="arxiv"
        )
        self.assertEqual(Paper.objects.filter(workspace=self.workspace).count(), 2)

        with patch("requests.get", return_value=mock_pdf_resp), \
             patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_scraper, \
             patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate", side_effect=mock_llm_generate):

            provider_inst = MagicMock()
            provider_inst.search.return_value = self.raw_scraped_items
            mock_scraper.return_value = provider_inst

            # Launch agent with reprocess_existing=True
            res_str = start_research_agent_logic(
                user=self.user,
                workspace_id=str(self.workspace.id),
                name="Reprocessing Run",
                reprocess_existing=True
            )
            run_info = json.loads(res_str)
            self.assertEqual(run_info["status"], "success")
            proc_id = run_info["process_id"]

            # Drive execution across all stages
            wait_res = self._drive_agent_to_completion(proc_id)
            self.assertEqual(wait_res["agent_status"], "completed")

            proc = ResearchAgentProcess.objects.get(id=proc_id)
            self.assertTrue(proc.pipeline_run.reprocess_existing)
            self.assertEqual(proc.pipeline_run.papers.count(), 2)

            # Check that all stages were executed in component runs
            comp_types = list(ComponentRun.objects.filter(pipeline_run=proc.pipeline_run).order_by("started_at", "id").values_list("step_type", flat=True))
            self.assertIn("search", comp_types)
            self.assertIn("download", comp_types)
            self.assertIn("screening", comp_types)
            self.assertIn("extraction", comp_types)
            self.assertIn("signal_score", comp_types)

            # Check extractions created
            extractions = Extraction.objects.filter(paper__in=proc.pipeline_run.papers.all())
            self.assertTrue(extractions.count() >= 2)

            # Check signal score evaluated and PaperMetric records generated per pipeline_run
            metrics = PaperMetric.objects.filter(pipeline_run=proc.pipeline_run)
            self.assertEqual(metrics.count(), 2)
            for m in metrics:
                self.assertEqual(float(m.signal_score), 7.25)
                self.assertEqual(m.pipeline_run, proc.pipeline_run)

            for paper in proc.pipeline_run.papers.all():
                pm = PaperMetric.objects.get(paper=paper, pipeline_run=proc.pipeline_run)
                self.assertIsNotNone(pm.signal_score)
                # TRL=6, Novelty=8.5 -> score = 0.5 * 6 + 0.5 * 8.5 = 7.25
                self.assertEqual(float(pm.signal_score), 7.25)

            # Verify extractions matrix via MCP
            matrix_json = get_paper_extractions_matrix_logic(user=self.user, workspace_id=str(self.workspace.id), pipeline_run_id=str(proc.pipeline_run.id))
            matrix = json.loads(matrix_json)
            self.assertEqual(matrix["total_papers"], 2)
            self.assertEqual(matrix["top_signal_score"], 7.25)
            self.assertEqual(matrix["avg_signal_score"], 7.25)
            for entry in matrix["papers"]:
                self.assertEqual(entry["signal_score"], 7.25)
                self.assertEqual(entry["extractions_count"], 2)

    def test_mcp_trigger_search_job_reprocess_existing_flag(self):
        """
        Tests trigger_search_job_logic MCP tool with reprocess_existing=True vs reprocess_existing=False.
        """
        # Create an existing paper in workspace
        old_run = PipelineRun.objects.create(workspace=self.workspace, status="completed", current_stage="completed")
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=old_run,
            hash_id=self.raw_scraped_items[0]["hash_id"],
            arxiv_id=self.raw_scraped_items[0]["arxiv_id"],
            doi=self.raw_scraped_items[0]["doi"],
            title=self.raw_scraped_items[0]["title"],
            authors=self.raw_scraped_items[0]["authors"],
            abstract=self.raw_scraped_items[0]["abstract"],
            source_database="arxiv"
        )

        with patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_scraper:
            provider_inst = MagicMock()
            provider_inst.search.return_value = self.raw_scraped_items
            mock_scraper.return_value = provider_inst

            # 1. Trigger with reprocess_existing=False
            res_false_str = trigger_search_job_logic(
                user=self.user,
                workspace_id=str(self.workspace.id),
                limit=10,
                reprocess_existing=False
            )
            res_false = json.loads(res_false_str)
            self.assertTrue(res_false["success"])
            run_false_id = res_false["pipeline_run_id"]
            run_false = PipelineRun.objects.get(id=run_false_id)
            self.assertFalse(run_false.reprocess_existing)
            # Only the 2nd paper (new) was created, the 1st paper (duplicate) was skipped
            self.assertEqual(run_false.papers.count(), 1)

            # 2. Trigger with reprocess_existing=True
            res_true_str = trigger_search_job_logic(
                user=self.user,
                workspace_id=str(self.workspace.id),
                limit=10,
                reprocess_existing=True
            )
            res_true = json.loads(res_true_str)
            self.assertTrue(res_true["success"])
            run_true_id = res_true["pipeline_run_id"]
            run_true = PipelineRun.objects.get(id=run_true_id)
            self.assertTrue(run_true.reprocess_existing)
            # Both papers are now linked to run_true (the re-linked duplicate + new paper)
            self.assertEqual(run_true.papers.count(), 2)


class WorkspaceReprocessFlagTestCase(TestCase):
    """
    Tests verifying the workspace-level `reprocess_existing` flag:
    1. Default value is False.
    2. Model, Admin, and REST API serialize and persist `reprocess_existing`.
    3. Pipeline runs and Agent processes inherit workspace default when not explicitly overridden.
    4. Per-run explicit overrides take precedence over workspace default (both True->False and False->True).
    5. MCP CRUD tools and DAG execution nodes honor workspace-level default.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="ws_reprocess_user", email="user@test.com", password="password123")
        self.admin = User.objects.create_superuser(username="ws_reprocess_admin", email="admin@test.com", password="password123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_workspace_default_reprocess_existing_is_false(self):
        ws = Workspace.objects.create(name="Default WS")
        self.assertFalse(ws.reprocess_existing)

        # Service creation
        ws2, err = create_workspace_record(user=self.user, name="Service WS")
        self.assertIsNone(err)
        self.assertFalse(ws2.reprocess_existing)

    def test_workspace_create_and_update_with_reprocess_existing_true(self):
        ws, err = create_workspace_record(user=self.admin, name="Reprocess Active WS", reprocess_existing=True)
        self.assertIsNone(err)
        self.assertTrue(ws.reprocess_existing)

        serialized = serialize_workspace_configuration(ws)
        self.assertTrue(serialized.get("reprocess_existing"))

        # Test REST API GET / PATCH
        res_get = self.client.get(f"/api/workspaces/{ws.id}/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertIn("reprocess_existing", res_get.data)
        self.assertTrue(res_get.data["reprocess_existing"])

        # Patch to False
        res_patch = self.client.patch(f"/api/workspaces/{ws.id}/", {"reprocess_existing": False}, format="json")
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        ws.refresh_from_db()
        self.assertFalse(ws.reprocess_existing)

    def test_mcp_workspace_crud_reprocess_existing_lifecycle(self):
        # 1. Create via MCP
        res_raw = create_workspace_logic(self.admin, name="MCP Reprocess WS", reprocess_existing=True)
        res = json.loads(res_raw)
        self.assertEqual(res["status"], "success")
        ws_id = res["workspace_id"]

        ws = Workspace.objects.get(id=ws_id)
        self.assertTrue(ws.reprocess_existing)

        # 2. Get via MCP
        details = json.loads(get_workspace_logic(self.admin, workspace_id=ws_id))
        self.assertTrue(details["reprocess_existing"])

        # 3. List via MCP
        ws_list = json.loads(list_workspaces_logic(self.admin))
        matched = next(w for w in ws_list if w["workspace_id"] == ws_id)
        self.assertTrue(matched["reprocess_existing"])

        # 4. Update via MCP to False
        up_raw = update_workspace_logic(self.admin, workspace_id=ws_id, reprocess_existing=False)
        up_res = json.loads(up_raw)
        self.assertEqual(up_res["status"], "success")
        ws.refresh_from_db()
        self.assertFalse(ws.reprocess_existing)

    def test_agent_process_inherits_workspace_reprocess_existing_default(self):
        ws_true = Workspace.objects.create(name="Reprocess Enabled WS", reprocess_existing=True)
        WorkspaceMember.objects.create(workspace=ws_true, user=self.admin, role="admin")

        # 1. Start agent without explicit override -> inherits True
        start_res_raw = start_research_agent_logic(self.admin, workspace_id=str(ws_true.id), name="Inherit True Agent")
        start_res = json.loads(start_res_raw)
        self.assertEqual(start_res["status"], "success")
        proc_true = ResearchAgentProcess.objects.get(id=start_res["process_id"])
        self.assertTrue(proc_true.configuration_override.get("reprocess_existing"))

        # Tick runner -> PipelineRun inherits True
        with patch("research_intelligence.tasks.orchestrator.dag.engine.WorkflowDAG.evaluate_and_dispatch") as mock_disp:
            mock_disp.return_value = {"status": "running"}
            ResearchAgentRunner.tick(str(proc_true.id))
            proc_true.refresh_from_db()
            self.assertIsNotNone(proc_true.pipeline_run)
            self.assertTrue(proc_true.pipeline_run.reprocess_existing)

        # 2. Start agent with explicit override reprocess_existing=False -> overrides workspace True
        start_false_raw = start_research_agent_logic(
            self.admin, workspace_id=str(ws_true.id), name="Override False Agent", reprocess_existing=False
        )
        proc_false = ResearchAgentProcess.objects.get(id=json.loads(start_false_raw)["process_id"])
        self.assertFalse(proc_false.configuration_override.get("reprocess_existing"))

    def test_pipeline_run_trigger_search_job_inherits_workspace_reprocess(self):
        ws_true = Workspace.objects.create(name="Scraper WS", reprocess_existing=True)
        WorkspaceMember.objects.create(workspace=ws_true, user=self.admin, role="admin")
        scraper = Scraper.objects.create(workspace=ws_true, provider="arxiv", search_query="quantum", is_active=True)

        with patch("mcp_server.tools.pipeline_runs.triggers.execute_scraper_run_job.delay"):
            # Trigger without explicit reprocess_existing argument -> inherits workspace True
            res_raw = trigger_search_job_logic(self.admin, workspace_id=str(ws_true.id), scraper_id=str(scraper.id))
            res = json.loads(res_raw)
            self.assertTrue(res.get("success"))
            run = PipelineRun.objects.get(id=res["pipeline_run_id"])
            self.assertTrue(run.reprocess_existing)

            # Trigger with explicit reprocess_existing=False -> overrides workspace True
            res_raw_override = trigger_search_job_logic(
                self.admin, workspace_id=str(ws_true.id), scraper_id=str(scraper.id), reprocess_existing=False
            )
            res_ov = json.loads(res_raw_override)
            self.assertTrue(res_ov.get("success"))
            run_override = PipelineRun.objects.get(id=res_ov["pipeline_run_id"])
            self.assertFalse(run_override.reprocess_existing)

    def test_dag_nodes_honor_workspace_reprocess_fallback(self):
        ws_true = Workspace.objects.create(name="DAG Fallback WS", reprocess_existing=True)
        run_no_override = PipelineRun.objects.create(workspace=ws_true, reprocess_existing=False)

        search_node = SearchNode()
        abs_node = AbstractScreeningNode()
        ft_node = FullTextScreeningNode()

        # When config is empty, fallback checks pipeline_run then workspace
        self.assertFalse(search_node.should_halt_pipeline(run_no_override, ws_true, {})[0])

    def test_reprocess_existing_preserves_historical_run_and_status(self):
        from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job
        ws = Workspace.objects.create(name="Preserve History WS")
        run_1 = PipelineRun.objects.create(workspace=ws, status='completed')
        paper_1 = Paper.objects.create(
            workspace=ws,
            pipeline_run=run_1,
            hash_id="unique_hash_paper_1",
            doi="10.1000/182",
            arxiv_id="2101.00001",
            title="Transformer Scaling Laws",
            authors="Vaswani et al.",
            abstract="Study on transformer scaling."
        )
        PaperMetric.objects.create(
            paper=paper_1,
            pipeline_run=run_1,
            workspace=ws,
            screening_status="abstract_passed",
            abstract_screening_reasoning="Passed in Run 1",
            signal_score=0.85
        )

        run_2 = PipelineRun.objects.create(workspace=ws, status='running', reprocess_existing=True)
        scraper = Scraper.objects.create(workspace=ws, provider="arxiv", search_query="transformer")
        comp_run_search = ComponentRun.objects.create(
            pipeline_run=run_2,
            step_type='search',
            component_name='arxiv_search',
            scraper=scraper,
            status='running'
        )

        mock_scraper_items = [{
            "source_database": "arxiv",
            "hash_id": "different_hash_from_scraper",
            "doi": "10.1000/182",
            "arxiv_id": "2101.00001",
            "title": "Transformer Scaling Laws",
            "authors": ["Vaswani et al."],
            "abstract": "Study on transformer scaling.",
            "published_date": "2021-01-01"
        }]

        with patch('research_intelligence.tasks.step_1_search.search.get_scraper_provider') as mock_get_provider:
            scraper_inst = MagicMock()
            scraper_inst.search.return_value = mock_scraper_items
            mock_get_provider.return_value = scraper_inst
            execute_scraper_run_job(component_run_id=str(comp_run_search.id))

        paper_1.refresh_from_db()
        self.assertEqual(paper_1.pipeline_run, run_1)
        self.assertEqual(run_1.papers.count(), 1)
        pm_1 = PaperMetric.objects.get(paper=paper_1, pipeline_run=run_1)
        self.assertEqual(pm_1.screening_status, "abstract_passed")
        self.assertEqual(pm_1.abstract_screening_reasoning, "Passed in Run 1")
        self.assertIn(run_2, paper_1.reprocessed_runs.all())
        self.assertIn(paper_1, run_2.get_papers())

    def test_start_pipeline_run_inherits_workspace_reprocess_existing_when_omitted(self):
        """
        Validates that POST /api/pipeline-runs/start/ and POST /api/workspaces/{id}/run-pipeline/
        inherit workspace.reprocess_existing=True when reprocess_existing is omitted from the payload,
        and honor explicit False overrides.
        """
        ws_true = Workspace.objects.create(name="Inherit Flag WS", reprocess_existing=True)
        WorkspaceMember.objects.create(workspace=ws_true, user=self.admin, role="admin")
        Scraper.objects.create(workspace=ws_true, provider="arxiv", search_query="quantum", is_active=True)

        mock_task = MagicMock(id="mock_celery_id_123")
        with patch("research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay", return_value=mock_task), \
             patch("mcp_server.tools.pipeline_runs.triggers.execute_scraper_run_job.delay", return_value=mock_task):
            # 1. Start via /api/pipeline-runs/start/ without reprocess_existing -> inherits True
            res_start = self.client.post("/api/pipeline-runs/start/", {
                "workspace_id": str(ws_true.id),
                "name": "Inherited True Run"
            }, format="json")
            self.assertEqual(res_start.status_code, status.HTTP_201_CREATED)
            run_id = res_start.data.get("pipeline_run_id")
            run = PipelineRun.objects.get(id=run_id)
            self.assertTrue(run.reprocess_existing)

            # 2. Start via /api/pipeline-runs/start/ with explicit reprocess_existing=False -> overrides to False
            res_start_false = self.client.post("/api/pipeline-runs/start/", {
                "workspace_id": str(ws_true.id),
                "name": "Explicit False Run",
                "reprocess_existing": False
            }, format="json")
            self.assertEqual(res_start_false.status_code, status.HTTP_201_CREATED)
            run_false = PipelineRun.objects.get(id=res_start_false.data.get("pipeline_run_id"))
            self.assertFalse(run_false.reprocess_existing)

            # 3. Start via /api/workspaces/{id}/run-pipeline/ without reprocess_existing -> inherits True
            res_ws_run = self.client.post(f"/api/workspaces/{ws_true.id}/run-pipeline/", {
                "name": "WS Action Inherited True"
            }, format="json")
            self.assertEqual(res_ws_run.status_code, status.HTTP_201_CREATED)
            run_ws = PipelineRun.objects.get(id=res_ws_run.data.get("pipeline_run_id"))
            self.assertTrue(run_ws.reprocess_existing)

            # 4. Create via POST /api/pipeline-runs/ without reprocess_existing -> inherits True
            res_create = self.client.post("/api/pipeline-runs/", {
                "workspace_id": str(ws_true.id),
                "name": "Create Endpoint Inherited True"
            }, format="json")
            self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
            run_created = PipelineRun.objects.get(id=res_create.data.get("id"))
            self.assertTrue(run_created.reprocess_existing)

    def test_reprocess_existing_only_relinks_scraper_results_and_ignores_out_of_window_papers(self):
        """
        Validates that when reprocess_existing=True, duplicate papers returned by the scraper
        within the search criteria are reprocessed, while other existing workspace papers
        outside the scraper results are NOT linked.
        """
        from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job
        ws = Workspace.objects.create(name="Scraper Scoped Reprocess WS", reprocess_existing=True)
        old_run = PipelineRun.objects.create(workspace=ws, status="completed")

        # Paper 1: Out of window historical paper from 2024 (NOT returned by scraper)
        p_out_of_window = Paper.objects.create(
            workspace=ws,
            pipeline_run=old_run,
            hash_id="hash_old_2024_out_of_window",
            doi="10.1000/old2024",
            arxiv_id="2401.99999",
            title="Ancient Historical Paper Out Of Window",
            authors="Old Author",
            abstract="Paper published years ago.",
            source_database="arxiv"
        )

        # Paper 2: In-window paper that already exists in DB (matching an item from scraper)
        p_in_window = Paper.objects.create(
            workspace=ws,
            pipeline_run=old_run,
            hash_id="hash_duplicate_in_window",
            doi="10.1000/duplicate2026",
            arxiv_id="2609.00001",
            title="Recent Paper Matching Scraper Query",
            authors="Recent Author",
            abstract="Paper within recent search window.",
            source_database="arxiv"
        )

        # Scraper returns: 1 duplicate (matching p_in_window) + 1 brand new paper
        mock_scraper_results = [
            {
                "source_database": "arxiv",
                "hash_id": "scraped_duplicate_item",
                "doi": "10.1000/duplicate2026",
                "arxiv_id": "2609.00001",
                "title": "Recent Paper Matching Scraper Query",
                "authors": ["Recent Author"],
                "abstract": "Paper within recent search window.",
                "published_date": "2026-09-05"
            },
            {
                "source_database": "arxiv",
                "hash_id": "scraped_brand_new_item",
                "doi": "10.1000/new2026",
                "arxiv_id": "2609.00002",
                "title": "Brand New Paper Just Published",
                "authors": ["New Author"],
                "abstract": "Fresh discoveries in robotics.",
                "published_date": "2026-09-08"
            }
        ]

        scraper = Scraper.objects.create(
            workspace=ws,
            provider="arxiv",
            search_query="robotics",
            is_active=True
        )

        new_run = PipelineRun.objects.create(
            workspace=ws,
            status="running",
            reprocess_existing=True,
            configuration_override={
                "start_date": "2026-09-01",
                "end_date": "2026-09-10"
            }
        )

        comp_run = ComponentRun.objects.create(
            pipeline_run=new_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=scraper,
            status="running",
            input_params={
                "start_date": "2026-09-01",
                "end_date": "2026-09-10"
            }
        )

        with patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_get_provider:
            provider_inst = MagicMock()
            provider_inst.search.return_value = mock_scraper_results
            mock_get_provider.return_value = provider_inst

            execute_scraper_run_job(component_run_id=str(comp_run.id))

        new_run.refresh_from_db()
        papers_in_new_run = list(new_run.get_papers())

        # Assert exactly 2 papers are linked (the in-window duplicate + the brand new paper)
        self.assertEqual(len(papers_in_new_run), 2)
        self.assertIn(p_in_window, papers_in_new_run)

        # Crucial assertion: the out-of-window workspace paper was NOT linked!
        self.assertNotIn(p_out_of_window, papers_in_new_run)


class PipelineDateRangeAndResultsPaginationE2ETestCase(TestCase):
    """
    End-to-End Test Suite validating:
    1. Pipeline execution with relative lookback (n_last_days) propagated to scrapers and stored in config.
    2. Pipeline execution with explicit date range (start_date, end_date) propagated to scrapers and stored in config.
    3. Proper formatting of the 'period' field ('Last 14 days' vs '2026-08-01 - 2026-08-15').
    4. Multi-page pagination of Briefings (PipelineRuns) with filtering by domain name.
    5. Multi-page pagination of resulting Papers within a briefing (page 1, page 2, page 3, prev/next links).
    6. Search query combined with pagination on briefing papers.
    7. REST API endpoints /api/pipeline-runs/start/ and /api/workspaces/{id}/run-pipeline/ with date parameters.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="e2e_dates_user", email="dates@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="Physical AI Lab",
            screening_llm_model="google/gemini-3.8-flash",
            ocr_provider=None,  # Direct multimodal PDF screening
            skip_abstract_screening=True,  # Direct Full-Text Screening
            full_text_acceptance_criteria="Accept quantum and physical AI computing architectures.",
            full_text_rejection_criteria="Reject unrelated software frameworks.",
            signal_score_code="score = 0.6 * trl_level + 0.4 * novelty_score\nreturn round(score, 2)"
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role='admin')

        self.scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="physical AI embodied robotics",
            limit=10,
            is_active=True
        )

        self.ext_def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            system_prompt="Extract technology readiness level 1-9.",
            user_prompt_template="Extract TRL from paper: {paper_text}",
            response_schema={"type": "object", "properties": {"trl": {"type": "integer"}}, "required": ["trl"]},
            exit_metrics="trl"
        )

        self.ext_def_nov = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            system_prompt="Rate novelty 1-10.",
            user_prompt_template="Extract novelty score from paper: {paper_text}",
            response_schema={"type": "object", "properties": {"score": {"type": "number"}}, "required": ["score"]},
            exit_metrics="score"
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.sample_papers = [
            {
                "hash_id": f"arxiv_pai_{i}",
                "arxiv_id": f"2601.000{i}v1",
                "doi": f"10.1000/arxiv.2601.000{i}",
                "title": f"Physical AI and Embodied Robotics Paradigm Part {i}",
                "authors": f"Dr. Scientist {i}, Prof. Researcher",
                "abstract": f"Abstract describing experimental robotics and neural physical synthesis {i}.",
                "source_database": "arxiv",
                "pdf_url": f"https://arxiv.org/pdf/2601.000{i}.pdf",
                "meta": {"published": f"2026-08-0{i}T12:00:00Z"}
            }
            for i in range(1, 6)
        ]

    def _mock_helpers(self):
        mock_pdf_resp = MagicMock()
        mock_pdf_resp.status_code = 200
        mock_pdf_resp.content = b"%PDF-1.5 Mock PDF Binary Content for Testing"
        mock_pdf_resp.headers = {"Content-Type": "application/pdf"}

        def mock_llm_generate(*args, **kwargs):
            prompt_str = str(kwargs.get("prompt", "") or (args[0] if len(args) > 0 else ""))
            sys_str = str(kwargs.get("system_instruction", "") or (args[1] if len(args) > 1 else ""))

            if "screening" in sys_str.lower() or "full_text" in prompt_str.lower() or "screening" in prompt_str.lower():
                return {
                    "passed": True,
                    "reasoning": "Strong methodology with physical AI experiments.",
                    "evidence_quotes": ["Real-world robotic trial with 99.4% accuracy."],
                    "decision_category": "ACCEPTED"
                }
            elif "trl" in sys_str.lower() or "trl" in prompt_str.lower():
                return {"trl": 6}
            elif "novelty" in sys_str.lower() or "novelty" in prompt_str.lower():
                return {"score": 8.0}
            return {"passed": True, "value": 7.0}

        return mock_pdf_resp, mock_llm_generate

    def _drive_agent_to_completion(self, process_id: str, max_ticks: int = 15):
        for _ in range(max_ticks):
            res_str = check_run_status_logic(user=self.user, process_id=process_id)
            res = json.loads(res_str)
            if res.get("is_finished") or res.get("status") in ["completed", "failed", "aborted"]:
                return res
        return json.loads(check_run_status_logic(user=self.user, process_id=process_id))

    def _drive_pipeline_run_to_completion(self, pipeline_run_id: str, max_ticks: int = 15):
        from research_intelligence.tasks.orchestrator.runner import PipelineRunner
        for _ in range(max_ticks):
            pr = PipelineRun.objects.get(id=pipeline_run_id)
            if pr.status in ['completed', 'failed', 'aborted']:
                return pr
            PipelineRunner.tick(pipeline_run_id)
        return PipelineRun.objects.get(id=pipeline_run_id)

    def test_e2e_pipeline_with_n_last_days_and_briefing_papers_pagination(self):
        """
        Scenario 1:
        1. Launches an autonomous pipeline run with n_last_days=14.
        2. Asserts scraper receives n_last_days=14 and returns 5 candidate papers.
        3. Executes all stages E2E to completion.
        4. Verifies configuration_override, period ('Last 14 days'), and metrics.
        5. Tests Briefings API pagination (?status=completed&page=1&page_size=1).
        6. Tests Papers API multi-page pagination (?page=1&page_size=2, page 2, page 3).
        7. Tests Papers API search combined with pagination.
        """
        mock_pdf_resp, mock_llm_generate = self._mock_helpers()

        with patch("requests.get", return_value=mock_pdf_resp), \
             patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_scraper, \
             patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate", side_effect=mock_llm_generate):

            provider_inst = MagicMock()
            provider_inst.search.return_value = self.sample_papers
            mock_scraper.return_value = provider_inst

            # 1. Start agent with n_last_days=14
            res_str = start_research_agent_logic(
                user=self.user,
                workspace_id=str(self.workspace.id),
                name="Robotics N-Days Review",
                n_last_days=14
            )
            run_info = json.loads(res_str)
            self.assertEqual(run_info["status"], "success")
            proc_id = run_info["process_id"]

            # 2. Drive to completion across all stages (search -> download -> screening -> extraction -> signal_score -> reporting)
            wait_res = self._drive_agent_to_completion(proc_id)
            self.assertEqual(wait_res["agent_status"], "completed")

            proc = ResearchAgentProcess.objects.get(id=proc_id)
            pr = proc.pipeline_run
            self.assertEqual(pr.status, "completed")
            self.assertEqual(pr.current_stage, "completed")

            # Verify scraper received n_last_days=14
            search_call_kwargs = provider_inst.search.call_args[1]
            self.assertEqual(search_call_kwargs.get("n_last_days"), 14)

            # Verify configuration_override and period formatting
            self.assertEqual(pr.configuration_override.get("n_last_days"), 14)
            self.assertEqual(pr.period, "Last 14 days")
            self.assertEqual(pr.total_papers_fetched, 5)
            self.assertEqual(pr.total_papers_passed_screening, 5)

            # Check signal scores: 0.6 * 6 + 0.4 * 8 = 6.8
            metrics = PaperMetric.objects.filter(pipeline_run=pr)
            self.assertEqual(metrics.count(), 5)
            for m in metrics:
                self.assertEqual(float(m.signal_score), 6.8)

            # 3. Test Briefings API Pagination (Screen 6 / Screen 2)
            res_briefings = self.client.get(
                f"/api/pipeline-runs/?domain=Physical AI Lab&status=completed&page=1&page_size=1"
            )
            self.assertEqual(res_briefings.status_code, status.HTTP_200_OK)
            b_data = res_briefings.json()
            self.assertIn("count", b_data)
            self.assertEqual(len(b_data["results"]), 1)
            first_briefing = b_data["results"][0]
            self.assertEqual(first_briefing["id"], str(pr.id))
            self.assertEqual(first_briefing["workspace_name"], "Physical AI Lab")
            self.assertEqual(first_briefing["period"], "Last 14 days")
            self.assertEqual(first_briefing["total_papers_screened"], 5)
            self.assertEqual(first_briefing["total_papers_passed_screening"], 5)

            # 4. Test Papers API Pagination for this Briefing (Screen 3)
            # Page 1: 2 items, next link exists, previous is null
            res_p1 = self.client.get(f"/api/papers/?pipeline_run={pr.id}&page=1&page_size=2")
            self.assertEqual(res_p1.status_code, status.HTTP_200_OK)
            d_p1 = res_p1.json()
            self.assertEqual(d_p1["count"], 5)
            self.assertEqual(len(d_p1["results"]), 2)
            self.assertIsNotNone(d_p1["next"])
            self.assertIsNone(d_p1["previous"])
            self.assertIn("page=2", d_p1["next"])
            # Check convenience fields on papers
            self.assertEqual(d_p1["results"][0]["pipeline_run_name"], "Robotics N-Days Review")
            self.assertIsNotNone(d_p1["results"][0]["published_date"])
            self.assertEqual(d_p1["results"][0]["signal_score"], 6.8)

            # Page 2: 2 items, both previous and next exist
            res_p2 = self.client.get(f"/api/papers/?pipeline_run={pr.id}&page=2&page_size=2")
            self.assertEqual(res_p2.status_code, status.HTTP_200_OK)
            d_p2 = res_p2.json()
            self.assertEqual(len(d_p2["results"]), 2)
            self.assertIsNotNone(d_p2["next"])
            self.assertIsNotNone(d_p2["previous"])
            self.assertIn("page=3", d_p2["next"])

            # Page 3: 1 item, previous exists, next is null
            res_p3 = self.client.get(f"/api/papers/?pipeline_run={pr.id}&page=3&page_size=2")
            self.assertEqual(res_p3.status_code, status.HTTP_200_OK)
            d_p3 = res_p3.json()
            self.assertEqual(len(d_p3["results"]), 1)
            self.assertIsNone(d_p3["next"])
            self.assertIsNotNone(d_p3["previous"])

            # 5. Test Search combined with Pagination within briefing
            res_search = self.client.get(f"/api/papers/?pipeline_run={pr.id}&search=Part 3&page=1&page_size=2")
            self.assertEqual(res_search.status_code, status.HTTP_200_OK)
            d_search = res_search.json()
            self.assertEqual(d_search["count"], 1)
            self.assertEqual(len(d_search["results"]), 1)
            self.assertIn("Part 3", d_search["results"][0]["title"])

    def test_e2e_pipeline_with_explicit_start_end_dates_and_results_pagination(self):
        """
        Scenario 2:
        1. Launches an autonomous pipeline run via REST API (/api/pipeline-runs/start/)
           specifying explicit start_date='2026-08-01' and end_date='2026-08-15'.
        2. Asserts scraper receives start_date and end_date.
        3. Drives the DAG execution through all stages to completion.
        4. Verifies period formatting ('2026-08-01 - 2026-08-15').
        5. Tests Briefings API domain filtering and paginated paper retrieval.
        """
        mock_pdf_resp, mock_llm_generate = self._mock_helpers()

        with patch("requests.get", return_value=mock_pdf_resp), \
             patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_scraper, \
             patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate", side_effect=mock_llm_generate):

            provider_inst = MagicMock()
            provider_inst.search.return_value = self.sample_papers
            mock_scraper.return_value = provider_inst

            # 1. Start via REST API
            payload = {
                "workspace_id": str(self.workspace.id),
                "name": "Date Range Robotics Review",
                "start_date": "2026-08-01",
                "end_date": "2026-08-15"
            }
            res = self.client.post("/api/pipeline-runs/start/", payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            pr_id = res.data["pipeline_run_id"]

            # 2. Drive PipelineRun to completion via DAG tick engine
            pr = self._drive_pipeline_run_to_completion(pr_id)
            self.assertEqual(pr.status, "completed")
            self.assertEqual(pr.current_stage, "completed")

            # Verify scraper was called with explicit date range
            search_call_kwargs = provider_inst.search.call_args[1]
            self.assertEqual(search_call_kwargs.get("start_date"), "2026-08-01")
            self.assertEqual(search_call_kwargs.get("end_date"), "2026-08-15")

            # Verify period formatting
            self.assertEqual(pr.configuration_override.get("start_date"), "2026-08-01")
            self.assertEqual(pr.configuration_override.get("end_date"), "2026-08-15")
            self.assertEqual(pr.period, "2026-08-01 - 2026-08-15")
            self.assertEqual(pr.total_papers_screened, 5)
            self.assertEqual(pr.total_papers_passed_screening, 5)

            # 3. Test Briefings API with domain filter and pagination
            res_briefing = self.client.get(
                f"/api/pipeline-runs/?domain=Physical AI Lab&status=completed&page=1&page_size=5"
            )
            self.assertEqual(res_briefing.status_code, status.HTTP_200_OK)
            b_items = res_briefing.json()["results"]
            matched_run = next(r for r in b_items if r["id"] == str(pr.id))
            self.assertEqual(matched_run["period"], "2026-08-01 - 2026-08-15")
            self.assertEqual(matched_run["total_papers_screened"], 5)
            self.assertEqual(matched_run["total_papers_passed_screening"], 5)

            # 4. Test Papers API pagination
            res_papers = self.client.get(f"/api/papers/?pipeline_run={pr.id}&page=1&page_size=3")
            self.assertEqual(res_papers.status_code, status.HTTP_200_OK)
            p_data = res_papers.json()
            self.assertEqual(p_data["count"], 5)
            self.assertEqual(len(p_data["results"]), 3)
            self.assertIsNotNone(p_data["next"])
            self.assertEqual(p_data["results"][0]["pipeline_run_name"], "Date Range Robotics Review")

            # Page 2 has the remaining 2 papers
            res_papers_p2 = self.client.get(f"/api/papers/?pipeline_run={pr.id}&page=2&page_size=3")
            self.assertEqual(res_papers_p2.status_code, status.HTTP_200_OK)
            p_data_p2 = res_papers_p2.json()
            self.assertEqual(len(p_data_p2["results"]), 2)
            self.assertIsNone(p_data_p2["next"])

    def test_workspace_run_pipeline_action_e2e_with_date_range(self):
        """
        Scenario 3:
        Validates the /api/workspaces/{id}/run-pipeline/ endpoint triggers an autonomous run
        with start_date, end_date, and n_last_days, and verifies workspace papers listing pagination.
        """
        mock_pdf_resp, mock_llm_generate = self._mock_helpers()

        with patch("requests.get", return_value=mock_pdf_resp), \
             patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_scraper, \
             patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate", side_effect=mock_llm_generate):

            provider_inst = MagicMock()
            provider_inst.search.return_value = self.sample_papers
            mock_scraper.return_value = provider_inst

            payload = {
                "start_date": "2026-07-01",
                "end_date": "2026-07-20",
                "n_last_days": 10
            }
            res = self.client.post(f"/api/workspaces/{self.workspace.id}/run-pipeline/", payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            pr_id = res.data["pipeline_run_id"]

            pr = self._drive_pipeline_run_to_completion(pr_id)
            self.assertEqual(pr.status, "completed")
            self.assertEqual(pr.period, "2026-07-01 - 2026-07-20")

            # Test /api/workspaces/{id}/papers/ with pagination
            res_ws_papers = self.client.get(f"/api/workspaces/{self.workspace.id}/papers/?page=1&page_size=3")
            self.assertEqual(res_ws_papers.status_code, status.HTTP_200_OK)
            ws_p_data = res_ws_papers.json()
            self.assertEqual(ws_p_data["count"], 5)
            self.assertEqual(len(ws_p_data["results"]), 3)
            self.assertIsNotNone(ws_p_data["next"])

    def test_e2e_pipeline_with_omitted_date_parameters_defaults_to_7_days(self):
        """
        Scenario 4 (Omitted Date & Day Parameters):
        1. Launches an autonomous pipeline run via REST API (/api/pipeline-runs/start/)
           WITHOUT providing start_date, end_date, or n_last_days (complete absence).
        2. Asserts scraper receives start_date=None, end_date=None, and default n_last_days=7.
        3. Drives the DAG execution through all stages to completion.
        4. Verifies period formatting defaults gracefully to 'Last 7 days'.
        5. Tests Briefings API and paginated paper retrieval.
        """
        mock_pdf_resp, mock_llm_generate = self._mock_helpers()

        with patch("requests.get", return_value=mock_pdf_resp), \
             patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_scraper, \
             patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate", side_effect=mock_llm_generate):

            provider_inst = MagicMock()
            provider_inst.search.return_value = self.sample_papers
            mock_scraper.return_value = provider_inst

            # 1. Start via REST API with date parameters completely omitted
            payload = {
                "workspace_id": str(self.workspace.id),
                "name": "Omitted Dates Robotics Review"
            }
            res = self.client.post("/api/pipeline-runs/start/", payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            pr_id = res.data["pipeline_run_id"]

            # 2. Drive PipelineRun to completion
            pr = self._drive_pipeline_run_to_completion(pr_id)
            self.assertEqual(pr.status, "completed")
            self.assertEqual(pr.current_stage, "completed")

            # Verify scraper called with default n_last_days=7 and no explicit dates
            search_call_kwargs = provider_inst.search.call_args[1]
            self.assertIsNone(search_call_kwargs.get("start_date"))
            self.assertIsNone(search_call_kwargs.get("end_date"))
            self.assertEqual(search_call_kwargs.get("n_last_days"), 7)

            # Verify period formatting
            self.assertEqual(pr.period, "Last 7 days")
            self.assertEqual(pr.total_papers_screened, 5)
            self.assertEqual(pr.total_papers_passed_screening, 5)

            # 3. Test Briefings API returns period 'Last 7 days'
            res_briefing = self.client.get(
                f"/api/pipeline-runs/?domain=Physical AI Lab&status=completed&page=1&page_size=5"
            )
            self.assertEqual(res_briefing.status_code, status.HTTP_200_OK)
            b_items = res_briefing.json()["results"]
            matched_run = next(r for r in b_items if r["id"] == str(pr.id))
            self.assertEqual(matched_run["period"], "Last 7 days")

            # 4. Test Papers API pagination
            res_papers = self.client.get(f"/api/papers/?pipeline_run={pr.id}&page=1&page_size=2")
            self.assertEqual(res_papers.status_code, status.HTTP_200_OK)
            p_data = res_papers.json()
            self.assertEqual(p_data["count"], 5)
            self.assertEqual(len(p_data["results"]), 2)
            self.assertIsNotNone(p_data["next"])
            self.assertIsNone(p_data["previous"])

    def test_e2e_pipeline_with_explicit_none_dates_and_days(self):
        """
        Scenario 5 (Explicit None Values for Date & Day Parameters):
        Validates that passing null / None explicitly for start_date, end_date, and n_last_days
        does not fail validation and defaults seamlessly to 7 days lookback.
        """
        mock_pdf_resp, mock_llm_generate = self._mock_helpers()

        with patch("requests.get", return_value=mock_pdf_resp), \
             patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_scraper, \
             patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate", side_effect=mock_llm_generate):

            provider_inst = MagicMock()
            provider_inst.search.return_value = self.sample_papers
            mock_scraper.return_value = provider_inst

            payload = {
                "workspace_id": str(self.workspace.id),
                "name": "Explicit None Dates Review",
                "start_date": None,
                "end_date": None,
                "n_last_days": None
            }
            res = self.client.post("/api/pipeline-runs/start/", payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            pr_id = res.data["pipeline_run_id"]

            pr = self._drive_pipeline_run_to_completion(pr_id)
            self.assertEqual(pr.status, "completed")

            search_call_kwargs = provider_inst.search.call_args[1]
            self.assertIsNone(search_call_kwargs.get("start_date"))
            self.assertIsNone(search_call_kwargs.get("end_date"))
            self.assertEqual(search_call_kwargs.get("n_last_days"), 7)
            self.assertEqual(pr.period, "Last 7 days")

    def test_e2e_pipeline_with_partial_date_ranges(self):
        """
        Scenario 6 (Partial Date Ranges):
        Validates runs with only start_date (period: 'From YYYY-MM-DD')
        and only end_date with n_last_days (period: 'Until YYYY-MM-DD').
        """
        mock_pdf_resp, mock_llm_generate = self._mock_helpers()

        with patch("requests.get", return_value=mock_pdf_resp), \
             patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_scraper, \
             patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate", side_effect=mock_llm_generate):

            provider_inst = MagicMock()
            provider_inst.search.return_value = self.sample_papers
            mock_scraper.return_value = provider_inst

            # Sub-test A: Only start_date provided
            payload_a = {
                "workspace_id": str(self.workspace.id),
                "name": "Only Start Date Review",
                "start_date": "2026-06-01"
            }
            res_a = self.client.post("/api/pipeline-runs/start/", payload_a, format="json")
            self.assertEqual(res_a.status_code, status.HTTP_201_CREATED)
            pr_a = self._drive_pipeline_run_to_completion(res_a.data["pipeline_run_id"])
            self.assertEqual(pr_a.status, "completed")
            self.assertEqual(pr_a.period, "From 2026-06-01")
            search_a = provider_inst.search.call_args[1]
            self.assertEqual(search_a.get("start_date"), "2026-06-01")
            self.assertIsNone(search_a.get("end_date"))

            # Sub-test B: Only end_date provided with n_last_days=10
            payload_b = {
                "workspace_id": str(self.workspace.id),
                "name": "Only End Date Review",
                "end_date": "2026-06-30",
                "n_last_days": 10
            }
            res_b = self.client.post("/api/pipeline-runs/start/", payload_b, format="json")
            self.assertEqual(res_b.status_code, status.HTTP_201_CREATED)
            pr_b = self._drive_pipeline_run_to_completion(res_b.data["pipeline_run_id"])
            self.assertEqual(pr_b.status, "completed")
            self.assertEqual(pr_b.period, "Until 2026-06-30")
            search_b = provider_inst.search.call_args[1]
            self.assertIsNone(search_b.get("start_date"))
            self.assertEqual(search_b.get("end_date"), "2026-06-30")
            self.assertEqual(search_b.get("n_last_days"), 10)



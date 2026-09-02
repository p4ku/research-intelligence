import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import (
    Workspace,
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
from mcp_server.tools.extractions import get_paper_extractions_matrix_logic

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
            exit_metric="trl"
        )

        self.ext_def_nov = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            system_prompt="Rate novelty 1-10.",
            user_prompt_template="Extract novelty score from paper: {paper_text}",
            response_schema={"type": "object", "properties": {"score": {"type": "number"}}, "required": ["score"]},
            exit_metric="score"
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
            extractions = Extraction.objects.filter(paper__pipeline_run=proc.pipeline_run)
            self.assertTrue(extractions.count() >= 2)

            # Check signal score evaluated and PaperMetric records generated per pipeline_run
            metrics = PaperMetric.objects.filter(pipeline_run=proc.pipeline_run)
            self.assertEqual(metrics.count(), 2)
            for m in metrics:
                self.assertEqual(float(m.signal_score), 7.25)
                self.assertEqual(m.pipeline_run, proc.pipeline_run)

            for paper in proc.pipeline_run.papers.all():
                self.assertIsNotNone(paper.signal_score)
                # TRL=6, Novelty=8.5 -> score = 0.5 * 6 + 0.5 * 8.5 = 7.25
                self.assertEqual(float(paper.signal_score), 7.25)

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

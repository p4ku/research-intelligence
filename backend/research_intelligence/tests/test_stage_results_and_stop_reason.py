import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch, MagicMock

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ResearchAgentProcess,
    ComponentRun,
    Paper,
    Scraper,
)
from research_intelligence.tasks.orchestrator.dag import build_default_slr_dag
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
from research_intelligence.admin import ResearchAgentProcessAdmin, PipelineRunAdmin
from django.contrib.admin.sites import AdminSite

User = get_user_model()


class StageResultsAndStopReasonTestCase(TestCase):
    """
    Tests that:
    1. Every pipeline stage records its status ('completed', 'failed', 'skipped', 'running') and summary message.
    2. The orchestrator persists this information into ResearchAgentProcess.stage_results.
    3. ResearchAgentProcess.stopped_at_step and stop_reason record exact halting reasons or completion summaries.
    4. Django Admin displays these stage breakdowns and badges accurately.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="analyst_test",
            email="analyst@example.com",
            password="testpassword123!"
        )
        self.workspace = Workspace.objects.create(
            name="Autonomous Intelligence Workspace",
            abstract_acceptance_criteria="Method must involve quantum neural networks.",
            abstract_rejection_criteria="Pure survey papers with no benchmarks.",
            ocr_provider=None  # direct multimodal PDF mode
        )
        self.site = AdminSite()
        self.agent_admin = ResearchAgentProcessAdmin(ResearchAgentProcess, self.site)
        self.run_admin = PipelineRunAdmin(PipelineRun, self.site)

    def test_search_zero_papers_records_stop_reason_and_stage_results(self):
        """
        When Search finishes with 0 papers (e.g. all duplicates or none found),
        verify that stopped_at_step='search', stop_reason is recorded, and stage_results has the search entry.
        """
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Search Zero Papers Agent",
            status="running",
            current_step="initialized",
            triggered_by=self.user,
            configuration_override={"limit": 10, "reprocess_existing": False}
        )

        # 1. First tick initializes pipeline_run and dispatches search
        with patch("research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay"):
            tick_agent_process(str(agent.id))

        agent.refresh_from_db()
        pr = agent.pipeline_run
        self.assertIsNotNone(pr)
        self.assertEqual(agent.current_step, "search")

        # Mark search component run as completed with 0 new papers
        comp_run = ComponentRun.objects.filter(pipeline_run=pr, step_type="search").last()
        self.assertIsNotNone(comp_run)
        comp_run.status = "completed"
        comp_run.metrics = {"total_found": 5, "ingested_new": 0, "duplicates_skipped": 5}
        comp_run.save()

        # 2. Second tick triggers DAG evaluation -> detects 0 papers and halts cleanly
        res = tick_agent_process(str(agent.id))
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("status"), "completed")

        agent.refresh_from_db()
        pr.refresh_from_db()

        # Check status & stop reason on agent process
        self.assertEqual(agent.status, "completed")
        self.assertEqual(agent.current_step, "completed")
        self.assertEqual(agent.stopped_at_step, "search")
        self.assertIn("0 papers were found matching criteria", agent.stop_reason)
        self.assertIn("5 were already ingested", agent.stop_reason)

        # Check stage_results JSON dictionary
        self.assertIn("search", agent.stage_results)
        search_res = agent.stage_results["search"]
        self.assertEqual(search_res["status"], "completed")
        self.assertIn("Search: 0 new papers", search_res["summary"])

        # Check PipelineRun status_message
        self.assertIn("0 papers were found matching criteria", pr.status_message)

        # Check admin rendering
        halt_badge = self.agent_admin.stopped_stage_badge(agent)
        self.assertIn("HALTED AT", str(halt_badge))
        self.assertIn("SEARCH", str(halt_badge))
        reason_display = self.agent_admin.stop_reason_display(agent)
        self.assertIn("0 papers were found", str(reason_display))
        preview_table = self.agent_admin.stage_results_preview(agent)
        self.assertIn("Search", str(preview_table))
        self.assertIn("COMPLETED", str(preview_table))

    def test_stage_failure_records_failed_stage_and_error_message(self):
        """
        When a stage fails (e.g. Gemini screening API error),
        verify stopped_at_step, stop_reason, and stage_results capture the failure.
        """
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Failing Agent Process",
            status="running",
            current_step="initialized",
            triggered_by=self.user,
            configuration_override={"limit": 5}
        )

        with patch("research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay"):
            tick_agent_process(str(agent.id))

        agent.refresh_from_db()
        pr = agent.pipeline_run

        # Simulate Search completed with 1 paper
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            title="Quantum Paper 1",
            abstract="Quantum neural net design."
        )
        search_comp = ComponentRun.objects.filter(pipeline_run=pr, step_type="search").last()
        search_comp.status = "completed"
        search_comp.metrics = {"total_found": 1, "ingested_new": 1, "duplicates_skipped": 0}
        search_comp.save()

        # Simulate Download completed
        ComponentRun.objects.create(
            pipeline_run=pr,
            step_type="download",
            component_name="pdf_download",
            status="completed",
            metrics={"downloaded": 1, "cached": 0, "failed": 0}
        )

        # Simulate Screening failed with 429 quota exception
        ComponentRun.objects.create(
            pipeline_run=pr,
            step_type="screening",
            component_name="abstract_screening",
            status="failed",
            error_message="ResourceExhausted: 429 Rate limit exceeded on Gemini API."
        )

        # Tick state engine
        res = tick_agent_process(str(agent.id))
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("status"), "failed")

        agent.refresh_from_db()
        pr.refresh_from_db()

        self.assertEqual(agent.status, "failed")
        self.assertIn(agent.stopped_at_step, ["screening", "abstract_screening"])
        self.assertIn("abstract_screening", agent.stop_reason)
        self.assertIn("429 Rate limit exceeded", agent.stop_reason)

        # Check stage_results has failed entry
        self.assertTrue("abstract_screening" in agent.stage_results or "screening" in agent.stage_results)
        scr_key = "abstract_screening" if "abstract_screening" in agent.stage_results else "screening"
        self.assertEqual(agent.stage_results[scr_key]["status"], "failed")

        # Check Admin
        fail_badge = self.agent_admin.stopped_stage_badge(agent)
        self.assertIn("FAILED AT", str(fail_badge))
        reason_display = self.agent_admin.stop_reason_display(agent)
        self.assertIn("429 Rate limit exceeded", str(reason_display))

    def test_full_pipeline_success_records_all_stages_and_summary(self):
        """
        When all stages complete, verify all stage_results are populated and
        stopped_at_step='completed'.
        """
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Full Review Agent",
            status="running",
            current_step="initialized",
            triggered_by=self.user
        )

        with patch("research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay"):
            tick_agent_process(str(agent.id))

        agent.refresh_from_db()
        pr = agent.pipeline_run

        # Populate complete successful components
        p1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            title="Complete Paper",
            screening_status="accepted"
        )
        ComponentRun.objects.create(pipeline_run=pr, step_type="search", status="completed", metrics={"total_found": 1, "ingested_new": 1})
        ComponentRun.objects.create(pipeline_run=pr, step_type="screening", component_name="abstract_screening", status="completed", metrics={"passed": 1, "total_screened": 1})
        ComponentRun.objects.create(pipeline_run=pr, step_type="download", status="completed", metrics={"downloaded": 1})
        ComponentRun.objects.create(pipeline_run=pr, step_type="ocr", status="skipped")
        ComponentRun.objects.create(pipeline_run=pr, step_type="screening", component_name="full_text_screening", status="completed", metrics={"passed": 1, "total_screened": 1})
        ComponentRun.objects.create(pipeline_run=pr, step_type="extraction", status="completed", metrics={"extractions_count": 4, "papers_processed": 1})
        ComponentRun.objects.create(pipeline_run=pr, step_type="signal_score", status="completed", metrics={"scored_count": 1})
        ComponentRun.objects.create(pipeline_run=pr, step_type="reporting", status="completed", metrics={"report_id": str(uuid.uuid4())})

        res = tick_agent_process(str(agent.id))
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("status"), "completed")

        agent.refresh_from_db()
        pr.refresh_from_db()

        self.assertEqual(agent.status, "completed")
        self.assertEqual(agent.stopped_at_step, "completed")
        self.assertIn("Full SLR pipeline finished successfully", agent.stop_reason)

        # Check all stages recorded in stage_results
        self.assertIn("search", agent.stage_results)
        self.assertIn("abstract_screening", agent.stage_results)
        self.assertIn("download", agent.stage_results)
        self.assertIn("ocr", agent.stage_results)
        self.assertIn("full_text_screening", agent.stage_results)
        self.assertIn("extraction", agent.stage_results)
        self.assertIn("signal_score", agent.stage_results)
        self.assertIn("reporting", agent.stage_results)

        self.assertEqual(agent.stage_results["ocr"]["status"], "skipped")
        self.assertEqual(agent.stage_results["extraction"]["status"], "completed")

        # Admin display
        stage_badge = self.agent_admin.stopped_stage_badge(agent)
        self.assertIn("ALL 8 STEPS DONE", str(stage_badge))
        preview = self.agent_admin.stage_results_preview(agent)
        self.assertIn("Extraction", str(preview))
        self.assertIn("Reporting", str(preview))

    def test_triggered_by_display_explicit_user(self):
        """
        Verifies triggered_by_display renders the user username and email properly.
        """
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Explicit Creator Agent",
            triggered_by=self.user,
            status="running"
        )
        display = self.agent_admin.triggered_by_display(agent)
        self.assertIn("analyst_test", str(display))
        self.assertIn("analyst@example.com", str(display))
        self.assertIn("👤", str(display))

    def test_triggered_by_display_fallback_to_pipeline_run(self):
        """
        When agent.triggered_by is None, verifies fallback to pipeline_run.triggered_by.
        """
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            name="Fallback Creator Agent",
            triggered_by=None,
            status="running"
        )
        display = self.agent_admin.triggered_by_display(agent)
        self.assertIn("analyst_test", str(display))
        self.assertIn("analyst@example.com", str(display))

    def test_triggered_by_display_automated_system(self):
        """
        When neither agent nor pipeline_run has a triggered_by user, renders System / Automated.
        """
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="System Agent",
            triggered_by=None,
            pipeline_run=None,
            status="running"
        )
        display = self.agent_admin.triggered_by_display(agent)
        self.assertIn("System / Automated", str(display))

    def test_admin_save_model_auto_populates_creator(self):
        """
        Verifies that save_model in ResearchAgentProcessAdmin automatically sets
        triggered_by to the authenticated request.user if not specified.
        """
        agent = ResearchAgentProcess(
            workspace=self.workspace,
            name="Admin Created Agent",
            status="pending"
        )
        request = MagicMock()
        request.user = self.user

        self.agent_admin.save_model(request, agent, form=None, change=False)
        agent.refresh_from_db()
        self.assertEqual(agent.triggered_by, self.user)

    def test_admin_run_full_pipeline_action_assigns_creator(self):
        """
        Verifies that running the admin action run_full_pipeline assigns request.user as triggered_by.
        """
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="pending",
            current_stage="search"
        )
        request = MagicMock()
        request.user = self.user

        with patch("research_intelligence.tasks.orchestrator.agent_engine.tick_agent_process"):
            self.run_admin.run_full_pipeline(request, PipelineRun.objects.filter(id=pr.id))

        created_agent = pr.agent_processes.last()
        self.assertIsNotNone(created_agent)
        self.assertEqual(created_agent.triggered_by, self.user)

    def test_pipeline_run_admin_triggered_by_display_and_auto_populate(self):
        """
        Verifies PipelineRunAdmin displays triggered_by user, falls back to agent if needed,
        and save_model auto-populates request.user.
        """
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )
        display = self.run_admin.triggered_by_display(pr)
        self.assertIn("analyst_test", str(display))
        self.assertIn("analyst@example.com", str(display))

        # Auto populate in save_model
        pr_new = PipelineRun(workspace=self.workspace, status="pending")
        request = MagicMock()
        request.user = self.user
        self.run_admin.save_model(request, pr_new, form=None, change=False)
        pr_new.refresh_from_db()
        self.assertEqual(pr_new.triggered_by, self.user)

    def test_component_run_admin_triggered_by_display(self):
        """
        Verifies ComponentRunAdmin displays the user who triggered the parent PipelineRun/Agent.
        """
        from research_intelligence.admin import ComponentRunAdmin
        comp_admin = ComponentRunAdmin(ComponentRun, self.site)

        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )
        cr = ComponentRun.objects.create(
            pipeline_run=pr,
            step_type="screening",
            component_name="abstract_screening",
            status="completed"
        )
        display = comp_admin.triggered_by_display(cr)
        self.assertIn("analyst_test", str(display))
        self.assertIn("analyst@example.com", str(display))

    def test_extraction_admin_validation_confidence_badge_and_links(self):
        """
        Verifies ExtractionAdmin combines validation status & confidence score into pills
        and generates links to pipeline run and component run.
        """
        from research_intelligence.admin import ExtractionAdmin
        from research_intelligence.models import Extraction, ExtractionDefinition
        
        ext_admin = ExtractionAdmin(Extraction, self.site)

        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )
        cr = ComponentRun.objects.create(
            pipeline_run=pr,
            step_type="extraction",
            component_name="gemini_extractor",
            status="completed"
        )
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            title="Quantum Matrix Synthesis",
            screening_status="accepted"
        )
        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Methodology",
            response_schema={"type": "object"}
        )

        ext_pass = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=ext_def,
            category="ml_method",
            fields_data={"value": "Quantum Net"},
            validation_status="pass",
            confidence_score=0.9
        )
        badge_pass = ext_admin.validation_confidence_badge(ext_pass)
        self.assertIn("PASS (0.9)", str(badge_pass))
        self.assertIn("#198754", str(badge_pass))

        ext_fail = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=ext_def,
            category="ml_method",
            fields_data={"value": "Inconclusive"},
            validation_status="fail",
            confidence_score=0.45
        )
        badge_fail = ext_admin.validation_confidence_badge(ext_fail)
        self.assertIn("FAIL (0.45)", str(badge_fail))
        self.assertIn("#dc3545", str(badge_fail))

        # Links verification
        pr_link = ext_admin.pipeline_run_link(ext_pass)
        self.assertIn(str(pr.id)[:8], str(pr_link))

        cr_link = ext_admin.component_run_link(ext_pass)
        self.assertIn(str(cr.id)[:8], str(cr_link))

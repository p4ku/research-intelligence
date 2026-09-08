from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, RequestFactory
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.urls import reverse

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ResearchAgentProcess,
    Paper,
    WorkflowSchedule,
)
from research_intelligence.admin import PipelineRunAdmin, ResearchAgentProcessAdmin

User = get_user_model()


class PipelineRunAdminConsolidationTestCase(TestCase):
    """
    Comprehensive tests for PipelineRun admin enhancements:
    - Removal of ResearchAgentProcess from admin.site UI and seamless HTTP redirect.
    - Single consolidated 'Papers (In ➔ Out)' funnel column formatting.
    - Halt / Final Stage badge (stopped_stage_badge).
    - Status message / stop reason display with error/history fallbacks.
    - Run Name display and links.
    - Stage results and step history previews.
    - Lifecycle actions (pause, resume, abort, tick).
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(
            username="admin_consolidation",
            email="admin@consolidation.com",
            password="password"
        )
        self.client.force_login(self.admin_user)
        self.site = AdminSite()
        self.admin_obj = PipelineRunAdmin(PipelineRun, self.site)

        self.workspace = Workspace.objects.create(name="Quantum NLP Consolidation")
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Alpha Quantum Run",
            status="running",
            current_stage="search",
            total_papers_fetched=50,
            total_papers_passed_screening=18,
            usd_cost=Decimal("0.0825")
        )

    def _get_request_with_messages(self):
        req = self.factory.get("/")
        req.user = self.admin_user
        setattr(req, 'session', {})
        messages = FallbackStorage(req)
        setattr(req, '_messages', messages)
        return req

    def test_researchagentprocess_not_in_admin_site_registry(self):
        """
        Confirms that ResearchAgentProcess is unregistered from Django admin UI,
        preventing duplicate menu items, while PipelineRun is registered.
        """
        self.assertNotIn(ResearchAgentProcess, admin.site._registry)
        self.assertIn(PipelineRun, admin.site._registry)

    def test_legacy_researchagentprocess_url_redirects_to_pipelinerun(self):
        """
        Validates that legacy agent process URLs redirect to the unified PipelineRun changelist.
        """
        # Exact changelist URL
        res = self.client.get("/admin/research_intelligence/researchagentprocess/")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, reverse('admin:research_intelligence_pipelinerun_changelist'))

        # Sub-path redirect
        res_sub = self.client.get("/admin/research_intelligence/researchagentprocess/detail-view/test/")
        self.assertEqual(res_sub.status_code, 302)
        self.assertEqual(res_sub.url, reverse('admin:research_intelligence_pipelinerun_changelist'))

        # Follow redirect lands on 200 OK PipelineRun changelist
        res_followed = self.client.get("/admin/research_intelligence/researchagentprocess/", follow=True)
        self.assertEqual(res_followed.status_code, 200)
        self.assertContains(res_followed, "Quantum NLP Consolidation")

    def test_papers_funnel_display_formatting(self):
        """
        Validates the single consolidated 'Papers (In ➔ Out)' column formatting.
        """
        # Case 1: Populated counts
        rendered = str(self.admin_obj.papers_funnel_display(self.pipeline_run))
        self.assertIn("50 in", rendered)
        self.assertIn("➔", rendered)
        self.assertIn("18 out", rendered)
        self.assertIn("#0d6efd", rendered)  # Blue for fetched
        self.assertIn("#198754", rendered)  # Green for passed

        # Case 2: Zero counts
        zero_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            total_papers_fetched=0,
            total_papers_passed_screening=0
        )
        rendered_zero = str(self.admin_obj.papers_funnel_display(zero_run))
        self.assertIn("0 in ➔ 0 out", rendered_zero)

        # Case 3: Fallback to get_papers() count if total_papers_fetched is 0
        fallback_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            total_papers_fetched=0,
            total_papers_passed_screening=2
        )
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=fallback_run,
            title="Fallback Paper 1",
            hash_id="fallback_hash_1",
            doi="10.1234/fallback.1",
            screening_status="accepted"
        )
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=fallback_run,
            title="Fallback Paper 2",
            hash_id="fallback_hash_2",
            doi="10.1234/fallback.2",
            screening_status="accepted"
        )
        rendered_fallback = str(self.admin_obj.papers_funnel_display(fallback_run))
        self.assertIn("2 in", rendered_fallback)
        self.assertIn("2 out", rendered_fallback)

        # Metadata attributes
        self.assertEqual(self.admin_obj.papers_funnel_display.short_description, "Papers (In ➔ Out)")
        self.assertEqual(self.admin_obj.papers_funnel_display.admin_order_field, "total_papers_fetched")
        self.assertEqual(self.admin_obj.papers_in_out, self.admin_obj.papers_funnel_display)

        # Backward-compatible helper methods
        self.assertEqual(self.admin_obj.total_papers_fetched(self.pipeline_run), 50)
        self.assertEqual(self.admin_obj.total_papers_passed_screening(self.pipeline_run), 18)

    def test_name_display(self):
        """
        Validates run name formatting with fallback to UUID prefix.
        """
        # Explicit name
        rendered = str(self.admin_obj.name_display(self.pipeline_run))
        self.assertIn("<strong>Alpha Quantum Run</strong>", rendered)

        # Blank name fallback
        unnamed_run = PipelineRun.objects.create(workspace=self.workspace, name="")
        rendered_blank = str(self.admin_obj.name_display(unnamed_run))
        self.assertIn(f"Run {str(unnamed_run.id)[:8]}", rendered_blank)

    def test_stopped_stage_badge_all_states(self):
        """
        Validates the Halt / Final Stage badge across all lifecycle states:
        running, halted early, completed normal, failed, paused, aborted.
        """
        # Running
        run_in_prog = PipelineRun(status="running", current_stage="search")
        badge = str(self.admin_obj.stopped_stage_badge(run_in_prog))
        self.assertIn("IN PROGRESS", badge)
        self.assertIn("SEARCH", badge)

        # Completed normal
        run_comp = PipelineRun(status="completed", current_stage="completed", stopped_at_stage="completed")
        badge = str(self.admin_obj.stopped_stage_badge(run_comp))
        self.assertIn("COMPLETED", badge)

        # Halted early at search
        run_halted = PipelineRun(status="completed", current_stage="search", stopped_at_stage="search")
        badge = str(self.admin_obj.stopped_stage_badge(run_halted))
        self.assertIn("HALTED AT", badge)
        self.assertIn("SEARCH", badge)

        # Failed
        run_fail = PipelineRun(status="failed", current_stage="ocr", stopped_at_stage="ocr")
        badge = str(self.admin_obj.stopped_stage_badge(run_fail))
        self.assertIn("FAILED AT", badge)
        self.assertIn("OCR", badge)

        # Paused
        run_paused = PipelineRun(status="paused", current_stage="download")
        badge = str(self.admin_obj.stopped_stage_badge(run_paused))
        self.assertIn("PAUSED", badge)

        # Aborted
        run_abort = PipelineRun(status="aborted", current_stage="screening")
        badge = str(self.admin_obj.stopped_stage_badge(run_abort))
        self.assertIn("ABORTED", badge)

    def test_status_message_display_with_fallbacks(self):
        """
        Validates status message display, warnings for 0 papers / halted,
        and fallback to error_message or step_history.
        """
        # Explicit warning message for truly halted run
        pr_warn = PipelineRun(status="completed", stopped_at_stage="search", status_message="Halted: 0 new papers found")
        msg = str(self.admin_obj.status_message_display(pr_warn))
        self.assertIn("⚠️", msg)
        self.assertIn("0 new papers found", msg)
        self.assertIn("#d63384", msg)

        # Successful completed run containing digits (e.g. 140 parameter extractions) must be GREEN ✅, not ⚠️!
        pr_success = PipelineRun(
            status="completed",
            stopped_at_stage="completed",
            status_message="Full SLR pipeline finished successfully. Papers: 94 fetched, 25 passed screening, 140 parameter extractions completed."
        )
        msg_success = str(self.admin_obj.status_message_display(pr_success))
        self.assertIn("✅", msg_success)
        self.assertNotIn("⚠️", msg_success)
        self.assertIn("#198754", msg_success)

        # Error message fallback
        pr_err = PipelineRun(status="failed", status_message="", error_message="LLM Context Exceeded")
        msg_err = str(self.admin_obj.status_message_display(pr_err))
        self.assertIn("❌", msg_err)
        self.assertIn("LLM Context Exceeded", msg_err)

        # Step history fallback
        pr_hist = PipelineRun(
            status="running",
            status_message="",
            step_history=[{"step": "search", "message": "Harvested 150 items"}]
        )
        msg_hist = str(self.admin_obj.status_message_display(pr_hist))
        self.assertIn("Harvested 150 items", msg_hist)

        # Running default
        pr_blank_running = PipelineRun(status="running", status_message="")
        msg_blank = str(self.admin_obj.status_message_display(pr_blank_running))
        self.assertIn("Active stage in progress", msg_blank)

    def test_stage_results_and_step_history_previews(self):
        """
        Validates HTML formatting of stage results table and step history list previews.
        """
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            stage_results={
                "search": {"status": "completed", "summary": "Found 32 papers", "updated_at": "2026-09-03T10:00:00Z"},
                "screening": {"status": "running", "summary": "Screening batch 1", "updated_at": "2026-09-03T10:05:00Z"},
            },
            step_history=[
                {"step": "search", "event": "completed", "papers_fetched": 32, "timestamp": "2026-09-03T10:00:00Z"},
                {"step": "screening", "event": "running", "timestamp": "2026-09-03T10:05:00Z"},
            ]
        )

        # Stage results preview
        preview_html = str(self.admin_obj.stage_results_preview(pr))
        self.assertIn("<table", preview_html)
        self.assertIn("Search", preview_html)
        self.assertIn("Found 32 papers", preview_html)
        self.assertIn("Screening", preview_html)

        # Step history preview
        hist_html = str(self.admin_obj.step_history_preview(pr))
        self.assertIn("<ul", hist_html)
        self.assertIn("search", hist_html)
        self.assertIn("32 papers", hist_html)

        # Empty states
        empty_pr = PipelineRun(stage_results={}, step_history=[])
        self.assertIn("No stage results recorded yet.", str(self.admin_obj.stage_results_preview(empty_pr)))
        self.assertEqual(self.admin_obj.step_history_preview(empty_pr), "-")

    @patch("research_intelligence.tasks.orchestrator.agent_engine.run_pipeline_tick")
    def test_pipeline_admin_lifecycle_actions(self, mock_run_tick):
        """
        Validates bulk admin actions: pause, resume, abort, tick.
        """
        req = self._get_request_with_messages()

        run1 = PipelineRun.objects.create(workspace=self.workspace, status="running")
        run2 = PipelineRun.objects.create(workspace=self.workspace, status="running")
        qs = PipelineRun.objects.filter(id__in=[run1.id, run2.id])

        # 1. Pause
        self.admin_obj.pause_selected_runs(req, qs)
        run1.refresh_from_db()
        run2.refresh_from_db()
        self.assertEqual(run1.status, "paused")
        self.assertEqual(run2.status, "paused")

        # 2. Resume
        self.admin_obj.resume_selected_runs(req, qs)
        run1.refresh_from_db()
        run2.refresh_from_db()
        self.assertEqual(run1.status, "running")
        self.assertEqual(run2.status, "running")
        self.assertEqual(mock_run_tick.call_count, 2)

        # 3. Abort
        self.admin_obj.abort_selected_runs(req, qs)
        run1.refresh_from_db()
        run2.refresh_from_db()
        self.assertEqual(run1.status, "aborted")
        self.assertEqual(run2.status, "aborted")

        # 4. Tick
        mock_run_tick.reset_mock()
        self.admin_obj.tick_selected_runs(req, qs)
        self.assertEqual(mock_run_tick.call_count, 2)

    def test_pipelinerun_changelist_full_render(self):
        """
        Validates that the PipelineRun changelist page loads successfully with HTTP 200
        and includes all updated headers and funnel cells.
        """
        url = reverse('admin:research_intelligence_pipelinerun_changelist')
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Papers (In ➔ Out)")
        self.assertContains(res, "Status and details")
        self.assertContains(res, "Alpha Quantum Run")
        self.assertContains(res, "50 in")
        self.assertContains(res, "18 out")
        self.assertContains(res, "$0.0825")
        self.assertContains(res, "Execution Time &amp; Cost")

    def test_status_and_details_formatting(self):
        """
        Validates the merged Status and details column:
        - Line 1: Status badge (e.g. RUNNING)
        - Line 2: Halt / final stage badge (e.g. IN PROGRESS (SEARCH))
        """
        rendered = str(self.admin_obj.status_and_details(self.pipeline_run))
        self.assertIn("RUNNING", rendered)
        self.assertIn("IN PROGRESS", rendered)
        self.assertIn("SEARCH", rendered)
        self.assertEqual(self.admin_obj.status_and_details.short_description, "Status and details")
        self.assertEqual(self.admin_obj.status_and_details.admin_order_field, "status")

    def test_execution_time_and_cost_formatting(self):
        """
        Validates the merged Execution Time & Cost column:
        - Line 1: Black bold execution time.
        - Line 2: Blue cost ($).
        """
        rendered = str(self.admin_obj.execution_time_and_cost(self.pipeline_run))
        self.assertIn("color: #000000; font-weight: bold;", rendered)
        self.assertIn("color: #0d6efd;", rendered)
        self.assertIn("$0.0825", rendered)
        self.assertEqual(self.admin_obj.execution_time_and_cost.short_description, "Execution Time & Cost")
        self.assertEqual(self.admin_obj.execution_time_and_cost.admin_order_field, "completed_at")

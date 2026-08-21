from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage

from research_intelligence.models import (
    Workspace,
    APIKey,
    ExtractionDefinition,
    Paper,
    Extraction,
    PipelineRun,
    ResearchAgentProcess,
    PaperMetric
)
from research_intelligence.admin import (
    WorkspaceAdmin,
    APIKeyAdmin,
    ExtractionAdmin,
    ResearchAgentProcessAdmin,
    PaperMetricAdmin
)
from research_intelligence.admin_views.storage_browser import (
    _get_file_icon,
    _format_size,
    _recursive_delete_dir
)

User = get_user_model()


class AdminActionsAndStorageSecurityTestCase(TestCase):
    """
    Validates Django Admin custom bulk actions, state machine triggers, and storage browser security utilities.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(username="admin_sec", email="admin@sec.com", password="password")
        self.site = AdminSite()

        self.workspace = Workspace.objects.create(name="Secure Storage Project")
        self.pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="running")

    def _get_request_with_messages(self):
        req = self.factory.get("/")
        req.user = self.admin_user
        setattr(req, 'session', {})
        messages = FallbackStorage(req)
        setattr(req, '_messages', messages)
        return req

    @patch("research_intelligence.tasks.orchestrator.agent_engine.tick_agent_process")
    def test_workspace_launch_agent_actions(self, mock_tick):
        admin_obj = WorkspaceAdmin(Workspace, self.site)
        req = self._get_request_with_messages()

        # 1. Standard launch
        admin_obj.launch_agent_standard(req, Workspace.objects.filter(id=self.workspace.id))
        self.assertTrue(ResearchAgentProcess.objects.filter(workspace=self.workspace, configuration_override__reprocess_existing=False).exists())
        self.assertEqual(mock_tick.call_count, 1)

        # 2. Reprocess launch
        admin_obj.launch_agent_reprocess(req, Workspace.objects.filter(id=self.workspace.id))
        self.assertTrue(ResearchAgentProcess.objects.filter(workspace=self.workspace, configuration_override__reprocess_existing=True).exists())
        self.assertEqual(mock_tick.call_count, 2)

    def test_apikey_revoke_keys_action(self):
        key = APIKey.objects.create(
            key_id="test_key_revoke",
            name="Revoke Key",
            user=self.admin_user,
            is_active=True
        )
        admin_obj = APIKeyAdmin(APIKey, self.site)
        req = self._get_request_with_messages()

        admin_obj.revoke_keys(req, APIKey.objects.filter(id=key.id))
        key.refresh_from_db()
        self.assertFalse(key.is_active)
        self.assertIn("REVOKED", admin_obj.status_badge(key))

    @patch("research_intelligence.tasks.step_5_extraction.extract._run_single_extraction_worker")
    def test_rerun_selected_extractions_action(self, mock_worker):
        mock_worker.return_value = {"success": True}

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="sec_paper_001",
            title="Sec Paper"
        )
        def_ext = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Param Def",
            system_prompt="P",
            user_prompt_template="P",
            response_schema={"type": "object"}
        )
        ext = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=def_ext,
            category="Param Def",
            fields_data={"score": 10}
        )

        admin_obj = ExtractionAdmin(Extraction, self.site)
        req = self._get_request_with_messages()

        admin_obj.rerun_selected_extractions(req, Extraction.objects.filter(id=ext.id))
        self.assertEqual(mock_worker.call_count, 1)

    @patch("research_intelligence.tasks.orchestrator.agent_engine.tick_agent_process")
    def test_agent_process_admin_actions(self, mock_tick):
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Test Agent Actions",
            status="running",
            current_step="screening"
        )
        admin_obj = ResearchAgentProcessAdmin(ResearchAgentProcess, self.site)
        req = self._get_request_with_messages()

        # Pause
        admin_obj.pause_selected_agents(req, ResearchAgentProcess.objects.filter(id=agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.status, "paused")

        # Resume
        admin_obj.resume_selected_agents(req, ResearchAgentProcess.objects.filter(id=agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.status, "running")
        mock_tick.assert_called_once()

        # Abort
        admin_obj.abort_selected_agents(req, ResearchAgentProcess.objects.filter(id=agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.status, "aborted")

    @patch("research_intelligence.tasks.orchestrator.agent_engine.tick_agent_process")
    def test_agent_admin_save_model_auto_ticks_new_agent(self, mock_tick):
        admin_obj = ResearchAgentProcessAdmin(ResearchAgentProcess, self.site)
        req = self._get_request_with_messages()

        agent = ResearchAgentProcess(
            workspace=self.workspace,
            name="New Admin Agent",
            status="running",
            current_step="initialized"
        )
        admin_obj.save_model(req, agent, form=None, change=False)
        self.assertIsNotNone(agent.id)
        mock_tick.assert_called_once_with(str(agent.id))

    @patch("research_intelligence.tasks.orchestrator.agent_engine.tick_agent_process")
    def test_agent_admin_changelist_reconciles_stuck_agents(self, mock_tick):
        agent1 = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Stuck Agent 1",
            status="running",
            current_step="initialized"
        )
        admin_obj = ResearchAgentProcessAdmin(ResearchAgentProcess, self.site)
        req = self._get_request_with_messages()

        admin_obj.changelist_view(req)
        mock_tick.assert_called_with(str(agent1.id))

    def test_agent_admin_badge_and_link_synchronization(self):
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="screening"
        )
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Badge Test Agent",
            pipeline_run=pr,
            status="running",
            current_step="initialized"
        )
        admin_obj = ResearchAgentProcessAdmin(ResearchAgentProcess, self.site)

        # 1. Badge reflects underlying pipeline stage
        badge_html = str(admin_obj.current_step_badge(agent))
        self.assertIn("SCREENING", badge_html.upper())

        # 2. Pipeline link renders link
        link_html = str(admin_obj.pipeline_run_link(agent))
        self.assertIn(str(pr.id)[:8], link_html)

        # 3. Orphan agent auto-links to workspace pipeline run
        orphan = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Orphan Link Agent",
            pipeline_run=None,
            status="running"
        )
        orphan_link_html = str(admin_obj.pipeline_run_link(orphan))
        orphan.refresh_from_db()
        self.assertEqual(orphan.pipeline_run, pr)
        self.assertIn(str(pr.id)[:8], orphan_link_html)

    def test_storage_browser_helper_functions(self):
        # File icons
        self.assertEqual(_get_file_icon("paper.pdf"), "📄 PDF")
        self.assertEqual(_get_file_icon("chart.png"), "🖼️ Image")
        self.assertEqual(_get_file_icon("data.json"), "📊 Data")
        self.assertEqual(_get_file_icon("notes.md"), "📝 Text")
        self.assertEqual(_get_file_icon("script.py"), "⚙️ Code")
        self.assertEqual(_get_file_icon("unknown.xyz"), "📄 File")

        # Size formatting
        self.assertEqual(_format_size(500), "500 B")
        self.assertEqual(_format_size(2048), "2.0 KB")
        self.assertEqual(_format_size(5 * 1024 * 1024), "5.0 MB")
        self.assertEqual(_format_size(None), "-")

        # Recursive delete root protection
        self.assertEqual(_recursive_delete_dir(""), 0)
        self.assertEqual(_recursive_delete_dir("workspaces"), 0)
        self.assertEqual(_recursive_delete_dir("cache"), 0)

    def test_papermetric_admin_badge_and_changelist_rendering(self):
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="pm_paper_001",
            title="Quantum Photonic Systems"
        )
        metric = PaperMetric.objects.create(
            workspace=self.workspace,
            paper=paper,
            pipeline_run=self.pipeline_run,
            signal_score=87.456,
            metrics_data={"fit_score": 92.5, "novelty": 88.0, "trl_level": 6.0}
        )
        metric_none = PaperMetric.objects.create(
            workspace=self.workspace,
            paper=Paper.objects.create(workspace=self.workspace, pipeline_run=self.pipeline_run, hash_id="pm_paper_002", title="Unscreened Paper"),
            pipeline_run=self.pipeline_run,
            signal_score=None,
            metrics_data={}
        )

        admin_obj = PaperMetricAdmin(PaperMetric, self.site)

        # 1. Badge rendering
        score_badge = str(admin_obj.signal_score_badge(metric))
        self.assertIn("87.46", score_badge)
        self.assertIn("⚡", score_badge)

        score_none_badge = str(admin_obj.signal_score_badge(metric_none))
        self.assertIn("-", score_none_badge)

        # 2. Metrics preview rendering
        preview = str(admin_obj.metrics_preview(metric))
        self.assertIn("fit_score", preview)
        self.assertIn("92.5", preview)

        preview_empty = str(admin_obj.metrics_preview(metric_none))
        self.assertIn("-", preview_empty)

        # 3. Pipeline run link
        pr_link = str(admin_obj.pipeline_run_link(metric))
        self.assertIn(str(self.pipeline_run.id)[:8], pr_link)

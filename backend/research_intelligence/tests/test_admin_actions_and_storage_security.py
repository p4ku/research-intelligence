from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.urls import reverse

from research_intelligence.models import (
    Workspace,
    APIKey,
    ExtractionDefinition,
    Paper,
    Extraction,
    PipelineRun,
    ComponentRun,
    ResearchAgentProcess,
    PaperMetric,
    Scraper,
    Subscriber
)
from research_intelligence.admin import (
    WorkspaceAdmin,
    APIKeyAdmin,
    ExtractionAdmin,
    ResearchAgentProcessAdmin,
    PaperMetricAdmin,
    ComponentRunAdmin
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

    def test_workspace_export_and_import_configuration(self):
        import json
        admin_obj = WorkspaceAdmin(Workspace, self.site)
        req = self._get_request_with_messages()

        # Set up full workspace details
        self.workspace.abstract_acceptance_criteria = "Accept autonomous AI agents"
        self.workspace.signal_score_code = "return 0.5 * fit_score"
        self.workspace.save()

        ed = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Strategic Fit",
            system_prompt="Assess strategic fit",
            user_prompt_template="Title: {title}",
            response_schema={"type": "object", "properties": {"fit_score": {"type": "number"}}},
            exit_metric="fit_score"
        )
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="cat:cs.AI AND agentic",
            limit=25
        )
        subscriber = Subscriber.objects.create(
            workspace=self.workspace,
            email="techlead@schwarz.com",
            subscription_type="result_report"
        )

        # 1. Test Export Action
        response = admin_obj.export_configuration(req, Workspace.objects.filter(id=self.workspace.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], "application/json; charset=utf-8")
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['version'], "1.0")
        self.assertEqual(len(payload['workspaces']), 1)
        ws_exported = payload['workspaces'][0]
        self.assertEqual(ws_exported['name'], "Secure Storage Project")
        self.assertEqual(ws_exported['abstract_acceptance_criteria'], "Accept autonomous AI agents")
        self.assertEqual(len(ws_exported['extraction_definitions']), 1)
        self.assertEqual(ws_exported['extraction_definitions'][0]['name'], "Strategic Fit")
        self.assertEqual(len(ws_exported['scrapers']), 1)
        self.assertEqual(ws_exported['scrapers'][0]['search_query'], "cat:cs.AI AND agentic")
        self.assertEqual(len(ws_exported['subscribers']), 1)
        self.assertEqual(ws_exported['subscribers'][0]['email'], "techlead@schwarz.com")

        # 2. Test Import View (Fine-tuning / updating existing workspace)
        ws_exported['abstract_acceptance_criteria'] = "Updated criteria from staging"
        ws_exported['extraction_definitions'][0]['system_prompt'] = "Updated prompt for strategic fit"
        ws_exported['scrapers'][0]['limit'] = 100

        post_req = self.factory.post("/", data={
            "raw_json": json.dumps(payload),
            "overwrite_existing": "yes"
        })
        post_req.user = self.admin_user
        setattr(post_req, 'session', {})
        messages = FallbackStorage(post_req)
        setattr(post_req, '_messages', messages)

        import_resp = admin_obj.import_configuration_view(post_req)
        self.assertEqual(import_resp.status_code, 302)

        # Verify in DB that existing workspace and related objects were updated in place
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.abstract_acceptance_criteria, "Updated criteria from staging")

        ed.refresh_from_db()
        self.assertEqual(ed.system_prompt, "Updated prompt for strategic fit")

        scraper.refresh_from_db()
        self.assertEqual(scraper.limit, 100)

        # 3. Test Import with overwrite_existing="no" (Existing should NOT be overwritten)
        payload['workspaces'][0]['abstract_acceptance_criteria'] = "Should not be applied"
        post_req_no = self.factory.post("/", data={
            "raw_json": json.dumps(payload),
            "overwrite_existing": "no"
        })
        post_req_no.user = self.admin_user
        setattr(post_req_no, 'session', {})
        messages_no = FallbackStorage(post_req_no)
        setattr(post_req_no, '_messages', messages_no)

        import_resp_no = admin_obj.import_configuration_view(post_req_no)
        self.assertEqual(import_resp_no.status_code, 302)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.abstract_acceptance_criteria, "Updated criteria from staging")

        # 4. Test Import of brand new Workspace
        new_ws_payload = {
            "workspaces": [
                {
                    "name": "Brand New Production Review",
                    "abstract_acceptance_criteria": "Brand new review criteria",
                    "extraction_definitions": [
                        {
                            "name": "TRL Level",
                            "system_prompt": "Extract TRL",
                            "user_prompt_template": "{full_text}",
                            "response_schema": {"type": "object"}
                        }
                    ],
                    "scrapers": [
                        {
                            "provider": "openalex",
                            "search_query": "solid state battery",
                            "limit": 40
                        }
                    ]
                }
            ]
        }
        post_req_new = self.factory.post("/", data={
            "raw_json": json.dumps(new_ws_payload),
            "overwrite_existing": "yes"
        })
        post_req_new.user = self.admin_user
        setattr(post_req_new, 'session', {})
        messages_new = FallbackStorage(post_req_new)
        setattr(post_req_new, '_messages', messages_new)

        import_resp_new = admin_obj.import_configuration_view(post_req_new)
        self.assertEqual(import_resp_new.status_code, 302)

        created_ws = Workspace.objects.get(name="Brand New Production Review")
        self.assertEqual(created_ws.abstract_acceptance_criteria, "Brand new review criteria")
        self.assertTrue(created_ws.extraction_definitions.filter(name="TRL Level").exists())
        self.assertTrue(created_ws.scrapers.filter(search_query="solid state battery").exists())

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

    @patch("research_intelligence.tasks.orchestrator.dag.nodes.DownloadNode.execute")
    @patch("research_intelligence.tasks.orchestrator.agent_engine.tick_agent_process")
    def test_component_run_rerun_from_step_forward(self, mock_tick, mock_download_exec):
        Paper.objects.create(workspace=self.workspace, pipeline_run=self.pipeline_run, hash_id="p1", title="Paper 1", screening_status="abstract_passed")
        comp_search = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            status="completed"
        )
        comp_download = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="pdf_fetcher",
            status="completed"
        )
        comp_screening = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="completed"
        )

        admin_obj = ComponentRunAdmin(ComponentRun, self.site)
        req = self._get_request_with_messages()

        # 2. Select the download step and trigger 'Rerun Pipeline from Selected Step Forward'
        admin_obj.rerun_from_this_component_step(req, ComponentRun.objects.filter(id=comp_download.id))

        # 3. Assert downstream steps (screening) and download were reset, and a new running download run exists
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, "running")

        # An agent process must have been created/resumed
        agent = ResearchAgentProcess.objects.filter(pipeline_run=self.pipeline_run).first()
        self.assertIsNotNone(agent)
        self.assertEqual(agent.status, "running")
        self.assertEqual(agent.current_step, "download")

        # Download node was dispatched into a fresh ComponentRun with status='running'
        running_download_run = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type="download", status="running").first()
        self.assertIsNotNone(running_download_run)

        # DownloadNode.execute was called with the new ComponentRun
        mock_download_exec.assert_called_once_with(self.pipeline_run, running_download_run, limit=None)

        # tick_agent_process was invoked
        mock_tick.assert_called_once_with(str(agent.id))

    @patch("research_intelligence.tasks.orchestrator.dag.nodes.DownloadNode.execute")
    def test_component_run_reexecute_single_task(self, mock_execute):
        comp_download = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="pdf_fetcher",
            status="completed",
            error_message="Old error"
        )

        admin_obj = ComponentRunAdmin(ComponentRun, self.site)
        req = self._get_request_with_messages()

        admin_obj.reexecute_single_component_run(req, ComponentRun.objects.filter(id=comp_download.id))

        comp_download.refresh_from_db()
        self.assertEqual(comp_download.status, "running")
        self.assertEqual(comp_download.error_message, "")
        self.assertIsNone(comp_download.completed_at)
        mock_execute.assert_called_once_with(self.pipeline_run, comp_download)

    @patch("django_project.celery.app.control.revoke")
    def test_component_run_abort_action(self, mock_revoke):
        comp = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            status="running",
            celery_task_id="celery-task-12345"
        )
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            name="Agent to abort",
            status="running",
            current_step="search"
        )

        admin_obj = ComponentRunAdmin(ComponentRun, self.site)
        req = self._get_request_with_messages()

        admin_obj.abort_selected_component_runs(req, ComponentRun.objects.filter(id=comp.id))

        # 1. ComponentRun must be aborted with error message
        comp.refresh_from_db()
        self.assertEqual(comp.status, "aborted")
        self.assertIn("Aborted manually by administrator", comp.error_message)
        self.assertIsNotNone(comp.completed_at)

        # 2. Celery task must have been revoked with SIGKILL
        mock_revoke.assert_called_once_with("celery-task-12345", terminate=True, signal="SIGKILL")

        # 3. PipelineRun and AgentProcess must be synchronized to aborted
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, "aborted")

        agent.refresh_from_db()
        self.assertEqual(agent.status, "aborted")
        self.assertEqual(agent.stopped_at_step, "search")

    @patch("research_intelligence.tasks.orchestrator.dag.nodes.DownloadNode.execute")
    def test_reexecute_resets_started_at_and_execution_time(self, mock_execute):
        from datetime import timedelta
        from django.utils import timezone

        old_start = timezone.now() - timedelta(minutes=45)
        old_completed = timezone.now() - timedelta(minutes=40)

        comp = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="pdf_fetcher",
            status="completed",
            error_message="Old error"
        )
        # Manually backdate started_at and completed_at to simulate an old finished task
        ComponentRun.objects.filter(id=comp.id).update(started_at=old_start, completed_at=old_completed)
        comp.refresh_from_db()
        self.assertAlmostEqual(comp.duration_seconds, 300.0, delta=5.0)

        admin_obj = ComponentRunAdmin(ComponentRun, self.site)
        req = self._get_request_with_messages()

        # Re-execute the component
        admin_obj.reexecute_single_component_run(req, ComponentRun.objects.filter(id=comp.id))

        comp.refresh_from_db()
        self.assertEqual(comp.status, "running")
        self.assertEqual(comp.error_message, "")
        self.assertIsNone(comp.completed_at)
        # started_at must have been reset to now
        self.assertAlmostEqual((timezone.now() - comp.started_at).total_seconds(), 0.0, delta=2.0)
        self.assertLess(comp.duration_seconds, 3.0)
        self.assertTrue(comp.execution_time_display.startswith("⏳"))

    def test_reap_zombie_tasks_and_admin_actions(self):
        from datetime import timedelta
        from django.utils import timezone
        from research_intelligence.tasks.auxiliary.zombie_watchdog import reap_zombie_tasks
        from research_intelligence.admin import PipelineRunAdmin

        stale_time = timezone.now() - timedelta(hours=2)

        # 1. Create a zombie ComponentRun
        zombie_comp = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="running",
            celery_task_id="stale_task_12345"
        )
        ComponentRun.objects.filter(id=zombie_comp.id).update(started_at=stale_time)

        # 2. Create a zombie AgentProcess
        zombie_agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            name="Zombie Agent Process",
            status="running",
            current_step="screening"
        )
        ResearchAgentProcess.objects.filter(id=zombie_agent.id).update(started_at=stale_time)

        # 3. Execute watchdog reaping
        stats = reap_zombie_tasks(max_component_age_minutes=30, force=False)
        self.assertGreaterEqual(stats["reaped_components"], 1)
        self.assertGreaterEqual(stats["reaped_pipelines"], 1)
        self.assertGreaterEqual(stats["reaped_agents"], 1)

        # Verify ComponentRun is now failed and completed_at is set (stops hourglass)
        zombie_comp.refresh_from_db()
        self.assertEqual(zombie_comp.status, "failed")
        self.assertIsNotNone(zombie_comp.completed_at)
        self.assertIn("Zombie task reaped", zombie_comp.error_message)

        # Verify PipelineRun is now failed and completed_at is set
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, "failed")
        self.assertIsNotNone(self.pipeline_run.completed_at)

        # Verify AgentProcess is now failed and completed_at is set
        zombie_agent.refresh_from_db()
        self.assertEqual(zombie_agent.status, "failed")
        self.assertIsNotNone(zombie_agent.completed_at)
        self.assertEqual(zombie_agent.stopped_at_step, "screening")
        self.assertIn("Zombie", zombie_agent.stop_reason)

        # 4. Test admin action invocation
        admin_obj = PipelineRunAdmin(PipelineRun, self.site)
        req = self._get_request_with_messages()
        admin_obj.reap_zombie_runs_action(req, PipelineRun.objects.filter(id=self.pipeline_run.id))


class APIKeyAdminTestCase(TestCase):
    """
    Validates APIKey admin views, change forms, custom secret configurations, and secret generation.
    """
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="test_admin_user",
            email="admin@example.com",
            password="adminpassword"
        )
        self.workspace = Workspace.objects.create(
            name="Test Workspace",
            abstract_acceptance_criteria="Accept if...",
            abstract_rejection_criteria="Reject if..."
        )
        self.api_key = APIKey.objects.create(
            name="Test Key",
            key_id="test_key_id",
            user=self.user,
            workspace=self.workspace
        )
        self.api_key.set_secret("oldsecret")
        self.api_key.save()
        self.client.force_login(self.user)

    def test_admin_change_form_renders(self):
        url = reverse('admin:research_intelligence_apikey_change', args=[self.api_key.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "⚡ Generate & Show New Secret")
        self.assertContains(response, "New Secret Key")

    def test_admin_save_custom_secret(self):
        url = reverse('admin:research_intelligence_apikey_change', args=[self.api_key.id])
        data = {
            'name': 'Updated Key Name',
            'key_id': self.api_key.key_id,
            'hashed_secret': self.api_key.hashed_secret,
            'is_active': 'on',
            'scopes': '[]',
            'user': self.user.id,
            'workspace': self.workspace.id,
            'new_secret': 'new_custom_secret',
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.name, 'Updated Key Name')
        self.assertTrue(self.api_key.check_secret('new_custom_secret'))
        
        messages = list(response.context['messages'])
        self.assertTrue(any("API Key secret successfully configured!" in str(m) for m in messages))

    def test_admin_save_blank_keeps_secret(self):
        url = reverse('admin:research_intelligence_apikey_change', args=[self.api_key.id])
        data = {
            'name': 'Updated Key Name 2',
            'key_id': self.api_key.key_id,
            'hashed_secret': self.api_key.hashed_secret,
            'is_active': 'on',
            'scopes': '[]',
            'user': self.user.id,
            'workspace': self.workspace.id,
            'new_secret': '', # blank
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.name, 'Updated Key Name 2')
        self.assertTrue(self.api_key.check_secret('oldsecret'))

    def test_admin_generate_secret_view(self):
        url = reverse('admin:generate-apikey-secret', args=[self.api_key.id])
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.api_key.refresh_from_db()
        self.assertFalse(self.api_key.check_secret('oldsecret'))
        messages = list(response.context['messages'])
        self.assertTrue(any("Successfully generated a new secret for API Key" in str(m) for m in messages))


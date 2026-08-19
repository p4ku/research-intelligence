import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from django.core import mail
from research_intelligence.models import (
    Workspace,
    Scraper,
    ExtractionDefinition,
    PipelineRun,
    ComponentRun,
    ResearchAgentProcess,
    Subscriber,
)
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process, _send_agent_notification
from research_intelligence.mcp.tools.agent_processes import (
    start_research_agent_logic,
    get_research_agent_status_logic,
    wait_for_research_agent_logic,
    pause_research_agent_logic,
    resume_research_agent_logic,
    abort_research_agent_logic,
    delete_research_agent_logic
)

User = get_user_model()


class ResearchAgentProcessTest(TestCase):
    def setUp(self):
        self.patcher = patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
        self.mock_generate = self.patcher.start()
        self.mock_generate.return_value = {
            "passed": True,
            "reasoning": "Mocked LLM generation response",
            "evidence_quotes": ["mock quote"],
            "decision_category": "ACCEPTED"
        }
        self.addCleanup(self.patcher.stop)

        self.tick_patcher = patch("research_intelligence.tasks.orchestrator.agent_engine.run_agent_process_tick.delay")
        self.mock_tick_delay = self.tick_patcher.start()
        self.addCleanup(self.tick_patcher.stop)

        self.user = User.objects.create_user(username="agent_user", email="agent_user@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="Autonomous Agent Workspace",
            abstract_acceptance_criteria="AI agent research",
            abstract_rejection_criteria="Out of domain",
            ocr_provider="pypdf",
            notification_email="notify@example.com"
        )
        from research_intelligence.models import WorkspaceMember
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")
        # Create active scraper
        self.scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="cat:cs.AI",
            is_active=True
        )
        # Create active extraction definition
        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Agent Extraction Def",
            system_prompt="System prompt",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"},
            is_active=True
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_agent_process_full_cycle_state_transitions(self):
        """
        Tests step-by-step state machine transitions:
        initialized -> search -> download -> ocr -> screening -> extraction -> completed
        """
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Test Ingestion Cycle",
            status="running",
            current_step="initialized",
            configuration_override={"limit": 10, "date_range_days": 30}
        )

        # Step 1: Initialized -> Search
        res1 = tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "search")
        self.assertIsNotNone(agent.pipeline_run)
        pr = agent.pipeline_run

        # Simulate completion of Step 1 ComponentRun
        comp_search = ComponentRun.objects.get(pipeline_run=pr, step_type="search")
        comp_search.status = "completed"
        comp_search.save()

        # Step 2: Search -> Download
        res2 = tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "download")

        # Simulate completion of Step 2 ComponentRun
        comp_download = ComponentRun.objects.get(pipeline_run=pr, step_type="download")
        comp_download.status = "completed"
        comp_download.save()

        # Step 3: Download -> OCR (since workspace.ocr_provider is 'pypdf')
        res3 = tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "ocr")

        # Simulate completion of Step 3 ComponentRun
        comp_ocr = ComponentRun.objects.get(pipeline_run=pr, step_type="ocr")
        comp_ocr.status = "completed"
        comp_ocr.save()

        # Step 4a: OCR -> Abstract Screening
        res4 = tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "screening")

        # Simulate completion of Stage 4a Abstract Screening ComponentRun
        comp_abstract = ComponentRun.objects.get(pipeline_run=pr, component_name="abstract_screening")
        comp_abstract.metrics = {"total_screened": 10, "passed": 5, "rejected": 5}
        comp_abstract.status = "completed"
        comp_abstract.save()

        # Step 4b: Abstract Screening -> Full-Text Screening
        res4b = tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "screening")
        comp_ft = ComponentRun.objects.get(pipeline_run=pr, component_name="full_text_screening")
        self.assertIsNotNone(comp_ft)

        # Simulate completion of Stage 4b Full-Text Screening ComponentRun
        comp_ft.metrics = {"total_screened": 5, "passed": 4, "rejected": 1}
        comp_ft.status = "completed"
        comp_ft.save()

        # Step 5: Full-Text Screening -> Extraction
        res5 = tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "extraction")

        # Simulate completion of Step 5 ComponentRun
        comp_ext = ComponentRun.objects.get(pipeline_run=pr, step_type="extraction")
        comp_ext.status = "completed"
        comp_ext.save()

        # Step 6: Extraction -> Completed
        res6 = tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "completed")
        self.assertEqual(agent.status, "completed")
        self.assertIsNotNone(agent.completed_at)

    def test_agent_process_ocr_skipping_when_unconfigured(self):
        """
        Verifies that when workspace.ocr_provider is None/unconfigured,
        the agent state machine automatically skips the OCR step and transitions directly from download to screening.
        """
        self.workspace.ocr_provider = None
        self.workspace.save()

        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="OCR Skipping Agent",
            status="running",
            current_step="download",
            pipeline_run=PipelineRun.objects.create(workspace=self.workspace, status="running")
        )

        comp_download = ComponentRun.objects.create(
            pipeline_run=agent.pipeline_run,
            step_type="download",
            component_name="pdf_downloader",
            status="completed"
        )

        # Tick download completion
        tick_agent_process(str(agent.id))
        agent.refresh_from_db()

        # Should skip OCR and transition directly to screening
        self.assertEqual(agent.current_step, "screening")
        comp_screening = ComponentRun.objects.filter(pipeline_run=agent.pipeline_run, step_type="screening")
        self.assertTrue(comp_screening.exists())

    def test_agent_process_mcp_tools(self):
        """
        Tests FastMCP tools for starting, monitoring, pausing, resuming, aborting, and deleting agent processes.
        """
        # 1. start_research_agent_logic
        start_res = json.loads(start_research_agent_logic(
            self.user,
            workspace_id=str(self.workspace.id),
            name="MCP Agent Process",
            limit=20,
            date_range_days=14,
            query_prefix="arxiv:cs.AI"
        ))
        self.assertEqual(start_res["status"], "success")
        proc_id = start_res["process_id"]

        # 2. get_research_agent_status_logic
        status_res = json.loads(get_research_agent_status_logic(self.user, proc_id))
        self.assertEqual(status_res["process_id"], proc_id)
        self.assertEqual(status_res["status"], "running")
        self.assertIn(status_res["current_step"], ["search", "download"])

        # 3. pause_research_agent_logic
        pause_res = json.loads(pause_research_agent_logic(self.user, proc_id))
        self.assertEqual(pause_res["status"], "success")
        self.assertEqual(pause_res["agent_status"], "paused")

        # 4. resume_research_agent_logic
        resume_res = json.loads(resume_research_agent_logic(self.user, proc_id))
        self.assertEqual(resume_res["status"], "success")
        self.assertEqual(resume_res["agent_status"], "running")

        # 5. abort_research_agent_logic
        abort_res = json.loads(abort_research_agent_logic(self.user, proc_id))
        self.assertEqual(abort_res["status"], "success")
        self.assertEqual(abort_res["agent_status"], "aborted")

        # 6. delete_research_agent_logic
        del_res = json.loads(delete_research_agent_logic(self.user, proc_id))
        self.assertEqual(del_res["status"], "success")
        self.assertFalse(ResearchAgentProcess.objects.filter(id=proc_id).exists())

    def test_agent_process_rest_api(self):
        """
        Tests REST API endpoints:
        - POST /api/agents/ (Start process)
        - GET /api/agents/ (List processes)
        - GET /api/agents/{id}/ (Get process details)
        - POST /api/agents/{id}/pause/ (Pause process)
        - POST /api/agents/{id}/resume/ (Resume process)
        - POST /api/agents/{id}/abort/ (Abort process)
        - DELETE /api/agents/{id}/ (Delete process)
        """
        # Start agent via REST API
        post_data = {
            "workspace": str(self.workspace.id),
            "name": "REST API Agent Process",
            "limit": 15,
            "date_range_days": 30
        }
        response = self.client.post("/api/agents/", post_data, format="json")
        self.assertEqual(response.status_code, 201)
        agent_id = response.data["id"]

        # List agents
        list_resp = self.client.get("/api/agents/")
        self.assertEqual(list_resp.status_code, 200)
        self.assertGreaterEqual(len(list_resp.data), 1)

        # Get status
        get_resp = self.client.get(f"/api/agents/{agent_id}/")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.data["id"], agent_id)

        # Pause
        pause_resp = self.client.post(f"/api/agents/{agent_id}/pause/")
        self.assertEqual(pause_resp.status_code, 200)
        self.assertEqual(pause_resp.data["agent_status"], "paused")

        # Resume
        resume_resp = self.client.post(f"/api/agents/{agent_id}/resume/")
        self.assertEqual(resume_resp.status_code, 200)
        self.assertEqual(resume_resp.data["agent_status"], "running")

        # Abort
        abort_resp = self.client.post(f"/api/agents/{agent_id}/abort/")
        self.assertEqual(abort_resp.status_code, 200)
        self.assertEqual(abort_resp.data["agent_status"], "aborted")

        # Delete
        del_resp = self.client.delete(f"/api/agents/{agent_id}/")
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse(ResearchAgentProcess.objects.filter(id=agent_id).exists())

    def test_wait_for_research_agent_mcp_tool(self):
        """
        Verifies wait_for_research_agent_logic returns completed status when agent finishes.
        """
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Fast Completing Agent",
            status="completed",
            current_step="completed",
            pipeline_run=PipelineRun.objects.create(workspace=self.workspace, status="completed")
        )

        res = json.loads(wait_for_research_agent_logic(
            self.user,
            process_id=str(agent.id),
            timeout_seconds=5,
            poll_interval_seconds=1
        ))
        self.assertEqual(res["status"], "finished")
        self.assertEqual(res["agent_status"], "completed")
        self.assertEqual(res["current_step"], "completed")

    def test_email_notification_to_subscribers_on_completion(self):
        """
        Verifies that _send_agent_notification sends emails to active subscribers, workspace members, and override emails.
        """
        # Create active subscriber
        sub1 = Subscriber.objects.create(
            workspace=self.workspace,
            email="subscriber1@corp.com",
            is_active=True
        )
        # Create inactive subscriber (should be excluded)
        sub2 = Subscriber.objects.create(
            workspace=self.workspace,
            email="inactive_subscriber@corp.com",
            is_active=False
        )

        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            tokens_in=1000,
            tokens_out=500,
            tokens_consumed=1500,
            usd_cost=0.05
        )

        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Notification Test Agent",
            status="completed",
            current_step="completed",
            pipeline_run=pr,
            configuration_override={"notification_email": "override_subscriber@corp.com"}
        )

        # Clear mail outbox
        mail.outbox = []

        # Send notification
        _send_agent_notification(agent)

        # Assert email was dispatched via Django mail backend
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn("subscriber1@corp.com", sent_email.to)
        self.assertIn("override_subscriber@corp.com", sent_email.to)
        self.assertIn("agent_user@example.com", sent_email.to)
        self.assertNotIn("inactive_subscriber@corp.com", sent_email.to)
        self.assertIn("[COMPLETED]", sent_email.subject)
        self.assertIn("Notification Test Agent", sent_email.body)
        self.assertIn("1,500", sent_email.body)

    def test_autonomous_task_completion_notifies_orchestrator_tick(self):
        """
        Tests that calling notify_pipeline_orchestrator_tick automatically triggers run_agent_process_tick.delay.
        """
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Autonomous Trigger Agent",
            status="running",
            current_step="initialized",
            configuration_override={"limit": 5}
        )

        # Initialized -> Search
        tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "search")
        pr = agent.pipeline_run

        # Simulate Search ComponentRun finishing
        comp_search = ComponentRun.objects.get(pipeline_run=pr, step_type="search")
        comp_search.status = "completed"
        comp_search.save()

        # ComponentRun completion calls notify_pipeline_orchestrator_tick
        self.mock_tick_delay.reset_mock()
        notify_pipeline_orchestrator_tick(pr)
        self.mock_tick_delay.assert_called_once_with(str(agent.id))

        # Executing the tick advances state to download
        tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "download")

        # Simulate Download ComponentRun finishing
        comp_download = ComponentRun.objects.get(pipeline_run=pr, step_type="download")
        comp_download.status = "completed"
        comp_download.save()

        self.mock_tick_delay.reset_mock()
        notify_pipeline_orchestrator_tick(pr)
        self.mock_tick_delay.assert_called_once_with(str(agent.id))

        tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "ocr")



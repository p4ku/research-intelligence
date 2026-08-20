import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Subscriber,
    PipelineRun,
    Paper,
    Extraction,
    ExtractionDefinition,
)
from research_intelligence.tasks.auxiliary.email_digest import (
    dispatch_pipeline_subscriber_digest,
    send_pipeline_subscriber_digest_task,
    build_pipeline_run_digest_payload,
)
from research_intelligence.mcp.tools.email_reports import send_pipeline_run_digest_email_logic

User = get_user_model()


class EmailDigestTaskTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="digest_admin", email="admin@soinventive.co.uk", password="pass")
        self.workspace = Workspace.objects.create(
            name="Quantum Computing Lab",
            screening_llm_model="google/gemini-3.7-flash"
        )
        WorkspaceMember.objects.create(user=self.user, workspace=self.workspace, role="admin")

        self.subscriber1 = Subscriber.objects.create(
            workspace=self.workspace,
            email="researcher1@example.com",
            name="Lead Researcher",
            is_active=True
        )
        self.subscriber2 = Subscriber.objects.create(
            workspace=self.workspace,
            email="researcher2@example.com",
            name="Principal Investigator",
            is_active=True
        )
        self.inactive_sub = Subscriber.objects.create(
            workspace=self.workspace,
            email="inactive@example.com",
            name="Inactive User",
            is_active=False
        )

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            total_papers_fetched=10,
            total_papers_passed_screening=2,
            tokens_in=5000,
            tokens_out=1500,
            tokens_consumed=6500,
            usd_cost=0.0450,
        )

        self.definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Qubit Count Extraction",
            system_prompt="Extract qubit counts",
            user_prompt_template="Extract qubits: {paper_text}",
            response_schema={"type": "object", "properties": {"qubits": {"type": "integer"}}},
            exit_metric="qubits"
        )

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Scalable Surface Codes with 100 Qubits",
            authors="Alice Smith, Bob Jones",
            arxiv_id="2401.00001",
            screening_status="accepted",
            abstract="We present a scalable surface code architecture achieving 100 physical qubits."
        )

        self.extraction = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.definition,
            category="Qubit Count Extraction",
            confidence_score=0.98,
            validation_status="pass",
            fields_data={"qubits": "100 Qubits"}
        )

    @patch("research_intelligence.tasks.auxiliary.email_digest.send_mailgun_message")
    def test_build_and_dispatch_digest_success(self, mock_mailgun):
        mock_mailgun.return_value = (True, {"id": "<msg@soinventive.co.uk>", "message": "Queued."})

        result = dispatch_pipeline_subscriber_digest(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id)
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_recipients"], 2)
        self.assertEqual(result["sent_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(mock_mailgun.call_count, 2)

        # Check call arguments
        args, kwargs = mock_mailgun.call_args
        self.assertIn("Quantum Computing Lab", kwargs["subject"])
        self.assertIn("Scalable Surface Codes with 100 Qubits", kwargs["html"])
        self.assertIn("100 Qubits", kwargs["html"])
        self.assertIn("$0.0450", kwargs["html"])

    def test_dispatch_rejects_incomplete_pipeline_run(self):
        running_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            total_papers_fetched=5
        )

        result = dispatch_pipeline_subscriber_digest(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(running_run.id)
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("completed", result["error"])

    def test_dispatch_no_active_subscribers(self):
        Subscriber.objects.filter(workspace=self.workspace).update(is_active=False)

        result = dispatch_pipeline_subscriber_digest(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id)
        )

        self.assertEqual(result["status"], "no_subscribers")
        self.assertEqual(result["sent_count"], 0)

    @patch("research_intelligence.tasks.auxiliary.email_digest.send_mailgun_message")
    def test_dispatch_with_recipient_override(self, mock_mailgun):
        mock_mailgun.return_value = (True, {"message": "Queued."})

        result = dispatch_pipeline_subscriber_digest(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            recipient_override=["executive@custom-domain.com"]
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_recipients"], 1)
        self.assertEqual(result["sent_count"], 1)
        mock_mailgun.assert_called_once()
        self.assertEqual(mock_mailgun.call_args[1]["to_email"], "executive@custom-domain.com")

    @patch("research_intelligence.tasks.auxiliary.email_digest.send_mailgun_message")
    def test_celery_task_execution(self, mock_mailgun):
        mock_mailgun.return_value = (True, {"message": "Queued."})

        task_res = send_pipeline_subscriber_digest_task(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id)
        )

        self.assertEqual(task_res["status"], "success")
        self.assertEqual(task_res["sent_count"], 2)

    @patch("research_intelligence.tasks.auxiliary.email_digest.send_mailgun_message")
    def test_mcp_tool_send_digest_email(self, mock_mailgun):
        mock_mailgun.return_value = (True, {"message": "Queued."})

        # Synchronous MCP execution
        resp_str = send_pipeline_run_digest_email_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            async_dispatch=False
        )
        data = json.loads(resp_str)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["sent_count"], 2)

        # Async MCP execution (queuing Celery task)
        resp_async_str = send_pipeline_run_digest_email_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            async_dispatch=True
        )
        data_async = json.loads(resp_async_str)
        self.assertEqual(data_async["status"], "queued")
        self.assertIn("celery_task_id", data_async)

import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User

from research_intelligence.models import Workspace, Paper, PipelineRun
from chat.models import PaperChatSession, PaperChatMessage
from chat.tasks import execute_paper_chat_task


class ChatTasksTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="celery_tester", email="celery@schwarz.com", password="pass")
        self.workspace = Workspace.objects.create(name="Celery Workspace")
        self.run = PipelineRun.objects.create(workspace=self.workspace)
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_celery_paper_01",
            title="Asynchronous Execution Benchmark"
        )
        self.session = PaperChatSession.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            user=self.user
        )

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_execute_paper_chat_task_success(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "Celery executed answer with high accuracy.",
            {"prompt_tokens": 400, "candidates_tokens": 30}
        )
        mock_get_llm_provider.return_value = mock_provider

        message = PaperChatMessage.objects.create(
            session=self.session,
            sender='user',
            question="Can Celery handle asynchronous turns?"
        )

        res = execute_paper_chat_task(str(message.id))
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["total_tokens"], 430)

        message.refresh_from_db()
        self.assertEqual(message.status, "completed")
        self.assertEqual(message.total_tokens, 430)

    def test_execute_paper_chat_task_nonexistent_message(self):
        fake_id = str(uuid.uuid4())
        res = execute_paper_chat_task(fake_id)
        self.assertEqual(res["status"], "failed")
        self.assertIn("not found", res["error"])

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from research_intelligence.models import Workspace, WorkspaceMember, Paper, PipelineRun
from chat.models import PaperChatSession, PaperChatMessage
from chat.engine import PaperChatEngine


class ChatStreamTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "SecurePassStream123!"

        self.user = User.objects.create_user(
            username="stream_tester",
            email="stream@schwarz.com",
            password=self.password
        )
        self.workspace = Workspace.objects.create(name="Streaming AI Lab")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="researcher")
        self.run = PipelineRun.objects.create(workspace=self.workspace)

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_stream_paper_01",
            title="Real-Time Optical Computing",
            abstract="Streaming inference on photonic integrated circuits."
        )

        login_res = self.client.post('/api/auth/login/', {
            'username': 'stream_tester',
            'password': self.password
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_res.data["access"]}')

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_sse_streaming_post_endpoint(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate_stream.return_value = iter([
            ("Real-time optical inference ", None),
            ("achieves 100 TOPS/W efficiency [Page 1, Fig 1].", {"prompt_tokens": 600, "candidates_tokens": 25, "total_tokens": 625})
        ])
        mock_get_llm_provider.return_value = mock_provider

        response = self.client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'question': "What is the efficiency of the optical engine?",
            'deep_thinking': True
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/event-stream')

        # Read streamed content
        raw_events = b"".join(response.streaming_content).decode('utf-8')
        self.assertIn("event: metadata", raw_events)
        self.assertIn("event: delta", raw_events)
        self.assertIn("event: fact_check", raw_events)
        self.assertIn("event: usage", raw_events)
        self.assertIn("event: done", raw_events)
        self.assertIn("Real-time optical inference", raw_events)

        # Verify message updated in DB
        msg = PaperChatMessage.objects.filter(session__paper=self.paper).latest('created_at')
        self.assertEqual(msg.status, 'completed')
        self.assertEqual(msg.tokens_in, 600)
        self.assertEqual(msg.tokens_out, 25)
        self.assertEqual(msg.total_tokens, 625)
        self.assertIn("Real-time optical inference", msg.message)

    def test_stream_unauthorized_access(self):
        other_user = User.objects.create_user(username="outsider", password="pass")
        other_client = APIClient()
        login_res = other_client.post('/api/auth/login/', {'username': 'outsider', 'password': 'pass'}, format='json')
        other_client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_res.data["access"]}')

        res = other_client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'question': "Try access"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

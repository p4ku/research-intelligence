import uuid
from unittest.mock import patch, MagicMock
from rest_framework import status
from rest_framework.test import APIClient

from chat.models import PaperChatMessage
from chat.tasks import execute_paper_chat_task
from .base import BaseChatTestCase


class ChatApiAndStreamingTestCase(BaseChatTestCase):
    """
    Consolidated test suite for Chat REST APIs, SSE streaming, and background Celery tasks:
    1. Synchronous Q&A turn via POST /api/chat/.
    2. Asynchronous Q&A submit and message polling lifecycle.
    3. Server-Sent Events (SSE) streaming with live tokens, thought process, and fact checking.
    4. Throttling and RBAC access control (403 Forbidden for outsiders).
    5. Celery background task execution and error handling.
    """

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_sync_chat_endpoint(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "The optical compute core dissipates 15 fJ per synaptic operation.",
            {"prompt_tokens": 750, "candidates_tokens": 35}
        )
        mock_get_llm_provider.return_value = mock_provider

        res = self.client.post('/api/chat/', {
            'paper_id': str(self.paper.id),
            'question': "What is the energy per synaptic operation?",
            'sync': True,
            'deep_thinking': True
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'completed')
        self.assertIn("15 fJ per synaptic operation", res.data['message'])
        self.assertEqual(res.data['tokens_in'], 750)
        self.assertEqual(res.data['tokens_out'], 35)
        self.assertEqual(res.data['total_tokens'], 785)
        self.assertTrue(res.data['deep_thinking'])

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_async_chat_and_message_polling(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "Async response: verified optical spiking dynamics.",
            {"prompt_tokens": 600, "candidates_tokens": 20}
        )
        mock_get_llm_provider.return_value = mock_provider

        submit_res = self.client.post('/api/chat/', {
            'paper_id': str(self.paper.id),
            'question': "Describe spiking dynamics."
        }, format='json')
        self.assertEqual(submit_res.status_code, status.HTTP_202_ACCEPTED)
        msg_id = submit_res.data['message_id']
        sess_id = submit_res.data['session_id']

        poll_res = self.client.get(f'/api/chat/messages/{msg_id}/')
        self.assertEqual(poll_res.status_code, status.HTTP_200_OK)
        self.assertEqual(poll_res.data['status'], 'completed')
        self.assertIn("verified optical spiking dynamics", poll_res.data['message'])

        sess_list_res = self.client.get('/api/chat/sessions/')
        self.assertEqual(sess_list_res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(sess_list_res.data), 1)

        sess_detail_res = self.client.get(f'/api/chat/sessions/{sess_id}/')
        self.assertEqual(sess_detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(sess_detail_res.data['messages']), 1)
        self.assertEqual(sess_detail_res.data['total_tokens'], 620)

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_sse_streaming_post_endpoint(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate_stream.return_value = iter([
            ("", {"thought": "First, analyze the power dissipation metrics..."}),
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

        raw_events = b"".join(response.streaming_content).decode('utf-8')
        self.assertIn("event: metadata", raw_events)
        self.assertIn("event: thought", raw_events)
        self.assertIn("First, analyze the power dissipation metrics", raw_events)
        self.assertIn("event: delta", raw_events)
        self.assertIn("event: fact_check", raw_events)
        self.assertIn("event: usage", raw_events)
        self.assertIn("event: done", raw_events)
        self.assertIn("Real-time optical inference", raw_events)

        msg = PaperChatMessage.objects.filter(session__paper=self.paper).latest('created_at')
        self.assertEqual(msg.status, 'completed')
        self.assertEqual(msg.tokens_in, 600)
        self.assertEqual(msg.tokens_out, 25)
        self.assertEqual(msg.total_tokens, 625)
        self.assertIn("Real-time optical inference", msg.message)
        self.assertIn("First, analyze the power dissipation metrics", msg.thinking_process)

    def test_stream_unauthorized_access(self):
        other_client = APIClient()
        self.authenticate_as(self.outsider, client=other_client)

        res = other_client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'question': "Try access"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_submit_chat(self):
        other_client = APIClient()
        self.authenticate_as(self.outsider, client=other_client)

        res = other_client.post('/api/chat/', {
            'paper_id': str(self.paper.id),
            'question': "Unauthorized question"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_view_message(self):
        msg = PaperChatMessage.objects.create(
            session=self.session,
            sender='user',
            question="Private message"
        )
        other_client = APIClient()
        self.authenticate_as(self.outsider, client=other_client)

        res = other_client.get(f'/api/chat/messages/{msg.id}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

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

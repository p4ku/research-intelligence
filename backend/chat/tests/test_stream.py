from unittest.mock import patch, MagicMock
from rest_framework import status
from rest_framework.test import APIClient

from chat.models import PaperChatMessage
from .base import BaseChatTestCase


class ChatStreamTestCase(BaseChatTestCase):
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

        # Read streamed content
        raw_events = b"".join(response.streaming_content).decode('utf-8')
        self.assertIn("event: metadata", raw_events)
        self.assertIn("event: thought", raw_events)
        self.assertIn("First, analyze the power dissipation metrics", raw_events)
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
        self.assertIn("First, analyze the power dissipation metrics", msg.thinking_process)

    def test_stream_unauthorized_access(self):
        other_client = APIClient()
        self.authenticate_as(self.outsider, client=other_client)

        res = other_client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'question': "Try access"
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

from unittest.mock import patch, MagicMock
from rest_framework import status
from .base import BaseChatTestCase


class ChatViewsTestCase(BaseChatTestCase):
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

        # 1. Async Submit (202)
        submit_res = self.client.post('/api/chat/', {
            'paper_id': str(self.paper.id),
            'question': "Describe spiking dynamics."
        }, format='json')
        self.assertEqual(submit_res.status_code, status.HTTP_202_ACCEPTED)
        msg_id = submit_res.data['message_id']
        sess_id = submit_res.data['session_id']

        # 2. Polling Message Detail (200)
        poll_res = self.client.get(f'/api/chat/messages/{msg_id}/')
        self.assertEqual(poll_res.status_code, status.HTTP_200_OK)
        self.assertEqual(poll_res.data['status'], 'completed')
        self.assertIn("verified optical spiking dynamics", poll_res.data['message'])

        # 3. Session List & Detail
        sess_list_res = self.client.get('/api/chat/sessions/')
        self.assertEqual(sess_list_res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(sess_list_res.data), 1)

        sess_detail_res = self.client.get(f'/api/chat/sessions/{sess_id}/')
        self.assertEqual(sess_detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(sess_detail_res.data['messages']), 1)
        self.assertEqual(sess_detail_res.data['total_tokens'], 620)

"""
Two rules of a chat turn that the streaming view had not pinned down:

1. A session never changes subject — a session_id filed against paper A
   cannot be continued with paper B (or with no paper at all).
2. When the reader stops the stream, the words that had already arrived are
   filed under `aborted` and billed, exactly as the reader saw them, and the
   provider stream is closed so no further tokens are paid for.
"""
from unittest.mock import patch, MagicMock

from rest_framework import status

from chat.models import PaperChatMessage, PaperChatSession
from research_intelligence.models.audit import LLMUsageRecord
from .base import BaseChatTestCase


class ChatSessionScopeTestCase(BaseChatTestCase):

    def setUp(self):
        super().setUp()
        self.other_paper = self.create_paper(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_other_paper_02",
            title="A Different Paper",
        )

    def test_session_of_another_paper_is_refused(self):
        """self.session belongs to self.paper; continuing it under another paper is a 400, not a silent re-file."""
        for path in ('/api/chat/', '/api/chat/stream/'):
            with self.subTest(path=path):
                res = self.client.post(path, {
                    'paper_id': str(self.other_paper.id),
                    'session_id': str(self.session.id),
                    'question': "Which paper am I in?",
                }, format='json')
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("different paper", res.data['error'])
        self.assertEqual(self.session.messages.count(), 0)

    def test_workspace_session_is_not_continued_under_a_paper(self):
        """A workspace-scope thread (no paper) cannot be resumed with a paper_id either."""
        ws_session = PaperChatSession.objects.create(
            workspace=self.workspace, paper=None, user=self.user, title="Corpus thread"
        )
        res = self.client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'session_id': str(ws_session.id),
            'question': "Now about this paper",
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ws_session.messages.count(), 0)


class ChatStreamDisconnectTestCase(BaseChatTestCase):

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_stop_files_the_partial_answer_and_bills_it(self, mock_get_llm_provider):
        closed = {'value': False}

        def chunks():
            try:
                # Gemini reports cumulative usage on every chunk.
                yield "The optical core ", {"prompt_tokens": 800, "candidates_tokens": 4}
                yield "dissipates 15 fJ", {"prompt_tokens": 800, "candidates_tokens": 9}
                yield " per synaptic operation.", {"prompt_tokens": 800, "candidates_tokens": 14}
            finally:
                closed['value'] = True

        mock_provider = MagicMock()
        mock_provider.generate_stream.return_value = chunks()
        mock_get_llm_provider.return_value = mock_provider

        response = self.client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'question': "What is the energy per synaptic operation?",
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        frames = iter(response.streaming_content)
        received = [next(frames).decode('utf-8') for _ in range(3)]  # metadata, delta, delta
        self.assertIn("event: metadata", received[0])
        self.assertIn("The optical core ", received[1])
        self.assertIn("dissipates 15 fJ", received[2])

        # The reader presses Stop: Django closes the response, the generator
        # gets GeneratorExit at its suspended yield.
        response.close()

        self.assertTrue(closed['value'], "the provider stream must be closed on disconnect")

        msg = PaperChatMessage.objects.filter(session__paper=self.paper).latest('created_at')
        self.assertEqual(msg.status, 'aborted')
        self.assertEqual(msg.message, "The optical core dissipates 15 fJ")
        self.assertEqual(msg.tokens_in, 800)
        self.assertEqual(msg.tokens_out, 9)
        self.assertGreater(float(msg.usd_cost), 0.0)
        self.assertIsNotNone(msg.completed_at)
        self.assertFalse(msg.error_message)

        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.tokens_consumed_this_month, 809)
        self.assertTrue(LLMUsageRecord.objects.filter(operation_type="chat").exists())
        msg.session.refresh_from_db()
        self.assertEqual(msg.session.total_tokens, 809)

        # The stopped answer is part of the conversation the next turn sees.
        mock_provider.generate_stream.return_value = iter([
            ("Yes.", {"prompt_tokens": 900, "candidates_tokens": 2}),
        ])
        follow_up = self.client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'session_id': str(msg.session_id),
            'question': "Is that low?",
        }, format='json')
        b"".join(follow_up.streaming_content)
        prompt = mock_provider.generate_stream.call_args.kwargs['prompt']
        self.assertIn("CONVERSATION MEMORY", prompt)
        self.assertIn("dissipates 15 fJ", prompt)

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_disconnect_before_the_first_token_is_still_aborted(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate_stream.return_value = iter([("never sent", None)])
        mock_get_llm_provider.return_value = mock_provider

        response = self.client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'question': "Hello?",
        }, format='json')
        frames = iter(response.streaming_content)
        next(frames)  # metadata only
        response.close()

        msg = PaperChatMessage.objects.filter(session__paper=self.paper).latest('created_at')
        self.assertEqual(msg.status, 'aborted')
        self.assertEqual(msg.message, "")

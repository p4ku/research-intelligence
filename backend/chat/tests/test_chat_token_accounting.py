from unittest.mock import patch, MagicMock
from decimal import Decimal
from rest_framework import status

from research_intelligence.models import LLMUsageRecord, Workspace
from chat.models import PaperChatMessage, PaperChatSession
from .base import BaseChatTestCase


class ChatTokenAccountingAndLedgerTestCase(BaseChatTestCase):
    """
    Test suite verifying that Chat with Paper accurately accounts for token usage and USD costs:
    1. Records immutable entries into LLMUsageRecord (operation_type='chat')
    2. Updates Workspace monthly counters (tokens_in, tokens_out, total, usd_spent)
    3. Handles stream thought deltas without wiping token metadata
    4. Applies robust fallback token estimation if provider returns 0 or None tokens
    """

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_streaming_chat_creates_llm_usage_record_with_positive_tokens_and_cost(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate_stream.return_value = iter([
            ("", {"thought": "Analyzing quantum error correction thresholds..."}),
            ("Surface code yields 1% threshold ", None),
            ("for physical qubit operations.", {"prompt_tokens": 850, "candidates_tokens": 120, "total_tokens": 970})
        ])
        mock_get_llm_provider.return_value = mock_provider

        initial_records_count = LLMUsageRecord.objects.filter(operation_type='chat').count()
        initial_ws_tokens = self.workspace.tokens_consumed_this_month or 0
        initial_ws_cost = self.workspace.usd_spent_this_month or Decimal("0.0000")

        response = self.client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'question': "What is the threshold for surface codes in this paper?",
            'deep_thinking': True
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Drain streaming generator
        b"".join(response.streaming_content)

        # 1. Verify LLMUsageRecord created in persistent global ledger
        new_records = LLMUsageRecord.objects.filter(operation_type='chat').order_by('-timestamp')
        self.assertEqual(new_records.count(), initial_records_count + 1)

        record = new_records.first()
        self.assertEqual(record.operation_type, 'chat')
        self.assertEqual(record.workspace_id_snapshot, str(self.workspace.id))
        self.assertEqual(record.workspace_name_snapshot, self.workspace.name)
        self.assertEqual(record.tokens_in, 850)
        self.assertEqual(record.tokens_out, 120)
        self.assertEqual(record.total_tokens, 970)
        self.assertGreater(record.usd_cost, Decimal("0.0000"))

        # 2. Verify Workspace counters updated
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.tokens_in_consumed_this_month, 850)
        self.assertEqual(self.workspace.tokens_out_consumed_this_month, 120)
        self.assertEqual(self.workspace.tokens_consumed_this_month, initial_ws_tokens + 970)
        self.assertGreater(self.workspace.usd_spent_this_month, initial_ws_cost)

        # 3. Verify PaperChatMessage metrics
        msg = PaperChatMessage.objects.filter(session__paper=self.paper).latest('created_at')
        self.assertEqual(msg.tokens_in, 850)
        self.assertEqual(msg.tokens_out, 120)
        self.assertEqual(msg.total_tokens, 970)
        self.assertEqual(msg.usd_cost, record.usd_cost)
        self.assertGreater(msg.usd_cost, Decimal("0.0000"))

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_streaming_chat_fallback_estimation_when_provider_returns_no_usage_metadata(self, mock_get_llm_provider):
        """
        When streaming deltas arrive with thoughts and text but NO usage_metadata (None or 0),
        the system must perform robust fallback estimation to record non-zero tokens and USD cost.
        """
        mock_provider = MagicMock()
        # Stream with no token metadata (usage=None or empty)
        mock_provider.generate_stream.return_value = iter([
            ("", {"thought": "Thinking deeply about topological braiding..."}),
            ("Topological majorana zero modes provide hardware protection against decoherence.", None)
        ])
        mock_get_llm_provider.return_value = mock_provider

        response = self.client.post('/api/chat/stream/', {
            'paper_id': str(self.paper.id),
            'question': "How do topological qubits prevent decoherence?",
            'deep_thinking': True
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        b"".join(response.streaming_content)

        # Verify fallback token counts are recorded in LLMUsageRecord
        record = LLMUsageRecord.objects.filter(operation_type='chat').latest('timestamp')
        self.assertGreater(record.tokens_in, 0, "Prompt tokens must be estimated when missing")
        self.assertGreater(record.tokens_out, 0, "Candidate tokens must be estimated when missing")
        self.assertGreater(record.total_tokens, 0)
        self.assertGreater(record.usd_cost, Decimal("0.0000"))

        # Verify PaperChatMessage also has non-zero tokens and cost
        msg = PaperChatMessage.objects.filter(session__paper=self.paper).latest('created_at')
        self.assertGreater(msg.tokens_in, 0)
        self.assertGreater(msg.tokens_out, 0)
        self.assertGreater(msg.total_tokens, 0)
        self.assertGreater(msg.usd_cost, Decimal("0.0000"))

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_sync_chat_records_token_usage_and_cost_in_ledger(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "Superconducting transmon qubits operate at 15 millikelvin.",
            {"prompt_tokens": 1200, "candidates_tokens": 180, "total_tokens": 1380, "thought_process": "Cryogenic analysis"}
        )
        mock_get_llm_provider.return_value = mock_provider

        response = self.client.post('/api/chat/', {
            'paper_id': str(self.paper.id),
            'question': "What is the operating temperature of transmon qubits?",
            'sync': True
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        record = LLMUsageRecord.objects.filter(operation_type='chat').latest('timestamp')
        self.assertEqual(record.tokens_in, 1200)
        self.assertEqual(record.tokens_out, 180)
        self.assertEqual(record.total_tokens, 1380)
        self.assertGreater(record.usd_cost, Decimal("0.0000"))

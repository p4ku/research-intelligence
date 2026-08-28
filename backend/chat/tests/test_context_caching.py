from unittest.mock import patch, MagicMock
from research_intelligence.models import Paper
from chat.models import PaperChatMessage
from chat.engine.cache_manager import GeminiContextCacheManager
from chat.engine import PaperChatEngine
from .base import BaseChatTestCase


class ContextCachingTestCase(BaseChatTestCase):
    def setUp(self):
        super().setUp()
        self.workspace.llm_provider = "google"
        self.workspace.screening_llm_model = "google/gemini-3.7-flash"
        self.workspace.save()

        self.large_paper = self.create_paper(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_large_cached_paper_01",
            title="Massive Optical Computing Review",
            abstract="Very long context paper " * 300 # ~6KB
        )
        self.cached_session = self.create_session(
            paper=self.large_paper,
            user=self.user,
            title="Cache Verification Session"
        )

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_gemini_context_cache_creation_and_reuse(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.create_context_cache.return_value = "cachedContents/schwarz_cache_998877"
        mock_provider.generate.return_value = (
            "Answer using cached context.",
            {"prompt_tokens": 150, "candidates_tokens": 20, "total_tokens": 170}
        )
        mock_get_llm_provider.return_value = mock_provider

        msg1 = PaperChatMessage.objects.create(
            session=self.cached_session,
            question="Summarize the core findings."
        )

        engine = PaperChatEngine()
        res1 = engine.execute(msg1)

        self.assertEqual(res1["status"], "completed")
        self.assertEqual(res1["cached_content"], "cachedContents/schwarz_cache_998877")

        # Verify session saved the cache key
        self.cached_session.refresh_from_db()
        self.assertEqual(self.cached_session.cached_content_name, "cachedContents/schwarz_cache_998877")

        # Second turn reuses the cached content without calling create_context_cache again
        mock_provider.create_context_cache.reset_mock()

        msg2 = PaperChatMessage.objects.create(
            session=self.cached_session,
            question="What is the energy density?"
        )
        res2 = engine.execute(msg2)

        self.assertEqual(res2["status"], "completed")
        self.assertEqual(res2["cached_content"], "cachedContents/schwarz_cache_998877")
        mock_provider.create_context_cache.assert_not_called()

    def test_cache_skipped_for_small_contexts(self):
        small_paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_tiny_paper",
            title="Tiny Note",
            abstract="Short."
        )
        small_session = self.create_session(paper=small_paper, user=self.user, title="Small Session")
        cache_mgr = GeminiContextCacheManager()
        cache_name = cache_mgr.get_or_create_cache(
            session=small_session,
            paper=small_paper,
            workspace=self.workspace,
            context_text="Small context",
            pdf_bytes=None,
            mime_type=None,
            system_instruction="Instruction"
        )
        self.assertIsNone(cache_name)

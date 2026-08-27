from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User

from research_intelligence.models import Workspace, Paper, PipelineRun
from chat.models import PaperChatSession, PaperChatMessage
from chat.engine.cache_manager import GeminiContextCacheManager
from chat.engine import PaperChatEngine


class ContextCachingTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cache_user", email="cache@schwarz.com", password="password")
        self.workspace = Workspace.objects.create(
            name="Context Cache Lab",
            llm_provider="google",
            screening_llm_model="google/gemini-3.7-flash"
        )
        self.run = PipelineRun.objects.create(workspace=self.workspace)
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_large_cached_paper_01",
            title="Massive Optical Computing Review",
            abstract="Very long context paper " * 300 # ~6KB
        )
        self.session = PaperChatSession.objects.create(
            workspace=self.workspace,
            paper=self.paper,
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
            session=self.session,
            question="Summarize the core findings."
        )

        engine = PaperChatEngine()
        res1 = engine.execute(msg1)

        self.assertEqual(res1["status"], "completed")
        self.assertEqual(res1["cached_content"], "cachedContents/schwarz_cache_998877")

        # Verify session saved the cache key
        self.session.refresh_from_db()
        self.assertEqual(self.session.cached_content_name, "cachedContents/schwarz_cache_998877")

        # Second turn reuses the cached content without calling create_context_cache again
        mock_provider.create_context_cache.reset_mock()

        msg2 = PaperChatMessage.objects.create(
            session=self.session,
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
        small_session = PaperChatSession.objects.create(
            workspace=self.workspace,
            paper=small_paper,
            user=self.user,
            title="Small Session"
        )
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

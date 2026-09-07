"""
Prompt shape and document memoisation: the paper is a stable prefix so Gemini's
implicit prefix cache can reuse it across turns, and the OCR markdown is read
from storage once rather than on every question.
"""
from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from research_intelligence.llm_providers.pricing import calculate_llm_cost
from research_intelligence.models import PaperMetric
from chat.models import PaperChatMessage
from chat.engine import PaperChatEngine, PaperContextBuilder
from .base import BaseChatTestCase


class PromptAssemblyTestCase(BaseChatTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.md_path = f"workspaces/{self.workspace.id}/documents/{self.paper.hash_id}/ocr.md"
        default_storage.save(self.md_path, ContentFile(b"# Spiking Photonics\nThe device reaches 12 pJ per synaptic event."))
        self.paper.converted_md_path = self.md_path
        self.paper.save(update_fields=['converted_md_path'])
        PaperMetric.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            paper=self.paper,
            signal_score=7.5,
            screening_status='accepted',
            screening_reasoning="Matches the neuromorphic hardware scope.",
        )

    def tearDown(self):
        if default_storage.exists(self.md_path):
            default_storage.delete(self.md_path)
        cache.clear()
        super().tearDown()

    def _completed_turn(self, question: str, answer: str = "Earlier answer."):
        return PaperChatMessage.objects.create(
            session=self.session, sender='user', status='completed', question=question, message=answer
        )

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_prompt_orders_document_before_everything_that_changes(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = ("Answer.", {"prompt_tokens": 900, "candidates_tokens": 10})
        mock_get_llm_provider.return_value = mock_provider

        self._completed_turn("What is the energy per event?")
        msg = PaperChatMessage.objects.create(session=self.session, question="And the latency?", deep_thinking=True)

        result = PaperChatEngine().execute(msg)
        self.assertEqual(result["status"], "completed")

        kwargs = mock_provider.generate.call_args.kwargs
        prompt = kwargs["prompt"]
        self.assertIn("Schwarz Research Intelligence", kwargs["system_instruction"])

        positions = [
            prompt.index("## PAPER DOCUMENT"),
            prompt.index("12 pJ per synaptic event"),
            prompt.index("## SCREENING, EXTRACTIONS & METRICS"),
            prompt.index("Matches the neuromorphic hardware scope."),
            prompt.index("## CONVERSATION MEMORY"),
            prompt.index("What is the energy per event?"),
            prompt.index("## DEEP SCIENTIFIC REASONING DIRECTIVE"),
            prompt.index("## USER QUESTION"),
            prompt.index("And the latency?"),
        ]
        self.assertEqual(positions, sorted(positions))
        # The whole prefix up to the annotations is identical to a fresh session's.
        fresh_prompt = PaperChatEngine()._assemble_prompt(
            PaperContextBuilder().document(self.paper).text, "", "", "Different question", False
        )
        prefix_end = prompt.index("## SCREENING, EXTRACTIONS & METRICS")
        self.assertTrue(fresh_prompt.startswith(prompt[:prefix_end].rstrip()))

    def test_document_markdown_is_read_from_storage_once(self):
        builder = PaperContextBuilder()
        with patch("chat.engine.context_builder.default_storage", wraps=default_storage) as storage:
            first = builder.document(self.paper)
            second = builder.document(self.paper)
            self.assertEqual(storage.open.call_count, 1)
            self.assertEqual(storage.exists.call_count, 1)
        self.assertEqual(first, second)
        self.assertIn("12 pJ per synaptic event", second.text)

    def test_annotations_are_read_fresh_each_turn(self):
        builder = PaperContextBuilder()
        before = builder.annotations(self.paper, self.workspace)
        self.assertIn("Composite Signal Score: 7.5", before)
        PaperMetric.objects.create(workspace=self.workspace, pipeline_run=self.run, paper=self.paper, signal_score=9.1)
        after = builder.annotations(self.paper, self.workspace)
        self.assertIn("Composite Signal Score: 9.1", after)
        self.assertNotIn("Composite Signal Score: 7.5", after)

    def test_build_composes_document_then_annotations(self):
        context_text, pdf_bytes, mime_type = PaperContextBuilder().build(self.paper)
        self.assertLess(context_text.index("### Paper Metadata"), context_text.index("### Full Document Text"))
        self.assertLess(context_text.index("### Full Document Text"), context_text.index("### SLR Screening Evaluation"))
        self.assertIsNone(pdf_bytes)
        self.assertIsNone(mime_type)

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_cached_prompt_tokens_are_billed_at_the_cached_rate(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "Answer.",
            {"prompt_tokens": 10_000, "candidates_tokens": 100, "cached_tokens": 8_000},
        )
        mock_get_llm_provider.return_value = mock_provider

        msg = PaperChatMessage.objects.create(session=self.session, question="Summarise.")
        result = PaperChatEngine().execute(msg)

        self.assertEqual(result["tokens_cached"], 8_000)
        expected = calculate_llm_cost(self.workspace.screening_llm_model, 10_000, 100, 8_000)
        uncached = calculate_llm_cost(self.workspace.screening_llm_model, 10_000, 100)
        self.assertAlmostEqual(result["usd_cost"], float(expected), places=8)
        self.assertLess(result["usd_cost"], float(uncached))

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_streaming_path_bills_cached_tokens_too(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate_stream.return_value = iter([
            ("Streamed ", None),
            ("answer.", {"prompt_tokens": 10_000, "candidates_tokens": 20, "cached_tokens": 8_000, "total_tokens": 10_020}),
        ])
        mock_get_llm_provider.return_value = mock_provider

        msg = PaperChatMessage.objects.create(session=self.session, question="Stream it.")
        events = "".join(PaperChatEngine().execute_stream(msg))
        self.assertIn("event: done", events)

        msg.refresh_from_db()
        expected = calculate_llm_cost(self.workspace.screening_llm_model, 10_000, 20, 8_000)
        self.assertAlmostEqual(float(msg.usd_cost), float(expected), places=5)
        self.assertEqual(msg.tokens_in, 10_000)

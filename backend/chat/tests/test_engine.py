from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import (
    Workspace,
    Paper,
    PipelineRun,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
)
from chat.models import PaperChatSession, PaperChatMessage
from chat.engine import (
    PaperChatEngine,
    PaperContextBuilder,
    HierarchicalSessionSummarizer,
    VisualCitationExtractor,
    CitationFactChecker,
)


class ChatEngineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="chat_scientist", email="scientist@schwarz.com", password="password")
        self.workspace = Workspace.objects.create(
            name="Photonics AI Lab",
            screening_llm_model="google/gemini-3.8-flash",
            signal_score_code="score = 0.6 * fit_score + 0.4 * novelty_score\nreturn round(score, 2)"
        )
        self.run = PipelineRun.objects.create(workspace=self.workspace)
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_photonic_chip_01",
            title="Integrated Photonic Tensor Core Architecture",
            abstract="We present an optical compute engine operating at 100 GHz with sub-picojoule energy efficiency.",
            authors="Dr. Light, Prof. Laser",
            doi="10.1038/s41566-025-0001-z"
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.run,
            workspace=self.workspace,
            screening_status="abstract_passed",
            abstract_screening_reasoning="High throughput optical compute engine matches domain scope",
            signal_score=9.2,
            signal_score_details={"fit_score": 9.5, "novelty_score": 8.8}
        )
        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Optical Bandwidth",
            system_prompt="Extract optical bandwidth",
            user_prompt_template="Analyze {paper_text}",
            response_schema={"type": "string"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.ext_def,
            category="performance_metric",
            fields_data={"bandwidth": "100 GHz modulated clock frequency"},
            confidence_score=0.98
        )
        PaperMetric.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            paper=self.paper,
            signal_score=9.2,
            metrics_data={"trl_level": "4.0"}
        )

    def test_context_builder_rich_and_clean(self):
        context_text, pdf_bytes, mime_type = PaperContextBuilder().build(self.paper)
        self.assertIn("Integrated Photonic Tensor Core Architecture", context_text)
        self.assertIn("100 GHz modulated clock frequency", context_text)
        self.assertIn("High throughput optical compute engine matches domain scope", context_text)
        self.assertIn("Composite Signal Score: 9.2", context_text)
        self.assertIn("score = 0.6 * fit_score", context_text)
        self.assertIsNone(pdf_bytes)

    def test_visual_citation_extraction(self):
        extractor = VisualCitationExtractor()

        # Structured JSON response
        json_output = '```json\n{\n  "answer": "Optical clock frequency is 100 GHz.",\n  "visual_citations": [{"page": 4, "box_2d": [100, 200, 300, 400], "label": "Figure 3a", "quote": "100 GHz modulated optical clock"}]\n}\n```'
        answer, cits = extractor.extract(json_output)
        self.assertEqual(answer, "Optical clock frequency is 100 GHz.")
        self.assertEqual(len(cits), 1)
        self.assertEqual(cits[0]["page"], 4)
        self.assertEqual(cits[0]["label"], "Figure 3a")

        # Inline citation format
        inline_output = "The bandwidth reaches maximum [Page 5, Figure 4, box_2d: [10, 20, 30, 40], quote: \"across 64 waveguides\"] in laboratory tests."
        answer_in, cits_in = extractor.extract(inline_output)
        self.assertEqual(len(cits_in), 1)
        self.assertEqual(cits_in[0]["page"], 5)
        self.assertEqual(cits_in[0]["quote"], "across 64 waveguides")

    def test_fact_checker_grounding_audit(self):
        checker = CitationFactChecker()
        source = "The optical tensor core achieves 100 GHz modulated optical clock frequency across 64 waveguides."

        # Pass case
        cits = [{"page": 4, "quote": "100 GHz modulated optical clock frequency"}]
        verified_cits, guard = checker.verify(source, cits)
        self.assertTrue(verified_cits[0]["verified_in_source"])
        self.assertTrue(guard["verified"])
        self.assertEqual(guard["status"], "PASS")

        # Hallucination case
        fake_cits = [{"page": 10, "quote": "Demonstrated 1000 Terahertz superconducting processor"}]
        v_fake, guard_fake = checker.verify(source, fake_cits)
        self.assertFalse(v_fake[0]["verified_in_source"])
        self.assertFalse(guard_fake["verified"])
        self.assertEqual(guard_fake["status"], "WARNING_UNVERIFIED_CLAIMS")

    def test_hierarchical_session_summarizer(self):
        summarizer = HierarchicalSessionSummarizer()
        session = PaperChatSession.objects.create(workspace=self.workspace, paper=self.paper, user=self.user)

        messages = [
            PaperChatMessage.objects.create(session=session, sender='user', question=f"Question {i}", message=f"Answer {i}", status='completed')
            for i in range(5)
        ]

        summarizer.compress_and_update(session, messages, threshold=4)
        session.refresh_from_db()
        self.assertIn("Question 0", session.summary)
        self.assertIn("Answer 0", session.summary)

        # Call again on turn 6 - should not duplicate Question 0
        new_msg = PaperChatMessage.objects.create(session=session, sender='user', question="Question 5", message="Answer 5", status='completed')
        messages.append(new_msg)
        summarizer.compress_and_update(session, messages, threshold=4)
        session.refresh_from_db()
        self.assertEqual(session.summary.count("Question 0"), 1)

        history_block = summarizer.build_history_block(session, messages)
        self.assertIn("Prior Conversation Context", history_block)
        self.assertIn("Recent Conversation Turns", history_block)

    def test_context_builder_reads_bytes_and_utf8_decoded_storage(self):
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        md_path = f"workspaces/{self.workspace.id}/test_ocr.md"
        default_storage.save(md_path, ContentFile(b"# Optical Modulators\nPerformance data: 120 GHz"))
        self.paper.converted_md_path = md_path
        self.paper.save()

        context_text, pdf_bytes, mime_type = PaperContextBuilder().build(self.paper)
        self.assertIn("Optical Modulators", context_text)
        self.assertIn("120 GHz", context_text)
        default_storage.delete(md_path)


    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_engine_full_execution_flow(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "The optical core operates at 100 GHz [Page 4, Figure 3a, quote: \"100 GHz modulated optical clock frequency\"].",
            {"prompt_tokens": 1500, "candidates_tokens": 80, "thought_process": "Internal derivation of tensor clock rate..."}
        )
        mock_get_llm_provider.return_value = mock_provider

        session = PaperChatSession.objects.create(workspace=self.workspace, paper=self.paper, user=self.user)
        message = PaperChatMessage.objects.create(
            session=session,
            sender='user',
            question="What optical clock frequency is achieved?",
            deep_thinking=True
        )

        res = PaperChatEngine().execute(message)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["tokens_in"], 1500)
        self.assertEqual(res["tokens_out"], 80)
        self.assertEqual(res["total_tokens"], 1580)
        self.assertEqual(res["thinking_process"], "Internal derivation of tensor clock rate...")
        self.assertGreater(res["usd_cost"], 0.0)
        self.assertTrue(res["deep_thinking"])
        self.assertEqual(res["llm_model"], "google/gemini-3.8-flash")

        # Check DB updates
        message.refresh_from_db()
        self.assertEqual(message.status, "completed")
        self.assertEqual(message.total_tokens, 1580)
        self.assertEqual(message.thinking_process, "Internal derivation of tensor clock rate...")
        self.assertGreater(float(message.usd_cost), 0.0)
        self.assertEqual(message.llm_model, "google/gemini-3.8-flash")

        session.refresh_from_db()
        self.assertEqual(session.total_tokens, 1580)
        self.assertGreater(float(session.total_usd_cost), 0.0)

        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.tokens_consumed_this_month, 1580)
        self.assertGreater(float(self.workspace.usd_spent_this_month), 0.0)

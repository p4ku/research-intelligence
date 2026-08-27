import json
import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from rest_framework.test import APIClient
from rest_framework import status

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Paper,
    PipelineRun,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
    PaperChatSession,
    PaperChatMessage,
    APIKey,
)
from research_intelligence.tasks.chat.engine import build_paper_context, execute_paper_chat_logic
from research_intelligence.tasks.chat.tasks import execute_paper_chat_task
from research_intelligence.mcp.tools.chat import ask_paper_logic


class PaperChatTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "Secr3tP@ssw0rd!"

        # User A (Researcher on Workspace A)
        self.user_a = User.objects.create_user(
            username="researcher_a",
            email="a@schwarz-intelligence.com",
            password=self.password,
            first_name="Ada",
            last_name="Lovelace"
        )
        self.workspace_a = Workspace.objects.create(
            name="Quantum Algorithms & Materials",
            abstract_acceptance_criteria="Quantum algorithms or superconducting materials",
            abstract_rejection_criteria="Pure classical CMOS papers without quantum relevance",
            full_text_acceptance_criteria="Empirical benchmark or quantum circuit simulation",
            full_text_rejection_criteria="No quantitative data",
            llm_provider="google",
            screening_llm_model="google/gemini-3.7-flash",
            signal_score_code="score = 0.5 * trl_level + 0.5 * novelty_score\nreturn round(score, 2)"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace_a,
            user=self.user_a,
            role="researcher"
        )

        # Pipeline Run & Ingested Paper in Workspace A
        self.run_a = PipelineRun.objects.create(
            workspace=self.workspace_a,
            status="completed"
        )
        self.paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="sha256_quantum_paper_001",
            doi="10.1038/s41586-024-0001-x",
            arxiv_id="2405.00001",
            title="Scalable Quantum Circuit Compilation on 128-Qubit Processor",
            authors="A. Lovelace, C. Babbage",
            abstract="We present a scalable compiler for 128-qubit quantum architectures with sub-microsecond latency.",
            source_database="arxiv",
            screening_status="full_text_passed",
            screening_reasoning="Demonstrates empirical 128-qubit compilation meeting full-text criteria.",
            signal_score=8.5,
            signal_score_details={"trl_level": 7.0, "novelty_score": 10.0}
        )

        # Create OCR Markdown file in storage
        md_content = "# Scalable Quantum Circuit Compilation\n\n## Results\nWe achieved 99.4% gate fidelity and 0.45us compilation latency."
        self.md_path = f"workspaces/{self.workspace_a.id}/runs/{self.run_a.id}/documents/{self.paper_a.hash_id}/layout.md"
        default_storage.save(self.md_path, ContentFile(md_content.encode('utf-8')))
        self.paper_a.converted_md_path = self.md_path
        self.paper_a.save()

        # Add Extractions
        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Qubit Benchmark Metrics",
            response_schema={"type": "object", "properties": {"qubits": {"type": "integer"}}}
        )
        self.extraction = Extraction.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a,
            extraction_definition=self.ext_def,
            category="performance_metric",
            fields_data={"qubit_count": 128, "gate_fidelity": "99.4%", "confidence": 0.95},
            validation_status="pass",
            is_hitl_validated=True
        )

        # Add Metrics
        PaperMetric.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a,
            pipeline_run=self.run_a,
            signal_score=8.5,
            metrics_data={"trl_level": 7.0, "qubit_fidelity_percentile": 92.5}
        )

        # User B (Member of separate Workspace B)
        self.user_b = User.objects.create_user(
            username="researcher_b",
            email="b@schwarz-intelligence.com",
            password=self.password
        )
        self.workspace_b = Workspace.objects.create(
            name="Agritech & Vertical Farming",
            abstract_acceptance_criteria="Hydroponics",
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace_b,
            user=self.user_b,
            role="researcher"
        )

    def tearDown(self):
        if self.paper_a.converted_md_path and default_storage.exists(self.paper_a.converted_md_path):
            default_storage.delete(self.paper_a.converted_md_path)

    def test_build_paper_context_full_data(self):
        """Verifies that full OCR markdown, screening rationale, extractions, and signal score are gathered when all data is present."""
        context_text, pdf_bytes, mime_type = build_paper_context(self.paper_a)
        
        self.assertIn("Scalable Quantum Circuit Compilation", context_text)
        self.assertIn("Authors: A. Lovelace, C. Babbage", context_text)
        self.assertIn("DOI: 10.1038/s41586-024-0001-x", context_text)
        self.assertIn("arXiv ID: 2405.00001", context_text)
        self.assertIn("99.4% gate fidelity", context_text)
        self.assertIn("128-qubit", context_text)
        self.assertIn("Demonstrates empirical 128-qubit compilation", context_text)
        self.assertIn("Qubit Benchmark Metrics", context_text)
        self.assertIn("Composite Signal Score: 8.5", context_text)
        self.assertIn("score = 0.5 * trl_level", context_text)
        self.assertIsNone(pdf_bytes)

    def test_build_paper_context_minimal_missing_data(self):
        """Verifies that when data is missing (no OCR, no PDF, no extractions, no metrics, no criteria), empty sections are completely omitted."""
        ws_empty = Workspace.objects.create(name="Bare Workspace")
        paper_minimal = Paper.objects.create(
            workspace=ws_empty,
            pipeline_run=self.run_a,
            hash_id="sha256_minimal_002",
            title="Minimalist Research Paper",
            abstract="Short abstract about minimalist theory."
        )

        context_text, pdf_bytes, mime_type = build_paper_context(paper_minimal)

        self.assertIn("Title: Minimalist Research Paper", context_text)
        self.assertIn("Short abstract about minimalist theory.", context_text)
        self.assertIsNone(pdf_bytes)
        self.assertIsNone(mime_type)

        # Confirm omitted sections (no noise or empty placeholder headers)
        self.assertNotIn("Authors:", context_text)
        self.assertNotIn("DOI:", context_text)
        self.assertNotIn("arXiv ID:", context_text)
        self.assertNotIn("Full Document Text", context_text)
        self.assertNotIn("SLR Screening Evaluation", context_text)
        self.assertNotIn("Extracted Research Parameters", context_text)
        self.assertNotIn("Computed Quality & Signal Metrics", context_text)
        self.assertNotIn("None recorded", context_text)
        self.assertNotIn("N/A", context_text)

    def test_build_paper_context_multimodal_pdf(self):
        """Verifies multimodal PDF binary loading when layout markdown is not available."""
        pdf_storage_path = f"workspaces/{self.workspace_a.id}/runs/{self.run_a.id}/documents/raw_pdf_003/original.pdf"
        dummy_pdf_content = b"%PDF-1.4 Mock binary content for multimodal Gemini testing"
        default_storage.save(pdf_storage_path, ContentFile(dummy_pdf_content))

        paper_pdf = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="sha256_raw_pdf_003",
            title="Multimodal PDF Paper",
            abstract="Testing multimodal fallback.",
            original_pdf_path=pdf_storage_path
        )

        try:
            context_text, pdf_bytes, mime_type = build_paper_context(paper_pdf)
            self.assertIn("Multimodal PDF Paper", context_text)
            self.assertIn("Full Document Binary: Attached as native multimodal PDF.", context_text)
            self.assertEqual(pdf_bytes, dummy_pdf_content)
            self.assertEqual(mime_type, "application/pdf")
        finally:
            if default_storage.exists(pdf_storage_path):
                default_storage.delete(pdf_storage_path)

    @patch("research_intelligence.tasks.chat.engine.get_llm_provider")
    def test_async_chat_and_polling_flow(self, mock_get_llm_provider):
        """Test full async Celery submission (202 Accepted) and message polling (200 OK)."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "The paper achieves 99.4% two-qubit gate fidelity with sub-microsecond compilation time.",
            {"prompt_tokens": 1200, "candidates_tokens": 65, "total_tokens": 1265}
        )
        mock_get_llm_provider.return_value = mock_provider

        # 1. Login User A
        login_resp = self.client.post('/api/auth/login/', {
            'username': 'researcher_a',
            'password': self.password
        }, format='json')
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)
        access_token = login_resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        # 2. Submit Question via POST /api/chat/
        chat_resp = self.client.post('/api/chat/', {
            'workspace_id': str(self.workspace_a.id),
            'paper_id': str(self.paper_a.id),
            'question': 'What gate fidelity did this compilation architecture achieve?'
        }, format='json')

        self.assertEqual(chat_resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('message_id', chat_resp.data)
        self.assertIn('session_id', chat_resp.data)
        self.assertEqual(chat_resp.data['status'], 'pending')

        message_id = str(chat_resp.data['message_id'])
        session_id = str(chat_resp.data['session_id'])

        # 3. Poll Completed Message State (eager Celery mode executes during request)
        poll_resp = self.client.get(f'/api/chat/messages/{message_id}/')
        self.assertEqual(poll_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(poll_resp.data['status'], 'completed')
        self.assertIn("99.4% two-qubit gate fidelity", poll_resp.data['message'])
        self.assertEqual(poll_resp.data['tokens_in'], 1200)

        # 4. Verify Workspace Token Accounting was updated
        self.workspace_a.refresh_from_db()
        self.assertGreater(self.workspace_a.tokens_consumed_this_month, 0)

    @patch("research_intelligence.tasks.chat.engine.get_llm_provider")
    def test_sync_chat_submission(self, mock_get_llm_provider):
        """Test synchronous chat execution with sync=True returning 200 OK immediately."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "The paper has a signal score of 8.5 because TRL is 7.0 and novelty is 10.0.",
            {"prompt_tokens": 850, "candidates_tokens": 40, "total_tokens": 890}
        )
        mock_get_llm_provider.return_value = mock_provider

        login_resp = self.client.post('/api/auth/login/', {
            'username': 'researcher_a',
            'password': self.password
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_resp.data["access"]}')

        res = self.client.post('/api/chat/', {
            'workspace_id': str(self.workspace_a.id),
            'paper_id': str(self.paper_a.id),
            'question': 'Why was this paper given a signal score of 8.5?',
            'sync': True
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'completed')
        self.assertIn("signal score of 8.5", res.data['message'])

    @patch("research_intelligence.tasks.chat.engine.get_llm_provider")
    def test_multi_turn_session_continuation(self, mock_get_llm_provider):
        """Verify that conversation history is preserved across consecutive turns."""
        mock_provider = MagicMock()
        mock_provider.generate.side_effect = [
            ("Turn 1: Yes, it compiles for 128 qubits.", {"prompt_tokens": 500, "candidates_tokens": 20}),
            ("Turn 2: The compilation latency is 0.45 microseconds.", {"prompt_tokens": 600, "candidates_tokens": 25})
        ]
        mock_get_llm_provider.return_value = mock_provider

        login_resp = self.client.post('/api/auth/login/', {
            'username': 'researcher_a',
            'password': self.password
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_resp.data["access"]}')

        # Turn 1
        res1 = self.client.post('/api/chat/', {
            'paper_id': str(self.paper_a.id),
            'question': 'Does this work on 128 qubits?',
            'sync': True
        }, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        session_id = str(res1.data['session'])

        # Turn 2 in same session
        res2 = self.client.post('/api/chat/', {
            'paper_id': str(self.paper_a.id),
            'session_id': session_id,
            'question': 'And what is the exact compilation latency?',
            'sync': True
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(str(res2.data['session']), session_id)

        # Retrieve session message list
        sess_resp = self.client.get(f'/api/chat/sessions/{session_id}/')
        self.assertEqual(sess_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(sess_resp.data['messages']), 2)

    def test_chat_tenant_isolation(self):
        """User B cannot access or chat with papers belonging to Workspace A."""
        login_resp = self.client.post('/api/auth/login/', {
            'username': 'researcher_b',
            'password': self.password
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_resp.data["access"]}')

        # User B attempts to chat with Workspace A paper
        res = self.client.post('/api/chat/', {
            'workspace_id': str(self.workspace_a.id),
            'paper_id': str(self.paper_a.id),
            'question': 'Tell me about quantum compiler secrets'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # User B checks sessions list -> gets 0
        sessions_res = self.client.get('/api/chat/sessions/')
        self.assertEqual(sessions_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(sessions_res.data), 0)

    @patch("research_intelligence.tasks.chat.engine.get_llm_provider")
    def test_fastmcp_ask_paper_tool(self, mock_get_llm_provider):
        """Test FastMCP ask_paper tool integration."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "FastMCP answer: 99.4% fidelity confirmed.",
            {"prompt_tokens": 900, "candidates_tokens": 30}
        )
        mock_get_llm_provider.return_value = mock_provider

        mcp_res = ask_paper_logic(
            user=self.user_a,
            workspace_id=str(self.workspace_a.id),
            paper_id=str(self.paper_a.id),
            question="What is the gate fidelity?"
        )
        parsed = json.loads(mcp_res)
        self.assertEqual(parsed['status'], 'completed')
        self.assertIn("99.4% fidelity confirmed", parsed['answer'])
        self.assertEqual(parsed['paper_title'], self.paper_a.title)
        self.assertIn('visual_citations', parsed)
        self.assertIn('hallucination_guard', parsed)

    def test_fact_checking_verifier_deterministic(self):
        """Tests that the hallucination guard verifies authentic quotes and flags ungrounded claims."""
        from research_intelligence.tasks.chat.verifier import verify_citations_against_source

        source_doc = "The scalable compiler demonstrates 99.4% gate fidelity across 128 physical qubits with 450ns latency."

        # Case 1: Grounded citation
        grounded_citations = [
            {"page": 2, "label": "Figure 2b", "quote": "99.4% gate fidelity across 128 physical qubits"}
        ]
        verified_cits, guard = verify_citations_against_source(source_doc, grounded_citations)
        self.assertTrue(verified_cits[0]["verified_in_source"])
        self.assertEqual(guard["grounding_score"], 1.0)
        self.assertTrue(guard["verified"])
        self.assertEqual(guard["status"], "PASS")

        # Case 2: Hallucinated / Fabricated claim
        hallucinated_citations = [
            {"page": 5, "label": "Table 1", "quote": "Achieved room-temperature superconductor at 300 Kelvin"}
        ]
        verified_cits_h, guard_h = verify_citations_against_source(source_doc, hallucinated_citations)
        self.assertFalse(verified_cits_h[0]["verified_in_source"])
        self.assertEqual(guard_h["grounding_score"], 0.0)
        self.assertFalse(guard_h["verified"])
        self.assertEqual(guard_h["status"], "WARNING_UNVERIFIED_CLAIMS")

    @patch("research_intelligence.tasks.chat.engine.get_llm_provider")
    def test_visual_citations_and_deep_thinking_in_chat(self, mock_get_llm_provider):
        """Tests that deep_thinking flag is accepted and visual citations [Page X, Fig Y] are parsed and verified."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "The architecture achieves high fidelity [Page 2, Figure 2b, quote: \"99.4% gate fidelity\"] on the benchmark.",
            {"prompt_tokens": 1500, "candidates_tokens": 120}
        )
        mock_get_llm_provider.return_value = mock_provider

        login_resp = self.client.post('/api/auth/login/', {
            'username': 'researcher_a',
            'password': self.password
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_resp.data["access"]}')

        res = self.client.post('/api/chat/', {
            'paper_id': str(self.paper_a.id),
            'question': 'Derive the exact gate fidelity equation from Figure 2b',
            'deep_thinking': True,
            'sync': True
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['deep_thinking'])
        self.assertGreater(len(res.data['visual_citations']), 0)
        
        vis_cit = res.data['visual_citations'][0]
        self.assertEqual(vis_cit['page'], 2)
        self.assertEqual(vis_cit['label'], 'Figure 2b')
        self.assertTrue(vis_cit['verified_in_source'])
        
        # Hallucination guard verified
        self.assertTrue(res.data['hallucination_guard']['verified'])
        self.assertEqual(res.data['hallucination_guard']['status'], 'PASS')

    @patch("research_intelligence.tasks.chat.engine.get_llm_provider")
    def test_hierarchical_session_summarization(self, mock_get_llm_provider):
        """Tests that long multi-turn sessions compress older turns into session.summary."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "Response to turn.",
            {"prompt_tokens": 500, "candidates_tokens": 50}
        )
        mock_get_llm_provider.return_value = mock_provider

        login_resp = self.client.post('/api/auth/login/', {
            'username': 'researcher_a',
            'password': self.password
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_resp.data["access"]}')

        # Create session and simulate 5 sequential turns
        session = PaperChatSession.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a,
            user=self.user_a,
            title="Multi-turn Deep Exploration"
        )

        for i in range(1, 6):
            res = self.client.post('/api/chat/', {
                'paper_id': str(self.paper_a.id),
                'session_id': str(session.id),
                'question': f'Scientific question turn {i}',
                'sync': True
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        session.refresh_from_db()
        self.assertGreater(len(session.summary), 0)
        self.assertIn("Scientific question turn", session.summary)
        self.assertEqual(session.messages.count(), 5)

    @patch("research_intelligence.tasks.chat.engine.get_llm_provider")
    def test_oop_paper_context_builder_and_engine(self, mock_get_llm_provider):
        """Tests explicit object-oriented initialization and execution of PaperChatEngine."""
        from research_intelligence.tasks.chat import (
            PaperChatEngine,
            PaperContextBuilder,
            HierarchicalSessionSummarizer,
            VisualCitationExtractor,
            CitationFactChecker,
        )

        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "OOP Engine answer: Gate fidelity confirmed [Page 1, Table 1, quote: \"99.4% gate fidelity\"].",
            {"prompt_tokens": 800, "candidates_tokens": 40}
        )
        mock_get_llm_provider.return_value = mock_provider

        builder = PaperContextBuilder()
        summarizer = HierarchicalSessionSummarizer()
        extractor = VisualCitationExtractor()
        fact_checker = CitationFactChecker()

        engine = PaperChatEngine(
            context_builder=builder,
            summarizer=summarizer,
            citation_extractor=extractor,
            fact_checker=fact_checker
        )

        session = PaperChatSession.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a,
            user=self.user_a,
            title="OOP Engine Test"
        )
        msg = PaperChatMessage.objects.create(
            session=session,
            sender='user',
            status='pending',
            question="What is the fidelity in Table 1?",
            deep_thinking=True
        )

        result = engine.execute(msg)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['deep_thinking'])
        self.assertEqual(len(result['visual_citations']), 1)
        self.assertEqual(result['visual_citations'][0]['label'], 'Table 1')
        self.assertTrue(result['visual_citations'][0]['verified_in_source'])
        self.assertTrue(result['hallucination_guard']['verified'])

    def test_visual_citation_extractor_structured_json(self):
        """Tests parsing structured ```json:citations blocks with bounding boxes."""
        from research_intelligence.tasks.chat import VisualCitationExtractor

        raw_llm_response = """
Here is the analysis of the quantum architecture.

```json:citations
[
  {
    "page": 7,
    "label": "Figure 4b: Energy Density vs Cycles",
    "box_2d": [320, 150, 680, 890],
    "quote": "Energy density reaches 520 Wh/kg"
  }
]
```
"""
        extractor = VisualCitationExtractor()
        cleaned_text, citations = extractor.extract(raw_llm_response)

        self.assertIn("Here is the analysis of the quantum architecture.", cleaned_text)
        self.assertNotIn("```json:citations", cleaned_text)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]['page'], 7)
        self.assertEqual(citations[0]['label'], "Figure 4b: Energy Density vs Cycles")
        self.assertEqual(citations[0]['box_2d'], [320, 150, 680, 890])
        self.assertEqual(citations[0]['quote'], "Energy density reaches 520 Wh/kg")

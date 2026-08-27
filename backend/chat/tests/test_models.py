from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from research_intelligence.models import Workspace, Paper, PipelineRun
from chat.models import PaperChatSession, PaperChatMessage


class ChatModelsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="chat_tester", email="tester@example.com", password="password")
        self.workspace = Workspace.objects.create(name="Quantum Workspace")
        self.run = PipelineRun.objects.create(workspace=self.workspace)
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_quantum_paper_001",
            title="Quantum Fault Tolerance with Neutral Atoms",
            doi="10.1038/s41586-024-0099-y"
        )

    def test_paper_chat_session_creation_and_cost_recording(self):
        session = PaperChatSession.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            user=self.user,
            title="Discussion on Neutral Atom Gates"
        )
        self.assertEqual(session.total_tokens, 0)
        self.assertEqual(session.total_usd_cost, Decimal('0.00000'))

        # Record message cost on session
        session.record_message_cost(tokens_in=1000, tokens_out=150, cost=Decimal('0.00250'))
        session.refresh_from_db()
        self.assertEqual(session.total_tokens_in, 1000)
        self.assertEqual(session.total_tokens_out, 150)
        self.assertEqual(session.total_tokens, 1150)
        self.assertEqual(session.total_usd_cost, Decimal('0.00250'))

        # Second turn increment
        session.record_message_cost(tokens_in=1200, tokens_out=200, cost=Decimal('0.00300'))
        session.refresh_from_db()
        self.assertEqual(session.total_tokens, 2550)
        self.assertEqual(session.total_usd_cost, Decimal('0.00550'))

    def test_paper_chat_message_creation_and_fields(self):
        session = PaperChatSession.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            user=self.user
        )
        msg = PaperChatMessage.objects.create(
            session=session,
            sender='user',
            question="What is the two-qubit gate error rate?",
            status='pending',
            deep_thinking=True,
            tokens_in=800,
            tokens_out=100,
            total_tokens=900,
            usd_cost=Decimal('0.00150'),
            llm_model='google/gemini-3.7-flash'
        )
        self.assertEqual(msg.session, session)
        self.assertEqual(msg.sender, 'user')
        self.assertTrue(msg.deep_thinking)
        self.assertEqual(msg.total_tokens, 900)
        self.assertEqual(msg.llm_model, 'google/gemini-3.7-flash')
        self.assertIn("user", str(msg))

    def test_cascading_deletion_on_paper_and_workspace(self):
        session = PaperChatSession.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            user=self.user
        )
        PaperChatMessage.objects.create(session=session, sender='user', question="Q?")
        self.assertEqual(PaperChatSession.objects.count(), 1)
        self.assertEqual(PaperChatMessage.objects.count(), 1)

        # Deleting paper should cascade delete sessions and messages
        self.paper.delete()
        self.assertEqual(PaperChatSession.objects.count(), 0)
        self.assertEqual(PaperChatMessage.objects.count(), 0)

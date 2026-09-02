from decimal import Decimal
from django.test import TestCase
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User

from research_intelligence.models import Workspace, Paper, PipelineRun
from chat.models import PaperChatSession, PaperChatMessage
from chat.admin import PaperChatSessionAdmin, PaperChatMessageAdmin, PaperChatMessageInline


class DummyAdminSite(AdminSite):
    pass


class ChatModelsAndAdminTestCase(TestCase):
    """
    Consolidated test suite for PaperChat models and Django Admin integration:
    1. Session token accumulation and USD cost tracking.
    2. Message fields, deep thinking flags, and cascade deletion.
    3. Admin list display columns, format_html badges, and inlines.
    """

    def setUp(self):
        self.site = DummyAdminSite()
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
        self.session = PaperChatSession.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            user=self.user,
            title="Discussion on Neutral Atom Gates",
            total_tokens=1500,
            total_usd_cost=Decimal('0.00350')
        )
        self.message = PaperChatMessage.objects.create(
            session=self.session,
            sender='user',
            status='completed',
            llm_model='google/gemini-3.8-flash',
            tokens_in=1000,
            tokens_out=500,
            total_tokens=1500,
            usd_cost=Decimal('0.00350'),
            question="Can we format tokens in admin?",
            message="Yes, custom format_html columns display token and cost metrics."
        )

    def test_paper_chat_session_creation_and_cost_recording(self):
        session = PaperChatSession.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            user=self.user,
            title="New Session"
        )
        self.assertEqual(session.total_tokens, 0)
        self.assertEqual(session.total_usd_cost, Decimal('0.00000'))

        session.record_message_cost(tokens_in=1000, tokens_out=150, cost=Decimal('0.00250'))
        session.refresh_from_db()
        self.assertEqual(session.total_tokens_in, 1000)
        self.assertEqual(session.total_tokens_out, 150)
        self.assertEqual(session.total_tokens, 1150)
        self.assertEqual(session.total_usd_cost, Decimal('0.00250'))

        session.record_message_cost(tokens_in=1200, tokens_out=200, cost=Decimal('0.00300'))
        session.refresh_from_db()
        self.assertEqual(session.total_tokens, 2550)
        self.assertEqual(session.total_usd_cost, Decimal('0.00550'))

    def test_paper_chat_message_creation_and_fields(self):
        msg = PaperChatMessage.objects.create(
            session=self.session,
            sender='user',
            question="What is the two-qubit gate error rate?",
            status='pending',
            deep_thinking=True,
            tokens_in=800,
            tokens_out=100,
            total_tokens=900,
            usd_cost=Decimal('0.00150'),
            llm_model='google/gemini-3.8-flash'
        )
        self.assertEqual(msg.session, self.session)
        self.assertEqual(msg.sender, 'user')
        self.assertTrue(msg.deep_thinking)
        self.assertEqual(msg.total_tokens, 900)
        self.assertEqual(msg.llm_model, 'google/gemini-3.8-flash')
        self.assertIn("user", str(msg))

    def test_cascading_deletion_on_paper_and_workspace(self):
        self.assertEqual(PaperChatSession.objects.count(), 1)
        self.assertEqual(PaperChatMessage.objects.count(), 1)

        self.paper.delete()
        self.assertEqual(PaperChatSession.objects.count(), 0)
        self.assertEqual(PaperChatMessage.objects.count(), 0)

    def test_session_admin_displays(self):
        admin_obj = PaperChatSessionAdmin(PaperChatSession, self.site)
        tokens_html = admin_obj.session_tokens_display(self.session)
        self.assertIn("1500", tokens_html)

        cost_html = admin_obj.session_cost_display(self.session)
        self.assertIn("$0.00350", cost_html)

        messages_count = admin_obj.messages_count(self.session)
        self.assertEqual(messages_count, 1)

    def test_message_admin_displays(self):
        admin_obj = PaperChatMessageAdmin(PaperChatMessage, self.site)
        tokens_str = admin_obj.tokens_total(self.message)
        self.assertIn("In: 1000", tokens_str)
        self.assertIn("Out: 500", tokens_str)
        self.assertIn("Tot: 1500", tokens_str)

        cost_str = admin_obj.usd_cost_display(self.message)
        self.assertIn("$0.00350", cost_str)

        badge_html = admin_obj.status_badge(self.message)
        self.assertIn("COMPLETED", badge_html)

        id_str = admin_obj.id_snippet(self.message)
        self.assertIn("...", id_str)

    def test_message_inline_snippets(self):
        inline = PaperChatMessageInline(PaperChatMessage, self.site)
        q_snip = inline.question_snippet(self.message)
        self.assertEqual(q_snip, self.message.question)

        a_snip = inline.message_snippet(self.message)
        self.assertIn("custom format_html columns", a_snip)

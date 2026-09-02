import uuid
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db.models import Sum

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    ComponentRun,
    LLMUsageRecord,
)

User = get_user_model()


class LLMUsageRecordPersistenceTestCase(TestCase):
    """
    Unit tests verifying that LLMUsageRecord acts as a persistent global ledger:
    1. Hook integration: Workspace.record_token_usage creates an immutable LLMUsageRecord.
    2. Deletion resilience: Deleting a Workspace retains LLMUsageRecord with snapshot metadata intact.
    3. Global aggregation: Querying LLMUsageRecord aggregates platform-wide tokens and costs accurately.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="ledger_tester", email="ledger@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="Persistent Billing Lab",
            screening_llm_model="google/gemini-3.8-flash"
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )

    def test_record_token_usage_hooks_into_llm_usage_record(self):
        """Workspace.record_token_usage automatically generates an LLMUsageRecord with denormalized snapshots."""
        initial_count = LLMUsageRecord.objects.count()

        cost = self.workspace.record_token_usage(
            tokens_in=1000,
            tokens_out=250,
            model_name="google/gemini-3.8-flash",
            operation_type="abstract_screening",
            user=self.user,
            pipeline_run_id=str(self.pipeline_run.id),
            component_run_id="comp-test-123"
        )

        self.assertEqual(LLMUsageRecord.objects.count(), initial_count + 1)
        record = LLMUsageRecord.objects.latest('timestamp')

        self.assertEqual(record.workspace_id, self.workspace.id)
        self.assertEqual(record.workspace_name_snapshot, "Persistent Billing Lab")
        self.assertEqual(record.workspace_id_snapshot, str(self.workspace.id))
        self.assertEqual(record.user_username_snapshot, "ledger_tester")
        self.assertEqual(record.operation_type, "abstract_screening")
        self.assertEqual(record.tokens_in, 1000)
        self.assertEqual(record.tokens_out, 250)
        self.assertEqual(record.total_tokens, 1250)
        self.assertGreater(record.usd_cost, Decimal('0.0000'))
        self.assertEqual(record.pipeline_run_id, str(self.pipeline_run.id))
        self.assertEqual(record.component_run_id, "comp-test-123")

    def test_llm_usage_record_survives_workspace_deletion(self):
        """When a Workspace is deleted, LLMUsageRecords are preserved with workspace=None and historical snapshots intact."""
        ws_id_str = str(self.workspace.id)
        ws_name_str = self.workspace.name

        self.workspace.record_token_usage(
            tokens_in=5000,
            tokens_out=1500,
            model_name="google/gemini-3.8-flash",
            operation_type="full_text_screening",
            user=self.user,
            pipeline_run_id=str(self.pipeline_run.id)
        )

        record_id = LLMUsageRecord.objects.latest('timestamp').id

        # Delete the workspace
        self.workspace.delete()

        # Verify the record still exists in the database!
        preserved_record = LLMUsageRecord.objects.get(id=record_id)
        self.assertIsNone(preserved_record.workspace)
        self.assertEqual(preserved_record.workspace_name_snapshot, ws_name_str)
        self.assertEqual(preserved_record.workspace_id_snapshot, ws_id_str)
        self.assertEqual(preserved_record.total_tokens, 6500)
        self.assertEqual(preserved_record.operation_type, "full_text_screening")

    def test_global_platform_aggregation_across_multiple_workspaces(self):
        """Verify that platform-wide totals aggregate accurately even when some workspaces are deleted."""
        ws2 = Workspace.objects.create(name="Ephemeral Lab", screening_llm_model="google/gemini-3.8-flash")

        # Record usage on WS1
        self.workspace.record_token_usage(1000, 200, operation_type="abstract_screening")
        # Record usage on WS2
        ws2.record_token_usage(2000, 400, operation_type="chat")

        # Delete WS2
        ws2.delete()

        # Global aggregate
        totals = LLMUsageRecord.objects.aggregate(
            total_tok=Sum('total_tokens'),
            total_cost=Sum('usd_cost')
        )

        self.assertEqual(totals['total_tok'], 3600)  # 1200 + 2400
        self.assertGreater(totals['total_cost'], Decimal('0.0000'))

from django.test import TestCase
from api.serializers.pipeline_runs import TriggerStepSerializer, StartPipelineRunSerializer
from api.serializers.agents import StartResearchAgentSerializer
from api.serializers.workspaces import ScraperSerializer
from api.pagination import StandardResultsSetPagination
from research_intelligence.models import Scraper, Workspace


class SerializerLimitTests(TestCase):
    def test_trigger_step_serializer_limit(self):
        # Default limit should be 2000
        serializer = TriggerStepSerializer(data={"step_type": "search"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["limit"], 2000)

        # Max limit should be 10000
        serializer = TriggerStepSerializer(data={"step_type": "search", "limit": 10000})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["limit"], 10000)

        # Limit > 10000 should be rejected
        serializer = TriggerStepSerializer(data={"step_type": "search", "limit": 10001})
        self.assertFalse(serializer.is_valid())
        self.assertIn("limit", serializer.errors)

        # Limit < 1 should be rejected
        serializer = TriggerStepSerializer(data={"step_type": "search", "limit": 0})
        self.assertFalse(serializer.is_valid())
        self.assertIn("limit", serializer.errors)

    def test_start_pipeline_run_serializer_limit(self):
        import uuid
        ws_id = str(uuid.uuid4())
        # Limit <= 10000 should be valid
        serializer = StartPipelineRunSerializer(data={"workspace_id": ws_id, "limit": 10000})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["limit"], 10000)

        # Limit > 10000 should be rejected
        serializer = StartPipelineRunSerializer(data={"workspace_id": ws_id, "limit": 10001})
        self.assertFalse(serializer.is_valid())
        self.assertIn("limit", serializer.errors)

        # Limit < 1 should be rejected
        serializer = StartPipelineRunSerializer(data={"workspace_id": ws_id, "limit": 0})
        self.assertFalse(serializer.is_valid())
        self.assertIn("limit", serializer.errors)

    def test_start_research_agent_serializer_limit(self):
        import uuid
        ws_id = str(uuid.uuid4())
        # Default limit should be 2000
        serializer = StartResearchAgentSerializer(data={"workspace_id": ws_id})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["limit"], 2000)

        # Limit up to 10000 should be valid
        serializer = StartResearchAgentSerializer(data={"workspace_id": ws_id, "limit": 10000})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["limit"], 10000)

        # Limit > 10000 should be rejected
        serializer = StartResearchAgentSerializer(data={"workspace_id": ws_id, "limit": 10001})
        self.assertFalse(serializer.is_valid())
        self.assertIn("limit", serializer.errors)

        # Limit < 1 should be rejected
        serializer = StartResearchAgentSerializer(data={"workspace_id": ws_id, "limit": 0})
        self.assertFalse(serializer.is_valid())
        self.assertIn("limit", serializer.errors)

    def test_scraper_serializer_limit(self):
        workspace = Workspace.objects.create(name="Test WS")

        # Default limit should be 2000
        serializer = ScraperSerializer(data={
            "workspace": workspace.id,
            "provider": "arxiv",
            "search_query": "machine learning"
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data.get("limit", 2000), 2000)

        # Limit up to 10000 should be valid
        serializer = ScraperSerializer(data={
            "workspace": workspace.id,
            "provider": "arxiv",
            "search_query": "machine learning",
            "limit": 10000
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["limit"], 10000)

        # Limit > 10000 should be rejected
        serializer = ScraperSerializer(data={
            "workspace": workspace.id,
            "provider": "arxiv",
            "search_query": "machine learning",
            "limit": 10001
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("limit", serializer.errors)

        # Limit < 1 should be rejected
        serializer = ScraperSerializer(data={
            "workspace": workspace.id,
            "provider": "arxiv",
            "search_query": "machine learning",
            "limit": 0
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("limit", serializer.errors)

    def test_scraper_model_default_limit(self):
        workspace = Workspace.objects.create(name="Test WS 2")
        scraper = Scraper.objects.create(
            workspace=workspace,
            provider="arxiv",
            search_query="test query"
        )
        self.assertEqual(scraper.limit, 2000)

    def test_pagination_max_page_size(self):
        pagination = StandardResultsSetPagination()
        self.assertEqual(pagination.max_page_size, 10000)

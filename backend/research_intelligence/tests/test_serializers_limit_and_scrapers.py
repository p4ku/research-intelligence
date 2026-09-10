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

    def test_search_node_respects_custom_scraper_limit_when_no_global_limit(self):
        from unittest.mock import patch
        from research_intelligence.models import PipelineRun, ComponentRun
        from research_intelligence.tasks.step_1_search.node import SearchNode

        workspace = Workspace.objects.create(name="Scraper Limit WS")
        s1 = Scraper.objects.create(workspace=workspace, provider="arxiv", search_query="test 1", limit=1500, is_active=True)
        s2 = Scraper.objects.create(workspace=workspace, provider="openalex", search_query="test 2", limit=2500, is_active=True)

        pipeline_run = PipelineRun.objects.create(workspace=workspace, configuration_override={})
        node = SearchNode()
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="search",
            component_name="workspace_search",
            input_params=node.get_input_params(pipeline_run, workspace, {}, limit=None)
        )

        with patch.object(node, 'dispatch_multiple_celery_tasks') as mock_dispatch:
            mock_dispatch.return_value = {"status": "ok"}
            node.execute(pipeline_run, comp_run, limit=None)

            self.assertTrue(mock_dispatch.called)
            dispatched_runs = mock_dispatch.call_args[0][1]
            dispatched_limit = mock_dispatch.call_args[1].get("limit")

            # Global dispatch limit must be None so execute_scraper_run_job uses scraper.limit
            self.assertIsNone(dispatched_limit)

            # Check individual component runs have their respective limits stored
            self.assertEqual(len(dispatched_runs), 2)
            self.assertEqual(dispatched_runs[0].input_params["limit"], 1500)
            self.assertEqual(dispatched_runs[1].input_params["limit"], 2500)

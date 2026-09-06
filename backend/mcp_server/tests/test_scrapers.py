from unittest.mock import patch, MagicMock
from research_intelligence.models import Scraper, Paper, PaperMetric, PipelineRun
from mcp_server.tools import (
    create_scraper_logic,
    list_scrapers_logic,
    get_scraper_logic,
    update_scraper_logic,
    delete_scraper_logic,
    preview_search_query_logic,
    list_papers_logic,
)
from .base import BaseMCPTestCase


class MCPScrapersTestCase(BaseMCPTestCase):
    def test_scraper_crud(self):
        res = self.parse_res(create_scraper_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            provider="arxiv",
            search_query="cat:cs.AI AND quantum",
            limit=25
        ))
        self.assertTrue(res["success"])
        s_id = res["scraper_id"]

        scrapers_res = self.parse_res(list_scrapers_logic(self.admin, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(scrapers_res), 1)
        self.assertEqual(scrapers_res[0]["search_query"], "cat:cs.AI AND quantum")

        up_res = self.parse_res(update_scraper_logic(self.admin, scraper_id=s_id, limit=50))
        self.assertTrue(up_res["success"])
        self.assertEqual(up_res["limit"], 50)

        del_res = self.parse_res(delete_scraper_logic(self.admin, scraper_id=s_id))
        self.assertTrue(del_res["success"])
        self.assertEqual(Scraper.objects.filter(workspace=self.workspace).count(), 0)

    @patch("research_intelligence.scrapers.factory.get_scraper_provider")
    def test_preview_search_query_success_and_validation(self, mock_get_scraper):
        mock_instance = MagicMock()
        mock_instance.search.return_value = [
            {"title": "Preview Paper 1", "abstract": "Test abstract 1", "authors": ["Alice"]}
        ]
        mock_get_scraper.return_value = mock_instance

        res = self.parse_res(preview_search_query_logic(self.admin, provider="arxiv", search_query="all:quantum", limit=5))
        self.assertTrue(res["success"])
        self.assertEqual(res["total_results"], 1)

        # Test with date range parameters
        res_date = self.parse_res(preview_search_query_logic(
            self.admin,
            provider="arxiv",
            search_query="all:quantum",
            limit=5,
            start_date="2026-09-01",
            end_date="2026-09-05",
            n_last_days=14
        ))
        self.assertTrue(res_date["success"])
        self.assertEqual(res_date["start_date"], "2026-09-01")
        self.assertEqual(res_date["end_date"], "2026-09-05")
        self.assertEqual(res_date["n_last_days"], 14)
        mock_instance.search.assert_called_with(
            "all:quantum",
            max_results=5,
            start_date="2026-09-01",
            end_date="2026-09-05",
            n_last_days=14
        )


    def test_list_papers_and_optional_params(self):
        run = PipelineRun.objects.create(workspace=self.workspace)
        p1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_p1",
            title="Listed Paper 1",
            abstract="Abstract 1"
        )
        PaperMetric.objects.create(paper=p1, pipeline_run=run, workspace=self.workspace, screening_status="abstract_passed")
        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_p2",
            title="Listed Paper 2",
            abstract="Abstract 2"
        )
        PaperMetric.objects.create(paper=p2, pipeline_run=run, workspace=self.workspace, screening_status="rejected")

        res = self.parse_res(list_papers_logic(self.admin, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(res), 2)

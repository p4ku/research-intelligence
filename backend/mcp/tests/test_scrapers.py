import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, WorkspaceMember, Scraper, Paper, PipelineRun
from mcp.tools import (
    create_scraper_logic,
    list_scrapers_logic,
    get_scraper_logic,
    update_scraper_logic,
    delete_scraper_logic,
    preview_search_query_logic,
    list_papers_logic,
)

User = get_user_model()


class MCPScrapersTestCase(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(username="scraper_admin", email="admin@schwarz.de", password="password")
        self.workspace = Workspace.objects.create(name="Scraper Test WS")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.admin_user, role="admin")

    def test_scraper_crud(self):
        res_str = create_scraper_logic(
            self.admin_user,
            workspace_id=str(self.workspace.id),
            provider="arxiv",
            search_query="cat:cs.AI AND quantum",
            limit=25
        )
        res = json.loads(res_str)
        self.assertTrue(res["success"])
        s_id = res["scraper_id"]

        scrapers_res = json.loads(list_scrapers_logic(self.admin_user, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(scrapers_res), 1)
        self.assertEqual(scrapers_res[0]["search_query"], "cat:cs.AI AND quantum")

        up_res = json.loads(update_scraper_logic(self.admin_user, scraper_id=s_id, limit=50))
        self.assertTrue(up_res["success"])
        self.assertEqual(up_res["limit"], 50)

        del_res = json.loads(delete_scraper_logic(self.admin_user, scraper_id=s_id))
        self.assertTrue(del_res["success"])
        self.assertEqual(Scraper.objects.filter(workspace=self.workspace).count(), 0)

    @patch("research_intelligence.scrapers.factory.get_scraper_provider")
    def test_preview_search_query_success_and_validation(self, mock_get_scraper):
        mock_instance = MagicMock()
        mock_instance.search.return_value = [
            {"title": "Preview Paper 1", "abstract": "Test abstract 1", "authors": ["Alice"]}
        ]
        mock_get_scraper.return_value = mock_instance

        res_str = preview_search_query_logic(self.admin_user, provider="arxiv", search_query="all:quantum", limit=5)
        res = json.loads(res_str)
        self.assertTrue(res["success"])
        self.assertEqual(res["total_results"], 1)

    def test_list_papers_and_optional_params(self):
        run = PipelineRun.objects.create(workspace=self.workspace)
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_p1",
            title="Listed Paper 1",
            abstract="Abstract 1",
            screening_status="passed"
        )
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="sha256_p2",
            title="Listed Paper 2",
            abstract="Abstract 2",
            screening_status="rejected"
        )

        res = json.loads(list_papers_logic(self.admin_user, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(res), 2)

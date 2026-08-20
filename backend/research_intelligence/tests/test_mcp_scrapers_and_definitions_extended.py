import json
import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Scraper,
    ExtractionDefinition,
    Paper,
    PipelineRun
)
from research_intelligence.mcp.tools.scrapers import (
    list_scrapers_logic,
    get_scraper_logic,
    create_scraper_logic,
    update_scraper_logic,
    delete_scraper_logic,
    preview_search_query_logic,
    list_papers_logic,
)
from research_intelligence.mcp.tools.extraction_definitions import (
    list_extraction_definitions_logic,
    get_extraction_definition_logic,
    create_extraction_definition_logic,
    update_extraction_definition_logic,
    delete_extraction_definition_logic,
)

User = get_user_model()


class MCPScrapersAndDefinitionsExtendedTestCase(TestCase):
    """
    Extensive test suite for Scraper management, search preview dry-runs,
    Extraction Definitions CRUD, and strict RBAC authorization boundaries.
    """

    def setUp(self):
        self.admin_user = User.objects.create_user(username="mcp_admin", email="admin@corp.com", password="pass")
        self.researcher_user = User.objects.create_user(username="mcp_researcher", email="res@corp.com", password="pass")
        self.outsider_user = User.objects.create_user(username="mcp_outsider", email="out@corp.com", password="pass")

        self.workspace = Workspace.objects.create(name="Quantum Hardware Scouting")
        self.pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="running")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.admin_user, role="admin")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.researcher_user, role="researcher")

    def test_preview_search_query_success_and_validation(self):
        # 1. Invalid provider
        err1 = preview_search_query_logic(self.admin_user, provider="invalid_engine", search_query="quantum")
        self.assertIn("Invalid provider", err1)

        # 2. Empty query
        err2 = preview_search_query_logic(self.admin_user, provider="arxiv", search_query="")
        self.assertIn("search_query is required", err2)

        # 3. Successful dry-run mock
        with patch("research_intelligence.scrapers.factory.get_scraper_provider") as mock_get_scraper:
            mock_inst = MagicMock()
            mock_inst.search.return_value = [
                {"title": "Superconducting Transmon", "arxiv_id": "2401.11111", "authors": "Alice"}
            ]
            mock_get_scraper.return_value = mock_inst

            res_str = preview_search_query_logic(self.admin_user, provider="arxiv", search_query="transmon", limit=5)
            data = json.loads(res_str)
            self.assertTrue(data["success"])
            self.assertEqual(data["total_results"], 1)
            self.assertEqual(data["papers"][0]["title"], "Superconducting Transmon")

    def test_scraper_crud_and_rbac(self):
        # 1. Researcher cannot create scraper (requires admin/manager)
        res_rbac = create_scraper_logic(self.researcher_user, str(self.workspace.id), provider="arxiv", search_query="q")
        self.assertIn("Error", res_rbac)

        # 2. Admin creates scraper
        res_create = create_scraper_logic(self.admin_user, str(self.workspace.id), provider="arxiv", search_query="quantum transmon")
        data = json.loads(res_create)
        self.assertTrue(data["success"])
        scraper_id = data["scraper_id"]

        # 3. Get scraper details
        res_get = get_scraper_logic(self.researcher_user, scraper_id)  # Read is allowed for researcher
        get_data = json.loads(res_get)
        self.assertEqual(get_data["search_query"], "quantum transmon")

        # 4. Update scraper
        res_update = update_scraper_logic(self.admin_user, scraper_id, search_query="quantum fluxonium", limit=100)
        up_data = json.loads(res_update)
        self.assertTrue(up_data["success"])

        # 5. Delete scraper
        res_del = delete_scraper_logic(self.admin_user, scraper_id)
        self.assertIn("Successfully deleted", res_del)
        self.assertFalse(Scraper.objects.filter(id=scraper_id).exists())

    def test_list_papers_logic_filtering(self):
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_list_001",
            title="Qubit Gate Fidelity",
            authors="Bob",
            abstract="Gate fidelity tests.",
            screening_status="accepted"
        )
        res_papers = list_papers_logic(self.researcher_user, str(self.workspace.id))
        papers_data = json.loads(res_papers)
        self.assertEqual(len(papers_data), 1)
        self.assertEqual(papers_data[0]["title"], "Qubit Gate Fidelity")

    def test_extraction_definition_crud_and_validation(self):
        # 1. Reject invalid response_schema
        err_schema = create_extraction_definition_logic(
            self.admin_user,
            workspace_id=str(self.workspace.id),
            name="Broken Schema Def",
            system_prompt="Test",
            user_prompt_template="Test",
            response_schema="{broken json"
        )
        self.assertIn("must be a valid JSON", err_schema)

        # 2. Valid creation
        schema = {"type": "object", "properties": {"qubit_type": {"type": "string"}}}
        res_create = create_extraction_definition_logic(
            self.admin_user,
            workspace_id=str(self.workspace.id),
            name="Qubit Architecture",
            system_prompt="Extract qubit type",
            user_prompt_template="Prompt",
            response_schema=schema,
            exit_metric="qubit_type",
            requires_consensus=True
        )
        create_data = json.loads(res_create)
        self.assertEqual(create_data.get("status"), "success")
        def_id = create_data["definition_id"]

        # 3. Read definition
        res_get = get_extraction_definition_logic(self.researcher_user, def_id)
        get_data = json.loads(res_get)
        self.assertEqual(get_data["name"], "Qubit Architecture")
        self.assertTrue(get_data["requires_consensus"])

        # 4. Update definition
        res_update = update_extraction_definition_logic(
            self.admin_user,
            def_id,
            name="Updated Qubit Architecture",
            requires_consensus=False
        )
        up_data = json.loads(res_update)
        self.assertEqual(up_data.get("status"), "success")

        # 5. Delete definition
        res_del = delete_extraction_definition_logic(self.admin_user, def_id)
        self.assertIn("was successfully deleted", res_del)
        self.assertFalse(ExtractionDefinition.objects.filter(id=def_id).exists())

    def test_unauthorized_outsider_access_denied(self):
        res = list_scrapers_logic(self.outsider_user, str(self.workspace.id))
        self.assertIn("Error", res)

        res_defs = list_extraction_definitions_logic(self.outsider_user, str(self.workspace.id))
        self.assertIn("Error", res_defs)

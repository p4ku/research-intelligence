import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from research_intelligence.models import Workspace, Paper, PipelineRun, PaperMetric, WorkspaceMember
from api.serializers.papers import PaperSerializer
from api.views.papers import PaperViewSet
from research_intelligence.services.scraper_service import list_workspace_papers
from mcp_server.tools.scrapers.search import list_papers_logic

User = get_user_model()


class PaperSourceUrlTestCase(TestCase):
    """
    Test suite verifying canonical source_url resolution across academic providers
    (ArXiv, OpenAlex with DOI, OpenAlex without DOI, Lens.org), DRF API serialization,
    and MCP server tool payloads.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="testresearcher", password="password123")
        self.workspace = Workspace.objects.create(name="Source URL Test Workspace")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")
        self.pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="completed")

    def test_arxiv_paper_source_url(self):
        """Verify arXiv paper resolves to canonical https://arxiv.org/abs/{arxiv_id}."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="arxiv_2303_08774",
            arxiv_id="2303.08774",
            title="GPT-4 Technical Report",
            authors="OpenAI",
            source_database="arxiv"
        )
        self.assertEqual(paper.source_url, "https://arxiv.org/abs/2303.08774")

        # Also verify if arxiv_id has arxiv: prefix
        paper_prefix = Paper.objects.create(
            workspace=self.workspace,
            hash_id="arxiv_prefix_123",
            arxiv_id="arxiv:1706.03762",
            title="Attention Is All You Need",
            authors="Vaswani et al.",
            source_database="arxiv"
        )
        self.assertEqual(paper_prefix.source_url, "https://arxiv.org/abs/1706.03762")

    def test_openalex_paper_with_doi_source_url(self):
        """Verify OpenAlex paper with DOI resolves to https://doi.org/{doi} publisher landing."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="openalex_w123_doi",
            doi="10.1016/j.artint.2020.103328",
            title="Reasoning About Actions",
            authors="John McCarthy",
            source_database="openalex",
            meta={"id": "https://openalex.org/W2963403868"}
        )
        # DOI takes precedence to lead directly to publisher page
        self.assertEqual(paper.source_url, "https://doi.org/10.1016/j.artint.2020.103328")

    def test_openalex_paper_without_doi_id_url(self):
        """Verify OpenAlex paper without DOI falls back to OpenAlex canonical URL from meta['id']."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="openalex_no_doi_1",
            title="Institutional Technical Report",
            authors="Jane Doe",
            source_database="openalex",
            meta={
                "id": "https://openalex.org/W4386266395",
                "open_access": {"is_oa": True}
            }
        )
        self.assertEqual(paper.source_url, "https://openalex.org/W4386266395")

    def test_openalex_paper_without_doi_landing_page_url(self):
        """Verify OpenAlex paper without DOI with primary_location.landing_page_url resolves properly."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="openalex_no_doi_landing",
            title="TU Delft Repository Report",
            authors="Delft Team",
            source_database="openalex",
            meta={
                "primary_location": {
                    "landing_page_url": "https://repository.tudelft.nl/islandora/object/uuid%3A1234"
                }
            }
        )
        self.assertEqual(paper.source_url, "https://repository.tudelft.nl/islandora/object/uuid%3A1234")

    def test_openalex_fallback_work_id_hash(self):
        """Verify OpenAlex paper with W... hash_id generates https://openalex.org/{W_id} if no meta is available."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="W1982736450",
            title="Legacy OpenAlex Paper",
            authors="Author X",
            source_database="openalex"
        )
        self.assertEqual(paper.source_url, "https://openalex.org/W1982736450")

    def test_lens_paper_source_url(self):
        """Verify Lens paper with meta other_url resolves properly."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="lens_doc_1",
            title="Solid-State Battery Breakthrough",
            authors="Battery Lab",
            source_database="lens",
            meta={
                "other_url": "https://www.lens.org/lens/scholar/article/012-345-678-901-234"
            }
        )
        self.assertEqual(paper.source_url, "https://www.lens.org/lens/scholar/article/012-345-678-901-234")

    def test_paper_serializer_exposes_source_url(self):
        """Verify PaperSerializer includes source_url in serialized output."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="arxiv_test_serializer",
            arxiv_id="2103.00020",
            title="Self-Supervised Learning",
            authors="Yann LeCun",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="accepted"
        )

        serializer = PaperSerializer(paper)
        data = serializer.data
        self.assertIn("source_url", data)
        self.assertEqual(data["source_url"], "https://arxiv.org/abs/2103.00020")

    def test_paper_viewset_scorecard_action_exposes_source_url(self):
        """Verify GET /api/papers/{id}/scorecard/ includes source_url."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="scorecard_test_paper",
            doi="10.1145/3318464.3389700",
            title="ACM Conference Paper",
            authors="ACM Authors",
            source_database="openalex"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="accepted"
        )

        from rest_framework.test import force_authenticate
        factory = APIRequestFactory()
        request = factory.get(f"/api/papers/{paper.id}/scorecard/")
        force_authenticate(request, user=self.user)

        view = PaperViewSet.as_view({'get': 'scorecard'})
        response = view(request, pk=str(paper.id))
        self.assertEqual(response.status_code, 200)
        paper_result = response.data.get("paper", {})
        self.assertIn("source_url", paper_result)
        self.assertEqual(paper_result["source_url"], "https://doi.org/10.1145/3318464.3389700")

    def test_mcp_list_papers_logic_returns_source_url(self):
        """Verify MCP list_papers_logic tool returns source_url in JSON payload."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="mcp_paper_test",
            arxiv_id="2401.99999",
            title="MCP Scientific Tool Ingestion",
            authors="Anthropic & SRI",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="pending"
        )

        raw_json = list_papers_logic(self.user, str(self.workspace.id))
        parsed = json.loads(raw_json)
        self.assertIsInstance(parsed, list)
        self.assertTrue(len(parsed) >= 1)
        found = next((p for p in parsed if p.get("paper_id") == str(paper.id)), None)
        self.assertIsNotNone(found)
        self.assertIn("source_url", found)
        self.assertEqual(found["source_url"], "https://arxiv.org/abs/2401.99999")

"""
Unit and Integration Tests for Data Integrity & Logical Consistency Fixes:
1. Non-destructive reprocess_existing (preserves historical pipeline_run and screening status).
2. Orphan agent process isolation in ResearchAgentRunner.handle_component_completion().
3. Safe prompt formatting resilience during screening execution.
"""

from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    PaperMetric,
    ComponentRun,
    ResearchAgentProcess
)
from research_intelligence.tasks.orchestrator.runner import ResearchAgentRunner
from research_intelligence.tasks.step_4_screening.abstract import screen_abstract
from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job

User = get_user_model()


class DataIntegrityRemediationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="integrity_tester", email="tester@example.com")
        self.workspace = Workspace.objects.create(
            name="Integrity WS",
            screening_llm_model="gemini-2.5-flash"
        )

    def test_reprocess_existing_preserves_historical_run_and_status(self):
        """
        Verify that reprocess_existing=True associates existing papers via
        reprocessed_runs without mutating paper.pipeline_run or prematurely wiping
        screening status.
        """
        # Run 1: Initial Ingestion Run
        run_1 = PipelineRun.objects.create(workspace=self.workspace, status='completed')
        paper_1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run_1,
            hash_id="unique_hash_paper_1",
            doi="10.1000/182",
            arxiv_id="2101.00001",
            title="Transformer Scaling Laws",
            authors="Vaswani et al.",
            abstract="Study on transformer scaling."
        )
        PaperMetric.objects.create(
            paper=paper_1,
            pipeline_run=run_1,
            workspace=self.workspace,
            screening_status="abstract_passed",
            screening_reasoning="Passed in Run 1",
            signal_score=0.85
        )

        self.assertEqual(run_1.papers.count(), 1)
        self.assertEqual(paper_1.pipeline_run, run_1)

        # Run 2: Trigger search with reprocess_existing=True and identical paper
        run_2 = PipelineRun.objects.create(
            workspace=self.workspace,
            status='running',
            reprocess_existing=True
        )
        from research_intelligence.models import Scraper
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="transformer"
        )
        comp_run_search = ComponentRun.objects.create(
            pipeline_run=run_2,
            step_type='search',
            component_name='arxiv_search',
            scraper=scraper,
            status='running'
        )

        mock_scraper_items = [{
            "source_database": "arxiv",
            "hash_id": "different_hash_from_scraper",
            "doi": "10.1000/182",  # Matching DOI
            "arxiv_id": "2101.00001",
            "title": "Transformer Scaling Laws",
            "authors": ["Vaswani et al."],
            "abstract": "Study on transformer scaling.",
            "published_date": "2021-01-01"
        }]

        with patch('research_intelligence.tasks.step_1_search.search.get_scraper_provider') as mock_get_provider:
            scraper_inst = MagicMock()
            scraper_inst.search.return_value = mock_scraper_items
            mock_get_provider.return_value = scraper_inst

            execute_scraper_run_job(
                component_run_id=str(comp_run_search.id)
            )

        paper_1.refresh_from_db()

        # 1. Historical pipeline_run on paper_1 must remain Run 1!
        self.assertEqual(paper_1.pipeline_run, run_1)
        # 2. Run 1 still has paper_1 in its reverse relation
        self.assertEqual(run_1.papers.count(), 1)
        # 3. Screening status on Run 1 was not prematurely wiped
        pm_1 = PaperMetric.objects.get(paper=paper_1, pipeline_run=run_1)
        self.assertEqual(pm_1.screening_status, "abstract_passed")
        self.assertEqual(pm_1.screening_reasoning, "Passed in Run 1")
        # 4. Run 2 is linked via reprocessed_runs ManyToMany
        self.assertIn(run_2, paper_1.reprocessed_runs.all())
        # 5. run_2.get_papers() includes paper_1
        self.assertIn(paper_1, run_2.get_papers())

    def test_orphan_agent_processes_are_not_hijacked(self):
        """
        Verify that handle_component_completion does NOT hijack unattached
        ResearchAgentProcess records in the workspace.
        """
        # Run A belonging to another execution or manual trigger
        run_a = PipelineRun.objects.create(workspace=self.workspace, status='running')

        # Unattached agent process (e.g. just initialized or standing)
        orphan_agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Independent Agent",
            status='running',
            pipeline_run=None
        )

        # Trigger component completion for run_a
        ResearchAgentRunner.handle_component_completion(str(run_a.id))

        # Refresh orphan_agent; pipeline_run must still be None
        orphan_agent.refresh_from_db()
        self.assertIsNone(orphan_agent.pipeline_run)

    def test_screen_abstract_with_json_in_prompt_template_succeeds(self):
        """
        Verify that a user prompt template containing JSON braces does not crash
        or silently discard custom criteria, and writes to PaperMetric for active run.
        """
        # Template with JSON braces that crashes str.format()
        self.workspace.abstract_screening_user_prompt_template = (
            "Review paper: {title}\n"
            "Schema: {\"format\": \"json\", \"accepted\": true}\n"
            "Criteria: {acceptance_criteria}\n"
            "LaTeX Math: \\mathcal{O}(n)"
        )
        self.workspace.abstract_acceptance_criteria = "Study on LLM agents"
        self.workspace.save()

        run = PipelineRun.objects.create(workspace=self.workspace, status='running')
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="p_test_json_template",
            title="Agentic Coding Workflows",
            authors="DeepMind",
            abstract="Study on autonomous programming agents."
        )

        mock_llm_response = {
            "decision": "PASSED",
            "passed": True,
            "reasoning": "Fits criteria well",
            "evidence_quotes": ["autonomous programming agents"]
        }

        with patch('research_intelligence.tasks.step_4_screening.abstract.get_llm_provider') as mock_get_provider:
            mock_prov = MagicMock()
            mock_prov.generate.return_value = (mock_llm_response, {"tokens_in": 50, "tokens_out": 20, "total_tokens": 70})
            mock_get_provider.return_value = mock_prov

            res = screen_abstract(
                str(paper.id),
                str(self.workspace.id),
                workspace_obj=self.workspace,
                paper_obj=paper,
                pipeline_run_id=str(run.id)
            )

            self.assertTrue(res.get("success"))
            self.assertTrue(res.get("passed"))

            # Verify prompt delivered to LLM contained substituted title and criteria, as well as JSON and LaTeX
            call_kwargs = mock_prov.generate.call_args[1]
            prompt_sent = call_kwargs["prompt"]
            self.assertIn("Review paper: Agentic Coding Workflows", prompt_sent)
            self.assertIn("Criteria: Study on LLM agents", prompt_sent)
            self.assertIn("Schema: {\"format\": \"json\", \"accepted\": true}", prompt_sent)
            self.assertIn("\\mathcal{O}(n)", prompt_sent)

            # Verify PaperMetric was recorded for this run
            pm = PaperMetric.objects.filter(paper=paper, pipeline_run=run).first()
            self.assertIsNotNone(pm)
            self.assertTrue(pm.metrics_data["abstract_screening"]["passed"])
            self.assertEqual(pm.metrics_data["abstract_screening"]["reasoning"], "Fits criteria well")

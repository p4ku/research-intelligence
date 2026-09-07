from unittest.mock import patch, MagicMock
from django.test import TestCase

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    PaperMetric,
    ComponentRun,
    Subscriber,
)
from research_intelligence.reports import reporter_registry, ResultReportReporter
from research_intelligence.tasks.step_7_reporting.node import ReportingNode


class ReportingTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Reporting Project",
            abstract_acceptance_criteria="Robotics",
            abstract_rejection_criteria="Heuristics"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="report_paper_1",
            title="Next Gen Robotics",
            authors="John Doe",
            abstract="Robotics in manufacturing."
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed",
            signal_score=8.5
        )
        self.subscriber = Subscriber.objects.create(
            workspace=self.workspace,
            email="researcher@example.com",
            subscription_type="result_report",
            is_active=True
        )
        self.component_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="reporting",
            component_name="executive_reporter",
            status="pending"
        )

    def test_result_report_payload_generation(self):
        reporter = ResultReportReporter()
        payload = reporter.build_payload(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run
        )
        self.assertIn("subject", payload)
        self.assertIn("context", payload)
        self.assertEqual(payload["stats"]["accepted_papers_count"], 1)

    @patch("research_intelligence.reports.registry.send_mailgun_message")
    def test_report_registry_dispatch(self, mock_mailer):
        mock_mailer.return_value = (True, {"id": "mailgun_test_id"})

        report_summary = reporter_registry.dispatch_report(
            workspace=self.workspace,
            event_type="result_report",
            pipeline_run=self.pipeline_run
        )
        self.assertEqual(report_summary["status"], "success")
        self.assertEqual(report_summary["sent_count"], 1)

    def test_reporting_node_contract_and_summary(self):
        node = ReportingNode()
        self.assertEqual(node.name, "reporting")
        self.assertEqual(node.dependencies, ["signal_score"])
        
        self.component_run.metrics = {"report_generated": True, "emails_sent": 1}
        summary = node.generate_stage_summary(self.component_run, status="completed")
        self.assertIn("Reporting", summary)

    def test_generate_executive_narrative_report_overwrites_existing_storage(self):
        """Test generating executive narrative report cleans existing storage without creating duplicate suffix files."""
        from django.core.files.storage import default_storage
        from research_intelligence.tasks.step_7_reporting.narrative import generate_executive_narrative_report
        from research_intelligence.models import NarrativeReport

        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])
        path = res["storage_path"]
        self.assertTrue(default_storage.exists(path))

        # Re-run report generation to test overwrite
        res2 = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res2["success"])
        self.assertEqual(res2["storage_path"], path)
        self.assertEqual(NarrativeReport.objects.filter(pipeline_run=self.pipeline_run).count(), 1)

    @patch("research_intelligence.llm_providers.get_llm_provider")
    def test_generate_executive_narrative_report_with_custom_prompt(self, mock_get_llm):
        from research_intelligence.tasks.step_7_reporting.narrative import generate_executive_narrative_report
        from research_intelligence.models import NarrativeReport

        mock_provider = MagicMock()
        mock_provider.generate.return_value = "### Custom Executive Synthesis\nAI synthesized briefing."
        mock_get_llm.return_value = mock_provider

        self.workspace.narrative_report_prompt = (
            "Briefing for {workspace_name}.\n"
            "Total top papers: {top_n_papers_count}.\n"
            "Papers list:\n{papers}\n"
            "JSON list:\n{papers_json}\n"
            "Score summary:\n{score_vectors_summary}"
        )
        self.workspace.narrative_report_system_prompt = "You are a senior tech strategist."
        self.workspace.narrative_report_top_n_papers = 5
        self.workspace.save()

        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])

        # Check LLM provider called with formatted variables
        mock_provider.generate.assert_called_once()
        call_kwargs = mock_provider.generate.call_args[1]
        self.assertEqual(call_kwargs["system_instruction"], "You are a senior tech strategist.")
        user_prompt = call_kwargs["prompt"]
        self.assertIn("Briefing for Reporting Project.", user_prompt)
        self.assertIn("Total top papers: 1.", user_prompt)
        self.assertIn("Next Gen Robotics", user_prompt)
        self.assertIn("signal_score", user_prompt)

        # Check narrative report content
        report = NarrativeReport.objects.get(pipeline_run=self.pipeline_run)
        self.assertEqual(report.content_markdown, "### Custom Executive Synthesis\nAI synthesized briefing.")

    @patch("research_intelligence.llm_providers.get_llm_provider")
    def test_generate_executive_narrative_report_top_n_papers_slice(self, mock_get_llm):
        """Verify only the top N accepted papers ranked by signal score are passed to the prompt."""
        from research_intelligence.tasks.step_7_reporting.narrative import generate_executive_narrative_report

        mock_provider = MagicMock()
        mock_provider.generate.return_value = "Top N Report"
        mock_get_llm.return_value = mock_provider

        # Create additional papers with varying signal scores
        for idx, score in enumerate([2.5, 9.8, 6.0, 4.0], start=2):
            p = Paper.objects.create(
                workspace=self.workspace,
                pipeline_run=self.pipeline_run,
                hash_id=f"paper_score_{idx}",
                title=f"Paper Rank {idx} Score {score}",
                abstract=f"Abstract for paper {idx}"
            )
            PaperMetric.objects.create(
                paper=p,
                pipeline_run=self.pipeline_run,
                workspace=self.workspace,
                screening_status="full_text_passed",
                signal_score=score
            )

        self.workspace.narrative_report_prompt = "Review top papers:\n{papers}"
        self.workspace.narrative_report_top_n_papers = 2
        self.workspace.save()

        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])

        user_prompt = mock_provider.generate.call_args[1]["prompt"]
        # Top 2 scores are 9.8 (paper rank 3) and 8.5 (self.paper)
        self.assertIn("Paper Rank 3 Score 9.8", user_prompt)
        self.assertIn("Next Gen Robotics", user_prompt)
        # Lower scored papers must NOT be included in the top 2 slice
        self.assertNotIn("Paper Rank 2 Score 2.5", user_prompt)
        self.assertNotIn("Paper Rank 5 Score 4.0", user_prompt)

    @patch("research_intelligence.llm_providers.get_llm_provider")
    def test_generate_executive_narrative_report_llm_failure_fallback(self, mock_get_llm):
        """Ensure that if the LLM provider fails, generation falls back safely to default deterministic briefing."""
        from research_intelligence.tasks.step_7_reporting.narrative import generate_executive_narrative_report
        from research_intelligence.models import NarrativeReport

        mock_provider = MagicMock()
        mock_provider.generate.side_effect = RuntimeError("Provider 503 Overloaded")
        mock_get_llm.return_value = mock_provider

        self.workspace.narrative_report_prompt = "Generate briefing: {papers}"
        self.workspace.save()

        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])

        report = NarrativeReport.objects.get(pipeline_run=self.pipeline_run)
        self.assertIn("Executive Research Briefing", report.content_markdown)
        self.assertIn("Next Gen Robotics", report.content_markdown)

    def test_workspace_narrative_model_getters_and_clamping(self):
        self.assertEqual(self.workspace.get_narrative_report_top_n_papers(), 10)
        self.assertIsNone(self.workspace.get_narrative_report_prompt())
        self.assertIn("Executive Research Briefing", self.workspace.get_narrative_report_system_prompt())

        self.workspace.narrative_report_top_n_papers = 0
        self.assertEqual(self.workspace.get_narrative_report_top_n_papers(), 10)

        self.workspace.narrative_report_top_n_papers = 25
        self.assertEqual(self.workspace.get_narrative_report_top_n_papers(), 25)

        self.workspace.narrative_report_top_n_papers = 999
        self.assertEqual(self.workspace.get_narrative_report_top_n_papers(), 50)



from unittest.mock import patch, MagicMock
from django.test import TestCase

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    ComponentRun,
    Subscriber,
)
from research_intelligence.reports import reporter_registry, ResultReportReporter
from research_intelligence.tasks.step_8_reporting.node import ReportingNode


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
            abstract="Robotics in manufacturing.",
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

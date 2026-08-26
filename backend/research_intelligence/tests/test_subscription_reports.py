import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from research_intelligence.models import (
    Workspace,
    Subscriber,
    PipelineRun,
    ComponentRun,
    Paper,
    ExtractionDefinition,
    Extraction,
    ResearchAgentProcess
)
from research_intelligence.reports import (
    BaseSubscriptionReporter,
    ResultReportReporter,
    PipelineErrorsReporter,
    PipelineStatusReporter,
    SubscriptionReporterRegistry,
    reporter_registry
)

User = get_user_model()


class SubscriptionReportsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="report_admin", email="rep_admin@corp.com", password="pass")
        self.workspace = Workspace.objects.create(name="Quantum Reports Workspace")

        self.sub_results = Subscriber.objects.create(
            workspace=self.workspace,
            email="results@corp.com",
            name="Results Officer",
            subscription_type="result_report",
            is_active=True
        )
        self.sub_errors = Subscriber.objects.create(
            workspace=self.workspace,
            email="devops@corp.com",
            name="DevOps Lead",
            subscription_type="pipeline_errors",
            is_active=True
        )
        self.sub_status = Subscriber.objects.create(
            workspace=self.workspace,
            email="manager@corp.com",
            name="Product Manager",
            subscription_type="pipeline_status",
            is_active=True
        )
        self.sub_all = Subscriber.objects.create(
            workspace=self.workspace,
            email="director@corp.com",
            name="Research Director",
            subscription_type="all",
            is_active=True
        )
        self.sub_inactive = Subscriber.objects.create(
            workspace=self.workspace,
            email="inactive@corp.com",
            name="Inactive User",
            subscription_type="all",
            is_active=False
        )

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            total_papers_fetched=5,
            total_papers_passed_screening=2,
            tokens_consumed=50000,
            usd_cost=0.0825
        )

        self.def1 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            system_prompt="Extract TRL",
            user_prompt_template="Paper: {title}",
            response_schema={"type": "object", "properties": {"trl": {"type": "string"}}},
            exit_metric="trl"
        )

        self.paper1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_rep_001",
            title="Scalable Superconducting Qubits",
            authors="Dr. Alice Smith",
            screening_status="full_text_passed",
            signal_score=88.5
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper1,
            extraction_definition=self.def1,
            category="parameter",
            fields_data={"trl": "TRL 4"},
            confidence_score=0.95,
            validation_status="pass"
        )


    def test_result_report_reporter_build_payload(self):
        reporter = ResultReportReporter()
        payload = reporter.build_payload(self.workspace, pipeline_run=self.pipeline_run)
        
        self.assertIn("subject", payload)
        self.assertIn("Quantum Reports Workspace", payload["subject"])
        self.assertIn("context", payload)
        self.assertEqual(payload["stats"]["accepted_papers_count"], 1)
        self.assertEqual(payload["stats"]["total_cost_usd"], 0.0825)
        papers = payload["context"].get("papers_data") or payload["context"].get("papers")
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["title"], "Scalable Superconducting Qubits")


    def test_pipeline_errors_reporter_build_payload(self):
        cr_failed = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            status="failed",
            error_message="PDF 404 Not Found at remote host"
        )


        reporter = PipelineErrorsReporter()
        error_context = {"stage": "download", "error": "Download worker connection refused."}
        payload = reporter.build_payload(
            self.workspace,
            pipeline_run=self.pipeline_run,
            error_context=error_context
        )

        self.assertIn("🚨 [Pipeline Alert]", payload["subject"])
        self.assertEqual(payload["context"]["failed_stage"], "download")
        self.assertEqual(payload["context"]["main_error"], "Download worker connection refused.")
        self.assertEqual(len(payload["context"]["failed_components"]), 1)
        self.assertIn("PDF 404 Not Found", payload["context"]["failed_components"][0]["error_log"])

    def test_pipeline_status_reporter_build_payload(self):
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            status="completed"
        )
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            status="running"
        )

        reporter = PipelineStatusReporter()
        payload = reporter.build_payload(self.workspace, pipeline_run=self.pipeline_run)

        self.assertIn("⚡ [Pipeline Status: COMPLETED]", payload["subject"])
        self.assertEqual(payload["stats"]["total_papers"], 1)
        self.assertEqual(payload["stats"]["stages_count"], 2)

    @patch("research_intelligence.reports.registry.send_mailgun_message")
    def test_registry_dispatch_result_report_filtering(self, mock_send_mailgun):
        mock_send_mailgun.return_value = (True, {"message": "Queued"})

        # Dispatch result_report: Should notify 'results@corp.com' and 'director@corp.com' (all)
        res = reporter_registry.dispatch_report(
            workspace=self.workspace,
            event_type="result_report",
            pipeline_run=self.pipeline_run
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_recipients"], 2)
        self.assertEqual(res["sent_count"], 2)
        emails_sent = [d["email"] for d in res["deliveries"]]
        self.assertIn("results@corp.com", emails_sent)
        self.assertIn("director@corp.com", emails_sent)
        self.assertNotIn("devops@corp.com", emails_sent)
        self.assertNotIn("manager@corp.com", emails_sent)
        self.assertNotIn("inactive@corp.com", emails_sent)

    @patch("research_intelligence.reports.registry.send_mailgun_message")
    def test_registry_dispatch_pipeline_errors_filtering(self, mock_send_mailgun):
        mock_send_mailgun.return_value = (True, {"message": "Queued"})

        # Dispatch pipeline_errors: Should notify 'devops@corp.com' and 'director@corp.com' (all)
        res = reporter_registry.dispatch_report(
            workspace=self.workspace,
            event_type="pipeline_errors",
            pipeline_run=self.pipeline_run,
            error_context={"error": "OCR API timeout"}
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_recipients"], 2)
        emails_sent = [d["email"] for d in res["deliveries"]]
        self.assertIn("devops@corp.com", emails_sent)
        self.assertIn("director@corp.com", emails_sent)
        self.assertNotIn("results@corp.com", emails_sent)

    def test_registry_custom_extension(self):
        class CustomExecutiveAlertReporter(BaseSubscriptionReporter):
            subscription_type = "executive_brief"
            display_name = "Executive Brief"
            description = "Custom high-level C-suite summary"
            template_name = "emails/pipeline_digest"

            def build_payload(self, workspace, **kwargs):
                return {
                    "subject": "C-Suite Alert",
                    "context": {"workspace_name": workspace.name},
                    "stats": {},
                    "template_name": self.template_name
                }

        registry = SubscriptionReporterRegistry()
        registry.register(CustomExecutiveAlertReporter())

        rep = registry.get_reporter("executive_brief")
        self.assertEqual(rep.display_name, "Executive Brief")
        self.assertEqual(rep.subscription_type, "executive_brief")
        payload = rep.build_payload(self.workspace)
        self.assertEqual(payload["subject"], "C-Suite Alert")

    def test_subscriber_admin_changelist_and_badges(self):
        self.client.force_login(self.user)
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        url = reverse('admin:research_intelligence_subscriber_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "results@corp.com")
        self.assertContains(response, "devops@corp.com")
        self.assertContains(response, "Result Report")
        self.assertContains(response, "Pipeline Errors")

    def test_result_report_with_realistic_complex_matrix_and_signal_scores(self):
        from django.template.loader import render_to_string

        # Add second definition and multiple realistic papers
        def_novelty = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            system_prompt="Assess Novelty",
            user_prompt_template="Paper: {title}",
            response_schema={"type": "object"},
            exit_metric="novelty_score"
        )
        def_rigour = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Methodology Rigour",
            system_prompt="Assess Rigour",
            user_prompt_template="Paper: {title}",
            response_schema={"type": "object"},
            exit_metric="rigour"
        )

        paper2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_rep_002",
            title="Fluxonium Qubits with Millisecond Coherence Times",
            authors="Bob Johnson, Carol Danvers",
            screening_status="accepted",
            signal_score=94.2
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper2,
            extraction_definition=self.def1,
            category="parameter",
            fields_data={"trl": "TRL 5", "evidence_quote": "Demonstrated in lab setting."},
            confidence_score=0.92,
            validation_status="pass"
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper2,
            extraction_definition=def_novelty,
            category="parameter",
            fields_data={"novelty_score": "9.5/10", "evidence_quote": "First demonstration of 1.2ms T1."},
            confidence_score=0.88,
            validation_status="pass"
        )

        # Rejected paper should be excluded from scorecard
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_rep_003",
            title="Non-Quantum Classical Compiler",
            authors="Out of Scope Author",
            screening_status="rejected",
            signal_score=12.0
        )

        reporter = ResultReportReporter()
        payload = reporter.build_payload(self.workspace, pipeline_run=self.pipeline_run)

        # Verify scorecard structure
        self.assertEqual(payload["stats"]["accepted_papers_count"], 2)
        self.assertEqual(payload["stats"]["rejected_papers_count"], 1)
        self.assertEqual(payload["stats"]["top_signal_score"], 94.2)
        self.assertEqual(payload["stats"]["avg_signal_score"], 91.35)

        # Verify template rendering without syntax errors
        html_out = render_to_string(payload["template_name"] + ".html", payload["context"])
        txt_out = render_to_string(payload["template_name"] + ".txt", payload["context"])

        self.assertIn("Fluxonium Qubits", html_out)
        self.assertIn("94.20", html_out)
        self.assertIn("TRL 5", html_out)
        self.assertIn("Fluxonium Qubits", txt_out)
        self.assertIn("94.20", txt_out)

    def test_result_report_resilience_with_corrupted_and_broken_data(self):
        from django.template.loader import render_to_string

        # 1. Broken paper with None fields and extremely long text
        broken_paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_broken_999",
            title="A" * 5000,
            authors="",
            screening_status="accepted",
            signal_score=None
        )

        # 2. Corrupted extraction with unparseable fields_data and orphaned definition
        Extraction.objects.create(
            workspace=self.workspace,
            paper=broken_paper,
            extraction_definition=None,
            category="broken_category",
            fields_data="non-json string or raw bytes",
            confidence_score=None,
            validation_status="warn"
        )

        # 3. Paper with empty dict fields_data
        Extraction.objects.create(
            workspace=self.workspace,
            paper=broken_paper,
            extraction_definition=self.def1,
            category="parameter",
            fields_data={},
            confidence_score=float("nan"),
            validation_status=""
        )

        reporter = ResultReportReporter()
        # Should not crash on broken paper & extraction records
        payload = reporter.build_payload(self.workspace, pipeline_run=self.pipeline_run)
        self.assertIsNotNone(payload)
        self.assertIn("subject", payload)

        # Template rendering should succeed without unhandled exceptions
        html_out = render_to_string(payload["template_name"] + ".html", payload["context"])
        txt_out = render_to_string(payload["template_name"] + ".txt", payload["context"])
        self.assertTrue(len(html_out) > 0)
        self.assertTrue(len(txt_out) > 0)

        # 4. Total fallback when pipeline_run is None and workspace has 0 papers
        empty_ws = Workspace.objects.create(name="Empty Ghost Workspace")
        empty_payload = reporter.build_payload(empty_ws, pipeline_run=None)
        self.assertEqual(empty_payload["stats"]["accepted_papers_count"], 0)
        self.assertEqual(empty_payload["stats"]["total_cost_usd"], 0.0)

    def test_pipeline_errors_reporter_realistic_and_corrupted_scenarios(self):
        from django.template.loader import render_to_string

        # 1. Realistic multiple stage failure
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="ocr",
            status="failed",
            error_message="Mistral OCR API 503 Server Overloaded: Traceback (most recent call last):\n  File 'convert.py', line 89, in execute\n    raise ServiceUnavailable()"
        )
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            status="failed",
            error_message="ArXiv 429 Too Many Requests: Rate limit exceeded for IP 192.168.1.1"
        )

        reporter = PipelineErrorsReporter()
        payload = reporter.build_payload(
            self.workspace,
            pipeline_run=self.pipeline_run,
            error_context={
                "stage": "ocr",
                "error": "OCR layout conversion failed after 3 retries.",
                "traceback": "Traceback...\nServiceUnavailable"
            }
        )

        self.assertIn("🚨 [Pipeline Alert]", payload["subject"])
        self.assertEqual(len(payload["context"]["failed_components"]), 2)

        # Verify template rendering
        html_out = render_to_string(payload["template_name"] + ".html", payload["context"])
        txt_out = render_to_string(payload["template_name"] + ".txt", payload["context"])
        self.assertIn("OCR layout conversion failed", html_out)
        self.assertIn("Mistral OCR API 503", html_out)
        self.assertIn("ArXiv 429 Too Many Requests", txt_out)

        # 2. Corrupted error scenarios (None error_context, empty strings)
        empty_payload = reporter.build_payload(
            self.workspace,
            pipeline_run=None,
            error_context=None
        )
        self.assertIn("unexpected error", empty_payload["context"]["main_error"].lower())
        html_empty = render_to_string(empty_payload["template_name"] + ".html", empty_payload["context"])
        self.assertTrue(len(html_empty) > 0)

    def test_pipeline_status_reporter_realistic_and_corrupted_scenarios(self):
        from django.template.loader import render_to_string

        # 1. Realistic 4-node DAG execution
        ComponentRun.objects.create(pipeline_run=self.pipeline_run, step_type="search", status="completed")
        ComponentRun.objects.create(pipeline_run=self.pipeline_run, step_type="download", status="completed")
        ComponentRun.objects.create(pipeline_run=self.pipeline_run, step_type="screening", status="running")

        reporter = PipelineStatusReporter()
        payload = reporter.build_payload(self.workspace, pipeline_run=self.pipeline_run)
        self.assertEqual(payload["stats"]["stages_count"], 3)
        self.assertEqual(payload["stats"]["status"], "COMPLETED")

        html_out = render_to_string(payload["template_name"] + ".html", payload["context"])
        txt_out = render_to_string(payload["template_name"] + ".txt", payload["context"])
        self.assertIn("Pipeline Status Digest", html_out)
        self.assertIn("COMPLETED", html_out)
        self.assertIn("RUNNING", html_out)
        self.assertIn("PIPELINE STATUS DIGEST", txt_out)


        # 2. Corrupted component metrics (string instead of dict)
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            status="failed",
            metrics="corrupted string non dict"
        )
        payload_corrupted = reporter.build_payload(self.workspace, pipeline_run=self.pipeline_run)
        self.assertIsNotNone(payload_corrupted)
        html_corrupted = render_to_string(payload_corrupted["template_name"] + ".html", payload_corrupted["context"])
        self.assertTrue(len(html_corrupted) > 0)

    @patch("research_intelligence.reports.registry.send_mailgun_message")
    def test_registry_mailgun_failure_and_unknown_event_resilience(self, mock_send_mailgun):
        # 1. Simulate Mailgun connection crash
        mock_send_mailgun.side_effect = Exception("Mailgun API Connection Timeout 504")

        res = reporter_registry.dispatch_report(
            workspace=self.workspace,
            event_type="result_report",
            pipeline_run=self.pipeline_run
        )
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["failed_count"], 2)
        self.assertIn("Mailgun API Connection Timeout", res["deliveries"][0]["error"])

        # 2. Unknown event type falls back to default reporter gracefully and delivers to 'all' subscribers
        mock_send_mailgun.side_effect = None
        mock_send_mailgun.return_value = (True, {"message": "Queued"})
        res_unknown = reporter_registry.dispatch_report(
            workspace=self.workspace,
            event_type="unknown_future_event_type",
            pipeline_run=self.pipeline_run
        )
        self.assertEqual(res_unknown["status"], "success")
        self.assertEqual(res_unknown["total_recipients"], 1)
        self.assertEqual(res_unknown["deliveries"][0]["email"], "director@corp.com")

        # 3. Workspace with zero subscribers returns no_subscribers
        empty_ws = Workspace.objects.create(name="Empty Subscriber Workspace")
        res_empty = reporter_registry.dispatch_report(
            workspace=empty_ws,
            event_type="result_report",
            pipeline_run=self.pipeline_run
        )
        self.assertEqual(res_empty["status"], "no_subscribers")
        self.assertEqual(res_empty["sent_count"], 0)



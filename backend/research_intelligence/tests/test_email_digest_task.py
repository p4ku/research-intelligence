import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Subscriber,
    PipelineRun,
    Paper,
    Extraction,
    ExtractionDefinition,
)
from research_intelligence.tasks.auxiliary.email_digest import (
    dispatch_pipeline_subscriber_digest,
    send_pipeline_subscriber_digest_task,
    build_pipeline_run_digest_payload,
)
from research_intelligence.mcp.tools.email_reports import send_pipeline_run_digest_email_logic

User = get_user_model()


class EmailDigestTaskTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="digest_admin", email="admin@soinventive.co.uk", password="pass")
        self.workspace = Workspace.objects.create(
            name="Quantum Computing Lab",
            screening_llm_model="google/gemini-3.7-flash"
        )
        WorkspaceMember.objects.create(user=self.user, workspace=self.workspace, role="admin")

        self.subscriber1 = Subscriber.objects.create(
            workspace=self.workspace,
            email="researcher1@example.com",
            name="Lead Researcher",
            is_active=True
        )
        self.subscriber2 = Subscriber.objects.create(
            workspace=self.workspace,
            email="researcher2@example.com",
            name="Principal Investigator",
            is_active=True
        )
        self.inactive_sub = Subscriber.objects.create(
            workspace=self.workspace,
            email="inactive@example.com",
            name="Inactive User",
            is_active=False
        )

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            total_papers_fetched=10,
            total_papers_passed_screening=2,
            tokens_in=5000,
            tokens_out=1500,
            tokens_consumed=6500,
            usd_cost=0.0450,
        )

        self.definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Qubit Count Extraction",
            system_prompt="Extract qubit counts",
            user_prompt_template="Extract qubits: {paper_text}",
            response_schema={"type": "object", "properties": {"qubits": {"type": "integer"}}},
            exit_metric="qubits"
        )

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Scalable Surface Codes with 100 Qubits",
            authors="Alice Smith, Bob Jones",
            arxiv_id="2401.00001",
            screening_status="accepted",
            abstract="We present a scalable surface code architecture achieving 100 physical qubits."
        )

        self.extraction = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.definition,
            category="Qubit Count Extraction",
            confidence_score=0.98,
            validation_status="pass",
            fields_data={"qubits": "100 Qubits"}
        )

    @patch("research_intelligence.tasks.auxiliary.email_digest.send_mailgun_message")
    def test_build_and_dispatch_digest_success(self, mock_mailgun):
        mock_mailgun.return_value = (True, {"id": "<msg@soinventive.co.uk>", "message": "Queued."})

        result = dispatch_pipeline_subscriber_digest(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id)
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_recipients"], 2)
        self.assertEqual(result["sent_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(mock_mailgun.call_count, 2)

        # Check call arguments
        args, kwargs = mock_mailgun.call_args
        self.assertIn("Quantum Computing Lab", kwargs["subject"])
        self.assertEqual(kwargs["template_name"], "emails/pipeline_digest")
        self.assertEqual(kwargs["context"]["workspace_name"], "Quantum Computing Lab")
        self.assertEqual(kwargs["context"]["papers_data"][0]["title"], "Scalable Surface Codes with 100 Qubits")
        self.assertEqual(kwargs["context"]["cost_usd"], 0.0450)

    def test_dispatch_rejects_incomplete_pipeline_run(self):
        running_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            total_papers_fetched=5
        )

        result = dispatch_pipeline_subscriber_digest(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(running_run.id)
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("completed", result["error"])

    def test_dispatch_no_active_subscribers(self):
        Subscriber.objects.filter(workspace=self.workspace).update(is_active=False)

        result = dispatch_pipeline_subscriber_digest(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id)
        )

        self.assertEqual(result["status"], "no_subscribers")
        self.assertEqual(result["sent_count"], 0)

    @patch("research_intelligence.tasks.auxiliary.email_digest.send_mailgun_message")
    def test_dispatch_with_recipient_override(self, mock_mailgun):
        mock_mailgun.return_value = (True, {"message": "Queued."})

        result = dispatch_pipeline_subscriber_digest(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            recipient_override=["executive@custom-domain.com"]
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_recipients"], 1)
        self.assertEqual(result["sent_count"], 1)
        mock_mailgun.assert_called_once()
        self.assertEqual(mock_mailgun.call_args[1]["to_email"], "executive@custom-domain.com")

    @patch("research_intelligence.tasks.auxiliary.email_digest.send_mailgun_message")
    def test_celery_task_execution(self, mock_mailgun):
        mock_mailgun.return_value = (True, {"message": "Queued."})

        task_res = send_pipeline_subscriber_digest_task(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id)
        )

        self.assertEqual(task_res["status"], "success")
        self.assertEqual(task_res["sent_count"], 2)

    @patch("research_intelligence.tasks.auxiliary.email_digest.send_mailgun_message")
    def test_mcp_tool_send_digest_email(self, mock_mailgun):
        mock_mailgun.return_value = (True, {"message": "Queued."})

        # Synchronous MCP execution
        resp_str = send_pipeline_run_digest_email_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            async_dispatch=False
        )
        data = json.loads(resp_str)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["sent_count"], 2)

        # Async MCP execution (queuing Celery task)
        resp_async_str = send_pipeline_run_digest_email_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            async_dispatch=True
        )
        data_async = json.loads(resp_async_str)
        self.assertEqual(data_async["status"], "queued")
        self.assertIn("celery_task_id", data_async)


class EmailCompositionBuilderTests(TestCase):

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Deep Tech & AI Materials",
            screening_llm_model="google/gemini-3.7-flash"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            total_papers_fetched=25,
            total_papers_passed_screening=3,
            tokens_in=12000,
            tokens_out=4500,
            tokens_consumed=16500,
            usd_cost=0.0825,
        )

        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            system_prompt="Extract TRL",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"trl": {"type": "integer"}}},
            exit_metric="trl"
        )
        self.def_material = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Material Compound",
            system_prompt="Extract compound",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"compound": {"type": "string"}}},
            exit_metric="compound"
        )

    def test_multi_paper_html_and_text_composition(self):
        import uuid
        # Paper 1: ArXiv accepted paper with 2 extractions (pass & warn)
        p1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Graphene Superconductors at High Pressure",
            authors="John Doe, Jane Miller",
            arxiv_id="2402.12345",
            screening_status="full_text_passed",
            abstract="Study on high pressure graphene superconductivity."
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=p1,
            extraction_definition=self.def_trl,
            category="TRL Level",
            confidence_score=0.95,
            validation_status="pass",
            fields_data={"trl": "TRL 4"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=p1,
            extraction_definition=self.def_material,
            category="Material Compound",
            confidence_score=0.80,
            validation_status="warn",
            fields_data={"compound": "C (Graphene) + Cu"}
        )

        # Paper 2: DOI accepted paper with 1 extraction
        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Room-Temperature Superconducting Hydrides",
            authors="Arthur Pendelton",
            doi="10.1038/s41586-024-00123-x",
            screening_status="accepted",
            abstract="Hydride synthesis and characterization."
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=p2,
            extraction_definition=self.def_material,
            category="Material Compound",
            confidence_score=None,
            validation_status="pass",
            fields_data={"compound": "LaH10"}
        )

        # Paper 3: Rejected paper (should not appear in scorecard blocks)
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Unrelated Battery Optimization",
            authors="Sam Battery",
            arxiv_id="2402.99999",
            screening_status="rejected",
            abstract="Battery chemical composition."
        )

        payload = build_pipeline_run_digest_payload(self.pipeline_run)

        # Verify subject
        self.assertIn("[Research Digest] Deep Tech & AI Materials", payload["subject"])
        self.assertIn("2 accepted papers", payload["subject"])

        # Verify HTML structure
        html = payload["html_content"]
        self.assertIn("Graphene Superconductors at High Pressure", html)
        self.assertIn("https://arxiv.org/pdf/2402.12345.pdf", html)
        self.assertIn("TRL Level", html)
        self.assertIn("TRL 4", html)
        self.assertIn("95%", html)
        self.assertIn("Material Compound", html)
        self.assertIn("C (Graphene) + Cu", html)
        self.assertIn("Room-Temperature Superconducting Hydrides", html)
        self.assertIn("https://doi.org/10.1038/s41586-024-00123-x", html)
        self.assertIn("LaH10", html)
        self.assertNotIn("Unrelated Battery Optimization", html)  # Rejected paper not shown in scorecard

        # Verify 4-Card KPI metrics in HTML
        self.assertIn("$0.0825", html)
        self.assertIn("16,500", html)
        self.assertIn("Extracted", html)
        self.assertIn("parameters", html)

        # Verify Plaintext version
        text = payload["text_content"]
        self.assertIn("Graphene Superconductors at High Pressure", text)
        self.assertIn("TRL Level: TRL 4", text)
        self.assertIn("Material Compound: LaH10", text)
        self.assertIn("USD Cost: $0.0825", text)
        self.assertIn("Token Consumption: 16,500 tokens", text)

        # Verify stats dict
        stats = payload["stats"]
        self.assertEqual(stats["total_papers"], 3)
        self.assertEqual(stats["accepted_papers"], 2)
        self.assertEqual(stats["rejected_papers"], 1)
        self.assertEqual(stats["total_extractions"], 3)
        self.assertEqual(stats["cost_usd"], 0.0825)
        self.assertEqual(stats["tokens_consumed"], 16500)

    def test_composition_with_all_papers_rejected(self):
        import uuid
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Rejected Paper 1",
            authors="Author 1",
            screening_status="rejected",
            abstract="Out of scope"
        )
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Rejected Paper 2",
            authors="Author 2",
            screening_status="rejected",
            abstract="Out of scope"
        )

        payload = build_pipeline_run_digest_payload(self.pipeline_run)
        html = payload["html_content"]
        self.assertIn("No accepted papers passed criteria in this execution run", html)
        self.assertEqual(payload["stats"]["accepted_papers"], 0)
        self.assertEqual(payload["stats"]["rejected_papers"], 2)

    def test_composition_with_zero_papers_empty_run(self):
        empty_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            total_papers_fetched=0,
            usd_cost=0.0
        )
        payload = build_pipeline_run_digest_payload(empty_run)
        html = payload["html_content"]
        self.assertIn("No accepted papers passed criteria in this execution run", html)
        self.assertEqual(payload["stats"]["total_papers"], 0)
        self.assertEqual(payload["stats"]["accepted_papers"], 0)
        self.assertEqual(payload["stats"]["cost_usd"], 0.0)

    def test_composition_special_characters_escaping(self):
        import uuid
        p = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Scalable <10nm> FinFETs & Nanoribbons: \"Novelty\"",
            authors="Dr. Jack & Jill <jack@tech.com>",
            screening_status="accepted",
            abstract="Test abstract with <script>alert(1)</script> special characters."
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=p,
            extraction_definition=self.def_trl,
            category="TRL Level",
            confidence_score=0.99,
            validation_status="pass",
            fields_data={"trl": "TRL > 5 & Verified"}
        )

        payload = build_pipeline_run_digest_payload(self.pipeline_run)
        html = payload["html_content"]
        self.assertIn("&lt;10nm&gt;", html)
        self.assertIn("&amp; Jill", html)
        self.assertIn("TRL &gt; 5 &amp; Verified", html)
        self.assertNotIn("<10nm>", html)  # Raw unescaped brackets should not exist


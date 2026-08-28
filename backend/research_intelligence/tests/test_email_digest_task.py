import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
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
from mcp.tools.diagnostics import send_pipeline_run_digest_email_logic

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

    def test_rich_parameter_matrix_and_scorecard_with_abstracts(self):
        """
        Validates that:
        1. Top Screened Papers & Parameter Matrix table renders with all definition column headers and cells.
        2. Top Screened Papers & Parameter Scorecard Details renders authors, PDF links, metric chips with confidence %, and full abstracts.
        3. Gated signal score indicators (*) appear for zero-scored papers.
        """
        import uuid
        def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Fit",
            exit_metric="fit_score",
            system_prompt="Fit",
            user_prompt_template="Fit",
            response_schema={"type": "object"}
        )
        def_novelty = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            exit_metric="novelty",
            system_prompt="Novelty",
            user_prompt_template="Novelty",
            response_schema={"type": "object"}
        )

        p1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Top Superconducting Topological Qubit",
            authors="Alice Quantum, Bob Qubit",
            arxiv_id="2403.11111",
            screening_status="accepted",
            signal_score=94.50,
            abstract="Detailed breakthrough abstract on Majorana zero modes and topological protection."
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=p1,
            extraction_definition=self.def_trl,
            category="TRL Level",
            confidence_score=0.96,
            fields_data={"trl": "TRL 6"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=p1,
            extraction_definition=def_fit,
            category="Schwarz Fit",
            confidence_score=0.90,
            fields_data={"fit_score": "9.5 / 10"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=p1,
            extraction_definition=def_novelty,
            category="Novelty Score",
            confidence_score=0.88,
            fields_data={"novelty": "8.5"}
        )

        # Paper 2: Gated paper (signal score 0.00*)
        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Gated Optical Transceiver",
            authors="Charlie Optics",
            doi="10.1038/s41586-gated",
            screening_status="accepted",
            signal_score=0.00,
            abstract="Optical transceiver without sufficient TRL maturity."
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=p2,
            extraction_definition=self.def_trl,
            category="TRL Level",
            confidence_score=0.95,
            fields_data={"trl": "TRL 2"}
        )

        payload = build_pipeline_run_digest_payload(self.pipeline_run)
        html = payload["html_content"]
        text = payload["text_content"]

        # 1. Verify Matrix Table in HTML
        self.assertIn("Top Screened Papers &amp; Parameter Matrix", html)
        self.assertIn("⚡ Signal Score", html)
        self.assertIn("TRL Level", html)
        self.assertIn("Schwarz Fit", html)
        self.assertIn("Novelty Score", html)
        self.assertIn("Top Superconducting Topological Qubit", html)
        self.assertIn("94.50", html)
        self.assertIn("TRL 6", html)
        self.assertIn("9.5 / 10", html)
        self.assertIn("8.5", html)
        self.assertIn("0.00*", html)
        self.assertIn("gated to 0.00 based on the workspace", html)

        # 2. Verify Scorecard Details and Full Abstracts in HTML
        self.assertIn("Top Screened Papers &amp; Parameter Scorecard Details", html)
        self.assertIn("Alice Quantum, Bob Qubit", html)
        self.assertIn("https://arxiv.org/pdf/2403.11111.pdf", html)
        self.assertIn("96% confidence", html)
        self.assertIn("Full Abstract", html)
        self.assertIn("Detailed breakthrough abstract on Majorana zero modes and topological protection.", html)
        self.assertIn("Optical transceiver without sufficient TRL maturity.", html)

        # 3. Verify Plaintext Matrix and Scorecard Rendering
        self.assertIn("TOP SCREENED PAPERS & PARAMETER MATRIX", text)
        self.assertIn("[1] Top Superconducting Topological Qubit", text)
        self.assertIn("TRL Level: TRL 6", text)
        self.assertIn("Schwarz Fit: 9.5 / 10", text)
        self.assertIn("Novelty Score: 8.5", text)
        self.assertIn("TOP SCREENED PAPERS & PARAMETER SCORECARD DETAILS", text)
        self.assertIn("Full Abstract:\n     Detailed breakthrough abstract on Majorana zero modes", text)

    def test_smart_exit_metric_resolution_variants(self):
        """
        Tests that Extraction.exit_metric unpacks correctly across various JSON formats:
        - Direct extraction_definition.exit_metric key match
        - Nested fields wrapper {'fields': {'key': 'value'}}
        - Nested value object {'key': {'value': 8.5}}
        - Fallback snake_case candidate keys
        - First scalar fallback
        """
        import uuid
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Unpacking Test Paper",
            screening_status="accepted"
        )
        def_test = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Commercial Viability",
            exit_metric="market_score",
            system_prompt="Test",
            user_prompt_template="Test",
            response_schema={"type": "object"}
        )

        # 1. Exact match
        e1 = Extraction(workspace=self.workspace, paper=paper, extraction_definition=def_test, fields_data={"market_score": "High ($10M+)"})
        self.assertEqual(e1.exit_metric, "High ($10M+)")

        # 2. Nested {'fields': {'market_score': {'value': 'Tier 1'}}}
        e2 = Extraction(workspace=self.workspace, paper=paper, extraction_definition=def_test, fields_data={"fields": {"market_score": {"value": "Tier 1"}}})
        self.assertEqual(e2.exit_metric, "Tier 1")

        # 3. Snake_case fallback when definition exit_metric is empty or mismatched
        def_empty_exit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Assessment Score",
            exit_metric="",
            system_prompt="Test",
            user_prompt_template="Test",
            response_schema={"type": "object"}
        )
        e3 = Extraction(workspace=self.workspace, paper=paper, extraction_definition=def_empty_exit, fields_data={"novelty_assessment_score": 9.2})
        self.assertEqual(e3.exit_metric, "9.2")

        # 4. First scalar fallback
        e4 = Extraction(workspace=self.workspace, paper=paper, extraction_definition=def_empty_exit, fields_data={"random_key": "Passed Criteria"})
        self.assertEqual(e4.exit_metric, "Passed Criteria")

    def test_email_digest_multistage_screening_and_full_matrix_population(self):
        """
        Tests that when a pipeline runs 2-stage screening:
        1. Only papers that reached terminal acceptance ('full_text_passed') are counted as accepted (e.g. 5 instead of 13).
        2. All extraction definitions and columns are matched properly.
        3. Signal scores and scorecard details are populated with confidence and metrics.
        """
        import uuid
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            total_papers_fetched=10,
            usd_cost=0.0373,
            tokens_consumed=32116
        )

        def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL (Technology Readiness Level)",
            exit_metric="trl_level",
            system_prompt="TRL",
            user_prompt_template="{paper_text}",
            response_schema={}
        )
        def_novelty = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty",
            exit_metric="novelty_score",
            system_prompt="Novelty",
            user_prompt_template="{paper_text}",
            response_schema={}
        )
        def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Fit",
            exit_metric="fit_score",
            system_prompt="Fit",
            user_prompt_template="{paper_text}",
            response_schema={}
        )

        # 5 papers passed full-text screening
        for i in range(5):
            p = Paper.objects.create(
                workspace=self.workspace,
                pipeline_run=pr,
                hash_id=uuid.uuid4().hex,
                title=f"Accepted Hybrid Quantum Paper #{i+1}",
                authors=f"Author {i+1}",
                screening_status="full_text_passed",
                signal_score=40.24 + i * 5.0,
                abstract=f"Abstract for paper {i+1}"
            )
            Extraction.objects.create(
                workspace=self.workspace,
                paper=p,
                extraction_definition=def_trl,
                confidence_score=0.95,
                validation_status="pass",
                fields_data={"trl_level": f"TRL {4+i}"}
            )
            Extraction.objects.create(
                workspace=self.workspace,
                paper=p,
                extraction_definition=def_novelty,
                confidence_score=0.90,
                validation_status="pass",
                fields_data={"novelty_score": f"{7.0+i}/10"}
            )
            Extraction.objects.create(
                workspace=self.workspace,
                paper=p,
                extraction_definition=def_fit,
                confidence_score=0.88,
                validation_status="pass",
                fields_data={"fit_score": "High"}
            )

        # 5 papers rejected
        for i in range(5):
            Paper.objects.create(
                workspace=self.workspace,
                pipeline_run=pr,
                hash_id=uuid.uuid4().hex,
                title=f"Rejected Paper #{i+1}",
                authors=f"Rejected Author {i+1}",
                screening_status="rejected",
                abstract=f"Rejected abstract {i+1}"
            )

        payload = build_pipeline_run_digest_payload(pr)
        html = payload["html_content"]
        text = payload["text_content"]

        # Exactly 5 accepted papers (not 10 or 13)
        self.assertEqual(payload["context"]["accepted_count"], 5)
        self.assertEqual(payload["context"]["rejected_count"], 5)
        self.assertEqual(payload["context"]["total_extractions"], 15)
        self.assertEqual(len(payload["context"]["papers_data"]), 5)

        # Matrix columns contain values
        self.assertIn("Accepted Hybrid Quantum Paper #1", html)
        self.assertIn("TRL 4", html)
        self.assertIn("7.0/10", html)
        self.assertIn("High", html)
        self.assertIn("95% confidence", html)


class MailgunMailerTests(TestCase):
    """
    Validates direct Mailgun HTTP API client, header/payload construction, and fail-silent wrapping.
    """
    @override_settings(
        MAILGUN_API_KEY="key-test123456",
        MAILGUN_API_URL="https://api.eu.mailgun.net/v3",
        MAILGUN_SENDER_DOMAIN="soinventive.co.uk",
        DEFAULT_FROM_EMAIL="noreply@soinventive.co.uk",
    )
    @patch("requests.post")
    def test_send_mailgun_message_success(self, mock_post):
        from research_intelligence.utils.mailer import send_mailgun_message
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "<20260820@soinventive.co.uk>", "message": "Queued. Thank you."}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        success, res = send_mailgun_message(
            to_email="client@example.com",
            subject="Research Pipeline Briefing",
            text="Your systematic literature review is ready.",
            html="<p>Your systematic literature review is ready.</p>"
        )

        self.assertTrue(success)
        self.assertEqual(res["message"], "Queued. Thank you.")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.eu.mailgun.net/v3/soinventive.co.uk/messages")
        self.assertEqual(kwargs["auth"], ("api", "key-test123456"))
        self.assertEqual(kwargs["data"]["to"], "client@example.com")
        self.assertEqual(kwargs["data"]["from"], "noreply@soinventive.co.uk")

    @override_settings(MAILGUN_API_KEY="")
    def test_send_mailgun_message_missing_key(self):
        from research_intelligence.utils.mailer import send_mailgun_message
        success, res = send_mailgun_message(
            to_email="client@example.com",
            subject="Test Subject",
            text="Hello"
        )
        self.assertFalse(success)
        self.assertIn("mailgun settings not configured", res)

    @override_settings(
        MAILGUN_API_KEY="key-test123456",
        MAILGUN_API_URL="https://api.eu.mailgun.net/v3",
        MAILGUN_SENDER_DOMAIN="soinventive.co.uk",
        DEFAULT_FROM_EMAIL="alerts@soinventive.co.uk",
    )
    @patch("research_intelligence.utils.mailer.send_mailgun_message")
    def test_send_mail_wrapper(self, mock_send_mailgun):
        from research_intelligence.utils.mailer import send_mail
        mock_send_mailgun.return_value = (True, {"message": "Queued."})

        sent_count = send_mail(
            subject="Weekly Alert",
            message="Alert message",
            from_email="alerts@soinventive.co.uk",
            recipient_list=["user1@example.com", "user2@example.com"],
            fail_silently=False
        )

        self.assertEqual(sent_count, 1)
        self.assertEqual(mock_send_mailgun.call_count, 2)

    @override_settings(
        MAILGUN_API_KEY="key-test123456",
        MAILGUN_API_URL="https://api.eu.mailgun.net/v3",
        MAILGUN_SENDER_DOMAIN="soinventive.co.uk",
    )
    @patch("requests.post")
    def test_send_mailgun_message_http_error(self, mock_post):
        from research_intelligence.utils.mailer import send_mailgun_message
        mock_post.side_effect = Exception("Connection Timeout")

        success, res = send_mailgun_message(
            to_email="client@example.com",
            subject="Error Subject",
            text="Test"
        )
        self.assertFalse(success)
        self.assertIn("Connection Timeout", res)

    @override_settings(
        MAILGUN_API_KEY="key-test123456",
        MAILGUN_API_URL="https://api.eu.mailgun.net/v3",
        MAILGUN_SENDER_DOMAIN="soinventive.co.uk",
    )
    @patch("research_intelligence.utils.mailer.send_mailgun_message")
    def test_send_mail_wrapper_failure(self, mock_send_mailgun):
        from research_intelligence.utils.mailer import send_mail
        mock_send_mailgun.return_value = (False, "Mailgun 401 Unauthorized")

        with self.assertRaises(Exception):
            send_mail(
                subject="Failing Alert",
                message="Fail",
                from_email="noreply@example.com",
                recipient_list=["user@example.com"],
                fail_silently=False
            )





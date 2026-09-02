import json
import uuid
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    Paper,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
    ResearchAgentProcess,
    Subscriber,
)
from research_intelligence.tasks.step_6_signal_score.scorer import (
    execute_signal_score_job,
    compute_paper_signal_score,
)
from research_intelligence.tasks.auxiliary.email_digest import (
    build_pipeline_run_digest_payload,
    dispatch_pipeline_subscriber_digest,
)
from mcp_server.tools.extractions import get_paper_extractions_matrix_logic
from mcp_server.tools.pipeline_runs import (
    get_pipeline_run_status_logic,
    trigger_signal_score_job_logic,
)
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process

User = get_user_model()


class SignalScoreEndToEndPipelineTests(TestCase):
    """
    Comprehensive End-to-End Pipeline & Integration Test Suite for Step 6: Signal Score Engine.
    Validates state machine progression, sandboxed calculation across papers, matrix payload generation,
    and responsive email digest rendering with signal score KPIs.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="e2e_lead", email="lead@schwarz.de")
        
        # Workspace configured with custom multi-variable conditional Signal Score formula
        self.workspace = Workspace.objects.create(
            name="Quantum Computing SLR",
            abstract_acceptance_criteria="Quantum algorithms and error correction",
            abstract_rejection_criteria="Classical HPC without quantum comparison",
            full_text_acceptance_criteria="Hardware benchmarks or fault-tolerant simulation",
            full_text_rejection_criteria="Purely philosophical commentary",
            screening_llm_model="google/gemini-3.8-flash",
            ocr_provider=None,
            signal_score_code="""
k = fit_score + 2 * novelty_score + trl_level
if k > 10:
    return 95.5
else:
    return 12.0
"""
        )

        from research_intelligence.models import WorkspaceMember
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        # 3 extraction definitions for multi-variable computation
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit Score",
            exit_metric="fit_score",
            system_prompt="Extract relevance fit (1-10)",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        self.def_novelty = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            exit_metric="novelty_score",
            system_prompt="Extract novelty (1-10)",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            exit_metric="trl_level",
            system_prompt="Extract TRL level (1-9)",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )

        # Subscribers for digest testing
        Subscriber.objects.create(
            workspace=self.workspace,
            email="tech_lead@schwarz.de",
            name="Tech Lead",
            is_active=True
        )

    def test_full_e2e_pipeline_orchestration_with_signal_score(self):
        """
        Runs full state machine from search -> download -> screening -> extraction -> signal_score -> completed.
        Verifies that Step 6 computes scores for all accepted papers and produces a complete scorecard.
        """
        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="search"
        )
        agent_process = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            name="Quantum Review Agent",
            status="running",
            current_step="search"
        )

        # Paper 1 (High Score Candidate: fit=5, novelty=4, trl=3 -> k=5+8+3=16 > 10 -> score=95.5)
        paper_high = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Fault-Tolerant Surface Code Architecture on Transmon Qubits",
            authors="Alice Quantum et al.",
            arxiv_id="2402.11111",
            screening_status="full_text_passed",
            abstract="Experimental realization of distance-3 surface codes."
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper_high,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": "5"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper_high,
            extraction_definition=self.def_novelty,
            fields_data={"novelty_score": "4"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper_high,
            extraction_definition=self.def_trl,
            fields_data={"trl_level": "TRL 3"}
        )

        # Paper 2 (Low Score Candidate: fit=1, novelty=1, trl=1 -> k=1+2+1=4 <= 10 -> score=12.0)
        paper_low = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Introductory Review of Qubit Gates",
            authors="Bob Beginner",
            arxiv_id="2402.22222",
            screening_status="full_text_passed",
            abstract="Textbook tutorial on Hadamard and CNOT gates."
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper_low,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": "1"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper_low,
            extraction_definition=self.def_novelty,
            fields_data={"novelty_score": "1"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper_low,
            extraction_definition=self.def_trl,
            fields_data={"trl_level": "1"}
        )

        # Simulate completion of Extraction step ComponentRun
        ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="extraction",
            component_name="parameter_extraction",
            status="completed"
        )
        agent_process.current_step = "extraction"
        agent_process.save(update_fields=['current_step'])

        # State machine tick: triggers Step 6 (Signal Score) and advances to completed in eager mode
        tick_agent_process(str(agent_process.id))

        agent_process.refresh_from_db()
        pipeline_run.refresh_from_db()
        self.assertEqual(agent_process.status, "completed")
        self.assertEqual(agent_process.current_step, "completed")
        self.assertEqual(pipeline_run.status, "completed")

        # 1. Verify Step 6 ComponentRun
        sig_comp_run = ComponentRun.objects.get(pipeline_run=pipeline_run, step_type="signal_score")
        self.assertEqual(sig_comp_run.status, "completed")
        self.assertEqual(sig_comp_run.metrics["scored_count"], 2)
        self.assertAlmostEqual(sig_comp_run.metrics["avg_signal_score"], (95.5 + 12.0) / 2.0, places=2)

        # 2. Verify Paper Models & PaperMetric Records
        paper_high.refresh_from_db()
        paper_low.refresh_from_db()
        self.assertEqual(paper_high.signal_score, 95.5)
        self.assertEqual(paper_low.signal_score, 12.0)
        self.assertIn("fit_score", paper_high.signal_score_details["variables"])

        metric_high = PaperMetric.objects.get(paper=paper_high, pipeline_run=pipeline_run)
        self.assertEqual(metric_high.signal_score, 95.5)
        self.assertEqual(metric_high.pipeline_run, pipeline_run)

        # 3. Verify MCP Matrix Tool: get_paper_extractions_matrix
        matrix_res = json.loads(get_paper_extractions_matrix_logic(
            user=self.user,
            pipeline_run_id=str(pipeline_run.id)
        ))
        self.assertEqual(matrix_res["total_papers"], 2)
        self.assertEqual(matrix_res["avg_signal_score"], 53.75)
        self.assertEqual(matrix_res["top_signal_score"], 95.5)
        
        matrix_papers = matrix_res["papers"]
        self.assertEqual(matrix_papers[0]["title"], paper_high.title)
        self.assertEqual(matrix_papers[0]["signal_score"], 95.5)
        self.assertIsNotNone(matrix_papers[0]["signal_score_details"])

        # 4. Verify MCP Pipeline Run Status Tool: get_pipeline_run_status
        status_res = json.loads(get_pipeline_run_status_logic(
            user=self.user,
            pipeline_run_id=str(pipeline_run.id)
        ))
        self.assertEqual(status_res["status"], "completed")
        preview = status_res["extractions_matrix_preview"]
        self.assertEqual(len(preview), 2)
        self.assertEqual(preview[0]["signal_score"], 95.5)

        # 5. Verify Email Digest Payload with Signal Score KPI & Badges
        payload = build_pipeline_run_digest_payload(pipeline_run)
        ctx = payload["context"]
        self.assertEqual(ctx["avg_signal_score"], "53.75")
        self.assertEqual(ctx["top_signal_score"], "95.50")
        self.assertEqual(len(ctx["papers_data"]), 2)
        # Top paper should be paper_high due to descending signal score sorting
        self.assertEqual(ctx["papers_data"][0]["title"], paper_high.title)
        self.assertEqual(ctx["papers_data"][0]["signal_score"], 95.5)

        # Verify HTML rendered content contains Signal Score badge and KPI
        html = payload["html_content"]
        self.assertIn("⚡ Signal Score", html)
        self.assertIn("53.75", html)
        self.assertIn("Top: 95.50", html)
        self.assertIn("95.50", html)

        # Verify Plaintext rendered content
        text = payload["text_content"]
        self.assertIn("Composite Signal Score: 53.75 (Top: 95.50)", text)
        self.assertIn("[⚡ Signal Score: 95.50]", text)

        # 6. Verify Email Dispatch to Subscribers via Mailgun Mock
        with patch("research_intelligence.tasks.auxiliary.email_digest.send_mailgun_message") as mock_mailer:
            mock_mailer.return_value = (True, {"id": "<message-12345@mailgun.org>"})
            dispatch_res = dispatch_pipeline_subscriber_digest(
                workspace_id=str(self.workspace.id),
                pipeline_run_id=str(pipeline_run.id)
            )
            self.assertEqual(dispatch_res["status"], "success")
            self.assertEqual(dispatch_res["sent_count"], 1)
            mock_mailer.assert_called_once()
            called_kwargs = mock_mailer.call_args[1]
            self.assertEqual(called_kwargs["to_email"], "tech_lead@schwarz.de")
            self.assertIn("[Research Digest]", called_kwargs["subject"])

    def test_manual_trigger_signal_score_job_tool(self):
        """
        Tests manually triggering Step 6 via trigger_signal_score_job_logic.
        """
        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            current_stage="extraction"
        )
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Quantum Annealing Benchmark",
            screening_status="accepted"
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": "8"}
        )

        res_json = json.loads(trigger_signal_score_job_logic(
            user=self.user,
            pipeline_run_id=str(pipeline_run.id)
        ))
        self.assertTrue(res_json["success"])
        self.assertIn("Successfully launched Signal Score", res_json["message"])

        paper.refresh_from_db()
        # With fit_score=8, novelty=0, trl=0 -> k=8 <= 10 -> score=12.0
        self.assertEqual(paper.signal_score, 12.0)

        metric = PaperMetric.objects.get(paper=paper, pipeline_run=pipeline_run)
        self.assertEqual(metric.signal_score, 12.0)
        self.assertEqual(metric.pipeline_run, pipeline_run)

    def test_paper_metrics_isolation_across_multiple_runs(self):
        """
        Tests that multiple pipeline runs evaluating the same Paper generate distinct,
        isolated PaperMetric records per pipeline_run.
        """
        run1 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            current_stage="extraction"
        )
        run2 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            current_stage="extraction"
        )

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run1,
            hash_id="multi_run_paper_hash_12345",
            title="Neuromorphic Vision Transformers",
            screening_status="accepted"
        )

        # Run 1 Extractions & Evaluation
        ext1 = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": "9.0"}
        )
        score1, _ = compute_paper_signal_score(paper, custom_code="return fit_score * 10.0", pipeline_run=run1)
        self.assertEqual(score1, 90.0)

        # Run 2 Evaluation on the same paper with different formula or parameters
        score2, _ = compute_paper_signal_score(paper, custom_code="return fit_score * 2.0", pipeline_run=run2)
        self.assertEqual(score2, 18.0)

        # Verify distinct PaperMetric instances exist for each run
        metrics = PaperMetric.objects.filter(paper=paper).order_by("created_at")
        self.assertEqual(metrics.count(), 2)

        metric_run1 = PaperMetric.objects.get(paper=paper, pipeline_run=run1)
        self.assertEqual(metric_run1.signal_score, 90.0)
        self.assertEqual(metric_run1.pipeline_run, run1)

        metric_run2 = PaperMetric.objects.get(paper=paper, pipeline_run=run2)
        self.assertEqual(metric_run2.signal_score, 18.0)
        self.assertEqual(metric_run2.pipeline_run, run2)

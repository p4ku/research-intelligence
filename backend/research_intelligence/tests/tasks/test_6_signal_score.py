import json
import uuid
from django.test import TestCase
from unittest.mock import patch, MagicMock
from ...models import (
    Workspace,
    PipelineRun,
    Paper,
    PaperMetric,
    ComponentRun,
    Extraction,
    ExtractionDefinition,
    ResearchAgentProcess,
    Subscriber,
)
from ...tasks.step_6_signal_score.scorer import (
    compute_paper_signal_score,
    execute_signal_score_job,
    _sanitize_identifier,
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


class SignalScoreTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Signal Score Test Project",
            llm_provider="google",
            signal_score_code="score = 0.5 * fit_score + 0.3 * novelty_score + 0.2 * trl_level\nreturn round(score, 2)"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="test_hash_signal_score_1",
            title="Advanced Quantum Routing",
            authors="Alice Q",
            abstract="Novel routing algorithm in NISQ devices with high fidelity."
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Fit",
            exit_metrics="fit_score",
            system_prompt="Extract fit",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"fit_score": {"type": "number"}}}
        )
        self.def_novelty = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            exit_metrics="novelty_score",
            system_prompt="Extract novelty",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"novelty_score": {"type": "number"}}}
        )
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            exit_metrics="trl_level",
            system_prompt="Extract TRL",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"trl_level": {"type": "number"}}}
        )

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": 8.0}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_novelty,
            fields_data={"novelty_score": 9.0}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_trl,
            fields_data={"trl_level": 4.0}
        )

    def test_sanitize_identifier(self):
        self.assertEqual(_sanitize_identifier("TRL Level"), "trl_level")
        self.assertEqual(_sanitize_identifier("Fit-Score (0-100)"), "fit_score_0_100")
        self.assertEqual(_sanitize_identifier("123abc"), "v_123abc")
        self.assertEqual(_sanitize_identifier(""), "param")

    def test_compute_paper_signal_score(self):
        # 0.5 * 8.0 + 0.3 * 9.0 + 0.2 * 4.0 = 4.0 + 2.7 + 0.8 = 7.5
        score, details = compute_paper_signal_score(self.paper, pipeline_run=self.pipeline_run)
        self.assertEqual(score, 7.5)
        self.assertIsNone(details.get("error"))

        # Verify saved on PaperMetric model
        metric = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.pipeline_run)
        self.assertEqual(metric.signal_score, 7.5)
        self.assertEqual(metric.metrics_data.get("fit_score"), 8.0)

    def test_execute_signal_score_job(self):
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="signal_score",
            component_name="signal_scorer",
            status="running"
        )

        res = execute_signal_score_job(str(comp_run.id))
        self.assertTrue(res["success"])
        self.assertEqual(res["metrics"]["scored_count"], 1)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertEqual(comp_run.metrics.get("scored_count"), 1)


class ScorerSingleSourceOfTruthTests(TestCase):
    """
    Dedicated tests verifying that:
    1. Paper table has NO signal_score column in database.
    2. compute_paper_signal_score and execute_signal_score_job write exclusively to PaperMetric.
    3. Multiple pipeline runs (including reprocess runs) score the same paper independently.
    4. Runtime AST evaluation errors in scorer store failure details on PaperMetric without corrupting Paper.
    """
    def setUp(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        self.user = User.objects.create_user(username="scorer_test_user", password="password")
        self.workspace = Workspace.objects.create(
            name="Scorer SSOT Workspace",
            signal_score_code="score = fit * 10\nreturn score"
        )
        self.run_1 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run_1,
            hash_id="ssot_paper_hash_001",
            title="SSOT Quantum Routing"
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.run_1,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit",
            exit_metrics="fit",
            system_prompt="Extract fit",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_fit,
            fields_data={"fit": 7.0}
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_paper_table_has_no_signal_score_column(self):
        """Verify that Paper database table has no physical 'signal_score' or 'signal_score_details' columns."""
        paper_values = Paper.objects.filter(id=self.paper.id).values().first()
        self.assertNotIn("signal_score", paper_values, "signal_score must NOT exist as a column in Paper DB table")
        self.assertNotIn("signal_score_details", paper_values, "signal_score_details must NOT exist as a column in Paper DB table")

    def test_scorer_writes_strictly_to_papermetric(self):
        """compute_paper_signal_score must persist to PaperMetric and keep Paper row clean."""
        score, details = compute_paper_signal_score(self.paper, pipeline_run=self.run_1)
        self.assertEqual(score, 70.0)

        # PaperMetric exists
        metric = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.run_1)
        self.assertEqual(metric.signal_score, 70.0)
        self.assertEqual(metric.signal_score_details.get("score"), 70.0)

        # Paper DB row has no signal_score column
        paper_raw = Paper.objects.filter(id=self.paper.id).values().first()
        self.assertNotIn("signal_score", paper_raw)

    def test_reprocessed_run_scorer_isolation(self):
        """
        Run 1 scores paper at 70.0.
        Run 2 modifies formula, reprocesses paper, and scores at 95.0.
        Verify Run 1 retains 70.0 and Run 2 stores 95.0 independently.
        """
        # 1. Execute Run 1 scoring job
        comp_run_1 = ComponentRun.objects.create(
            pipeline_run=self.run_1,
            step_type="signal_score",
            component_name="signal_scorer",
            status="running"
        )
        res_1 = execute_signal_score_job(str(comp_run_1.id))
        self.assertTrue(res_1["success"])
        metric_1 = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.run_1)
        self.assertEqual(metric_1.signal_score, 70.0)

        # 2. Create Run 2 (reprocess existing) with updated workspace formula
        self.workspace.signal_score_code = "score = fit * 10 + 25\nreturn score"
        self.workspace.save()

        run_2 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            reprocess_existing=True
        )
        self.paper.reprocessed_runs.add(run_2)
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=run_2,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )

        comp_run_2 = ComponentRun.objects.create(
            pipeline_run=run_2,
            step_type="signal_score",
            component_name="signal_scorer",
            status="running"
        )
        res_2 = execute_signal_score_job(str(comp_run_2.id))
        self.assertTrue(res_2["success"])

        # Verify Run 2 metric is 95.0
        metric_2 = PaperMetric.objects.get(paper=self.paper, pipeline_run=run_2)
        self.assertEqual(metric_2.signal_score, 95.0)

        # Verify Run 1 metric was NOT mutated and remains 70.0
        metric_1.refresh_from_db()
        self.assertEqual(metric_1.signal_score, 70.0, "Run 1 PaperMetric must not be overwritten by Run 2")

    def test_scorer_ast_error_handling_stores_details_in_papermetric(self):
        """When AST code violates sandbox or raises an error, error details are saved in PaperMetric."""
        self.workspace.signal_score_code = "import os\nreturn 10"
        self.workspace.save()

        score, details = compute_paper_signal_score(self.paper, pipeline_run=self.run_1)
        self.assertEqual(score, 0.0)
        self.assertIsNotNone(details.get("error"))
        self.assertIn("Import", details.get("error", ""))

        metric = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.run_1)
        self.assertEqual(metric.signal_score, 0.0)
        self.assertIn("Import", metric.signal_score_details.get("error", ""))


class SignalScoreEndToEndPipelineTests(TestCase):
    """
    Comprehensive End-to-End Pipeline & Integration Test Suite for Step 6: Signal Score Engine.
    Validates state machine progression, sandboxed calculation across papers, matrix payload generation,
    and responsive email digest rendering with signal score KPIs.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username="e2e_lead", email="lead@schwarz.de")

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

        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit Score",
            exit_metrics="fit_score",
            system_prompt="Extract relevance fit (1-10)",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        self.def_novelty = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            exit_metrics="novelty_score",
            system_prompt="Extract novelty (1-10)",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            exit_metrics="trl_level",
            system_prompt="Extract TRL level (1-9)",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )

        Subscriber.objects.create(
            workspace=self.workspace,
            email="tech_lead@schwarz.de",
            name="Tech Lead",
            is_active=True
        )

    def test_full_e2e_pipeline_orchestration_with_signal_score(self):
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

        paper_high = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Fault-Tolerant Surface Code Architecture on Transmon Qubits",
            authors="Alice Quantum et al.",
            arxiv_id="2402.11111",
            abstract="Experimental realization of distance-3 surface codes."
        )
        PaperMetric.objects.create(paper=paper_high, pipeline_run=pipeline_run, workspace=self.workspace, screening_status="full_text_passed")
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

        paper_low = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Introductory Review of Qubit Gates",
            authors="Bob Beginner",
            arxiv_id="2402.22222",
            abstract="Textbook tutorial on Hadamard and CNOT gates."
        )
        PaperMetric.objects.create(paper=paper_low, pipeline_run=pipeline_run, workspace=self.workspace, screening_status="full_text_passed")
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

        ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="extraction",
            component_name="parameter_extraction",
            status="completed"
        )
        agent_process.current_step = "extraction"
        agent_process.save(update_fields=['current_step'])

        tick_agent_process(str(agent_process.id))

        agent_process.refresh_from_db()
        pipeline_run.refresh_from_db()
        self.assertEqual(agent_process.status, "completed")
        self.assertEqual(agent_process.current_step, "completed")
        self.assertEqual(pipeline_run.status, "completed")

        sig_comp_run = ComponentRun.objects.get(pipeline_run=pipeline_run, step_type="signal_score")
        self.assertEqual(sig_comp_run.status, "completed")
        self.assertEqual(sig_comp_run.metrics["scored_count"], 2)
        self.assertAlmostEqual(sig_comp_run.metrics["avg_signal_score"], (95.5 + 12.0) / 2.0, places=2)

        metric_high = PaperMetric.objects.get(paper=paper_high, pipeline_run=pipeline_run)
        metric_low = PaperMetric.objects.get(paper=paper_low, pipeline_run=pipeline_run)
        self.assertEqual(metric_high.signal_score, 95.5)
        self.assertEqual(metric_low.signal_score, 12.0)

        matrix_res = json.loads(get_paper_extractions_matrix_logic(
            user=self.user,
            pipeline_run_id=str(pipeline_run.id)
        ))
        self.assertEqual(matrix_res["total_papers"], 2)
        self.assertEqual(matrix_res["avg_signal_score"], 53.75)
        self.assertEqual(matrix_res["top_signal_score"], 95.5)

        status_res = json.loads(get_pipeline_run_status_logic(
            user=self.user,
            pipeline_run_id=str(pipeline_run.id)
        ))
        self.assertEqual(status_res["status"], "completed")

        payload = build_pipeline_run_digest_payload(pipeline_run)
        ctx = payload["context"]
        self.assertEqual(ctx["avg_signal_score"], "53.75")
        self.assertEqual(ctx["top_signal_score"], "95.50")
        self.assertEqual(len(ctx["papers_data"]), 2)

    def test_manual_trigger_signal_score_job_tool(self):
        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            current_stage="extraction"
        )
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Quantum Annealing Benchmark"
        )
        PaperMetric.objects.create(paper=paper, pipeline_run=pipeline_run, workspace=self.workspace, screening_status="accepted")
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

        metric = PaperMetric.objects.get(paper=paper, pipeline_run=pipeline_run)
        self.assertEqual(metric.signal_score, 12.0)
        self.assertEqual(metric.pipeline_run, pipeline_run)

    def test_paper_metrics_isolation_across_multiple_runs(self):
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
            title="Neuromorphic Vision Transformers"
        )
        PaperMetric.objects.create(paper=paper, pipeline_run=run1, workspace=self.workspace, screening_status="accepted")

        ext1 = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": "9.0"}
        )
        score1, _ = compute_paper_signal_score(paper, custom_code="return fit_score * 10.0", pipeline_run=run1)
        self.assertEqual(score1, 90.0)

        score2, _ = compute_paper_signal_score(paper, custom_code="return fit_score * 2.0", pipeline_run=run2)
        self.assertEqual(score2, 18.0)

        metrics = PaperMetric.objects.filter(paper=paper).order_by("created_at")
        self.assertEqual(metrics.count(), 2)

        metric_run1 = PaperMetric.objects.get(paper=paper, pipeline_run=run1)
        self.assertEqual(metric_run1.signal_score, 90.0)
        metric_run2 = PaperMetric.objects.get(paper=paper, pipeline_run=run2)
        self.assertEqual(metric_run2.signal_score, 18.0)

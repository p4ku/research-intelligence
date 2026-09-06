import uuid
import json
from django.test import TestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    Paper,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
    ResearchAgentProcess,
)
from research_intelligence.utils.sandbox import (
    execute_sandboxed_snippet,
    SandboxSecurityError,
    SandboxExecutionError,
)
from research_intelligence.tasks.step_6_signal_score.scorer import (
    compute_paper_signal_score,
    execute_signal_score_job,
    extract_paper_parameters,
    _parse_numeric_value,
    _sanitize_identifier,
)

User = get_user_model()


class SandboxSecurityTests(TestCase):
    """
    Tests ensuring the Python sandbox prevents any code escape, filesystem access,
    introspection traversal, or infinite loop hanging.
    """

    def test_block_import_os(self):
        code = "import os\nreturn os.system('echo 1')"
        with self.assertRaises(SandboxSecurityError):
            execute_sandboxed_snippet(code, {"x": 1})

    def test_block_from_import(self):
        code = "from subprocess import Popen\nreturn 1"
        with self.assertRaises(SandboxSecurityError):
            execute_sandboxed_snippet(code, {"x": 1})

    def test_block_dunder_class_traversal(self):
        code = "return ().__class__.__bases__[0].__subclasses__()"
        with self.assertRaises(SandboxSecurityError):
            execute_sandboxed_snippet(code, {"x": 1})

    def test_block_builtins_escape(self):
        code = "return __builtins__['open']('/etc/passwd')"
        with self.assertRaises(SandboxSecurityError):
            execute_sandboxed_snippet(code, {"x": 1})

    def test_block_forbidden_functions(self):
        forbidden_snippets = [
            "open('/tmp/test', 'w')",
            "eval('1 + 1')",
            "exec('a = 1')",
            "compile('1+1', '', 'eval')",
            "getattr(math, 'sqrt')",
            "globals()",
            "locals()",
            "vars()",
        ]
        for snip in forbidden_snippets:
            with self.subTest(snippet=snip):
                with self.assertRaises((SandboxSecurityError, SandboxExecutionError)):
                    execute_sandboxed_snippet(snip, {"x": 1})

    def test_infinite_loop_timeout_protection(self):
        code = "while True:\n    pass\nreturn 1"
        with self.assertRaises(SandboxExecutionError) as ctx:
            execute_sandboxed_snippet(code, {"x": 1})
        self.assertIn("loop limit", str(ctx.exception).lower())

    def test_block_huge_power(self):
        code = "return 9 ** 999"
        with self.assertRaises(SandboxSecurityError) as ctx:
            execute_sandboxed_snippet(code, {"x": 1})
        self.assertIn("exponent exceeds safety limit", str(ctx.exception).lower())

    def test_block_unbounded_comprehension(self):
        code = "return sum([i for i in range(1000000)])"
        with self.assertRaises(SandboxSecurityError) as ctx:
            execute_sandboxed_snippet(code, {"x": 1})
        self.assertIn("comprehension range exceeds safety limit", str(ctx.exception).lower())

    def test_block_string_replication_bomb(self):
        code = "return len('a' * 50000)"
        with self.assertRaises(SandboxSecurityError) as ctx:
            execute_sandboxed_snippet(code, {"x": 1})
        self.assertIn("string replication exceeds safety limit", str(ctx.exception).lower())

    def test_execution_timeout_enforcement(self):
        # Snippet with many iterations below loop guard (10000) that exceeds a short timeout
        code = """
s = 0
for i in range(9000):
    for j in range(9000):
        s += 1
return float(s)
"""
        with self.assertRaises(SandboxExecutionError) as ctx:
            execute_sandboxed_snippet(code, {"x": 1}, timeout_seconds=0.2)
        self.assertTrue("timed out" in str(ctx.exception).lower() or "loop limit" in str(ctx.exception).lower())



class SandboxCalculationTests(TestCase):
    """
    Tests validating calculation logic, multi-variable formulas, string parsing,
    and user-specified conditionals.
    """

    def test_user_requested_example_snippet(self):
        # Snippet specified in user request:
        snippet = """
k = fit_score + 2 * novelty_score + trl_level
if k > 10:
    return 5
else:
    return 99
"""
        # Case 1: k = 4 + (2 * 3) + 2 = 12 > 10 -> return 5
        res1 = execute_sandboxed_snippet(snippet, {
            "fit_score": 4.0,
            "novelty_score": 3.0,
            "trl_level": 2.0
        })
        self.assertEqual(res1, 5.0)

        # Case 2: k = 1 + (2 * 1) + 1 = 4 <= 10 -> return 99
        res2 = execute_sandboxed_snippet(snippet, {
            "fit_score": 1.0,
            "novelty_score": 1.0,
            "trl_level": 1.0
        })
        self.assertEqual(res2, 99.0)

    def test_simple_arithmetic_expression(self):
        code = "w1 * 0.3 + w2 * 0.7"
        res = execute_sandboxed_snippet(code, {"w1": 10.0, "w2": 20.0})
        self.assertAlmostEqual(res, 17.0)

    def test_assignment_to_score_variable(self):
        code = "score = (fit_score * 10) + 5"
        res = execute_sandboxed_snippet(code, {"fit_score": 8.0})
        self.assertEqual(res, 85.0)

    def test_math_library_functions(self):
        code = "return math.sqrt(novelty) + abs(-10) + round(3.7)"
        res = execute_sandboxed_snippet(code, {"novelty": 16.0})
        self.assertEqual(res, 18.0)

    def test_safe_builtins_collection_functions(self):
        code = "return max([fit_score, novelty_score, trl_level]) + min(1, 2, 3)"
        result = execute_sandboxed_snippet(code, {"fit_score": 5.0, "novelty_score": 8.0, "trl_level": 4.0})
        self.assertEqual(result, 9.0)

    def test_complex_multi_branch_conditional_formula(self):
        code = """
if trl_level < 3:
    score = 0.0
elif trl_level >= 7 and fit_score >= 8.0:
    score = 100.0 * (1.1 if novelty_score > 7 else 1.0)
else:
    score = 50.0 + 5.0 * novelty_score
return round(score, 1)
"""
        # Branch 1
        res1 = execute_sandboxed_snippet(code, {"trl_level": 2, "fit_score": 9.0, "novelty_score": 8.0})
        self.assertEqual(res1, 0.0)

        # Branch 2
        res2 = execute_sandboxed_snippet(code, {"trl_level": 7, "fit_score": 8.5, "novelty_score": 8.0})
        self.assertEqual(res2, 110.0)

        # Branch 3
        res3 = execute_sandboxed_snippet(code, {"trl_level": 5, "fit_score": 6.0, "novelty_score": 6.0})
        self.assertEqual(res3, 80.0)

    def test_fallback_when_code_is_empty(self):
        res = execute_sandboxed_snippet("", {"a": 10.0, "b": 25.0})
        self.assertEqual(res, 35.0)

    def test_explicit_function_with_specific_parameters(self):
        code = """def compute_signal_score(fit_score, novelty_score):
    return fit_score * 0.6 + novelty_score * 0.4"""
        res = execute_sandboxed_snippet(code, {"fit_score": 10.0, "novelty_score": 5.0})
        self.assertEqual(res, 8.0)

    def test_explicit_function_preceded_by_comments_and_helpers(self):
        code = """# Scientific scoring algorithm
def clamp(val):
    return max(0.0, min(10.0, val))

def compute_signal_score(fit_score, trl_level):
    return clamp(fit_score) * 2.0 + trl_level"""
        res = execute_sandboxed_snippet(code, {"fit_score": 4.0, "trl_level": 3.0})
        self.assertEqual(res, 11.0)


    def test_helper_numeric_parser(self):
        self.assertEqual(_parse_numeric_value("4"), 4.0)
        self.assertEqual(_parse_numeric_value("TRL 4"), 4.0)
        self.assertEqual(_parse_numeric_value("85%"), 0.85)
        self.assertEqual(_parse_numeric_value("Level 7.5 (High)"), 7.5)
        self.assertEqual(_parse_numeric_value(None), 0.0)
        self.assertEqual(_parse_numeric_value("-"), 0.0)

    def test_helper_identifier_sanitizer(self):
        self.assertEqual(_sanitize_identifier("TRL Level"), "trl_level")
        self.assertEqual(_sanitize_identifier("Fit-Score (0-100)"), "fit_score_0_100")
        self.assertEqual(_sanitize_identifier("1st Parameter"), "v_1st_parameter")


class SignalScoreTaskTests(TestCase):
    """
    Tests verifying Step 6 Celery task, Paper parameter extraction, and model persistence.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="signal_tester", email="tester@example.com")
        self.workspace = Workspace.objects.create(
            name="Materials Lab",
            signal_score_code="""
k = fit_score + 2 * novelty_score + trl_level
if k > 10:
    return 100.0
else:
    return 50.0
"""
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="extraction"
        )
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit Score",
            exit_metrics="fit_score",
            system_prompt="Extract fit",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        self.def_novelty = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            exit_metrics="novelty_score",
            system_prompt="Extract novelty",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            exit_metrics="trl_level",
            system_prompt="Extract TRL",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="High Temperature Superconducting Thin Films",
            authors="Alice Doe",
            abstract="Study on high temp superconductivity."
        )
        PaperMetric.objects.create(paper=self.paper, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="full_text_passed")

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": "4"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_novelty,
            fields_data={"novelty_score": "4"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_trl,
            fields_data={"trl_level": "TRL 4"}
        )

    def test_extract_paper_parameters(self):
        params = extract_paper_parameters(self.paper)
        self.assertEqual(params["fit_score"], 4.0)
        self.assertEqual(params["novelty_score"], 4.0)
        self.assertEqual(params["trl_level"], 4.0)

    def test_compute_paper_signal_score(self):
        score, details = compute_paper_signal_score(self.paper)
        # k = 4 + (2*4) + 4 = 16 > 10 -> returns 100.0
        self.assertEqual(score, 100.0)

        # Verify PaperMetric updated per pipeline_run
        metric = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.pipeline_run)
        self.assertEqual(metric.signal_score, 100.0)
        self.assertEqual(metric.pipeline_run, self.pipeline_run)
        self.assertIn("fit_score", metric.signal_score_details["variables"])

    def test_execute_signal_score_job(self):
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="signal_score",
            component_name="signal_score_evaluation",
            status="pending"
        )

        res = execute_signal_score_job(str(comp_run.id))
        self.assertTrue(res["success"])

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertEqual(comp_run.metrics["scored_count"], 1)
        self.assertEqual(comp_run.metrics["avg_signal_score"], 100.0)


class AgentOrchestratorSignalScoreIntegrationTests(TestCase):
    """
    Tests verifying state machine transitions from Step 5 (Extraction) -> Step 6 (Signal Score) -> Completed.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Autonomous Review Project",
            screening_llm_model="google/gemini-3.8-flash",
            signal_score_code="return fit_score * 10"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="extraction"
        )
        self.process = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            name="Test Review Agent",
            status="running",
            current_step="extraction"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Quantum Dots"
        )
        PaperMetric.objects.create(paper=self.paper, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="full_text_passed")
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit Score",
            exit_metrics="fit_score",
            response_schema={}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": "8"}
        )

    def test_state_transition_extraction_to_signal_score_to_completed(self):
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process

        # 1. Simulate Extraction step finished
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="parameter_extraction",
            status="completed"
        )

        # Tick 1: in eager test mode, triggers Step 6 (signal_score) which executes and completes
        tick_res1 = tick_agent_process(str(self.process.id))
        self.process.refresh_from_db()
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.process.status, "completed")
        self.assertEqual(self.process.current_step, "completed")
        self.assertEqual(self.pipeline_run.status, "completed")

        # Verify ComponentRun and Paper signal score
        sig_run = ComponentRun.objects.filter(pipeline_run=self.pipeline_run, step_type="signal_score").first()
        self.assertIsNotNone(sig_run)
        self.assertEqual(sig_run.status, "completed")

        metric = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.pipeline_run)
        self.assertEqual(metric.signal_score, 80.0)
        self.assertIn("fit_score", metric.signal_score_details["variables"])

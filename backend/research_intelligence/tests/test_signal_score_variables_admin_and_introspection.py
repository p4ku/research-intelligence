import json
from unittest.mock import MagicMock
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.urls import reverse

from research_intelligence.models import Workspace, ExtractionDefinition
from research_intelligence.models.workspace import get_default_signal_variables
from research_intelligence.admin import WorkspaceAdmin, SignalScoreCodeWidget
from research_intelligence.utils.sandbox import execute_sandboxed_snippet

User = get_user_model()


class SignalScoreVariablesAdminAndIntrospectionTestCase(TestCase):
    """
    Test suite verifying:
    1. Workspace signal variable introspection (screening, extraction definitions, exit metrics,
       postprocessed metrics, schemas, and runtime paper metrics).
    2. SignalScoreCodeWidget rendering (visual chips, search filter, live linter, test button).
    3. WorkspaceAdmin.test_signal_score_view AJAX sandbox dry-run execution and error handling.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(
            username="signal_admin",
            email="admin@test.com",
            password="adminpassword123"
        )
        self.site = AdminSite()
        self.workspace_admin = WorkspaceAdmin(Workspace, self.site)

        self.workspace = Workspace.objects.create(
            name="Quantum Computing Intelligence",
            abstract_acceptance_criteria="Quantum hardware and error mitigation",
            signal_score_code="return round(0.6 * fit_score + 0.4 * novelty_score, 4)"
        )

        # Create extraction definitions with multiple exit metrics, schemas, and postprocessing rules
        self.ext_def_1 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Qubit Fidelity & Gate Count",
            system_prompt="Extract qubit metrics",
            exit_metrics=["qubit_count", "two_qubit_gate_fidelity"],
            postprocessing_code="log_transform = math.log(qubit_count)",
            response_schema={
                "type": "object",
                "properties": {
                    "processor_name": {"type": "string"},
                    "error_rate": {"type": "number"}
                }
            }
        )

        self.ext_def_2 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Technology Readiness Level",
            system_prompt="Extract TRL",
            exit_metrics=["trl_score"],
            response_schema={
                "type": "object",
                "properties": {
                    "commercial_maturity": {"type": "string"}
                }
            }
        )

    def test_get_default_signal_variables(self):
        """Verify default signals contain screening metrics."""
        defaults = get_default_signal_variables()
        var_names = [d["name"] for d in defaults]

        self.assertIn("fit_score", var_names)
        self.assertIn("novelty_score", var_names)

        # Check screening category
        fit_item = next(d for d in defaults if d["name"] == "fit_score")
        self.assertEqual(fit_item["category"], "Screening Exit Metric")
        self.assertIn("float", fit_item["type"].lower())

    def test_workspace_get_available_signal_variables_introspection(self):
        """Verify workspace introspection deduces all extraction slugs, exit metrics, postprocessed metrics, and schemas."""
        signals = self.workspace.get_available_signal_variables()
        var_names = [s["name"] for s in signals]

        # 1. Screening metrics
        self.assertIn("fit_score", var_names)
        self.assertIn("novelty_score", var_names)

        # 2. Sanitized extraction definition slugs
        self.assertIn("qubit_fidelity_gate_count", var_names)
        self.assertIn("technology_readiness_level", var_names)

        # 3. Multi exit metrics
        self.assertIn("qubit_count", var_names)
        self.assertIn("two_qubit_gate_fidelity", var_names)
        self.assertIn("trl_score", var_names)

        # 4. Postprocessed metric variations
        self.assertIn("qubit_fidelity_gate_count_postprocessed", var_names)
        self.assertIn("qubit_fidelity_gate_count_computed", var_names)
        self.assertIn("qubit_count_postprocessed", var_names)

        # 5. Schema properties
        self.assertIn("processor_name", var_names)
        self.assertIn("error_rate", var_names)
        self.assertIn("commercial_maturity", var_names)

        # Verify category assignments
        trl_item = next(s for s in signals if s["name"] == "trl_score")
        self.assertEqual(trl_item["category"], "Exit Metric")

        ext_item = next(s for s in signals if s["name"] == "technology_readiness_level")
        self.assertEqual(ext_item["category"], "Extraction Definition")

        post_item = next(s for s in signals if s["name"] == "qubit_count_postprocessed")
        self.assertEqual(post_item["category"], "Postprocessed Metric")

        schema_item = next(s for s in signals if s["name"] == "error_rate")
        self.assertEqual(schema_item["category"], "Schema Property")

    def test_workspace_get_signal_score_prompt_snapshot(self):
        """Verify the prompt snapshot generator incorporates extraction-scoped scoring variables."""
        snapshot = self.workspace.get_signal_score_prompt_snapshot()
        var_names = [v["variable_name"] for v in snapshot.get("scoring_variables", [])]
        self.assertIn("qubit_count", var_names)
        self.assertIn("trl_score", var_names)
        self.assertIn("two_qubit_gate_fidelity", var_names)
        self.assertIn("qubit_count_postprocessed", var_names)
        self.assertTrue(snapshot.get("has_custom_formula"))

    def test_signal_score_code_widget_rendering(self):
        """Verify SignalScoreCodeWidget renders categorized chips, search filter, test button, and linter."""
        widget = SignalScoreCodeWidget(workspace=self.workspace)
        rendered_html = widget.render(
            name="signal_score_code",
            value="return 0.5 * fit_score + 0.5 * qubit_count",
            attrs={"id": "id_signal_score_code"}
        )

        # Visual chips
        self.assertIn('data-var="fit_score"', rendered_html)
        self.assertIn('data-var="qubit_count"', rendered_html)
        self.assertIn('data-var="two_qubit_gate_fidelity"', rendered_html)
        self.assertIn('data-var="trl_score"', rendered_html)

        # Click insertion handler
        self.assertIn("window.insertSignalVar", rendered_html)

        # Real-time linter container
        self.assertIn("id_signal_score_code_linter_box", rendered_html)
        self.assertIn("runLiveLinter", rendered_html)

        # Test execution button & result box
        self.assertIn("id_signal_score_code_test_btn", rendered_html)
        self.assertIn("id_signal_score_code_test_result", rendered_html)
        self.assertIn("window.testSignalFormula", rendered_html)

        # Schema details table
        self.assertIn("Available Variables & Signals for this Workspace", rendered_html)
        self.assertIn("View Schema Table", rendered_html)
        self.assertIn("filterSignalVars", rendered_html)

        # Inline extractions dynamic observer
        self.assertIn("observeInlineExtractions", rendered_html)

    def test_test_signal_score_view_valid_execution(self):
        """Verify successful sandbox dry run with valid formula returns 200 and numeric score."""
        payload = {
            "code": "return round(0.7 * fit_score + 0.3 * novelty_score, 3)",
            "mock_variables": {}
        }
        request = self.factory.post(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertTrue(data["success"])
        self.assertIsInstance(data["score"], (int, float))
        self.assertIn("execution_time_ms", data)
        self.assertIn("variables_evaluated", data)
        # 0.7 * 8.5 + 0.3 * 7.0 = 5.95 + 2.1 = 8.05
        self.assertAlmostEqual(data["score"], 8.05, places=2)

    def test_test_signal_score_view_with_custom_extraction_and_exit_metrics(self):
        """Verify formulas using custom deduced extraction metrics execute accurately."""
        payload = {
            "code": "return round(qubit_count * 0.01 + two_qubit_gate_fidelity * 10.0 + trl_score, 2)",
            "mock_variables": {
                "qubit_count": 100,
                "two_qubit_gate_fidelity": 0.995,
                "trl_score": 4.0
            }
        }
        request = self.factory.post(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertTrue(data["success"])
        # 100 * 0.01 + 0.995 * 10 + 4.0 = 1.0 + 9.95 + 4.0 = 14.95
        self.assertAlmostEqual(data["score"], 14.95, places=2)

    def test_test_signal_score_view_with_math_library(self):
        """Verify standard safe math operations succeed in the sandbox without explicit imports."""
        payload = {
            "code": "score = math.sqrt(fit_score) + math.log10(100)\nreturn round(score, 3)",
            "mock_variables": {"fit_score": 0.64}
        }
        request = self.factory.post(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertTrue(data["success"])
        # sqrt(0.64) + log10(100) = 0.8 + 2.0 = 2.8
        self.assertAlmostEqual(data["score"], 2.8, places=2)

    def test_test_signal_score_view_syntax_error(self):
        """Verify syntax errors return structured error response with success=False."""
        payload = {
            "code": "def invalid_syntax(\nreturn 123",
            "mock_variables": {}
        }
        request = self.factory.post(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertFalse(data["success"])
        self.assertIn("error", data)
        self.assertIn(data["error_type"], ["SyntaxError", "SandboxExecutionError", "SandboxSecurityError"])

    def test_test_signal_score_view_runtime_division_by_zero(self):
        """Verify division by zero is safely handled by sandbox fallback defaulting to 0.0."""
        payload = {
            "code": "return fit_score / 0",
            "mock_variables": {}
        }
        request = self.factory.post(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertTrue(data["success"])
        self.assertEqual(data["score"], 0.0)

    def test_test_signal_score_view_runtime_exception(self):
        """Verify unhandled runtime exceptions return structured diagnostic output with success=False."""
        payload = {
            "code": "return int('invalid_number_string')",
            "mock_variables": {}
        }
        request = self.factory.post(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertFalse(data["success"])
        self.assertIn("SandboxExecutionError", [data["error_type"], type(data.get("error")).__name__])

    def test_test_signal_score_view_forbidden_security_violation(self):
        """Verify forbidden imports or AST operations trigger SandboxSecurityError."""
        payload = {
            "code": "import os\nos.system('echo test')\nreturn 1.0",
            "mock_variables": {}
        }
        request = self.factory.post(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertFalse(data["success"])
        self.assertIn("SandboxSecurityError", [data["error_type"], type(data.get("error")).__name__])

    def test_test_signal_score_view_non_numeric_score(self):
        """Verify non-numeric returns are rejected."""
        payload = {
            "code": "return {'some': 'dict'}",
            "mock_variables": {}
        }
        request = self.factory.post(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertFalse(data["success"])
        self.assertIn("non-numeric", data["error"].lower())

    def test_test_signal_score_view_empty_code(self):
        """Verify empty code payload returns EmptyCodeError."""
        payload = {"code": "   "}
        request = self.factory.post(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertFalse(data["success"])
        self.assertEqual(data["error_type"], "EmptyCodeError")

    def test_test_signal_score_view_method_not_allowed(self):
        """Verify GET request to test endpoint returns 405."""
        request = self.factory.get(
            f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/"
        )
        request.user = self.admin_user

        response = self.workspace_admin.test_signal_score_view(request, object_id=str(self.workspace.pk))
        self.assertEqual(response.status_code, 405)

    def test_test_signal_score_url_resolution(self):
        """Verify the custom admin URLs reverse properly for both workspace specific and generic routes."""
        url_specific = reverse('admin:research_intelligence_workspace_test_signal_score', args=[str(self.workspace.pk)])
        self.assertTrue(url_specific.endswith(f"/workspace/{self.workspace.pk}/test-signal-score/"))

        url_generic = reverse('admin:research_intelligence_workspace_test_signal_score_generic')
        self.assertTrue(url_generic.endswith("/workspace/test-signal-score/"))

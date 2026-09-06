import json
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite

from research_intelligence.models import Workspace, ExtractionDefinition
from research_intelligence.models.extraction import get_default_postprocessing_variables
from research_intelligence.admin import ExtractionDefinitionAdmin, PostprocessingCodeWidget

User = get_user_model()


class PostprocessingVariablesIntrospectionAndAdminTests(TestCase):
    """
    Tests validating ExtractionDefinition postprocessing variables introspection,
    PostprocessingCodeWidget HTML rendering, and the test_postprocessing_view AJAX endpoint.
    """

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin_tester",
            email="admin@example.com",
            password="admin_secret_password"
        )
        self.workspace = Workspace.objects.create(
            name="Quantum Computing Workspace"
        )
        self.extraction_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Methodology & Rigour",
            response_schema={
                "type": "object",
                "properties": {
                    "rigour_score": {
                        "type": "number",
                        "description": "Scientific rigour assessment (1-10)"
                    },
                    "methodology_type": {
                        "type": "string",
                        "description": "Classification of methodology"
                    },
                    "is_empirical": {
                        "type": "boolean",
                        "description": "Whether experimental validation is present"
                    },
                    "key_findings": {
                        "type": "array",
                        "description": "List of core research findings"
                    },
                    "metadata_details": {
                        "type": "object",
                        "description": "Nested methodology parameters"
                    }
                },
                "required": ["rigour_score", "methodology_type"]
            },
            exit_metrics="rigour_score, empirical_index",
            postprocessing_code="return round(rigour_score * 1.5, 2)"
        )
        self.site = AdminSite()
        self.admin = ExtractionDefinitionAdmin(ExtractionDefinition, self.site)
        self.factory = RequestFactory()

    def test_get_available_postprocessing_variables_deduction(self):
        """Verifies that variables are properly deduced from response_schema, exit_metrics, context, and dicts."""
        vars_list = self.extraction_def.get_available_postprocessing_variables()
        var_names = {v["name"] for v in vars_list}

        # 1. Schema properties
        self.assertIn("rigour_score", var_names)
        self.assertIn("methodology_type", var_names)
        self.assertIn("is_empirical", var_names)
        self.assertIn("key_findings", var_names)
        self.assertIn("metadata_details", var_names)

        # 2. Exit metrics
        self.assertIn("empirical_index", var_names)

        # 3. Paper metadata context
        self.assertIn("title", var_names)
        self.assertIn("abstract", var_names)
        self.assertIn("arxiv_id", var_names)
        self.assertIn("doi", var_names)

        # 4. Extracted fields dictionaries
        self.assertIn("fields", var_names)
        self.assertIn("data", var_names)
        self.assertIn("extractions", var_names)
        self.assertIn("fields_data", var_names)
        self.assertIn("json_data", var_names)
        self.assertIn("raw_data", var_names)

        # Check category mappings
        cat_map = {v["name"]: v["category"] for v in vars_list}
        self.assertEqual(cat_map["rigour_score"], "Schema Property")
        self.assertEqual(cat_map["empirical_index"], "Exit Metric")
        self.assertEqual(cat_map["title"], "Paper Metadata Context")
        self.assertEqual(cat_map["fields"], "Extracted Fields Dictionary")

    def test_get_default_postprocessing_variables(self):
        """Verifies default candidate variables fallback when no specific schema is configured."""
        default_vars = get_default_postprocessing_variables()
        default_names = {v["name"] for v in default_vars}

        self.assertIn("score", default_names)
        self.assertIn("confidence", default_names)
        self.assertIn("category", default_names)
        self.assertIn("title", default_names)
        self.assertIn("abstract", default_names)
        self.assertIn("fields", default_names)
        self.assertIn("data", default_names)

    def test_postprocessing_code_widget_render(self):
        """Verifies PostprocessingCodeWidget HTML includes chips, linter, table, and test runner."""
        widget = PostprocessingCodeWidget(extraction_definition=self.extraction_def)
        html = widget.render(name="postprocessing_code", value="return rigour_score * 2.0")

        self.assertIn("Available Variables & Context for Postprocessing", html)
        self.assertIn("sri-postprocess-chip", html)
        self.assertIn("rigour_score", html)
        self.assertIn("methodology_type", html)
        self.assertIn("Test Postprocessing Code (Dry Run)", html)
        self.assertIn("AST Sandbox Guard", html)
        self.assertIn("View Schema Table", html)
        self.assertIn("observeResponseSchema", html)

    def test_ajax_test_postprocessing_view_success_scalar(self):
        """Verifies test_postprocessing_view executes valid scalar formula successfully."""
        request = self.factory.post(
            f"/admin/research_intelligence/extractiondefinition/{self.extraction_def.pk}/test-postprocessing/",
            data=json.dumps({"code": "return round(rigour_score * 1.5, 2)"}),
            content_type="application/json"
        )
        request.user = self.user

        response = self.admin.test_postprocessing_view(request, object_id=str(self.extraction_def.pk))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode("utf-8"))

        self.assertTrue(data["success"])
        # rigour_score default is 8.5 -> 8.5 * 1.5 = 12.75
        self.assertEqual(data["result"], 12.75)
        self.assertIn("rigour_score", data["fields_evaluated"])
        self.assertGreater(data["execution_time_ms"], 0.0)

    def test_ajax_test_postprocessing_view_success_dict(self):
        """Verifies test_postprocessing_view executes snippet returning a dictionary payload."""
        code = """
return {
    "computed_score": rigour_score * 2,
    "method": methodology_type,
    "is_empirical": is_empirical
}
"""
        request = self.factory.post(
            f"/admin/research_intelligence/extractiondefinition/{self.extraction_def.pk}/test-postprocessing/",
            data=json.dumps({"code": code}),
            content_type="application/json"
        )
        request.user = self.user

        response = self.admin.test_postprocessing_view(request, object_id=str(self.extraction_def.pk))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode("utf-8"))

        self.assertTrue(data["success"])
        self.assertIsInstance(data["result"], dict)
        self.assertEqual(data["result"]["computed_score"], 17.0)
        self.assertEqual(data["result"]["method"], "sample_methodology_type")
        self.assertTrue(data["result"]["is_empirical"])

    def test_ajax_test_postprocessing_view_with_context_and_dict_alias(self):
        """Verifies access to paper metadata (title) and dictionary container (fields)."""
        code = """
return len(title) + fields['rigour_score']
"""
        request = self.factory.post(
            f"/admin/research_intelligence/extractiondefinition/{self.extraction_def.pk}/test-postprocessing/",
            data=json.dumps({"code": code}),
            content_type="application/json"
        )
        request.user = self.user

        response = self.admin.test_postprocessing_view(request, object_id=str(self.extraction_def.pk))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode("utf-8"))

        self.assertTrue(data["success"])
        self.assertGreater(data["result"], 0)

    def test_ajax_test_postprocessing_view_dynamic_client_schema(self):
        """Verifies dry-run evaluation using client-provided dynamic schema from unsaved form."""
        custom_schema = {
            "type": "object",
            "properties": {
                "quantum_fidelity": {"type": "number"},
                "gate_error_rate": {"type": "number"}
            }
        }
        code = "return quantum_fidelity - gate_error_rate"

        request = self.factory.post(
            "/admin/research_intelligence/extractiondefinition/test-postprocessing/",
            data=json.dumps({
                "code": code,
                "schema": custom_schema
            }),
            content_type="application/json"
        )
        request.user = self.user

        response = self.admin.test_postprocessing_view(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode("utf-8"))

        self.assertTrue(data["success"])
        self.assertIn("quantum_fidelity", data["fields_evaluated"])
        self.assertIn("gate_error_rate", data["fields_evaluated"])

    def test_ajax_test_postprocessing_view_empty_code(self):
        """Verifies error response when empty code snippet is provided."""
        request = self.factory.post(
            f"/admin/research_intelligence/extractiondefinition/{self.extraction_def.pk}/test-postprocessing/",
            data=json.dumps({"code": "   "}),
            content_type="application/json"
        )
        request.user = self.user

        response = self.admin.test_postprocessing_view(request, object_id=str(self.extraction_def.pk))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode("utf-8"))

        self.assertFalse(data["success"])
        self.assertEqual(data["error_type"], "EmptyCodeError")

    def test_ajax_test_postprocessing_view_security_restriction(self):
        """Verifies forbidden operations like importing os or builtins are rejected."""
        malicious_code = "import os; return os.name"
        request = self.factory.post(
            f"/admin/research_intelligence/extractiondefinition/{self.extraction_def.pk}/test-postprocessing/",
            data=json.dumps({"code": malicious_code}),
            content_type="application/json"
        )
        request.user = self.user

        response = self.admin.test_postprocessing_view(request, object_id=str(self.extraction_def.pk))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode("utf-8"))

        self.assertFalse(data["success"])
        self.assertEqual(data["error_type"], "SandboxSecurityError")

from research_intelligence.models import Workspace
from mcp_server.tools import (
    create_workspace_logic,
    get_workspace_logic,
    update_workspace_logic,
    add_workspace_member_logic,
)
from .base import BaseMCPTestCase


class MCPWorkspacesTestCase(BaseMCPTestCase):
    def test_workspace_crud_and_membership_roles(self):
        res = self.parse_res(create_workspace_logic(
            self.admin,
            name="Quantum Computing Review",
            abstract_acceptance_criteria=["Quantum hardware", "Qubits > 50"],
            abstract_rejection_criteria=["Classical simulation only"],
            screening_llm_model="google/gemini-3.7-flash"
        ))
        self.assertEqual(res["status"], "success")
        ws_id = res["workspace_id"]

        ws = Workspace.objects.get(id=ws_id)
        self.assertEqual(ws.name, "Quantum Computing Review")
        self.assertEqual(ws.get_abstract_acceptance_criteria(), "Quantum hardware\nQubits > 50")
        self.assertEqual(ws.get_abstract_rejection_criteria(), "Classical simulation only")
        self.assertIsNone(ws.ocr_provider)

        mem_res = self.parse_res(add_workspace_member_logic(
            self.admin,
            workspace_id=ws_id,
            target_username=self.researcher.username,
            role="researcher"
        ))
        self.assertEqual(mem_res["status"], "success")

        ws_details = self.parse_res(get_workspace_logic(self.researcher, workspace_id=ws_id))
        self.assertEqual(ws_details["name"], "Quantum Computing Review")
        self.assertEqual(len(ws_details["members"]), 2)

        up_res = self.parse_res(update_workspace_logic(
            self.admin,
            workspace_id=ws_id,
            name="Advanced Quantum Computing Review",
            ocr_provider="pypdf"
        ))
        self.assertEqual(up_res["status"], "success")

        ws.refresh_from_db()
        self.assertEqual(ws.name, "Advanced Quantum Computing Review")
        self.assertEqual(ws.ocr_provider, "pypdf")

    def test_workspace_ocr_provider_default_and_normalization(self):
        res = self.parse_res(create_workspace_logic(self.admin, name="No OCR WS", ocr_provider=None))
        ws_id = res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)
        self.assertIsNone(ws.ocr_provider)

        update_workspace_logic(self.admin, workspace_id=ws_id, ocr_provider="none")
        ws.refresh_from_db()
        self.assertIsNone(ws.ocr_provider)

    def test_workspace_dynamic_screening_crud(self):
        res = self.parse_res(create_workspace_logic(
            self.admin,
            name="Criteria Test Workspace",
            abstract_acceptance_criteria=["Must test in vitro"],
            abstract_rejection_criteria=["Review papers"],
            full_text_acceptance_criteria=["Must report IC50 in nM"],
            full_text_rejection_criteria=["No numerical data reported"]
        ))
        ws = Workspace.objects.get(id=res["workspace_id"])
        self.assertEqual(ws.get_abstract_acceptance_criteria(), "Must test in vitro")
        self.assertEqual(ws.get_full_text_acceptance_criteria(), "Must report IC50 in nM")

        update_workspace_logic(
            self.admin,
            workspace_id=str(ws.id),
            abstract_acceptance_criteria=["Must test in vivo"],
            full_text_acceptance_criteria=["Must report Kd < 100nM"]
        )
        ws.refresh_from_db()
        self.assertEqual(ws.get_abstract_acceptance_criteria(), "Must test in vivo")
        self.assertEqual(ws.get_full_text_acceptance_criteria(), "Must report Kd < 100nM")

    def test_workspace_token_and_cost_recording(self):
        ws_res = self.parse_res(create_workspace_logic(self.admin, name="Token Metric Test WS"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)

        cost1 = ws.record_token_usage(tokens_in=1000000, tokens_out=1000000, model_name="gemini-3.7-flash")
        self.assertEqual(cost1, 4.5)
        self.assertEqual(ws.tokens_consumed_this_month, 2000000)
        self.assertEqual(float(ws.usd_spent_this_month), 4.5)

    def test_workspace_signal_score_code_mcp_lifecycle(self):
        ws_res = self.parse_res(create_workspace_logic(
            self.admin,
            name="Signal Code WS",
            signal_score_code="score = 0.5 * fit + 0.5 * novelty\nreturn score"
        ))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)
        self.assertIn("score = 0.5", ws.signal_score_code)

        update_workspace_logic(self.admin, workspace_id=ws_id, signal_score_code="score = 0.9 * fit\nreturn score")
        ws.refresh_from_db()
        self.assertIn("score = 0.9", ws.signal_score_code)

    def test_unauthorized_outsider_access_denied(self):
        ws_res = self.parse_res(create_workspace_logic(self.admin, name="Private Lab"))
        ws_id = ws_res["workspace_id"]

        get_res = get_workspace_logic(self.outsider, workspace_id=ws_id)
        self.assertIn("Error: Access denied", get_res)

    def test_workspace_advanced_prompts_and_quotas_persistence(self):
        res = self.parse_res(create_workspace_logic(
            self.admin,
            name="Advanced Prompts WS",
            abstract_screening_system_prompt="Custom System Prompt for Abstract",
            abstract_screening_user_prompt_template="Custom Template: {title}",
            abstract_screening_response_schema={"type": "object", "properties": {"score": {"type": "number"}}},
            abstract_screening_exit_metric="score",
            full_text_screening_system_prompt="Custom FT System Prompt",
            full_text_screening_user_prompt_template="Custom FT Template: {full_text}",
            full_text_screening_response_schema={"type": "object", "properties": {"ft_score": {"type": "number"}}},
            full_text_screening_exit_metric="ft_score",
            digest_schedule="0 10 * * 1",
            monthly_token_limit=5000000,
            monthly_usd_limit=250.00
        ))
        self.assertEqual(res["status"], "success")
        ws_id = res["workspace_id"]

        ws = Workspace.objects.get(id=ws_id)
        self.assertEqual(ws.abstract_screening_system_prompt, "Custom System Prompt for Abstract")
        self.assertEqual(ws.abstract_screening_user_prompt_template, "Custom Template: {title}")
        self.assertEqual(ws.abstract_screening_response_schema, {"type": "object", "properties": {"score": {"type": "number"}}})
        self.assertEqual(ws.abstract_screening_exit_metric, "score")
        self.assertEqual(ws.full_text_screening_system_prompt, "Custom FT System Prompt")
        self.assertEqual(ws.full_text_screening_user_prompt_template, "Custom FT Template: {full_text}")
        self.assertEqual(ws.full_text_screening_response_schema, {"type": "object", "properties": {"ft_score": {"type": "number"}}})
        self.assertEqual(ws.full_text_screening_exit_metric, "ft_score")
        self.assertEqual(ws.digest_schedule, "0 10 * * 1")
        self.assertEqual(ws.monthly_token_limit, 5000000)
        self.assertEqual(float(ws.monthly_usd_limit), 250.00)

        up_res = self.parse_res(update_workspace_logic(
            self.admin,
            workspace_id=ws_id,
            abstract_screening_exit_metric="relevance_score",
            monthly_token_limit=8000000,
            cost_limit_usd=500.00
        ))
        self.assertEqual(up_res["status"], "success")

        ws.refresh_from_db()
        self.assertEqual(ws.abstract_screening_exit_metric, "relevance_score")
        self.assertEqual(ws.monthly_token_limit, 8000000)
        self.assertEqual(float(ws.monthly_usd_limit), 500.00)

    def test_create_workspace_validation_errors(self):
        # Empty name
        res_empty = self.parse_res(create_workspace_logic(self.admin, name="   "))
        self.assertEqual(res_empty["status"], "error")
        self.assertIn("name cannot be empty", res_empty["error"].lower())

        # Invalid OCR provider
        res_ocr = self.parse_res(create_workspace_logic(self.admin, name="Valid Name", ocr_provider="invalid_engine"))
        self.assertEqual(res_ocr["status"], "error")
        self.assertIn("invalid ocr_provider", res_ocr["error"].lower())

        # Invalid LLM provider
        res_llm = self.parse_res(create_workspace_logic(self.admin, name="Valid Name 2", llm_provider="unsupported_llm"))
        self.assertEqual(res_llm["status"], "error")
        self.assertIn("invalid llm_provider", res_llm["error"].lower())

    def test_create_workspace_string_criteria(self):
        res = self.parse_res(create_workspace_logic(
            self.admin,
            name="String Criteria WS",
            abstract_acceptance_criteria="Single line criteria text\nSecond line",
            abstract_rejection_criteria="Rejection criteria text"
        ))
        self.assertEqual(res["status"], "success")
        ws = Workspace.objects.get(id=res["workspace_id"])
        self.assertEqual(ws.get_abstract_acceptance_criteria(), "Single line criteria text\nSecond line")
        self.assertEqual(ws.get_abstract_rejection_criteria(), "Rejection criteria text")



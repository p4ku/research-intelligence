from research_intelligence.models import Workspace
from mcp.tools import (
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

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
            screening_llm_model="google/gemini-3.8-flash"
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

        cost1 = ws.record_token_usage(tokens_in=1000000, tokens_out=1000000, model_name="gemini-3.8-flash")
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

    def test_get_workspace_with_scrapers_and_definitions(self):
        from research_intelligence.models import Scraper, ExtractionDefinition
        ws_res = self.parse_res(create_workspace_logic(self.admin, name="Scraper WS"))
        ws_id = ws_res["workspace_id"]
        ws = Workspace.objects.get(id=ws_id)

        scraper = Scraper.objects.create(
            workspace=ws,
            provider='arxiv',
            search_query='cat:cs.AI',
            limit=30,
            is_active=True
        )

        ext_def = ExtractionDefinition.objects.create(
            workspace=ws,
            name='Test Definition',
            system_prompt='Extract metric',
            response_schema={'type': 'object'},
            llm_model='google/gemini-3.8-flash',
            is_active=True
        )

        ws_details = self.parse_res(get_workspace_logic(self.admin, workspace_id=ws_id))
        self.assertEqual(ws_details["name"], "Scraper WS")
        self.assertEqual(len(ws_details["scrapers"]), 1)
        self.assertEqual(ws_details["scrapers"][0]["scraper_id"], str(scraper.id))
        self.assertEqual(ws_details["scrapers"][0]["provider"], "arxiv")
        self.assertEqual(ws_details["scrapers"][0]["provider_name"], "arXiv")
        self.assertEqual(ws_details["scrapers"][0]["search_query"], "cat:cs.AI")
        self.assertEqual(ws_details["scrapers"][0]["limit"], 30)
        self.assertTrue(ws_details["scrapers"][0]["is_active"])

        self.assertEqual(len(ws_details["extraction_definitions"]), 1)
        self.assertEqual(ws_details["extraction_definitions"][0]["name"], "Test Definition")

    def test_workspace_reasoning_effort_mcp_lifecycle(self):
        # 1. Test default reasoning effort is 'medium'
        res = self.parse_res(create_workspace_logic(self.admin, name="Default Reasoning WS"))
        self.assertEqual(res["status"], "success")
        ws = Workspace.objects.get(id=res["workspace_id"])
        self.assertEqual(ws.reasoning_effort, "medium")

        ws_details = self.parse_res(get_workspace_logic(self.admin, workspace_id=str(ws.id)))
        self.assertEqual(ws_details["reasoning_effort"], "medium")

        # 2. Test explicit creation with reasoning_effort='high'
        res_high = self.parse_res(create_workspace_logic(
            self.admin,
            name="High Reasoning WS",
            reasoning_effort="high"
        ))
        self.assertEqual(res_high["status"], "success")
        ws_high = Workspace.objects.get(id=res_high["workspace_id"])
        self.assertEqual(ws_high.reasoning_effort, "high")

        # 3. Test update to reasoning_effort='off'
        up_res = self.parse_res(update_workspace_logic(
            self.admin,
            workspace_id=str(ws_high.id),
            reasoning_effort="off"
        ))
        self.assertEqual(up_res["status"], "success")
        ws_high.refresh_from_db()
        self.assertEqual(ws_high.reasoning_effort, "off")

        # 4. Test validation error on invalid reasoning_effort
        err_res = self.parse_res(update_workspace_logic(
            self.admin,
            workspace_id=str(ws_high.id),
            reasoning_effort="ultra_turbo"
        ))
        self.assertEqual(err_res["status"], "error")
        self.assertIn("invalid reasoning_effort", err_res["error"].lower())

    def test_workspace_skip_abstract_screening_mcp_lifecycle(self):
        res = self.parse_res(create_workspace_logic(
            self.admin,
            name="Skip Screening WS",
            skip_abstract_screening=True
        ))
        self.assertEqual(res["status"], "success")
        ws = Workspace.objects.get(id=res["workspace_id"])
        self.assertTrue(ws.skip_abstract_screening)

        ws_details = self.parse_res(get_workspace_logic(self.admin, workspace_id=str(ws.id)))
        self.assertTrue(ws_details["skip_abstract_screening"])

        up_res = self.parse_res(update_workspace_logic(
            self.admin,
            workspace_id=str(ws.id),
            skip_abstract_screening=False
        ))
        self.assertEqual(up_res["status"], "success")
        ws.refresh_from_db()
        self.assertFalse(ws.skip_abstract_screening)

    def test_workspace_schedules_nested_mcp_representation(self):
        from research_intelligence.models import WorkflowSchedule
        ws = Workspace.objects.create(name="Schedule Nesting WS")
        from research_intelligence.models import WorkspaceMember
        WorkspaceMember.objects.create(workspace=ws, user=self.admin, role="admin")

        schedule = WorkflowSchedule.objects.create(
            workspace=ws,
            name="Daily Schedule",
            frequency="daily",
            prevent_overlap=True,
            is_active=True
        )

        ws_details = self.parse_res(get_workspace_logic(self.admin, workspace_id=str(ws.id)))
        self.assertIn("schedules", ws_details)
        self.assertEqual(len(ws_details["schedules"]), 1)
        sched_data = ws_details["schedules"][0]
        self.assertEqual(sched_data["schedule_id"], str(schedule.id))
        self.assertEqual(sched_data["name"], "Daily Schedule")
        self.assertTrue(sched_data["prevent_overlap"])
        self.assertEqual(sched_data["consecutive_failures_count"], 0)
        self.assertEqual(sched_data["max_consecutive_failures"], 5)




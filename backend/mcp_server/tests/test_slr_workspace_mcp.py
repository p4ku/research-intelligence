import json
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, WorkspaceMember
from slr_review.models import SLRWorkspaceConfig, SLRProtocol
from mcp_server.tools import (
    configure_slr_workspace_logic,
    get_slr_workspace_config_logic,
    get_workspace_logic,
    list_workspaces_logic,
)
from .base import BaseMCPTestCase

User = get_user_model()


class SLRMCPWorkspaceTestCase(BaseMCPTestCase):
    """
    Test suite for SLR Workspace MCP Tools:
    - Side-by-side creation of Workspace + SLR Policy + Protocol
    - Upgrading existing standard workspace to SLR type
    - Inspection via get_slr_workspace_config and get_workspace
    - PRISMA summary generation
    - RBAC and parameter boundary validations
    """

    def parse_res(self, res_str: str) -> dict:
        return json.loads(res_str)

    def test_create_slr_workspace_side_by_side(self):
        """Verify creating a new SLR workspace provisions both base settings and SLR policy in 1 call."""
        res = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            name="Favipiravir Clinical Trials SLR",
            abstract_acceptance_criteria=["Randomized controlled trial", "Lassa or Ebola virus"],
            abstract_rejection_criteria=["In-vitro only", "Animal models"],
            full_text_acceptance_criteria=["Human patient cohort >= 20", "Mortality endpoint reported"],
            full_text_rejection_criteria=["No control group"],
            screening_llm_model="google/gemini-3.8-flash",
            llm_provider="google",
            reasoning_effort="high",
            # SLR parameters
            checkpoint_gate_mode="two_stage_split",
            enable_extraction_gate=True,
            screening_quorum_size=2,
            extraction_quorum_size=1,
            require_blind_review=True,
            sampling_mode="uncertainty_stratified",
            abstract_sample_percentage=15.0,
            full_text_sample_percentage=25.0,
            extraction_sample_percentage=10.0,
            negative_control_percentage=7.5,
            enable_rob_assessment=True,
            rob_framework="rob2",
            require_human_rob_validation=True,
            designated_arbiter=self.researcher.username,
            tie_breaker_strategy="arbiter_ruling",
            exclusion_reasons=["Wrong Target Pathogen", "Animal Model", "Insufficient Follow-up"],
            require_evidence_on_exclusion=True,
            require_evidence_on_override=True,
            notify_reviewers_on_pause=True,
            stale_queue_reminder_days=2,
            # Formal Protocol
            protocol_title="Favipiravir Efficacy in Acute Arenavirus Infections",
            protocol_review_question="Does oral Favipiravir reduce 28-day all-cause mortality compared to Ribavirin?",
            pico_population="Hospitalized patients with RT-PCR confirmed Lassa or Ebola infection",
            pico_intervention="Oral or intravenous Favipiravir",
            pico_comparison="Standard of care Ribavirin or placebo",
            pico_outcome="28-day mortality rate, viral clearance time",
            prospero_registration_id="CRD42026998877"
        ))

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["workspace_type"], "slr")
        ws_id = res["workspace_id"]

        # 1. Verify base Workspace domain model
        ws = Workspace.objects.get(id=ws_id)
        self.assertEqual(ws.name, "Favipiravir Clinical Trials SLR")
        self.assertEqual(ws.reasoning_effort, "high")
        self.assertIn("Randomized controlled trial", ws.get_abstract_acceptance_criteria())
        self.assertIn("No control group", ws.get_full_text_rejection_criteria())

        # Creator must be Workspace Admin
        membership = WorkspaceMember.objects.get(workspace=ws, user=self.admin)
        self.assertEqual(membership.role, "admin")

        # 2. Verify SLRWorkspaceConfig policy engine
        slr_cfg = SLRWorkspaceConfig.objects.get(workspace=ws)
        self.assertEqual(slr_cfg.checkpoint_gate_mode, "two_stage_split")
        self.assertEqual(slr_cfg.screening_quorum_size, 2)
        self.assertEqual(slr_cfg.extraction_quorum_size, 1)
        self.assertTrue(slr_cfg.require_blind_review)
        self.assertEqual(slr_cfg.abstract_sample_percentage, 15.0)
        self.assertEqual(slr_cfg.full_text_sample_percentage, 25.0)
        self.assertEqual(slr_cfg.negative_control_percentage, 7.5)
        self.assertEqual(slr_cfg.rob_framework, "rob2")
        self.assertEqual(slr_cfg.designated_arbiter, self.researcher)
        self.assertEqual(slr_cfg.tie_breaker_strategy, "arbiter_ruling")
        self.assertEqual(slr_cfg.exclusion_reasons, ["Wrong Target Pathogen", "Animal Model", "Insufficient Follow-up"])
        self.assertEqual(slr_cfg.stale_queue_reminder_days, 2)

        # 3. Verify Formal SLR Protocol
        protocol = SLRProtocol.objects.get(workspace=ws)
        self.assertEqual(protocol.title, "Favipiravir Efficacy in Acute Arenavirus Infections")
        self.assertEqual(protocol.prospero_registration_id, "CRD42026998877")
        self.assertEqual(protocol.version, 1)

        # 4. Verify PRISMA summary in returned JSON
        prisma = res["prisma_summary"]
        self.assertEqual(len(prisma["active_gates"]), 3)  # Gate 1, Gate 2, Gate 3 (Extraction)
        self.assertTrue(prisma["blind_dual_review"])
        self.assertIn("7.5%", prisma["negative_controls"])

    def test_update_existing_workspace_to_slr(self):
        """Verify upgrading a standard workspace to SLR type side-by-side."""
        standard_ws = self.create_workspace(name="Standard Oncology Workspace", user=self.admin, role="admin")

        res = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(standard_ws.id),
            name="Oncology Systematic Review 2026",
            checkpoint_gate_mode="single_combined_post_fulltext",
            full_text_sample_percentage=50.0,
            screening_quorum_size=3,
            rob_framework="robins_i",
            designated_arbiter=self.admin.username,
        ))

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["workspace_type"], "slr")

        standard_ws.refresh_from_db()
        self.assertEqual(standard_ws.name, "Oncology Systematic Review 2026")

        slr_cfg = SLRWorkspaceConfig.objects.get(workspace=standard_ws)
        self.assertEqual(slr_cfg.checkpoint_gate_mode, "single_combined_post_fulltext")
        self.assertEqual(slr_cfg.screening_quorum_size, 3)
        self.assertEqual(slr_cfg.rob_framework, "robins_i")
        self.assertEqual(slr_cfg.designated_arbiter, self.admin)

    def test_get_slr_workspace_config(self):
        """Verify get_slr_workspace_config returns side-by-side configuration details."""
        ws = self.create_workspace(name="Genomics SLR", user=self.admin, role="admin")
        SLRWorkspaceConfig.objects.create(
            workspace=ws,
            checkpoint_gate_mode="two_stage_split",
            screening_quorum_size=2,
            designated_arbiter=self.researcher,
            abstract_sample_percentage=20.0
        )

        res = self.parse_res(get_slr_workspace_config_logic(
            user=self.admin,
            workspace_id=str(ws.id)
        ))

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["workspace_type"], "slr")
        self.assertTrue(res["is_slr_configured"])
        self.assertEqual(res["workspace"]["name"], "Genomics SLR")
        self.assertEqual(res["slr_config"]["checkpoint_gate_mode"], "two_stage_split")
        self.assertEqual(res["slr_config"]["screening_quorum_size"], 2)
        self.assertEqual(res["slr_config"]["designated_arbiter"]["username"], self.researcher.username)
        self.assertIsNotNone(res["prisma_summary"])

    def test_list_and_get_workspace_includes_slr_type(self):
        """Verify list_workspaces and get_workspace distinguish SLR vs standard workspaces."""
        # Workspace 1: SLR
        slr_ws = self.create_workspace(name="Vaccine SLR", user=self.admin, role="admin")
        SLRWorkspaceConfig.objects.create(workspace=slr_ws, screening_quorum_size=2)

        # Workspace 2: Standard
        std_ws = self.create_workspace(name="Standard Tech Scouting", user=self.admin, role="admin")

        # 1. list_workspaces
        list_res = self.parse_res(list_workspaces_logic(self.admin))
        ws_map = {w["workspace_id"]: w for w in list_res}

        self.assertEqual(ws_map[str(slr_ws.id)]["workspace_type"], "slr")
        self.assertTrue(ws_map[str(slr_ws.id)]["is_slr"])

        self.assertEqual(ws_map[str(std_ws.id)]["workspace_type"], "standard")
        self.assertFalse(ws_map[str(std_ws.id)]["is_slr"])

        # 2. get_workspace on SLR workspace
        detail_slr = self.parse_res(get_workspace_logic(self.admin, str(slr_ws.id)))
        self.assertEqual(detail_slr["workspace_type"], "slr")
        self.assertTrue(detail_slr["is_slr"])
        self.assertIsNotNone(detail_slr["slr_config"])
        self.assertEqual(detail_slr["slr_config"]["screening_quorum_size"], 2)

        # 3. get_workspace on standard workspace
        detail_std = self.parse_res(get_workspace_logic(self.admin, str(std_ws.id)))
        self.assertEqual(detail_std["workspace_type"], "standard")
        self.assertFalse(detail_std["is_slr"])
        self.assertIsNone(detail_std["slr_config"])

    def test_slr_workspace_validation_and_rbac(self):
        """Verify input validation and permission enforcement."""
        ws = self.create_workspace(name="Confidential Medical SLR", user=self.admin, role="admin")

        # 1. Invalid screening quorum (> 6)
        res_quorum = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            screening_quorum_size=10
        ))
        self.assertEqual(res_quorum["status"], "error")
        self.assertIn("screening_quorum_size must be between 1 and 6", res_quorum["error"])

        # 2. Invalid sampling percentage (> 100)
        res_sample = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            abstract_sample_percentage=150.0
        ))
        self.assertEqual(res_sample["status"], "error")
        self.assertIn("abstract_sample_percentage must be between 0.0 and 100.0%", res_sample["error"])

        # 3. Non-existent designated arbiter
        res_arb = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            designated_arbiter="ghost_user_does_not_exist"
        ))
        self.assertEqual(res_arb["status"], "error")
        self.assertIn("could not be found", res_arb["error"])

        # 4. RBAC: outsider cannot configure workspace
        res_rbac = self.parse_res(configure_slr_workspace_logic(
            user=self.outsider,
            workspace_id=str(ws.id),
            screening_quorum_size=2
        ))
        self.assertEqual(res_rbac["status"], "error")
        self.assertIn("Access denied", res_rbac["error"])

    def test_all_checkpoint_gate_modes_and_prisma_summary(self):
        """Verify all 4 checkpoint gate modes and their PRISMA summary active gates."""
        ws = self.create_workspace(name="Gate Modes Test Workspace", user=self.admin, role="admin")

        # Mode 1: two_stage_split (Abstract + FullText + Extraction)
        res1 = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            checkpoint_gate_mode="two_stage_split",
            enable_extraction_gate=True,
            abstract_sample_percentage=12.0,
            full_text_sample_percentage=22.0,
            extraction_sample_percentage=10.0,
        ))
        prisma1 = res1["prisma_summary"]
        gate_names1 = [g["gate"] for g in prisma1["active_gates"]]
        self.assertIn("Gate 1: Abstract Screening", gate_names1)
        self.assertIn("Gate 2: Full-Text Screening", gate_names1)
        self.assertIn("Gate 3: Parameter Extraction", gate_names1)

        # Mode 2: two_stage_split with extraction gate disabled
        res2 = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            checkpoint_gate_mode="two_stage_split",
            enable_extraction_gate=False,
        ))
        prisma2 = res2["prisma_summary"]
        gate_names2 = [g["gate"] for g in prisma2["active_gates"]]
        self.assertEqual(len(gate_names2), 2)
        self.assertNotIn("Gate 3: Parameter Extraction", gate_names2)

        # Mode 3: single_combined_post_fulltext
        res3 = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            checkpoint_gate_mode="single_combined_post_fulltext",
            enable_extraction_gate=False,
        ))
        prisma3 = res3["prisma_summary"]
        gate_names3 = [g["gate"] for g in prisma3["active_gates"]]
        self.assertEqual(len(gate_names3), 1)
        self.assertIn("Combined Gate: Post Full-Text Screening", gate_names3[0])

        # Mode 4: abstract_only_gate
        res4 = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            checkpoint_gate_mode="abstract_only_gate",
            enable_extraction_gate=False,
        ))
        prisma4 = res4["prisma_summary"]
        gate_names4 = [g["gate"] for g in prisma4["active_gates"]]
        self.assertEqual(len(gate_names4), 1)
        self.assertIn("Gate 1: Abstract Screening (Scoping)", gate_names4[0])

        # Mode 5: autonomous_benchmark (no active pause gates)
        res5 = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            checkpoint_gate_mode="autonomous_benchmark",
            enable_extraction_gate=False,
        ))
        prisma5 = res5["prisma_summary"]
        self.assertEqual(len(prisma5["active_gates"]), 0)

    def test_sampling_modes_and_rob_frameworks(self):
        """Verify all sampling modes and Cochrane RoB frameworks."""
        ws = self.create_workspace(name="RoB & Sampling SLR", user=self.admin, role="admin")

        # 1. Pure random sampling + ROBINS-I
        res1 = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            sampling_mode="pure_random",
            enable_rob_assessment=True,
            rob_framework="robins_i",
            require_human_rob_validation=True,
        ))
        self.assertEqual(res1["status"], "success")
        slr_cfg = SLRWorkspaceConfig.objects.get(workspace=ws)
        self.assertEqual(slr_cfg.sampling_mode, "pure_random")
        self.assertEqual(slr_cfg.rob_framework, "robins_i")
        self.assertTrue(slr_cfg.require_human_rob_validation)

        # 2. Full audit + Newcastle-Ottawa scale (NOS)
        res2 = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            sampling_mode="full_audit",
            rob_framework="nos",
        ))
        self.assertEqual(res2["status"], "success")
        slr_cfg.refresh_from_db()
        self.assertEqual(slr_cfg.sampling_mode, "full_audit")
        self.assertEqual(slr_cfg.rob_framework, "nos")

        # 3. Uncertainty-stratified + Auto detect RoB
        res3 = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            sampling_mode="uncertainty_stratified",
            rob_framework="auto_detect",
        ))
        self.assertEqual(res3["status"], "success")
        slr_cfg.refresh_from_db()
        self.assertEqual(slr_cfg.sampling_mode, "uncertainty_stratified")
        self.assertEqual(slr_cfg.rob_framework, "auto_detect")

    def test_designated_arbiter_resolution_modes(self):
        """Verify resolving designated senior arbiter by username, email, ID, or unsetting."""
        ws = self.create_workspace(name="Arbiter Resolution SLR", user=self.admin, role="admin")

        # 1. Resolve by username
        res_user = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            designated_arbiter=self.researcher.username,
        ))
        self.assertEqual(res_user["status"], "success")
        slr_cfg = SLRWorkspaceConfig.objects.get(workspace=ws)
        self.assertEqual(slr_cfg.designated_arbiter, self.researcher)

        # 2. Resolve by email
        res_email = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            designated_arbiter=self.researcher.email,
        ))
        self.assertEqual(res_email["status"], "success")
        slr_cfg.refresh_from_db()
        self.assertEqual(slr_cfg.designated_arbiter, self.researcher)

        # 3. Resolve by ID (PK)
        res_id = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            designated_arbiter=str(self.admin.pk),
        ))
        self.assertEqual(res_id["status"], "success")
        slr_cfg.refresh_from_db()
        self.assertEqual(slr_cfg.designated_arbiter, self.admin)

        # 4. Resolve empty / unset
        res_unset = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=str(ws.id),
            designated_arbiter="",
        ))
        self.assertEqual(res_unset["status"], "success")
        slr_cfg.refresh_from_db()
        self.assertIsNone(slr_cfg.designated_arbiter)

    def test_slr_protocol_creation_and_update(self):
        """Verify formal SLR protocol creation, PICO criteria persistence, and updating."""
        res_create = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            name="Cardiology Systematic Review",
            protocol_title="SGLT2 Inhibitors in Heart Failure with Preserved Ejection Fraction",
            protocol_review_question="Does empagliflozin reduce cardiovascular death in HFpEF patients?",
            pico_population="Adults >= 18 with symptomatic HF and LVEF > 40%",
            pico_intervention="Empagliflozin 10mg once daily",
            pico_comparison="Standard medical therapy + Placebo",
            pico_outcome="Composite cardiovascular death or hospitalization for heart failure",
            study_design_criteria="Double-blind randomized controlled trials",
            prospero_registration_id="CRD42026112233",
        ))
        self.assertEqual(res_create["status"], "success")
        ws_id = res_create["workspace_id"]
        protocol_data = res_create["protocol"]
        self.assertIsNotNone(protocol_data)
        self.assertEqual(protocol_data["title"], "SGLT2 Inhibitors in Heart Failure with Preserved Ejection Fraction")
        self.assertEqual(protocol_data["pico"]["population"], "Adults >= 18 with symptomatic HF and LVEF > 40%")
        self.assertEqual(protocol_data["prospero_registration_id"], "CRD42026112233")

        # Update protocol fields
        res_update = self.parse_res(configure_slr_workspace_logic(
            user=self.admin,
            workspace_id=ws_id,
            protocol_title="SGLT2 Inhibitors in HFpEF: Extended 2026 Protocol",
            pico_outcome="All-cause mortality, KCCQ clinical summary score, and eGFR decline rate",
        ))
        self.assertEqual(res_update["status"], "success")
        updated_protocol = res_update["protocol"]
        self.assertEqual(updated_protocol["title"], "SGLT2 Inhibitors in HFpEF: Extended 2026 Protocol")
        self.assertIn("KCCQ clinical summary score", updated_protocol["pico"]["outcome"])
        # Population should be preserved
        self.assertEqual(updated_protocol["pico"]["population"], "Adults >= 18 with symptomatic HF and LVEF > 40%")

    def test_get_slr_workspace_config_on_standard_workspace(self):
        """Verify get_slr_workspace_config handles a standard workspace that has no SLR policy attached."""
        std_ws = self.create_workspace(name="Standard Tech Intelligence", user=self.admin, role="admin")

        res = self.parse_res(get_slr_workspace_config_logic(
            user=self.admin,
            workspace_id=str(std_ws.id)
        ))

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["workspace_type"], "standard")
        self.assertFalse(res["is_slr_configured"])
        self.assertIsNone(res["slr_config"])
        self.assertIsNone(res["protocol"])
        self.assertIsNone(res["prisma_summary"])
        self.assertEqual(res["workspace"]["name"], "Standard Tech Intelligence")


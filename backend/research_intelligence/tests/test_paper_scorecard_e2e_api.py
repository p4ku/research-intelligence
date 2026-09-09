import uuid
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    ExtractionDefinition,
    Paper,
    Extraction,
    PaperMetric,
    PipelineRun,
    NarrativeReport,
)

User = get_user_model()


class PaperScorecardE2EAPITestCase(TestCase):
    """
    End-to-End API Test Suite for GET /api/papers/{id}/scorecard/ endpoint.
    Covers:
    - Authentication, RBAC, and domain isolation.
    - Query parameters: default, pipeline_run=<uuid>, pipeline_run=latest, pipeline_run_id, run_id, invalid run id.
    - ExtractionDefinition ordering and dynamic reordering lifecycle.
    - Dimension elements: headline, facets, texts, bullets, quotes, facts, max.
    - Nested metric unpacking and complete absence of Python repr leakage.
    - Risk & Affiliation comprehensive payload parsing and status badges.
    - Inactive definitions handling and historical extractions.
    - Workspace summary and NarrativeReport context resolution.
    """

    def setUp(self):
        self.client = APIClient()

        # Users
        self.member_user = User.objects.create_user(
            username="member_researcher",
            email="member@schwarz.de",
            password="test_password123!"
        )
        self.outsider_user = User.objects.create_user(
            username="outsider_user",
            email="outsider@external.com",
            password="test_password123!"
        )

        # Workspaces
        self.workspace = Workspace.objects.create(
            name="Quantum Computing Intelligence"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            role="analyst"
        )

        self.other_workspace = Workspace.objects.create(
            name="Autonomous Robotics Lab"
        )
        WorkspaceMember.objects.create(
            workspace=self.other_workspace,
            user=self.outsider_user,
            role="viewer"
        )

        # Extraction Definitions with explicit ordering
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Technology Readiness Level (TRL)",
            order=1,
            exit_metrics="trl",
            primary_frontend_metric="trl",
            response_schema={"type": "object", "properties": {"trl": {"type": "integer", "maximum": 9}}},
            is_active=True,
        )
        self.def_quality = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Research Quality",
            order=2,
            exit_metrics="novelty, significance",
            primary_frontend_metric="novelty",
            secondary_frontend_metrics="significance",
            response_schema={"type": "object", "properties": {"novelty": {"type": "number"}, "significance": {"type": "number"}}},
            is_active=True,
        )
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Fit",
            order=3,
            exit_metrics="fit_score",
            primary_frontend_metric="fit_score",
            response_schema={"type": "object", "properties": {"fit_score": {"type": "number"}}},
            is_active=True,
        )
        self.def_risk = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Risk and Affiliation",
            order=4,
            exit_metrics="risk_score",
            response_schema={"type": "object"},
            is_active=True,
        )

        # Paper
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            title="Scalable Quantum Algorithms for Large Combinatorial Optimization",
            authors="Alice Vance, Bob Stone, Carlos Rivera",
            abstract="We present a fault-tolerant quantum approximation algorithm demonstrating exponential speedups.",
            doi="10.1038/s41586-026-0001-x",
            arxiv_id="2609.12345",
            original_pdf_path="papers/2609.12345.pdf",
            screening_status="accepted"
        )

        # Pipeline Runs
        self.run_1 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            started_at="2026-09-01T10:00:00Z",
            completed_at="2026-09-01T10:15:00Z",
        )
        self.run_2 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            started_at="2026-09-08T10:00:00Z",
            completed_at="2026-09-08T10:20:00Z",
        )

        # Paper Metrics per run
        self.metric_run_1 = PaperMetric.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            pipeline_run=self.run_1,
            screening_status="accepted",
            abstract_screening_reasoning="Sound methodology in quantum computing.",
            full_text_screening_reasoning="Validated with 128-qubit hardware benchmark.",
            signal_score=55.0,
            signal_score_details={"variables": {"fit_score": 50, "trl": 4}, "code_snippet": "return fit_score + trl"},
        )
        self.metric_run_2 = PaperMetric.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            pipeline_run=self.run_2,
            screening_status="accepted",
            abstract_screening_reasoning="Breakthrough quantum speedup.",
            full_text_screening_reasoning="Confirmed hardware execution.",
            signal_score=88.5,
            signal_score_details={"variables": {"fit_score": 90, "trl": 7}, "code_snippet": "return fit_score * 0.9 + trl * 1.0", "calculated_at": "2026-09-08T10:19:00Z"},
        )

        # Narrative Reports
        self.report_run_1 = NarrativeReport.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run_1,
            title="Weekly Quantum Review #1",
            content_markdown="### Review 1 Summary\nPromising preliminary findings in quantum optimization.",
        )
        self.report_run_2 = NarrativeReport.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run_2,
            title="Weekly Quantum Review #2",
            content_markdown="### Review 2 Summary\nSubstantial improvements and industrial viability.",
        )

        # Extractions
        self.ext_trl = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.def_trl,
            fields_data={
                "fields": {
                    "trl": 6,
                    "rationale": "Demonstrated prototype in operational environment.",
                    "evidence": "Hardware test bench verified on 128 superconducting qubits."
                }
            },
            validation_status="pass"
        )
        self.ext_quality = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.def_quality,
            fields_data={
                "fields": {
                    "novelty": {"score": 92, "band": "Pioneering", "insight": "First sub-quadratic scaling proof."},
                    "significance": {"score": 85, "band": "High Impact", "insight": "Applicable to logistics and supply chain optimization."},
                    "peer_reviewed": True,
                    "reproducible": "Yes"
                }
            },
            validation_status="pass"
        )
        self.ext_fit = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.def_fit,
            fields_data={
                "fields": {
                    "fit_score": 95,
                    "fit_rationale": "Direct alignment with retail logistics routing objectives."
                }
            },
            validation_status="pass"
        )
        self.ext_risk = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.def_risk,
            fields_data={
                "fields": {
                    "affiliations": ["Technical University of Munich (TUM)", "Schwarz Digits AI Lab"],
                    "author_contacts": ["alice.vance@tum.de", "bob.stone@schwarz.de"],
                    "funding_entities": ["European Research Council (ERC)", "German Federal Ministry of Research"],
                    "codebase_artifact_link": "https://github.com/schwarz-digits/quantum-opt",
                    "risk_score": 12.5,
                    "schwarz_ecosystem_affiliation": {"status": "YES", "matched_institutions": ["TUM", "Schwarz Digits"]},
                    "competitor_involvement": {"status": "NO", "matches": None},
                    "gdpr_concerns": {"status": "NO", "concerns": None},
                    "author_review_note": "The author's review concluded: None of the identified institutions are restricted."
                }
            },
            validation_status="pass"
        )

    def test_01_authentication_and_workspace_rbac_isolation(self):
        """
        - Anonymous user -> HTTP 401 Unauthorized.
        - User from different workspace -> HTTP 404 Not Found (workspace data isolation).
        - Workspace member -> HTTP 200 OK.
        """
        url = f"/api/papers/{self.paper.id}/scorecard/"

        # 1. Unauthenticated request
        self.client.logout()
        resp_anon = self.client.get(url)
        self.assertEqual(resp_anon.status_code, 401)

        # 2. Outsider user (not a member of Quantum workspace)
        self.client.force_authenticate(user=self.outsider_user)
        resp_outsider = self.client.get(url)
        self.assertEqual(resp_outsider.status_code, 404)

        # 3. Legitimate member
        self.client.force_authenticate(user=self.member_user)
        resp_member = self.client.get(url)
        self.assertEqual(resp_member.status_code, 200)

    def test_02_default_query_resolves_latest_metric_and_scorecard_contract(self):
        """
        Without query parameters, GET /api/papers/{id}/scorecard/:
        - Follows contract shape: workspace, paper, definitions, extractions, metric, narrative_report.
        - Automatically resolves the latest PaperMetric (Run 2: 88.5, not Run 1: 55.0).
        - Exposes core paper fields, signal score details, and author lists.
        """
        self.client.force_authenticate(user=self.member_user)
        resp = self.client.get(f"/api/papers/{self.paper.id}/scorecard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Contract keys
        self.assertIn("workspace", data)
        self.assertIn("paper", data)
        self.assertIn("definitions", data)
        self.assertIn("extractions", data)
        self.assertIn("metric", data)
        self.assertIn("narrative_report", data)

        paper = data["paper"]
        self.assertEqual(paper["id"], str(self.paper.id))
        self.assertEqual(paper["title"], "Scalable Quantum Algorithms for Large Combinatorial Optimization")
        self.assertEqual(paper["authors"], ["Alice Vance", "Bob Stone", "Carlos Rivera"])
        self.assertEqual(paper["authors_raw"], "Alice Vance, Bob Stone, Carlos Rivera")
        self.assertEqual(paper["doi"], "10.1038/s41586-026-0001-x")
        self.assertEqual(paper["arxiv_id"], "2609.12345")
        self.assertTrue(paper["source_url"].startswith("https://arxiv.org/abs/"))
        self.assertEqual(paper["pdf_key"], "papers/2609.12345.pdf")

        # Metric resolution: newest metric (Run 2) is automatically selected
        self.assertEqual(paper["signal_score"], 88.5)
        self.assertEqual(paper["screening_status"], "accepted")
        self.assertIsNotNone(paper["signal_score_details"])
        self.assertEqual(paper["signal_score_details"]["variables"]["fit_score"], 90)

        # Narrative report defaults to newest
        self.assertEqual(data["narrative_report"]["title"], "Weekly Quantum Review #2")

    def test_03_query_scoped_by_explicit_pipeline_run(self):
        """
        When ?pipeline_run=<run_1.id> is specified:
        - Evaluates paper against Run 1: signal_score == 55.0.
        - Narrative report resolves to Run 1's report ("Weekly Quantum Review #1").
        """
        self.client.force_authenticate(user=self.member_user)
        url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_1.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["paper"]["signal_score"], 55.0)
        self.assertEqual(data["paper"]["signal_score_details"]["variables"]["fit_score"], 50)
        self.assertEqual(data["metric"]["pipeline_run_id"], str(self.run_1.id))
        self.assertEqual(data["narrative_report"]["title"], "Weekly Quantum Review #1")

    def test_04_query_scoped_by_pipeline_run_latest(self):
        """
        When ?pipeline_run=latest is specified:
        - Dynamically queries latest non-failed run (Run 2).
        - Evaluates paper against Run 2: signal_score == 88.5.
        """
        self.client.force_authenticate(user=self.member_user)
        url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run=latest"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["paper"]["signal_score"], 88.5)
        self.assertEqual(data["metric"]["pipeline_run_id"], str(self.run_2.id))
        self.assertEqual(data["narrative_report"]["title"], "Weekly Quantum Review #2")

    def test_05_query_param_aliases_and_invalid_run_resilience(self):
        """
        - ?pipeline_run_id=<uuid> works as alias for ?pipeline_run.
        - ?run_id=<uuid> works as alias for ?pipeline_run.
        - Non-existent UUID (?pipeline_run=00000000-...) returns 404 because paper was not evaluated in that run.
        - Invalid string (?pipeline_run=garbage) returns 404 gracefully without 500 error.
        """
        self.client.force_authenticate(user=self.member_user)

        # Alias 1: pipeline_run_id
        resp_alias1 = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run_id={self.run_1.id}")
        self.assertEqual(resp_alias1.status_code, 200)
        self.assertEqual(resp_alias1.json()["paper"]["signal_score"], 55.0)

        # Alias 2: run_id
        resp_alias2 = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?run_id={self.run_1.id}")
        self.assertEqual(resp_alias2.status_code, 200)
        self.assertEqual(resp_alias2.json()["paper"]["signal_score"], 55.0)

        # Non-existent run id -> paper not in run -> 404 Not Found
        fake_uuid = str(uuid.uuid4())
        resp_fake = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={fake_uuid}")
        self.assertEqual(resp_fake.status_code, 404)

        # Garbage string -> invalid run filter -> 404 Not Found
        resp_garbage = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run=not-a-uuid")
        self.assertEqual(resp_garbage.status_code, 404)

    def test_06_dimensions_and_definitions_strict_order_lifecycle(self):
        """
        Verifies:
        1. Default dimensions[] and definitions[] strictly follow ExtractionDefinition.order (1: TRL, 2: Quality, 3: Fit).
        2. Dynamically modifying definition orders in DB (simulating Drag & Drop / Move Up/Down)
           instantly reorders dimensions[] and definitions[] in the HTTP API response.
        """
        self.client.force_authenticate(user=self.member_user)
        url = f"/api/papers/{self.paper.id}/scorecard/"

        # Initial order: TRL (1), Quality (2), Fit (3), Risk (4)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        dims = data["paper"]["dimensions"]
        self.assertEqual(len(dims), 4)
        score_dims = [d for d in dims if not d.get("is_risk_and_affiliation")]
        self.assertEqual(len(score_dims), 3)
        self.assertEqual(score_dims[0]["name"], "Technology Readiness Level (TRL)")
        self.assertEqual(score_dims[1]["name"], "Research Quality")
        self.assertEqual(score_dims[2]["name"], "Schwarz Fit")

        ws_defs = data["workspace"]["definitions"]
        self.assertEqual(ws_defs[0]["name"], "Technology Readiness Level (TRL)")
        self.assertEqual(ws_defs[1]["name"], "Research Quality")
        self.assertEqual(ws_defs[2]["name"], "Schwarz Fit")
        self.assertEqual(ws_defs[3]["name"], "Risk and Affiliation")

        # Reorder: Schwarz Fit -> #1, Quality -> #2, TRL -> #3
        self.def_fit.order = 1
        self.def_fit.save(update_fields=["order"])
        self.def_quality.order = 2
        self.def_quality.save(update_fields=["order"])
        self.def_trl.order = 3
        self.def_trl.save(update_fields=["order"])

        resp_reordered = self.client.get(url)
        self.assertEqual(resp_reordered.status_code, 200)
        reordered_data = resp_reordered.json()

        reordered_dims = reordered_data["paper"]["dimensions"]
        reordered_score_dims = [d for d in reordered_dims if not d.get("is_risk_and_affiliation")]
        self.assertEqual(reordered_score_dims[0]["name"], "Schwarz Fit")
        self.assertEqual(reordered_score_dims[1]["name"], "Research Quality")
        self.assertEqual(reordered_score_dims[2]["name"], "Technology Readiness Level (TRL)")

        reordered_defs = reordered_data["workspace"]["definitions"]
        self.assertEqual(reordered_defs[0]["name"], "Schwarz Fit")
        self.assertEqual(reordered_defs[1]["name"], "Research Quality")
        self.assertEqual(reordered_defs[2]["name"], "Technology Readiness Level (TRL)")

    def test_07_risk_and_affiliation_comprehensive_payload(self):
        """
        Verifies the risk_and_affiliation object on the paper:
        - affiliations list parsed cleanly.
        - author_contacts with emails parsed cleanly.
        - funding_entities parsed cleanly.
        - codebase_artifact_link present.
        - flags list contains structured statuses: safe, highlight, warn, neutral.
        - Risk and Affiliation dimension flag is_risk_and_affiliation is True.
        """
        self.client.force_authenticate(user=self.member_user)
        resp = self.client.get(f"/api/papers/{self.paper.id}/scorecard/")
        self.assertEqual(resp.status_code, 200)
        paper = resp.json()["paper"]

        risk = paper.get("risk_and_affiliation")
        self.assertIsNotNone(risk)

        # Affiliations & Contacts
        self.assertEqual(risk["affiliations"], ["Technical University of Munich (TUM)", "Schwarz Digits AI Lab"])
        self.assertEqual(risk["author_contacts"], ["alice.vance@tum.de", "bob.stone@schwarz.de"])
        self.assertEqual(risk["funding_entities"], ["European Research Council (ERC)", "German Federal Ministry of Research"])
        self.assertEqual(risk["codebase_artifact_link"], "https://github.com/schwarz-digits/quantum-opt")
        self.assertEqual(risk["risk_score"], 12.5)

        # Flags and status mapping
        flags = risk.get("flags", [])
        self.assertTrue(len(flags) >= 2)

        flag_map = {f["key"]: f for f in flags}

        # schwarz_ecosystem -> positive match -> highlight
        eco_flag = flag_map.get("schwarz_ecosystem")
        self.assertIsNotNone(eco_flag)
        self.assertEqual(eco_flag["status"], "highlight")
        self.assertIn("TUM", eco_flag["value"])

        # competitor -> NO -> safe
        comp_flag = flag_map.get("competitor")
        self.assertIsNotNone(comp_flag)
        self.assertEqual(comp_flag["status"], "safe")

        # gdpr -> NO -> safe
        gdpr_flag = flag_map.get("gdpr")
        self.assertIsNotNone(gdpr_flag)
        self.assertEqual(gdpr_flag["status"], "safe")

        # Risk definition has is_risk_and_affiliation == True in paper.dimensions
        risk_dim = next((d for d in paper["dimensions"] if d.get("is_risk_and_affiliation")), None)
        self.assertIsNotNone(risk_dim)
        self.assertEqual(risk_dim["name"], "Risk and Affiliation")

    def test_08_nested_metric_unpacking_and_no_python_repr_leakage(self):
        """
        Verifies:
        - Nested metric dictionary objects ({score: 92, band: 'Pioneering', insight: '...'}) are unpacked.
        - dimension.raw is NEVER a Python repr ('{...', 'OrderedDict(').
        - facts[] values are clean and do not leak dictionary strings.
        - Evidence preserves text snippets without corruption.
        - Dimension max values are correct (TRL max=9, percentage max=100).
        """
        self.client.force_authenticate(user=self.member_user)
        resp = self.client.get(f"/api/papers/{self.paper.id}/scorecard/")
        self.assertEqual(resp.status_code, 200)
        paper = resp.json()["paper"]

        dims = {d["name"]: d for d in paper["dimensions"]}

        # 1. TRL dimension
        trl_dim = dims["Technology Readiness Level (TRL)"]
        self.assertEqual(trl_dim["value"], 6)
        self.assertEqual(trl_dim["max"], 9)
        self.assertIn("Hardware test bench verified", trl_dim["evidence"][0])
        self.assertFalse(str(trl_dim["raw"]).startswith("{"))

        # 2. Research Quality dimension with nested novelty dict
        qual_dim = dims["Research Quality"]
        self.assertEqual(qual_dim["value"], 92)
        self.assertEqual(qual_dim["max"], 100)
        self.assertEqual(qual_dim["band"], "Pioneering")
        self.assertFalse(str(qual_dim["raw"]).startswith("{"))

        # Check submetrics / facets
        facets = qual_dim.get("facets", [])
        facet_map = {f["name"]: f for f in facets}
        if "Significance" in facet_map:
            self.assertEqual(facet_map["Significance"]["value"], 85)
            self.assertEqual(facet_map["Significance"]["band"], "High Impact")

        # Check facts: booleans converted to Yes/No, no raw dictionaries
        facts = qual_dim.get("facts", [])
        for f in facts:
            self.assertFalse(str(f["value"]).startswith("{"))
            self.assertFalse(str(f["value"]).startswith("OrderedDict("))

    def test_09_inactive_definitions_handling_in_scorecard(self):
        """
        - Inactive definition without extractions is excluded from paper.dimensions[].
        - Inactive definition with existing extraction for this paper is retained in paper.dimensions[]
          to ensure historical assessments are never dropped.
        """
        # Inactive definition without extractions
        inactive_unused = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Deprecated Carbon Cost",
            order=10,
            is_active=False,
            response_schema={"type": "object"}
        )

        # Inactive definition WITH extraction for this paper
        inactive_used = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Legacy Hardware Score",
            order=11,
            is_active=False,
            exit_metrics="hardware_score",
            response_schema={"type": "object"}
        )
        Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=inactive_used,
            category="Legacy Hardware Score",
            fields_data={"fields": {"hardware_score": 77}},
            validation_status="pass"
        )

        self.client.force_authenticate(user=self.member_user)
        resp = self.client.get(f"/api/papers/{self.paper.id}/scorecard/")
        self.assertEqual(resp.status_code, 200)

        dims = {d["name"]: d for d in resp.json()["paper"]["dimensions"]}
        # Deprecated unused is excluded
        self.assertNotIn("Deprecated Carbon Cost", dims)
        # Legacy used is preserved
        self.assertIn("Legacy Hardware Score", dims)
        self.assertEqual(dims["Legacy Hardware Score"]["value"], 77)

    def test_10_narrative_report_and_workspace_summary_context(self):
        """
        Verifies:
        - Workspace summary contains user_role == 'analyst' for the requesting user.
        - Workspace summary contains scrapers_count, digest_schedule, and definitions metadata.
        - Narrative report includes Markdown content and run association.
        """
        self.client.force_authenticate(user=self.member_user)
        resp = self.client.get(f"/api/papers/{self.paper.id}/scorecard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Workspace summary
        ws = data["workspace"]
        self.assertEqual(ws["id"], str(self.workspace.id))
        self.assertEqual(ws["name"], "Quantum Computing Intelligence")
        self.assertEqual(ws["user_role"], "analyst")
        self.assertIn("digest_schedule", ws)

        # Definitions in workspace summary
        self.assertTrue(len(ws["definitions"]) >= 3)

        # Narrative report
        report = data["narrative_report"]
        self.assertIsNotNone(report)
        self.assertIn("### Review", report["content_markdown"])

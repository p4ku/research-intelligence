import uuid
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from unittest.mock import patch, MagicMock

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    Paper,
    PaperMetric,
    ExtractionDefinition,
    Extraction,
    ComponentRun,
    NarrativeReport,
)

from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job

from research_intelligence.services.scorecard_extractors import (
    _unwrap_val,
    extract_risk_and_affiliation,
    extract_rich_dimension_details,
    extract_metrics_for_extraction,
    resolve_field_val,
)
from research_intelligence.services.scorecard_service import format_workspace_summary

User = get_user_model()


class PaperScorecardMetricsClassificationTestCase(TestCase):
    """
    Comprehensive test suite for GET /api/papers/{id}/scorecard/ verifying:
    1. Rule 1: Exit metrics only (first is primary, rest are secondary).
    2. Rule 2: Postprocessing code returning a single scalar or 1-key dict (unpacked as primary, exit metrics as secondary).
    3. Rule 2: Postprocessing code returning >1 keys with a matching primary candidate (all extra become secondary).
    4. Rule 2: Postprocessing code returning >1 keys without a matching primary candidate (all become secondary).
    5. Nested fields_data dictionary unpacking patterns (e.g. {"value": X}, 1-key dicts).
    6. Extraction without definition (ad-hoc category extraction).
    7. Full API response structure: definitions (with schemas & postprocessing code), extractions,
       dimensions, run-scoped metrics, and narrative_report.
    8. Pipeline run scoping: ?pipeline_run={id}, ?pipeline_run=latest, and default scoping.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="scorecard_tester",
            email="scorecard_tester@schwarz.de",
            password="testpassword123!"
        )
        self.workspace = Workspace.objects.create(name="Deep Learning & Quantum Workspace")
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Create two pipeline runs
        self.run_alpha = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run Alpha 2026-01",
            status="completed"
        )
        self.run_beta = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run Beta 2026-02",
            status="completed"
        )

        # Create paper
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            title="Fault-Tolerant Quantum Error Correction at Scale",
            hash_id="hash_ft_qec_001",
            doi="10.1103/qec.2026.01",
            arxiv_id="2603.99999",
            authors="Dr. Alice Quantum, Bob Syndrome",
            abstract="We demonstrate macroscopic fault-tolerant logical qubits with lattice surgery...",
            source_database="arxiv",
            source_url="https://arxiv.org/abs/2603.99999",
            pipeline_run=self.run_beta,
        )

        # Attach PaperMetrics for both runs
        self.metric_alpha = PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.run_alpha,
            workspace=self.workspace,
            screening_status="borderline",
            abstract_screening_reasoning="Borderline novelty in alpha.",
            signal_score=62.0,
            metrics_data={"trl_level": 4, "schwarz_fit": 55},
        )
        self.metric_beta = PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.run_beta,
            workspace=self.workspace,
            screening_status="accepted",
            abstract_screening_reasoning="Strong theoretical foundations in beta.",
            full_text_screening_reasoning="Verified fault tolerance threshold experimentally.",
            signal_score=94.5,
            metrics_data={"trl_level": 6, "schwarz_fit": 92},
        )

        # Attach NarrativeReport for run_beta
        self.narrative_report = NarrativeReport.objects.create(
            pipeline_run=self.run_beta,
            workspace=self.workspace,
            title="Executive Briefing: Quantum Fault Tolerance Milestone",
            content_markdown="# Executive Summary\n\nThis paper demonstrates significant architectural maturity...",
            refinement_depth=2,
        )

    def test_1_rule_1_exit_metrics_only_classification(self):
        """
        Rule 1: No postprocessing code.
        Given a definition with Exit Metrics: ['trl_level', 'readiness_confidence', 'cost_feasibility']
        - 'trl_level' must be the PRIMARY metric (numeric_value=6, source='exit_metric')
        - 'readiness_confidence' and 'cost_feasibility' must be SECONDARY metrics
        """
        def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level Assessment",
            response_schema={
                "type": "object",
                "properties": {
                    "trl_level": {"type": "integer", "minimum": 1, "maximum": 9},
                    "readiness_confidence": {"type": "number"},
                    "cost_feasibility": {"type": "string"},
                },
                "required": ["trl_level"],
            },
            exit_metrics="trl_level, readiness_confidence, cost_feasibility",
            postprocessing_code="",  # No postprocessing
            llm_model="claude-3-7-sonnet",
            is_active=True,
        )

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=def_trl,
            category="Readiness",
            fields_data={
                "trl_level": 6,
                "readiness_confidence": 0.95,
                "cost_feasibility": "High",
                "reasoning": "Prototypes tested in operational environment.",
            },
            confidence_score=0.92,
            validation_status="pass",
            is_hitl_validated=True,
        )

        res = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        dim = next(d for d in data["paper"]["dimensions"] if d["definition_id"] == str(def_trl.id))
        self.assertFalse(dim["has_postprocessing"])
        self.assertTrue(dim["is_trl"])
        self.assertEqual(dim["max"], 9)

        # Primary metric checks
        primary = dim["primary_metric"]
        self.assertEqual(primary["key"], "trl_level")
        self.assertEqual(primary["label"], "TRL Level")
        self.assertEqual(primary["numeric_value"], 6)
        self.assertEqual(primary["raw"], "6")
        self.assertTrue(primary["is_numeric"])
        self.assertEqual(primary["source"], "exit_metric")

        # Headline dimension value must match primary metric
        self.assertEqual(dim["value"], 6)

        # Secondary metrics checks
        secondary = dim["secondary_metrics"]
        self.assertEqual(len(secondary), 2)
        sec_keys = [s["key"] for s in secondary]
        self.assertEqual(sec_keys, ["readiness_confidence", "cost_feasibility"])

        # Check secondary details
        conf_sec = next(s for s in secondary if s["key"] == "readiness_confidence")
        self.assertEqual(conf_sec["numeric_value"], 0.95)
        self.assertEqual(conf_sec["source"], "exit_metric")

        cost_sec = next(s for s in secondary if s["key"] == "cost_feasibility")
        self.assertEqual(cost_sec["raw"], "High")
        self.assertIsNone(cost_sec["numeric_value"])

    def test_2_rule_2_postprocessing_single_scalar_unpacked(self):
        """
        Rule 2 (Case A): Postprocessing code is present.
        Postprocessing emits 1 key-value dict: {"schwarz_fit_postprocessed": 88.5}.
        - 'schwarz_fit_postprocessed' is unpacked as PRIMARY metric (source='postprocessing').
        - All declared exit_metrics ('raw_alignment_score', 'relevance_index') become SECONDARY metrics.
        """
        def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Fit",
            response_schema={"type": "object", "properties": {"raw_alignment_score": {"type": "number"}}},
            exit_metrics="raw_alignment_score, relevance_index",
            postprocessing_code="""
# Calculate calibrated Schwarz Fit
return {"schwarz_fit_postprocessed": raw_alignment_score * 1.1}
""",
            llm_model="gpt-4o",
            is_active=True,
        )

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=def_fit,
            category="Strategic Alignment",
            fields_data={
                "fields": {
                    "raw_alignment_score": 75,
                    "relevance_index": 82,
                    "schwarz_fit_postprocessed": {"value": 88.5},  # nested dict unpacking test
                }
            },
            confidence_score=0.88,
        )

        res = self.client.get(f"/api/papers/{self.paper.id}/scorecard/")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        dim = next(d for d in data["paper"]["dimensions"] if d["definition_id"] == str(def_fit.id))
        self.assertTrue(dim["has_postprocessing"])

        # Primary metric is the postprocessed value
        primary = dim["primary_metric"]
        self.assertEqual(primary["key"], "schwarz_fit_postprocessed")
        self.assertEqual(primary["numeric_value"], 88.5)
        self.assertEqual(primary["source"], "postprocessing")
        self.assertEqual(dim["value"], 88.5)

        # Secondary metrics must contain ALL exit metrics
        sec_keys = [s["key"] for s in dim["secondary_metrics"]]
        self.assertIn("raw_alignment_score", sec_keys)
        self.assertIn("relevance_index", sec_keys)

        raw_align = next(s for s in dim["secondary_metrics"] if s["key"] == "raw_alignment_score")
        self.assertEqual(raw_align["numeric_value"], 75)
        self.assertEqual(raw_align["source"], "exit_metric")

    def test_3_rule_2_postprocessing_multiple_keys_with_primary_candidate(self):
        """
        Rule 2 (Case B): Postprocessing code emits a multi-key dictionary containing:
          - 'quantum_advantage_postprocessed': 94.0 (matches primary candidate)
          - 'qubit_efficiency_ratio': 1.85
          - 'decoherence_penalty': 6.0
        Plus exit_metrics: ['base_advantage_metric'].

        Expected:
        - primary_metric: 'quantum_advantage_postprocessed' (94.0)
        - secondary_metrics: 'qubit_efficiency_ratio', 'decoherence_penalty' (from postprocessing)
                             AND 'base_advantage_metric' (from exit_metric).
        """
        def_qa = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Quantum Advantage",
            response_schema={"type": "object"},
            exit_metrics="base_advantage_metric",
            postprocessing_code="""
return {
    "quantum_advantage_postprocessed": 94.0,
    "qubit_efficiency_ratio": 1.85,
    "decoherence_penalty": 6.0
}
""",
            is_active=True,
        )

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=def_qa,
            category="Benchmarking",
            fields_data={
                "base_advantage_metric": 80.0,
                "quantum_advantage_postprocessed": 94.0,
                "qubit_efficiency_ratio": 1.85,
                "decoherence_penalty": 6.0,
            },
        )

        res = self.client.get(f"/api/papers/{self.paper.id}/scorecard/")
        self.assertEqual(res.status_code, 200)
        dim = next(d for d in res.json()["paper"]["dimensions"] if d["definition_id"] == str(def_qa.id))

        self.assertTrue(dim["has_postprocessing"])
        self.assertEqual(dim["primary_metric"]["key"], "quantum_advantage_postprocessed")
        self.assertEqual(dim["primary_metric"]["numeric_value"], 94.0)
        self.assertEqual(dim["value"], 94.0)

        secondary = dim["secondary_metrics"]
        sec_keys = [s["key"] for s in secondary]
        self.assertIn("qubit_efficiency_ratio", sec_keys)
        self.assertIn("decoherence_penalty", sec_keys)
        self.assertIn("base_advantage_metric", sec_keys)

        # Check source tags
        qubit_eff = next(s for s in secondary if s["key"] == "qubit_efficiency_ratio")
        self.assertEqual(qubit_eff["source"], "postprocessing")
        self.assertEqual(qubit_eff["numeric_value"], 1.85)

        base_adv = next(s for s in secondary if s["key"] == "base_advantage_metric")
        self.assertEqual(base_adv["source"], "exit_metric")
        self.assertEqual(base_adv["numeric_value"], 80.0)

    def test_4_rule_2_postprocessing_multiple_keys_without_primary_candidate(self):
        """
        Rule 2 (Case B): Postprocessing returns >1 keys with NO key matching *_postprocessed.
        E.g. {"sub_factor_one": 45, "sub_factor_two": 55}.
        All returned postprocessing keys must become SECONDARY metrics.
        """
        def_multi = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Multi Sub Metric Def",
            response_schema={"type": "object"},
            exit_metrics="initial_score",
            postprocessing_code="""
return {
    "sub_factor_one": 45,
    "sub_factor_two": 55
}
""",
            is_active=True,
        )

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=def_multi,
            category="Diagnostics",
            fields_data={
                "initial_score": 50,
                "multi_sub_metric_def_postprocessed": {
                    "sub_factor_one": 45,
                    "sub_factor_two": 55,
                }
            },
        )

        res = self.client.get(f"/api/papers/{self.paper.id}/scorecard/")
        self.assertEqual(res.status_code, 200)
        dim = next(d for d in res.json()["paper"]["dimensions"] if d["definition_id"] == str(def_multi.id))

        self.assertTrue(dim["has_postprocessing"])
        # Both keys from the dict become secondary metrics
        sec_keys = [s["key"] for s in dim["secondary_metrics"]]
        self.assertIn("sub_factor_one", sec_keys)
        self.assertIn("sub_factor_two", sec_keys)
        self.assertIn("initial_score", sec_keys)

    def test_5_ad_hoc_extraction_without_definition(self):
        """
        Validates handling of custom/ad-hoc extractions not attached to any ExtractionDefinition.
        They must appear in paper.dimensions and top-level extractions.
        """
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=None,
            category="Security & Vulnerability Audit",
            fields_data={
                "vulnerability_score": 12,
                "cve_critical_count": 0,
                "reasoning": "No open CVEs found in cited repositories.",
            },
            confidence_score=0.99,
        )

        res = self.client.get(f"/api/papers/{self.paper.id}/scorecard/")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        dim = next(d for d in data["paper"]["dimensions"] if d["name"] == "Security & Vulnerability Audit")
        self.assertIsNone(dim["definition_id"])
        self.assertFalse(dim["has_postprocessing"])
        self.assertEqual(dim["primary_metric"]["numeric_value"], 12)
        self.assertEqual(dim["value"], 12)

    def test_6_complete_scorecard_payload_verification(self):
        """
        Comprehensive check of top-level response contracts:
        - workspace: id, name, definitions
        - paper: metadata, authors array, screening, signal_score & signal_score_details
        - definitions: response_schema, exit_metrics list, postprocessing_code
        - extractions: raw unflattened fields_data, primary_metric, secondary_metrics
        - narrative_report: title, content_markdown
        - metric: run-scoped PaperMetric
        """
        res = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}")
        self.assertEqual(res.status_code, 200)
        body = res.json()

        # 1. Top-level keys
        for key in ("workspace", "paper", "definitions", "extractions", "metric", "narrative_report"):
            self.assertIn(key, body, f"Missing top-level key: {key}")

        # 2. Workspace
        self.assertEqual(body["workspace"]["id"], str(self.workspace.id))
        self.assertEqual(body["workspace"]["name"], self.workspace.name)

        # 3. Paper metadata
        paper_res = body["paper"]
        self.assertEqual(paper_res["id"], str(self.paper.id))
        self.assertEqual(paper_res["title"], self.paper.title)
        self.assertEqual(paper_res["authors"], ["Dr. Alice Quantum", "Bob Syndrome"])
        self.assertEqual(paper_res["source_url"], "https://arxiv.org/abs/2603.99999")
        self.assertEqual(paper_res["signal_score"], 94.5)
        self.assertEqual(paper_res["screening_status"], "accepted")
        self.assertEqual(paper_res["pipeline_run_id"], str(self.run_beta.id))
        self.assertEqual(paper_res["pipeline_run_name"], "Run Beta 2026-02")

        # 4. Narrative Report
        self.assertIsNotNone(body["narrative_report"])
        self.assertEqual(body["narrative_report"]["title"], "Executive Briefing: Quantum Fault Tolerance Milestone")
        self.assertIn("# Executive Summary", body["narrative_report"]["content_markdown"])

        # 5. PaperMetric
        self.assertIsNotNone(body["metric"])
        self.assertEqual(body["metric"]["pipeline_run_id"], str(self.run_beta.id))
        self.assertEqual(body["metric"]["signal_score"], 94.5)

    def test_7_pipeline_run_scoping_alpha_vs_beta(self):
        """
        Verifies that querying ?pipeline_run={run_alpha.id} returns metrics and status
        specifically for run_alpha rather than the latest run.
        """
        res_alpha = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_alpha.id}")
        self.assertEqual(res_alpha.status_code, 200)
        data_alpha = res_alpha.json()

        self.assertEqual(data_alpha["paper"]["pipeline_run_id"], str(self.run_alpha.id))
        self.assertEqual(data_alpha["paper"]["screening_status"], "borderline")
        self.assertEqual(data_alpha["paper"]["signal_score"], 62.0)
        self.assertEqual(data_alpha["metric"]["signal_score"], 62.0)

        # Querying run_beta returns the beta metrics
        res_beta = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}")
        self.assertEqual(res_beta.status_code, 200)
        data_beta = res_beta.json()

        self.assertEqual(data_beta["paper"]["pipeline_run_id"], str(self.run_beta.id))
        self.assertEqual(data_beta["paper"]["screening_status"], "accepted")
        self.assertEqual(data_beta["paper"]["signal_score"], 94.5)
        self.assertEqual(data_beta["metric"]["signal_score"], 94.5)

    def test_8_rich_dimension_details_and_risk_and_affiliation(self):
        """
        Verifies:
        1. Dimension rich layout matching Image 1: facets with sub-scores, prose insight texts, rationale
        2. Dimension rich layout matching Image 2: band pill label, facts key-value pairs
        3. Risk & Affiliation extraction is extracted into paper['risk_and_affiliation']
           and flagged on dimension with is_risk_and_affiliation=True.
        """
        # Definition 1: Research Metrics (Image 1 style: headline 68, facets Novelty 68, Significance 72, prose insight)
        def_research = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Research Metrics",
            response_schema={
                "type": "object",
                "properties": {
                    "research_score": {"type": "number"},
                    "novelty_score": {"type": "number"},
                    "significance_score": {"type": "number"},
                    "research_quality_insight": {"type": "string"},
                },
            },
            exit_metrics="research_score, novelty_score, significance_score",
            is_active=True,
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=def_research,
            category="Research Metrics",
            fields_data={
                "research_score": 68,
                "novelty_score": 68,
                "significance_score": 72,
                "research_quality_insight": "The work excels in formal grounding and algorithmic innovation.",
            },
            confidence_score=0.90,
            version_info={"llm_model": "google/gemini-3.8-flash"},
        )

        # Definition 2: TRL (Image 2 style: band pill, headline 4 / 9, facts Confidence & Core technology)
        def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Technology Readiness Level (TRL)",
            response_schema={
                "type": "object",
                "properties": {
                    "trl_level": {"type": "number"},
                    "trl_band": {"type": "string"},
                    "confidence_assessment": {"type": "string"},
                    "core_technology": {"type": "string"},
                },
            },
            exit_metrics="trl_level",
            is_active=True,
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=def_trl,
            category="TRL",
            fields_data={
                "trl_level": 4,
                "trl_band": "TRL 4 — Technology validated in lab",
                "rationale": "The authors designed, implemented, and fully integrated an end-to-end prototype agentic pipeline.",
                "confidence_level": "HIGH",
                "core_technology": "LLM-driven stepwise formal program refinement framework",
            },
            confidence_score=0.90,
            version_info={"llm_model": "google/gemini-3.8-flash"},
        )

        # Definition 3: Risk and Affiliation Flagging
        def_risk = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Risk and Affiliation Flagging",
            response_schema={
                "type": "object",
                "properties": {
                    "author_affiliation": {"type": "string"},
                    "author_contacts": {"type": "array"},
                    "funding_entities": {"type": "array"},
                    "schwarz_ecosystem_affiliation": {"type": "string"},
                    "gdpr_concerns": {"type": "string"},
                    "codebase_artifact_link": {"type": "string"},
                },
            },
            exit_metrics="schwarz_ecosystem_affiliation, gdpr_concerns",
            is_active=True,
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=def_risk,
            category="risk_and_affiliation",
            fields_data={
                "author_affiliation": "University of Edinburgh, University of Cambridge",
                "author_contacts": ["alex.rice@ed.ac.uk", "chris.heunen@ed.ac.uk"],
                "funding_entities": ["EPSRC Grant EP/T001234/1"],
                "codebase_artifact_link": "https://doi.org/10.5281/zenodo.1234567",
                "schwarz_ecosystem_affiliation": "NO (Academic institutions)",
                "gdpr_concerns": "NO (Synthetic benchmark datasets)",
                "competitor_involvement": "NO",
                "risk_score": 10.0,
                "risk_score_assessment": "Low risk academic publication.",
            },
            confidence_score=0.95,
        )

        res = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Check 1: Image 1 style dimension (Research Metrics)
        dim_res = next(d for d in data["paper"]["dimensions"] if d["definition_id"] == str(def_research.id))
        self.assertEqual(dim_res["value"], 68)
        self.assertIsNotNone(dim_res["facets"])
        facet_keys = [f["key"] for f in dim_res["facets"]]
        self.assertIn("novelty_score", facet_keys)
        self.assertIn("significance_score", facet_keys)
        # Check values
        novelty_facet = next(f for f in dim_res["facets"] if f["key"] == "novelty_score")
        self.assertEqual(novelty_facet["value"], 68)
        self.assertEqual(novelty_facet["name"], "Novelty")
        signif_facet = next(f for f in dim_res["facets"] if f["key"] == "significance_score")
        self.assertEqual(signif_facet["value"], 72)
        self.assertEqual(signif_facet["name"], "Significance")
        # Check texts (prose insight)
        self.assertIsNotNone(dim_res["texts"])
        text_entry = next(t for t in dim_res["texts"] if t["key"] == "research_quality_insight")
        self.assertEqual(text_entry["name"], "Research quality insight")
        self.assertIn("algorithmic innovation", text_entry["value"])

        # Check 2: Image 2 style dimension (TRL)
        dim_trl = next(d for d in data["paper"]["dimensions"] if d["definition_id"] == str(def_trl.id))
        self.assertEqual(dim_trl["value"], 4)
        self.assertEqual(dim_trl["max"], 9)
        self.assertEqual(dim_trl["band"], "TRL 4 — Technology validated in lab")
        self.assertIn("prototype agentic pipeline", dim_trl["rationale"])
        self.assertIsNotNone(dim_trl["facts"])
        fact_keys = [f["key"] for f in dim_trl["facts"]]
        self.assertIn("core_technology", fact_keys)
        ct_fact = next(f for f in dim_trl["facts"] if f["key"] == "core_technology")
        self.assertEqual(ct_fact["name"], "Core technology")
        self.assertEqual(ct_fact["value"], "LLM-driven stepwise formal program refinement framework")

        # Check 3: Risk and Affiliation Flagging
        risk_dim = next(d for d in data["paper"]["dimensions"] if d["definition_id"] == str(def_risk.id))
        self.assertTrue(risk_dim["is_risk_and_affiliation"])

        # Paper level structured risk_and_affiliation object
        ra = data["paper"]["risk_and_affiliation"]
        self.assertIsNotNone(ra)
        self.assertIn("University of Edinburgh", ra["affiliations"])
        self.assertIn("alex.rice@ed.ac.uk", ra["author_contacts"])
        self.assertIn("EPSRC Grant EP/T001234/1", ra["funding_entities"])
        self.assertEqual(ra["codebase_artifact_link"], "https://doi.org/10.5281/zenodo.1234567")
        self.assertIn("NO", ra["gdpr_concerns"])
        self.assertIn("NO", ra["schwarz_ecosystem_affiliation"])
        self.assertEqual(len(ra["flags"]), 3)

    def test_9_nested_value_unwrapping_in_risk_and_affiliation(self):
        """
        Verifies SOTA recursive _unwrap_val and extra aliases in extract_risk_and_affiliation:
        - {"value": ...} recursive unwrapping
        - Extra repo aliases: github_url, zenodo_link, repository_url, dataset_url
        - Nested dictionary flag values
        """
        # Test unit function _unwrap_val directly
        self.assertEqual(_unwrap_val({"value": "direct"}), "direct")
        self.assertEqual(_unwrap_val({"value": {"value": {"value": 42}}}), 42)
        self.assertEqual(_unwrap_val("scalar"), "scalar")
        self.assertEqual(_unwrap_val([1, 2]), [1, 2])

        fields_nested = {
            "fields": {
                "author_affiliation": {"value": "Schwarz Research, Technical University of Munich"},
                "author_contacts": {"value": ["researcher@schwarz.de", "info@tum.de"]},
                "funding_entities": {"value": "Schwarz Innovation Grant 2026"},
                "github_url": {"value": {"value": "https://github.com/schwarzit/quantum-opt"}},
                "schwarz_ecosystem_affiliation": {"value": "YES (Schwarz Digits Partner)"},
                "gdpr_concerns": {"value": "NO (No PII involved)"},
                "competitor_involvement": {"value": "NO (Independent academic evaluation)"},
                "risk_score": {"value": 15.0},
                "risk_score_assessment": {"value": "Low overall sovereign risk profile."},
            }
        }
        res = extract_risk_and_affiliation(fields_nested)
        self.assertIsNotNone(res)
        self.assertEqual(res["affiliations"], ["Schwarz Research", "Technical University of Munich"])
        self.assertEqual(res["author_contacts"], ["researcher@schwarz.de", "info@tum.de"])
        self.assertEqual(res["funding_entities"], ["Schwarz Innovation Grant 2026"])
        self.assertEqual(res["codebase_artifact_link"], "https://github.com/schwarzit/quantum-opt")
        self.assertEqual(res["schwarz_ecosystem_affiliation"], "YES (Schwarz Digits Partner)")
        self.assertEqual(res["gdpr_concerns"], "NO (No PII involved)")
        self.assertEqual(res["competitor_involvement"], "NO (Independent academic evaluation)")
        self.assertEqual(res["risk_score"], 15.0)
        self.assertEqual(res["risk_score_assessment"], "Low overall sovereign risk profile.")

        # Flag statuses
        flag_map = {f["key"]: f for f in res["flags"]}
        self.assertEqual(flag_map["gdpr"]["status"], "safe")
        self.assertEqual(flag_map["schwarz_ecosystem"]["status"], "highlight")
        self.assertEqual(flag_map["competitor"]["status"], "safe")

    def test_10_rich_dimension_zero_boundary_probability_scale(self):
        """
        Verifies that confidence/probability facets with values between 0.0 and 1.0
        (including zero boundary 0.0 and 1.0) receive max=1 instead of max=100.
        """
        fields_data = {
            "fields": {
                "primary_score": 85,
                "confidence_score": 0.0,  # zero boundary
                "confidence_assessment": "Uncertain theoretical conjecture",
                "detection_probability": 0.98,
                "error_rate": 0.05,
                "general_score": 75,
            }
        }
        primary_metric = {"key": "primary_score", "numeric_value": 85}
        secondary_metrics = [
            {"key": "confidence_score", "is_numeric": True, "numeric_value": 0.0},
            {"key": "detection_probability", "is_numeric": True, "numeric_value": 0.98},
            {"key": "error_rate", "is_numeric": True, "numeric_value": 0.05},
            {"key": "general_score", "is_numeric": True, "numeric_value": 75},
        ]

        rich = extract_rich_dimension_details(
            fields_data=fields_data,
            primary_metric=primary_metric,
            secondary_metrics=secondary_metrics,
            max_val=100,
        )

        facets = {f["key"]: f for f in rich["facets"]}
        # confidence_score: 0.0 -> max must be 1
        self.assertEqual(facets["confidence_score"]["value"], 0.0)
        self.assertEqual(facets["confidence_score"]["max"], 1)
        self.assertEqual(facets["confidence_score"]["text"], "Uncertain theoretical conjecture")

        # detection_probability: 0.98 -> max must be 1
        self.assertEqual(facets["detection_probability"]["value"], 0.98)
        self.assertEqual(facets["detection_probability"]["max"], 1)

        # error_rate: 0.05 -> max must be 1 (rate keyword)
        self.assertEqual(facets["error_rate"]["value"], 0.05)
        self.assertEqual(facets["error_rate"]["max"], 1)

        # general_score: 75 -> max must remain 100
        self.assertEqual(facets["general_score"]["value"], 75)
        self.assertEqual(facets["general_score"]["max"], 100)

    def test_11_workspace_scorecard_endpoint(self):
        """
        Verify GET /api/workspaces/{id}/scorecard/ and ?run_id= returns structured
        workspace scorecard with workspace summary and list of ScoredPapers.
        """
        # 1. Without run_id
        res = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("workspace", data)
        self.assertIn("papers", data)
        self.assertIn("results", data)
        self.assertEqual(data["workspace"]["id"], str(self.workspace.id))
        self.assertGreaterEqual(len(data["papers"]), 1)
        p = data["papers"][0]
        self.assertIn("dimensions", p)
        self.assertIn("signal_score", p)
        self.assertIn("title", p)

        # 2. With ?run_id=
        res_run = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={self.run_beta.id}")
        self.assertEqual(res_run.status_code, 200)
        data_run = res_run.json()
        self.assertEqual(data_run["workspace"]["id"], str(self.workspace.id))
        p_run = data_run["papers"][0]
        self.assertEqual(p_run["pipeline_run_id"], str(self.run_beta.id))
        self.assertEqual(p_run["signal_score"], 94.5)

        # 3. With ?pipeline_run={alpha}
        res_alpha = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?pipeline_run={self.run_alpha.id}")
        self.assertEqual(res_alpha.status_code, 200)
        p_alpha = res_alpha.json()["papers"][0]
        self.assertEqual(p_alpha["pipeline_run_id"], str(self.run_alpha.id))
        self.assertEqual(p_alpha["signal_score"], 62.0)
        self.assertEqual(p_alpha["screening_status"], "borderline")

        # 4. With ?screening_status=accepted
        res_stat = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={self.run_beta.id}&screening_status=accepted")
        self.assertEqual(res_stat.status_code, 200)
        self.assertEqual(len(res_stat.json()["papers"]), 1)

    def test_12_structured_dict_submetrics_and_flags_unpacking(self):
        """
        Verifies unpacking of structured dictionaries for sub-metrics (e.g. Novelty, Significance, Rigour)
        and risk flags (Schwarz Ecosystem, Competitor Involvement).
        - band, insight, evidence are cleanly unpacked
        - score is not duplicated in prose texts
        - status and matched institutions/competitors formatted cleanly
        """
        from research_intelligence.services.scorecard_extractors import (
            extract_rich_dimension_details,
            extract_risk_and_affiliation,
        )

        # 1. Test rich dimension details with dictionary sub-metric
        fields_with_dict = {
            "research_quality_insight": "Overall solid paper.",
            "novelty": {
                "band": "Substantial",
                "score": 68,
                "insight": "The paper introduces a substantial new framing by formulating an end-to-end hybrid quantum-classical architecture.",
                "evidence": [
                    "quantum-assisted framework for PDE-based Bayesian inverse problems",
                    "hybrid quantum-classical algorithm using quantum linear system algorithms (QLSAs)",
                ],
            },
            "significance": str({
                "band": "Important",
                "score": 62,
                "insight": "This work addresses a prominent bottleneck in computational science.",
                "evidence": ["mitigates the cubic complexity barrier in large-scale inverse problems"],
            }),
            "novelty_computed": 68,
            "novelty_postprocessed": 68,
        }

        rich = extract_rich_dimension_details(
            fields_data=fields_with_dict,
            primary_metric={"key": "research_quality_score", "numeric_value": 75, "value": 75},
            secondary_metrics=[
                {"key": "novelty", "name": "Novelty", "numeric_value": 68, "is_numeric": True},
            ],
            max_val=100,
        )

        # Check texts
        text_by_key = {t["key"]: t for t in rich["texts"]}
        self.assertIn("novelty", text_by_key)
        self.assertEqual(text_by_key["novelty"]["band"], "Substantial")
        self.assertEqual(
            text_by_key["novelty"]["value"],
            "The paper introduces a substantial new framing by formulating an end-to-end hybrid quantum-classical architecture.",
        )
        self.assertNotIn("68", text_by_key["novelty"]["value"])
        self.assertEqual(len(text_by_key["novelty"]["evidence"]), 2)

        self.assertIn("significance", text_by_key)
        self.assertEqual(text_by_key["significance"]["band"], "Important")
        self.assertEqual(
            text_by_key["significance"]["value"],
            "This work addresses a prominent bottleneck in computational science.",
        )
        self.assertEqual(text_by_key["significance"]["type"], "dict")
        self.assertTrue(text_by_key["significance"]["is_dict"])
        self.assertIsInstance(text_by_key["significance"]["dict_value"], dict)

        self.assertEqual(text_by_key["novelty"]["type"], "dict")
        self.assertTrue(text_by_key["novelty"]["is_dict"])
        self.assertIsInstance(text_by_key["novelty"]["dict_value"], dict)
        self.assertEqual(text_by_key["novelty"]["score"], 68)

        # Ensure pipeline internal duplicates are excluded
        self.assertNotIn("novelty_computed", text_by_key)
        self.assertNotIn("novelty_postprocessed", text_by_key)

        # Check facets: Novelty facet has band and text
        facet_by_key = {f["key"]: f for f in rich["facets"]}
        self.assertIn("novelty", facet_by_key)
        self.assertEqual(facet_by_key["novelty"]["band"], "Substantial")
        self.assertEqual(
            facet_by_key["novelty"]["text"],
            "The paper introduces a substantial new framing by formulating an end-to-end hybrid quantum-classical architecture.",
        )

        # Check evidence list
        self.assertIn("quantum-assisted framework for PDE-based Bayesian inverse problems", rich["evidence"])
        self.assertIn("mitigates the cubic complexity barrier in large-scale inverse problems", rich["evidence"])

        # 2. Test risk and affiliation unpacking with dictionaries
        risk_fields = {
            "schwarz_ecosystem_affiliation": "{'status': 'YES', 'matched_institutions': ['TUM']}",
            "competitor_involvement": "{'status': 'NO', 'matches': None}",
            "gdpr_concerns": "{'status': 'NO', 'details': None}",
        }
        risk_res = extract_risk_and_affiliation(risk_fields)
        self.assertEqual(risk_res["schwarz_ecosystem_affiliation"], "YES (TUM)")
        self.assertEqual(risk_res["competitor_involvement"], "None")
        self.assertEqual(risk_res["gdpr_concerns"], "NO")
        self.assertIn("TUM", risk_res["affiliations"])

        flag_by_key = {f["key"]: f for f in risk_res["flags"]}
        self.assertEqual(flag_by_key["schwarz_ecosystem"]["value"], "YES (TUM)")
        self.assertEqual(flag_by_key["schwarz_ecosystem"]["status"], "highlight")
        self.assertEqual(flag_by_key["schwarz_ecosystem"]["type"], "dict")
        self.assertTrue(flag_by_key["schwarz_ecosystem"]["is_dict"])
        self.assertIsInstance(flag_by_key["schwarz_ecosystem"]["dict_value"], dict)

        self.assertEqual(flag_by_key["competitor"]["value"], "None")
        self.assertEqual(flag_by_key["competitor"]["status"], "safe")
        self.assertEqual(flag_by_key["competitor"]["type"], "dict")
        self.assertTrue(flag_by_key["competitor"]["is_dict"])

        self.assertEqual(flag_by_key["gdpr"]["value"], "NO")
        self.assertEqual(flag_by_key["gdpr"]["status"], "safe")

        # Test competitor with positive match
        risk_comp = extract_risk_and_affiliation({
            "competitor_involvement": {"status": "YES", "matches": ["Google", "Amazon"]},
        })
        self.assertEqual(risk_comp["competitor_involvement"], "YES (Google, Amazon)")
        flag_comp = {f["key"]: f for f in risk_comp["flags"]}
        self.assertEqual(flag_comp["competitor"]["value"], "YES (Google, Amazon)")
        self.assertEqual(flag_comp["competitor"]["status"], "warn")
        self.assertEqual(flag_comp["competitor"]["type"], "dict")
        self.assertTrue(flag_comp["competitor"]["is_dict"])
        self.assertIsInstance(flag_comp["competitor"]["dict_value"], dict)

    def test_13_explicit_frontend_metrics_classification(self):
        """
        Verifies explicit primary_frontend_metric and secondary_frontend_metrics:
        - Primary and secondary metrics are taken directly from explicit definition fields.
        - Magic heuristic / suffix scanning is bypassed.
        - Serializer correctly represents primary_frontend_metric and secondary_frontend_metrics.
        - Scorecard API endpoint delivers explicit frontend metrics in metadata and dimensions.
        """
        from research_intelligence.services.scorecard_extractors import extract_metrics_for_extraction
        from api.serializers.workspaces import ExtractionDefinitionSerializer

        # 1. Create definition with explicit frontend metrics
        def_explicit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Quantum Computing Practicality",
            system_prompt="Extract practicality parameters.",
            user_prompt_template="Extract for {paper_text}",
            response_schema={"type": "object", "properties": {"practicality_score": {"type": "number"}}},
            primary_frontend_metric="practicality_score",
            secondary_frontend_metrics=["qubit_fidelity", "gate_speed", "coherence_time"],
            exit_metrics="practicality_score, signal_var1",
        )

        extraction_data = {
            "practicality_score": 88,
            "qubit_fidelity": 99.9,
            "gate_speed": {"score": 95, "band": "High Speed", "insight": "Sub-nanosecond gate execution."},
            "coherence_time": 120,
            "random_extra_score": 50,  # Should NOT be scanned as a secondary metric because secondary_frontend_metrics is explicit!
            "irrelevant_computed": 42,
        }

        ext = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=def_explicit,
            category="Quantum Computing Practicality",
            fields_data=extraction_data,
        )

        # 2. Verify extractor resolution
        prim, sec, has_post = extract_metrics_for_extraction(ext, def_explicit)
        self.assertEqual(prim["key"], "practicality_score")
        self.assertEqual(prim["numeric_value"], 88)
        self.assertEqual(prim["source"], "frontend_metric")

        sec_keys = [s["key"] for s in sec]
        self.assertEqual(sec_keys, ["qubit_fidelity", "gate_speed", "coherence_time"])
        self.assertNotIn("random_extra_score", sec_keys)
        self.assertNotIn("irrelevant_computed", sec_keys)

        # 3. Verify serializer output
        ser = ExtractionDefinitionSerializer(def_explicit)
        self.assertEqual(ser.data["primary_frontend_metric"], "practicality_score")
        self.assertEqual(ser.data["secondary_frontend_metrics"], ["qubit_fidelity", "gate_speed", "coherence_time"])

        # 4. Verify scorecard API response payload
        url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Check definition metadata
        def_meta = next((d for d in data["definitions"] if d["id"] == str(def_explicit.id)), None)
        self.assertIsNotNone(def_meta)
        self.assertEqual(def_meta["primary_frontend_metric"], "practicality_score")
        self.assertEqual(def_meta["secondary_frontend_metrics"], ["qubit_fidelity", "gate_speed", "coherence_time"])
        self.assertEqual(def_meta["primary_metric_key"], "practicality_score")
        self.assertEqual(def_meta["secondary_metric_keys"], ["qubit_fidelity", "gate_speed", "coherence_time"])

        # Check dimension
        dim = next((d for d in data["paper"]["dimensions"] if d["definition_id"] == str(def_explicit.id)), None)
        self.assertIsNotNone(dim)
        self.assertEqual(dim["value"], 88)
        self.assertEqual(dim["primary_frontend_metric"], "practicality_score")
        self.assertEqual(dim["secondary_frontend_metrics"], ["qubit_fidelity", "gate_speed", "coherence_time"])

        facet_keys = [f["key"] for f in dim["facets"]]
        self.assertIn("qubit_fidelity", facet_keys)
        self.assertIn("gate_speed", facet_keys)
        self.assertIn("coherence_time", facet_keys)
        self.assertNotIn("random_extra_score", facet_keys)

    def test_14_explicit_metrics_all_four_permutation_cases(self):
        """
        Verify all 4 permutation cases for primary and secondary frontend metrics:
        1. Explicit primary + several secondary:
           - Headline gets primary; submetrics get all secondaries (no duplicate promotion).
        2. Explicit primary + NO secondary:
           - Headline gets primary; NO secondary submetrics.
        3. NO primary + several secondary (user's exact bug case: novelty, significance, rigour):
           - Headline has NO number (value=None, raw=None); all 3 secondary metrics rendered in submetrics.
        4. NO primary + NO secondary:
           - Defaults to legacy algorithm (exit metrics fallback: first is primary, rest are secondary).
        """
        # Case 1: Explicit primary + multiple secondary
        def_case1 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Case 1 Primary And Secondaries",
            response_schema={"type": "object", "properties": {"main_score": {"type": "number"}, "sub_a": {"type": "number"}, "sub_b": {"type": "number"}}},
            exit_metrics="fallback_exit, sub_a, sub_b",
            primary_frontend_metric="main_score",
            secondary_frontend_metrics="sub_a, sub_b",
            is_active=True,
        )
        ext_case1 = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=def_case1,
            category="Case 1 Primary And Secondaries",
            fields_data={"main_score": 85, "sub_a": 70, "sub_b": 80, "fallback_exit": 99},
        )
        self.assertTrue(def_case1.has_explicit_frontend_metrics())
        self.assertEqual(def_case1.get_primary_frontend_metric(), "main_score")
        self.assertEqual(def_case1.get_secondary_frontend_metrics_list(), ["sub_a", "sub_b"])
        prim1, sec1, _ = extract_metrics_for_extraction(ext_case1, def_case1)
        self.assertEqual(prim1["key"], "main_score")
        self.assertEqual(prim1["numeric_value"], 85)
        self.assertEqual([s["key"] for s in sec1], ["sub_a", "sub_b"])

        # Case 2: Explicit primary + NO secondary
        def_case2 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Case 2 Primary And No Secondaries",
            response_schema={"type": "object", "properties": {"solo_score": {"type": "number"}, "fallback_1": {"type": "number"}, "fallback_2": {"type": "number"}}},
            exit_metrics="fallback_1, fallback_2",
            primary_frontend_metric="solo_score",
            secondary_frontend_metrics="",
            is_active=True,
        )
        ext_case2 = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=def_case2,
            category="Case 2 Primary And No Secondaries",
            fields_data={"solo_score": 92, "fallback_1": 60, "fallback_2": 70},
        )
        self.assertTrue(def_case2.has_explicit_frontend_metrics())
        self.assertEqual(def_case2.get_primary_frontend_metric(), "solo_score")
        self.assertEqual(def_case2.get_secondary_frontend_metrics_list(), [])
        prim2, sec2, _ = extract_metrics_for_extraction(ext_case2, def_case2)
        self.assertEqual(prim2["key"], "solo_score")
        self.assertEqual(prim2["numeric_value"], 92)
        self.assertEqual(sec2, [])

        # Case 3: NO primary + multiple secondary (User's case: novelty, significance, rigour)
        def_case3 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Research Metrics Test Case",
            response_schema={"type": "object", "properties": {"novelty": {"type": "number"}, "significance": {"type": "number"}, "rigour": {"type": "number"}}},
            exit_metrics="novelty, significance, rigour",
            primary_frontend_metric="",
            secondary_frontend_metrics="novelty, significance, rigour",
            is_active=True,
        )
        ext_case3 = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=def_case3,
            category="Research Metrics Test Case",
            fields_data={"novelty": 68, "significance": 65, "rigour": 72},
        )
        self.assertTrue(def_case3.has_explicit_frontend_metrics())
        self.assertIsNone(def_case3.get_primary_frontend_metric())
        self.assertEqual(def_case3.get_secondary_frontend_metrics_list(), ["novelty", "significance", "rigour"])
        prim3, sec3, _ = extract_metrics_for_extraction(ext_case3, def_case3)
        self.assertIsNone(prim3)
        self.assertEqual([s["key"] for s in sec3], ["novelty", "significance", "rigour"])

        # Case 4: NO primary + NO secondary (legacy algorithm fallback)
        def_case4 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Case 4 Legacy Fallback",
            response_schema={"type": "object", "properties": {"first_exit": {"type": "number"}, "second_exit": {"type": "number"}, "third_exit": {"type": "number"}}},
            exit_metrics="first_exit, second_exit, third_exit",
            primary_frontend_metric="",
            secondary_frontend_metrics="",
            is_active=True,
        )
        ext_case4 = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=def_case4,
            category="Case 4 Legacy Fallback",
            fields_data={"first_exit": 50, "second_exit": 60, "third_exit": 70},
        )
        self.assertFalse(def_case4.has_explicit_frontend_metrics())
        self.assertEqual(def_case4.get_primary_frontend_metric(), "first_exit")
        self.assertEqual(def_case4.get_secondary_frontend_metrics_list(), ["second_exit", "third_exit"])
        prim4, sec4, _ = extract_metrics_for_extraction(ext_case4, def_case4)
        self.assertEqual(prim4["key"], "first_exit")
        self.assertEqual(prim4["numeric_value"], 50)
        self.assertEqual([s["key"] for s in sec4], ["second_exit", "third_exit"])

        # Verify all 4 dimensions in scorecard API endpoint
        url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        dims = {d["definition_id"]: d for d in data["paper"]["dimensions"]}

        # Check Case 1 API payload:
        dim1 = dims[str(def_case1.id)]
        self.assertEqual(dim1["value"], 85)
        self.assertEqual(dim1["primary_metric"]["key"], "main_score")
        self.assertEqual(len(dim1["secondary_metrics"]), 2)
        self.assertEqual([f["key"] for f in dim1["facets"]], ["sub_a", "sub_b"])

        # Check Case 2 API payload:
        dim2 = dims[str(def_case2.id)]
        self.assertEqual(dim2["value"], 92)
        self.assertEqual(dim2["primary_metric"]["key"], "solo_score")
        self.assertEqual(dim2["secondary_metrics"], [])
        self.assertEqual(dim2["facets"], [])

        # Check Case 3 API payload (no primary, 3 secondaries):
        dim3 = dims[str(def_case3.id)]
        self.assertIsNone(dim3["value"])
        self.assertIsNone(dim3["raw"])
        self.assertIsNone(dim3["primary_metric"])
        self.assertEqual(len(dim3["secondary_metrics"]), 3)
        self.assertEqual([s["key"] for s in dim3["secondary_metrics"]], ["novelty", "significance", "rigour"])
        self.assertEqual([f["key"] for f in dim3["facets"]], ["novelty", "significance", "rigour"])
        self.assertEqual(dim3["facets"][0]["value"], 68)
        self.assertEqual(dim3["facets"][1]["value"], 65)
        self.assertEqual(dim3["facets"][2]["value"], 72)

        # Check Case 4 API payload (legacy defaults):
        dim4 = dims[str(def_case4.id)]
        self.assertEqual(dim4["value"], 50)
        self.assertEqual(dim4["primary_metric"]["key"], "first_exit")
        self.assertEqual(len(dim4["secondary_metrics"]), 2)
        self.assertEqual([f["key"] for f in dim4["facets"]], ["second_exit", "third_exit"])

    def test_15_postprocessing_dict_returned_as_primary_and_secondary_frontend_metrics(self):
        """
        Validates postprocessing returning a dictionary of metrics where one of the returned
        keys (e.g. 'research_metric_avg') is selected as primary_frontend_metric, and others
        as secondary_frontend_metrics. Even if fields_data in the database initially only
        contained raw submetrics ('novelty', 'significance', 'rigour') without the computed key,
        the scorecard engine evaluates the postprocessing dynamically and surfaces the value on frontend.
        """
        post_code = """
novelty_score = float(novelty.get("score", 0) or 0)
significance_score = float(significance.get("score", 0) or 0)
rigour_score = float(rigour.get("score", 0) or 0)
research_metric = (novelty_score + significance_score + rigour_score) / 3
return {
    "novelty_score": novelty_score,
    "significance_score": significance_score,
    "rigour_score": rigour_score,
    "research_metric_avg": research_metric
}
"""
        def_res = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Research Rigour & Quality",
            response_schema={"type": "object"},
            primary_frontend_metric="research_metric_avg",
            secondary_frontend_metrics="novelty_score, significance_score, rigour_score",
            postprocessing_code=post_code,
            is_active=True,
        )

        ext = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=def_res,
            category="Research Quality",
            fields_data={
                "novelty": {"score": 8, "reasoning": "High novelty"},
                "significance": {"score": 7, "reasoning": "Good significance"},
                "rigour": {"score": 9, "reasoning": "Rigorous proofs"},
            },
        )

        url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        dim = next(d for d in data["paper"]["dimensions"] if d["definition_id"] == str(def_res.id))
        self.assertIsNotNone(dim["primary_metric"])
        self.assertEqual(dim["primary_metric"]["key"], "research_metric_avg")
        self.assertEqual(dim["primary_metric"]["numeric_value"], 8.0)
        self.assertEqual(dim["value"], 8.0)

        # Check secondary metrics
        sec_keys = [s["key"] for s in dim["secondary_metrics"]]
        self.assertIn("novelty_score", sec_keys)
        self.assertIn("significance_score", sec_keys)
        self.assertIn("rigour_score", sec_keys)

        # Check facets
        facet_keys = [f["key"] for f in dim["facets"]]
        self.assertIn("novelty_score", facet_keys)
        self.assertIn("significance_score", facet_keys)
        self.assertIn("rigour_score", facet_keys)
        nov_f = next(f for f in dim["facets"] if f["key"] == "novelty_score")
        self.assertEqual(nov_f["value"], 8.0)

    def test_16_extraction_pipeline_job_executes_postprocessing_dict_and_serves_via_api(self):
        """
        End-to-End test for extraction pipeline job execution with postprocessing returning a dict:
        1. Configures ExtractionDefinition with postprocessing snippet returning a dictionary of multiple metrics,
           and sets primary_frontend_metric="research_metric_avg", secondary_frontend_metrics="novelty_score, significance_score, rigour_score".
        2. Executes the real Step 5 Celery task (execute_extraction_job) with mocked LLM output.
        3. Verifies that the Extraction record in PostgreSQL has fields_data populated with the postprocessed dictionary.
        4. Calls Paper Scorecard API (GET /api/papers/{id}/scorecard/?pipeline_run={id}), verifying:
           - primary_metric: key="research_metric_avg", numeric_value=9.0, dimension value=9.0
           - secondary_metrics: contains novelty_score (9.0), significance_score (8.0), rigour_score (10.0)
           - facets: contains the parsed secondary metrics.
        5. Calls Workspace Scorecard API (GET /api/workspaces/{id}/scorecard/?pipeline_run={id}), verifying
           the paper's dimensions are rendered with the postprocessed metrics.
        6. Updates definition primary_frontend_metric dynamically to another key in the postprocessed dict,
           and confirms API reflects the updated selection immediately.
        """
        post_code = """
novelty_score = float(novelty.get("score", 0) or 0)
significance_score = float(significance.get("score", 0) or 0)
rigour_score = float(rigour.get("score", 0) or 0)
research_metric = (novelty_score + significance_score + rigour_score) / 3
return {
    "novelty_score": novelty_score,
    "significance_score": significance_score,
    "rigour_score": rigour_score,
    "research_metric_avg": research_metric
}
"""
        def_pipeline = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="E2E Pipeline Rigour & Quality",
            response_schema={"type": "object"},
            primary_frontend_metric="research_metric_avg",
            secondary_frontend_metrics="novelty_score, significance_score, rigour_score",
            postprocessing_code=post_code,
            is_active=True,
        )

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.run_beta,
            step_type="extraction",
            component_name="parameter_extraction",
            status="pending",
        )

        # Mock LLM provider to return the raw model outputs for the paper
        with patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider") as mock_get_llm:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (
                {
                    "novelty": {"score": 9.0, "reasoning": "Highly novel approach"},
                    "significance": {"score": 8.0, "reasoning": "Clear industrial impact"},
                    "rigour": {"score": 10.0, "reasoning": "Rigorous proofs and benchmarks"},
                },
                {"prompt_tokens": 15, "candidates_tokens": 10},
            )
            mock_get_llm.return_value = mock_provider

            # Execute the extraction job
            job_success = execute_extraction_job(str(comp_run.id))
            self.assertTrue(job_success)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")

        # 1. Verify Extraction record in database was generated and populated with postprocessed dict
        ext = Extraction.objects.get(paper=self.paper, extraction_definition=def_pipeline)
        self.assertIsNotNone(ext)
        self.assertIn("research_metric_avg", ext.fields_data)
        self.assertEqual(ext.fields_data["research_metric_avg"], 9.0)
        self.assertEqual(ext.fields_data["novelty_score"], 9.0)
        self.assertEqual(ext.fields_data["significance_score"], 8.0)
        self.assertEqual(ext.fields_data["rigour_score"], 10.0)

        # 2. Call Paper Scorecard API
        url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        dim = next(d for d in data["paper"]["dimensions"] if d["definition_id"] == str(def_pipeline.id))
        self.assertIsNotNone(dim["primary_metric"])
        self.assertEqual(dim["primary_metric"]["key"], "research_metric_avg")
        self.assertEqual(dim["primary_metric"]["numeric_value"], 9.0)
        self.assertEqual(dim["value"], 9.0)

        sec_keys = [s["key"] for s in dim["secondary_metrics"]]
        self.assertEqual(sec_keys, ["novelty_score", "significance_score", "rigour_score"])
        sec_map = {s["key"]: s["numeric_value"] for s in dim["secondary_metrics"]}
        self.assertEqual(sec_map["novelty_score"], 9.0)
        self.assertEqual(sec_map["significance_score"], 8.0)
        self.assertEqual(sec_map["rigour_score"], 10.0)

        facet_keys = [f["key"] for f in dim["facets"]]
        self.assertIn("novelty_score", facet_keys)
        self.assertIn("significance_score", facet_keys)
        self.assertIn("rigour_score", facet_keys)

        # 3. Call Workspace Scorecard API
        ws_url = f"/api/workspaces/{self.workspace.id}/scorecard/?pipeline_run={self.run_beta.id}"
        ws_resp = self.client.get(ws_url)
        self.assertEqual(ws_resp.status_code, 200)
        ws_data = ws_resp.json()
        paper_item = next(p for p in ws_data["papers"] if p["id"] == str(self.paper.id))
        ws_dim = next(d for d in paper_item["dimensions"] if d["definition_id"] == str(def_pipeline.id))
        self.assertEqual(ws_dim["primary_metric"]["key"], "research_metric_avg")
        self.assertEqual(ws_dim["primary_metric"]["numeric_value"], 9.0)
        self.assertEqual(ws_dim["value"], 9.0)

        # 4. Dynamic reconfiguration test: change primary_frontend_metric to 'significance_score'
        def_pipeline.primary_frontend_metric = "significance_score"
        def_pipeline.save()

        resp_dyn = self.client.get(url)
        self.assertEqual(resp_dyn.status_code, 200)
        dim_dyn = next(d for d in resp_dyn.json()["paper"]["dimensions"] if d["definition_id"] == str(def_pipeline.id))
        self.assertEqual(dim_dyn["primary_metric"]["key"], "significance_score")
        self.assertEqual(dim_dyn["primary_metric"]["numeric_value"], 8.0)
        self.assertEqual(dim_dyn["value"], 8.0)

    def test_17_extraction_definition_init_and_sanitization_and_page_size_safety(self):
        """
        Validates issue #142 hygiene fixes:
        1. ExtractionDefinition.__init__ correctly handles both singular and plural alias without TypeError.
        2. get_primary_frontend_metric sanitizes identifiers on read.
        3. format_workspace_summary outputs real workspace created_at instead of hardcoded '2026-01-01T00:00:00Z'.
        4. GET /api/workspaces/{id}/scorecard/ clamps page_size <= 0 without raising HTTP 500.
        """
        # 1. Alias handling without TypeError
        ed1 = ExtractionDefinition(
            workspace=self.workspace,
            name="Alias Test 1",
            primary_frontend_metric="main_metric",
            primary_frontend_metrics="alias_metric",
        )
        self.assertEqual(ed1.primary_frontend_metric, "main_metric")

        ed2 = ExtractionDefinition(
            workspace=self.workspace,
            name="Alias Test 2",
            primary_frontend_metrics="alias_only",
        )
        self.assertEqual(ed2.primary_frontend_metric, "alias_only")

        # 2. Sanitization on read
        ed3 = ExtractionDefinition(
            workspace=self.workspace,
            name="Sanitize Test",
            primary_frontend_metric="  Novelty Score & Rigour!  ",
        )
        self.assertEqual(ed3.get_primary_frontend_metric(), "novelty_score_rigour")

        # 3. format_workspace_summary created_at real ISO string
        summary = format_workspace_summary(self.workspace)
        self.assertNotEqual(summary["created_at"], "2026-01-01T00:00:00Z")
        self.assertTrue(summary["created_at"].startswith(str(self.workspace.created_at.year)))

        # 4. page_size safety (negative and zero values do not cause HTTP 500)
        resp_neg = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?page_size=-3")
        self.assertEqual(resp_neg.status_code, 200)

        resp_zero = self.client.get(f"/api/workspaces/{self.workspace.id}/scorecard/?page_size=0")
        self.assertEqual(resp_zero.status_code, 200)

    def test_18_production_spec_nested_risk_and_affiliation_adapter(self):
        """
        Validates Option A Tolerant Adapter (issue #142 / backlog item 9):
        On production, Risk & Affiliation LLM extraction results are nested under `metadata`:
          - metadata.institutional_affiliations: list[str]
          - metadata.author_contacts: list[dict with author_name and email]
          - metadata.funding_entities: list[str]
          - metadata.codebase_links: list[str]
          - gdpr_concern: dict with status and concerns[]
          - competitor_involvement: dict with status and competitors[]
          - schwarz_ecosystem_affiliation: dict with status and matched_institutions[]
        Confirms the adapter recovers all data and produces the exact canonical OpenAPI contract:
          - affiliations: unpacked from metadata.institutional_affiliations
          - author_contacts: clean emails (alice@ethz.ch) and names when email is None (Bob Syndrome)
          - codebase_artifact_link: primary string URL (not stringified list)
          - funding_entities: clean list of grant entities
          - gdpr_concerns: formatted with Article 9 reason in parens
          - flags: safe/warn/highlight badges with unpacked reasons
        """
        def_risk = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Risk and Affiliation Flagging",
            response_schema={"type": "object"},
            is_active=True,
        )

        prod_spec_data = {
            "metadata": {
                "institutional_affiliations": ["ETH Zürich", "Stanford University"],
                "author_contacts": [
                    {"author_name": "Dr. Alice Quantum", "email": "alice@ethz.ch"},
                    {"author_name": "Bob Syndrome", "email": None},
                ],
                "funding_entities": ["European Research Council (ERC)", "SNSF Grant 12345"],
                "codebase_links": [
                    "https://github.com/schwarz-research/quantum-error-correction",
                    "https://zenodo.org/record/99999",
                ],
                "dataset_links": ["https://huggingface.co/datasets/quantum-benchmarks"],
            },
            "gdpr_concern": {
                "status": "YES",
                "concerns": ["Article 9 biometric and health-related genetic data processing"],
            },
            "competitor_involvement": {
                "status": "NO",
                "competitors": [],
            },
            "schwarz_ecosystem_affiliation": {
                "status": "YES",
                "matched_institutions": ["ETH Zürich"],
            },
            "risk_score": 25.0,
            "risk_score_assessment": "Moderate compliance review required for Article 9 processing.",
        }

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=def_risk,
            category="risk_and_affiliation",
            fields_data=prod_spec_data,
        )

        url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        risk = data["paper"]["risk_and_affiliation"]
        self.assertIsNotNone(risk)

        # 1. Affiliations recovered from metadata.institutional_affiliations
        self.assertIn("ETH Zürich", risk["affiliations"])
        self.assertIn("Stanford University", risk["affiliations"])

        # 2. Author contacts: email extracted for Alice, clean name for Bob (no 'None' email)
        self.assertIn("alice@ethz.ch", risk["author_contacts"])
        self.assertIn("Bob Syndrome", risk["author_contacts"])
        self.assertNotIn("Bob Syndrome <None>", risk["author_contacts"])

        # 3. Funding entities recovered from metadata.funding_entities
        self.assertIn("European Research Council (ERC)", risk["funding_entities"])
        self.assertIn("SNSF Grant 12345", risk["funding_entities"])

        # 4. Codebase link: first item as string (not "['https://...']")
        self.assertEqual(
            risk["codebase_artifact_link"],
            "https://github.com/schwarz-research/quantum-error-correction"
        )

        # 5. GDPR concerns recovered from singular gdpr_concern with Article 9 reason
        self.assertEqual(
            risk["gdpr_concerns"],
            "YES (Article 9 biometric and health-related genetic data processing)"
        )

        # 6. Flags verification
        flag_map = {f["key"]: f for f in risk["flags"]}
        self.assertEqual(flag_map["gdpr"]["status"], "warn")
        self.assertIn("Article 9", flag_map["gdpr"]["value"])

        self.assertEqual(flag_map["schwarz_ecosystem"]["status"], "highlight")
        self.assertEqual(flag_map["schwarz_ecosystem"]["value"], "YES (ETH Zürich)")

        self.assertEqual(flag_map["competitor"]["status"], "safe")
        self.assertEqual(flag_map["competitor"]["value"], "None")

        # 7. Risk score & assessment
        self.assertEqual(risk["risk_score"], 25.0)
        self.assertEqual(risk["risk_score_assessment"], "Moderate compliance review required for Article 9 processing.")

    def test_19_exact_tum_mqt_core_production_extraction(self):
        """
        Validates the exact production extraction for TUM / mqt-core:
        - metadata.institutional_affiliations -> affiliations (3 German/Austrian research institutions)
        - metadata.funding_entities -> funding_entities (ERC, Bavarian Ministry, BMBF)
        - metadata.author_contacts -> author_contacts (clean emails for mailto links)
        - metadata.codebase_links -> codebase_artifact_link (GitHub URL)
        - gdpr_concern -> status NO (safe)
        - competitor_involvement -> status NO (safe)
        - schwarz_ecosystem_affiliation -> status YES with matched TUM (highlight)
        """
        raw_extraction = {
            "metadata": {
                "dataset_links": [],
                "codebase_links": [
                    "https://github.com/cda-tum/mqt-core"
                ],
                "author_contacts": [
                    {
                        "email": "lukas.berent@tum.de",
                        "author_name": "L. Berent"
                    },
                    {
                        "email": "robert.wille@tum.de",
                        "author_name": "R. Wille"
                    }
                ],
                "funding_entities": [
                    "European Research Council (ERC)",
                    "Bavarian State Ministry of Science and Arts",
                    "Federal Ministry of Education and Research (BMBF)"
                ],
                "institutional_affiliations": [
                    "Technical University of Munich, Germany",
                    "Munich Quantum Valley, Germany",
                    "Software Competence Center Hagenberg GmbH, Austria"
                ]
            },
            "gdpr_concern": {
                "status": "NO",
                "concerns": None
            },
            "competitor_involvement": {
                "status": "NO",
                "matches": None
            },
            "schwarz_ecosystem_affiliation": {
                "status": "YES",
                "matched_institutions": [
                    "TUM"
                ]
            }
        }

        # Test both direct adapter and scorecard extractor
        from research_intelligence.services.affiliation_adapter import adapt_affiliation_data
        result = adapt_affiliation_data(raw_extraction)

        self.assertIsNotNone(result)

        # 1. Institutional affiliations
        self.assertEqual(
            result["affiliations"],
            [
                "Technical University of Munich, Germany",
                "Munich Quantum Valley, Germany",
                "Software Competence Center Hagenberg GmbH, Austria",
            ]
        )

        # 2. Author contacts (clean emails for mailto links in frontend header)
        self.assertEqual(
            result["author_contacts"],
            ["lukas.berent@tum.de", "robert.wille@tum.de"]
        )

        # 3. Funding entities
        self.assertEqual(
            result["funding_entities"],
            [
                "European Research Council (ERC)",
                "Bavarian State Ministry of Science and Arts",
                "Federal Ministry of Education and Research (BMBF)",
            ]
        )

        # 4. Codebase artifact repository link
        self.assertEqual(
            result["codebase_artifact_link"],
            "https://github.com/cda-tum/mqt-core"
        )

        # 5. Sovereignty & Risk flags
        self.assertEqual(result["gdpr_concerns"], "NO")
        self.assertEqual(result["competitor_involvement"], "None")
        self.assertEqual(result["schwarz_ecosystem_affiliation"], "YES (TUM)")

        flags_by_key = {f["key"]: f for f in result["flags"]}
        self.assertEqual(flags_by_key["gdpr"]["status"], "safe")
        self.assertEqual(flags_by_key["gdpr"]["value"], "NO")

        self.assertEqual(flags_by_key["competitor"]["status"], "safe")
        self.assertEqual(flags_by_key["competitor"]["value"], "None")

        self.assertEqual(flags_by_key["schwarz_ecosystem"]["status"], "highlight")
        self.assertEqual(flags_by_key["schwarz_ecosystem"]["value"], "YES (TUM)")

        # 6. End-to-end API test with actual Extraction ID 0ee3ad96-c128-4aa0-a4f8-0a6ee644659d
        import uuid
        def_risk, _ = ExtractionDefinition.objects.get_or_create(
            workspace=self.workspace,
            name="Risk and Affiliation Flagging",
            defaults={"response_schema": {"type": "object"}, "is_active": True},
        )
        # Clear any existing extractions for this paper to test in isolation
        Extraction.objects.filter(paper=self.paper).delete()
        Extraction.objects.create(
            id=uuid.UUID("0ee3ad96-c128-4aa0-a4f8-0a6ee644659d"),
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=def_risk,
            category="Risk and Affiliation Flagging",
            fields_data=raw_extraction,
        )

        api_url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}"
        api_resp = self.client.get(api_url)
        self.assertEqual(api_resp.status_code, 200)
        api_data = api_resp.json()

        paper_risk = api_data["paper"]["risk_and_affiliation"]
        self.assertIsNotNone(paper_risk)
        self.assertEqual(
            paper_risk["affiliations"],
            [
                "Technical University of Munich, Germany",
                "Munich Quantum Valley, Germany",
                "Software Competence Center Hagenberg GmbH, Austria",
            ]
        )
        self.assertEqual(paper_risk["author_contacts"], ["lukas.berent@tum.de", "robert.wille@tum.de"])
        self.assertEqual(
            paper_risk["funding_entities"],
            [
                "European Research Council (ERC)",
                "Bavarian State Ministry of Science and Arts",
                "Federal Ministry of Education and Research (BMBF)",
            ]
        )
        self.assertEqual(paper_risk["codebase_artifact_link"], "https://github.com/cda-tum/mqt-core")
        self.assertEqual(paper_risk["schwarz_ecosystem_affiliation"], "YES (TUM)")
        self.assertEqual(paper_risk["gdpr_concerns"], "NO")
        self.assertEqual(paper_risk["competitor_involvement"], "None")

    def test_20_missing_and_malformed_risk_and_affiliation_handling(self):
        """
        Tests edge cases where risk and affiliation data is completely absent,
        partially missing, contains nulls/None, or cannot be extracted:
        1. None or non-dict input -> returns None (no crash)
        2. Empty dict input -> returns clean structure with empty lists and nulls
        3. Inputs containing placeholders like 'None', 'null', 'n/a', '' -> safely filtered out
        4. Paper with NO risk extraction at all -> API returns paper.risk_and_affiliation: null
        5. Paper with empty risk extraction -> API returns empty arrays and empty flags
        """
        from research_intelligence.services.affiliation_adapter import adapt_affiliation_data

        # 1. Non-dict or null inputs
        self.assertIsNone(adapt_affiliation_data(None))
        self.assertIsNone(adapt_affiliation_data("malformed non-json string"))
        self.assertIsNone(adapt_affiliation_data([1, 2, 3]))
        self.assertEqual(adapt_affiliation_data({"fields": None})["affiliations"], [])

        # 2. Empty dict input
        empty_res = adapt_affiliation_data({})
        self.assertIsNotNone(empty_res)
        self.assertEqual(empty_res["affiliations"], [])
        self.assertEqual(empty_res["author_contacts"], [])
        self.assertEqual(empty_res["funding_entities"], [])
        self.assertIsNone(empty_res["codebase_artifact_link"])
        self.assertIsNone(empty_res["schwarz_ecosystem_affiliation"])
        self.assertIsNone(empty_res["gdpr_concerns"])
        self.assertIsNone(empty_res["competitor_involvement"])
        self.assertEqual(empty_res["flags"], [])

        # 3. Inputs containing placeholder strings ('None', 'null', 'n/a', '')
        placeholders_data = {
            "metadata": {
                "institutional_affiliations": ["None", "null", "N/A", "", "  ", None],
                "author_contacts": [
                    {"email": "None", "author_name": "null"},
                    {"email": "  ", "author_name": ""},
                    None,
                ],
                "funding_entities": ["None", "", "n/a", None],
                "codebase_links": ["none", "", "null"],
            },
            "gdpr_concern": None,
            "competitor_involvement": None,
            "schwarz_ecosystem_affiliation": None,
        }
        res_placeholders = adapt_affiliation_data(placeholders_data)
        self.assertEqual(res_placeholders["affiliations"], [])
        self.assertEqual(res_placeholders["author_contacts"], [])
        self.assertEqual(res_placeholders["funding_entities"], [])
        self.assertIsNone(res_placeholders["codebase_artifact_link"])
        self.assertEqual(res_placeholders["flags"], [])

        # 4. End-to-end API: Paper with NO risk extraction at all
        Extraction.objects.filter(paper=self.paper).delete()
        api_url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}"
        resp_no_ext = self.client.get(api_url)
        self.assertEqual(resp_no_ext.status_code, 200)
        data_no_ext = resp_no_ext.json()
        self.assertIsNone(data_no_ext["paper"]["risk_and_affiliation"])

        # 5. End-to-end API: Paper with completely empty fields_data={}
        ext_empty = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            category="Risk and Affiliation Flagging",
            fields_data={},
        )
        resp_empty_ext = self.client.get(api_url)
        self.assertEqual(resp_empty_ext.status_code, 200)
        # Truthiness of empty dict in scorecard_service means risk_and_affiliation is cleanly None
        self.assertIsNone(resp_empty_ext.json()["paper"]["risk_and_affiliation"])

        # 6. End-to-end API: Paper with non-risk fields_data (no affiliations found in paper)
        ext_empty.fields_data = {"notes": "No affiliations disclosed"}
        ext_empty.save()
        resp_notes = self.client.get(api_url)
        self.assertEqual(resp_notes.status_code, 200)
        risk_notes = resp_notes.json()["paper"]["risk_and_affiliation"]
        self.assertIsNotNone(risk_notes)
        self.assertEqual(risk_notes["affiliations"], [])
        self.assertEqual(risk_notes["author_contacts"], [])
        self.assertEqual(risk_notes["funding_entities"], [])
        self.assertIsNone(risk_notes["codebase_artifact_link"])
        self.assertEqual(risk_notes["flags"], [])

    def test_21_definition_get_put_roundtrip_preserves_auto_mode_and_headline(self):
        """
        Issue #139: GET->PUT round trip of an ExtractionDefinition must NOT persist
        fallback secondary metrics (exit_metrics[1:]) into secondary_frontend_metrics.
        If persisted, has_explicit_frontend_metrics() flips to True, which overrides
        Rule 2 postprocessing and breaks the headline score (e.g. 37 down to 30).
        """
        # 1. Create definition in auto mode with exit_metrics and postprocessing code
        def_auto = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Strategic Schwarz Fit",
            system_prompt="Extract metrics",
            user_prompt_template="Paper: {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "raw_score": {"type": "number"},
                    "sub_a": {"type": "number"},
                    "sub_b": {"type": "number"},
                }
            },
            exit_metrics="raw_score, sub_a, sub_b",
            postprocessing_code="""
def postprocess(fields_data):
    return {"schwarz_fit": 37, "fit_confidence": 0.95}
""".strip(),
            primary_frontend_metric="",
            secondary_frontend_metrics="",
            is_active=True,
        )

        # Verify initial model state
        self.assertFalse(def_auto.has_explicit_frontend_metrics())
        self.assertEqual(def_auto.get_explicit_secondary_frontend_metrics_list(), [])
        self.assertEqual(def_auto.get_secondary_frontend_metrics_list(), ["sub_a", "sub_b"])

        # 2. Client performs GET /api/extraction-definitions/{id}/
        get_url = f"/api/extraction-definitions/{def_auto.id}/"
        get_resp = self.client.get(get_url)
        self.assertEqual(get_resp.status_code, 200)
        get_data = get_resp.json()

        # Representation MUST emit empty list for secondary_frontend_metrics (NOT the fallback ["sub_a", "sub_b"])
        self.assertIsNone(get_data["primary_frontend_metric"])
        self.assertEqual(get_data["secondary_frontend_metrics"], [])
        self.assertEqual(get_data["exit_metrics"], ["raw_score", "sub_a", "sub_b"])

        # 3. Client performs PUT /api/extraction-definitions/{id}/ with unchanged payload
        put_resp = self.client.put(get_url, data=get_data, format="json")
        self.assertEqual(put_resp.status_code, 200)

        # 4. Refresh definition and verify that has_explicit_frontend_metrics is STILL False
        def_auto.refresh_from_db()
        self.assertFalse(def_auto.has_explicit_frontend_metrics())
        self.assertEqual(def_auto.get_explicit_secondary_frontend_metrics_list(), [])
        self.assertEqual(def_auto.get_secondary_frontend_metrics_list(), ["sub_a", "sub_b"])
        self.assertEqual(def_auto.secondary_frontend_metrics, "")

        # 5. Verify scorecard evaluation for paper
        ext = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=def_auto,
            category="Strategic Schwarz Fit",
            fields_data={
                "raw_score": 30,
                "sub_a": 8,
                "sub_b": 6,
                "strategic_schwarz_fit_postprocessed": 37,
            },
        )

        scorecard_url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run_beta.id}"
        sc_resp = self.client.get(scorecard_url)
        self.assertEqual(sc_resp.status_code, 200)
        sc_data = sc_resp.json()

        dim = next((d for d in sc_data["paper"]["dimensions"] if d["definition_id"] == str(def_auto.id)), None)
        self.assertIsNotNone(dim)
        # Headline value MUST be postprocessed 37, NOT raw_score 30!
        self.assertEqual(dim["value"], 37)
        self.assertEqual(dim["primary_metric"]["numeric_value"], 37)
        self.assertEqual(dim["primary_metric"]["source"], "postprocessing")
        self.assertTrue(dim["has_postprocessing"])
        sec_keys = [s["key"] for s in dim["secondary_metrics"]]
        self.assertIn("raw_score", sec_keys)
        self.assertIn("sub_a", sec_keys)
        self.assertIn("sub_b", sec_keys)

    def test_22_workspace_export_import_roundtrip_preserves_auto_mode(self):
        """
        Verify serialize_workspace_configuration and import_workspace_configuration_bundle
        round-trip does not leak fallback exit metrics into secondary_frontend_metrics.
        """
        from research_intelligence.services.workspace_service import (
            serialize_workspace_configuration,
            import_workspace_configuration_bundle,
        )

        def_auto = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Export Auto Definition",
            system_prompt="Extract info",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object"},
            exit_metrics="score, metric_x, metric_y",
            primary_frontend_metric="",
            secondary_frontend_metrics="",
            is_active=True,
        )
        self.assertFalse(def_auto.has_explicit_frontend_metrics())

        # Serialize workspace
        exported = serialize_workspace_configuration(self.workspace)
        ed_export = next(ed for ed in exported["extraction_definitions"] if ed["name"] == "Export Auto Definition")
        self.assertEqual(ed_export["secondary_frontend_metrics"], [])
        self.assertIsNone(ed_export["primary_frontend_metric"])

        # Re-import configuration
        stats = import_workspace_configuration_bundle(exported, user=self.user, update_existing=True)
        self.assertGreaterEqual(stats["updated_workspaces"], 1)

        def_auto.refresh_from_db()
        self.assertFalse(def_auto.has_explicit_frontend_metrics())
        self.assertEqual(def_auto.get_explicit_secondary_frontend_metrics_list(), [])
        self.assertEqual(def_auto.get_secondary_frontend_metrics_list(), ["metric_x", "metric_y"])

    def test_23_explicit_frontend_metrics_roundtrip_preserves_values(self):
        """
        Verify that definitions with explicitly configured secondary frontend metrics
        continue to serialize and round-trip their explicit metrics correctly.
        """
        def_explicit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Explicit Metrics Roundtrip",
            system_prompt="Extract info",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object"},
            exit_metrics="raw_total, sec_one, sec_two, sec_three",
            primary_frontend_metric="sec_one",
            secondary_frontend_metrics="sec_two, sec_three",
            is_active=True,
        )
        self.assertTrue(def_explicit.has_explicit_frontend_metrics())
        self.assertEqual(def_explicit.get_explicit_secondary_frontend_metrics_list(), ["sec_two", "sec_three"])

        # GET API
        get_url = f"/api/extraction-definitions/{def_explicit.id}/"
        get_resp = self.client.get(get_url)
        self.assertEqual(get_resp.status_code, 200)
        data = get_resp.json()
        self.assertEqual(data["primary_frontend_metric"], "sec_one")
        self.assertEqual(data["secondary_frontend_metrics"], ["sec_two", "sec_three"])

        # PUT API
        put_resp = self.client.put(get_url, data=data, format="json")
        self.assertEqual(put_resp.status_code, 200)

        def_explicit.refresh_from_db()
        self.assertTrue(def_explicit.has_explicit_frontend_metrics())
        self.assertEqual(def_explicit.primary_frontend_metric, "sec_one")
        self.assertEqual(def_explicit.get_explicit_secondary_frontend_metrics_list(), ["sec_two", "sec_three"])

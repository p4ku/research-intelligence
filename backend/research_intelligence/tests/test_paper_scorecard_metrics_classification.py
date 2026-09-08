import uuid
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    Paper,
    PaperMetric,
    ExtractionDefinition,
    Extraction,
    NarrativeReport,
)

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

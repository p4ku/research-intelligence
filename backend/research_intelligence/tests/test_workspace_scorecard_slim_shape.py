import json
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    ExtractionDefinition,
    Paper,
    Extraction,
    PaperMetric,
    PipelineRun,
)

User = get_user_model()


class WorkspaceScorecardSlimShapeTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="slim_scorecard_admin",
            email="slim_admin@schwarz.de",
            password="password123!"
        )
        self.client.force_authenticate(user=self.user)

        self.workspace = Workspace.objects.create(name="Slim Workspace")
        self.membership = WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="owner"
        )
        self.definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Technology Readiness Level (TRL)",
            order=1,
            exit_metrics="trl",
            response_schema={
                "type": "object",
                "properties": {
                    "trl": {"type": "integer", "minimum": 1, "maximum": 9},
                    "justification": {"type": "string"},
                },
                "required": ["trl"],
            },
        )
        self.definition_risk = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Risk and Affiliation",
            order=2,
            exit_metrics="risk_score",
            response_schema={"type": "object"},
        )

        self.run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Test Run 1",
            status="completed"
        )

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            title="Quantum Transformer Scaling Laws",
            abstract="Exploring architectures and scaling for quantum models.",
            arxiv_id="2609.12345",
        )

        self.metric = PaperMetric.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            pipeline_run=self.run,
            signal_score=88.5,
            screening_status="accepted",
        )

        self.extraction = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.definition,
            fields_data={
                "fields": {
                    "trl": 5,
                    "justification": "Validated in prototype lab setup.",
                    "evidence": [{"quote": "Validated on 100 qubits", "rationale": "Empirical lab result"}],
                }
            },
            validation_status="pass",
            confidence_score=0.92,
        )

        self.extraction_risk = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.definition_risk,
            fields_data={
                "fields": {
                    "affiliations": ["Schwarz IT", "TUM"],
                    "risk_score": 12,
                    "flags": [{"key": "dual_use", "label": "Dual Use", "status": "clear", "value": "None"}],
                    "raw_internal_log": "Secret debug dump that shouldn't bloat list view",
                }
            },
            validation_status="pass",
        )

    def test_workspace_scorecard_returns_slim_shape_by_default(self):
        """
        Workspace scorecard GET /api/workspaces/{id}/scorecard/ defaults to slim shape:
        - dimensions omit bloated response_schema, fields_data, main_metric, auxiliary_metrics
        - dimensions preserve primary_metric, secondary_metrics, facets, texts, rationale, evidence
        - risk_and_affiliation omits raw dump
        """
        url = f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={self.run.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("results", data)
        self.assertIn("papers", data)
        self.assertEqual(len(data["results"]), 1)
        paper = data["results"][0]

        # 1. Verify paper dimensions are slimmed
        dimensions = paper["dimensions"]
        self.assertGreater(len(dimensions), 0)
        trl_dim = next((d for d in dimensions if d["definition_id"] == str(self.definition.id)), None)
        self.assertIsNotNone(trl_dim)

        # Slim checks: bloated/redundant fields must NOT be in dimension
        self.assertNotIn("response_schema", trl_dim)
        self.assertNotIn("fields_data", trl_dim)
        self.assertNotIn("main_metric", trl_dim)
        self.assertNotIn("auxiliary_metrics", trl_dim)

        # Essential presentation fields MUST be present
        self.assertEqual(trl_dim["name"], "Technology Readiness Level (TRL)")
        self.assertEqual(trl_dim["value"], 5)
        self.assertEqual(trl_dim["max"], 9)
        self.assertTrue(trl_dim["is_trl"])
        self.assertIn("primary_metric", trl_dim)
        self.assertEqual(trl_dim["primary_metric"]["value"], 5)
        self.assertIn("secondary_metrics", trl_dim)
        self.assertIn("evidence", trl_dim)

        # 2. Verify risk_and_affiliation omits 'raw'
        risk = paper.get("risk_and_affiliation")
        self.assertIsNotNone(risk)
        self.assertNotIn("raw", risk)
        self.assertIn("affiliations", risk)
        self.assertIn("flags", risk)

    def test_paper_scorecard_detail_endpoint_preserves_full_detail(self):
        """
        Single paper scorecard GET /api/papers/{id}/scorecard/ must preserve full detail
        (response_schema, fields_data, etc.) required by assessment.tsx resolveSubMeasures.
        """
        url = f"/api/papers/{self.paper.id}/scorecard/?pipeline_run_id={self.run.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        paper = data["paper"]
        dimensions = paper["dimensions"]
        trl_dim = next((d for d in dimensions if d["definition_id"] == str(self.definition.id)), None)
        self.assertIsNotNone(trl_dim)

        # Detail checks: full detail fields MUST be present
        self.assertIn("response_schema", trl_dim)
        self.assertIsNotNone(trl_dim["response_schema"])
        self.assertEqual(trl_dim["response_schema"]["type"], "object")

        self.assertIn("fields_data", trl_dim)
        self.assertIsNotNone(trl_dim["fields_data"])

        self.assertIn("main_metric", trl_dim)
        self.assertIn("auxiliary_metrics", trl_dim)

        risk = paper.get("risk_and_affiliation")
        self.assertIsNotNone(risk)
        self.assertIn("raw", risk)

    def test_workspace_scorecard_detail_true_query_param(self):
        """
        Passing ?detail=true on the workspace scorecard overrides slim default
        and returns full response_schema and fields_data.
        """
        url = f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={self.run.id}&detail=true"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        paper = data["results"][0]
        trl_dim = next((d for d in paper["dimensions"] if d["definition_id"] == str(self.definition.id)), None)
        self.assertIn("response_schema", trl_dim)
        self.assertIn("fields_data", trl_dim)

    def test_workspace_scorecard_results_only_query_param(self):
        """
        Passing ?results_only=true omits the duplicate 'papers' key from payload.
        """
        url = f"/api/workspaces/{self.workspace.id}/scorecard/?run_id={self.run.id}&results_only=true"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("results", data)
        self.assertNotIn("papers", data)
        self.assertEqual(len(data["results"]), 1)

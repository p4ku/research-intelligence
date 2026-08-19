import json
from django.test import TestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import Workspace, WorkspaceMember, PipelineRun, Paper, Extraction, ExtractionDefinition
from research_intelligence.mcp.tools.extractions import (
    get_paper_extractions_matrix_logic,
    list_extractions_logic,
    get_extraction_logic
)

User = get_user_model()


class PipelineMatrixAndReportingTestCase(TestCase):
    """
    Validates end-to-end extraction results aggregation and tabular reporting tools:
    1. get_paper_extractions_matrix_logic (primary scorecard aggregation for research runs).
    2. list_extractions_logic (filtering by workspace, run, definition, validation status).
    3. get_extraction_logic (detailed single extraction inspection with confidence & audit trail).
    """

    def setUp(self):
        self.user = User.objects.create_user(username="lead_analyst", email="analyst@company.com", password="password123")
        self.workspace = Workspace.objects.create(name="Solid State Battery Matrix")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="completed"
        )

        # 1. Accepted Paper 1
        self.paper1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_mat_001",
            title="Sulfide Solid Electrolyte with 25 mS/cm Ionic Conductivity",
            authors="Zhang et al.",
            doi="10.1000/battery.001",
            arxiv_id="2401.55555",
            abstract="High ionic conductivity sulfide electrolyte.",
            screening_status="accepted"
        )

        # 2. Accepted Paper 2
        self.paper2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_mat_002",
            title="Oxide-Based Garnet Electrolyte for All-Solid-State Batteries",
            authors="Kim et al.",
            doi="10.1000/battery.002",
            abstract="LLZO garnet electrolyte stability study.",
            screening_status="accepted"
        )

        # 3. Rejected Paper (should be excluded when screening_status='accepted')
        self.paper_rejected = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_mat_003",
            title="Liquid Electrolyte Battery Degradation",
            abstract="Out of scope study.",
            screening_status="rejected"
        )

        # Extraction Definition
        self.def_conductivity = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Ionic Conductivity",
            exit_metric="value_ms_cm",
            llm_model="google/gemini-3.7-flash",
            system_prompt="Extract ionic conductivity values in mS/cm.",
            response_schema={"type": "object", "properties": {"value_ms_cm": {"type": "number"}}}
        )

        # Extractions
        self.ext1 = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper1,
            extraction_definition=self.def_conductivity,
            category="Ionic Conductivity",
            fields_data={"value_ms_cm": 25.0, "temperature_c": 25, "electrolyte_type": "Sulfide"},
            validation_status="pass",
            confidence_score=0.98
        )

        self.ext2 = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper2,
            extraction_definition=self.def_conductivity,
            category="Ionic Conductivity",
            fields_data={"value_ms_cm": 1.2, "temperature_c": 25, "electrolyte_type": "Oxide Garnet"},
            validation_status="pass",
            confidence_score=0.91
        )

    def test_get_paper_extractions_matrix_accepted_only(self):
        """
        Validates that get_paper_extractions_matrix_logic returns all accepted papers
        with their aggregated parameter metrics and excludes rejected papers.
        """
        matrix_str = get_paper_extractions_matrix_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            screening_status="accepted"
        )
        matrix = json.loads(matrix_str)

        self.assertEqual(matrix["total_papers"], 2)
        self.assertEqual(matrix["screening_status_filter"], "accepted")

        # Verify paper 1 entry
        p1_entry = next(p for p in matrix["papers"] if p["paper_id"] == str(self.paper1.id))
        self.assertEqual(p1_entry["title"], "Sulfide Solid Electrolyte with 25 mS/cm Ionic Conductivity")
        self.assertEqual(p1_entry["metrics_summary"]["Ionic Conductivity"], "25.0")
        self.assertEqual(p1_entry["extractions_count"], 1)

        # Verify paper 2 entry
        p2_entry = next(p for p in matrix["papers"] if p["paper_id"] == str(self.paper2.id))
        self.assertEqual(p2_entry["metrics_summary"]["Ionic Conductivity"], "1.2")

    def test_list_extractions_filters(self):
        """
        Validates filtering extractions by validation_status and workspace.
        """
        list_str = list_extractions_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            validation_status="pass"
        )
        extractions = json.loads(list_str)
        self.assertEqual(len(extractions), 2)
        self.assertEqual(extractions[0]["validation_status"], "pass")

    def test_get_single_extraction_details(self):
        """
        Validates get_extraction_logic returning complete inspection payload.
        """
        ext_str = get_extraction_logic(user=self.user, extraction_id=str(self.ext1.id))
        ext_detail = json.loads(ext_str)

        self.assertEqual(ext_detail["id"], str(self.ext1.id))
        self.assertEqual(ext_detail["definition_name"], "Ionic Conductivity")
        self.assertEqual(ext_detail["confidence_score"], 0.98)
        self.assertEqual(ext_detail["fields_data"]["value_ms_cm"], 25.0)

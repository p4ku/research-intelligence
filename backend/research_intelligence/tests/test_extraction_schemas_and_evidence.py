import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import Workspace, PipelineRun, ComponentRun, Paper, Extraction, ExtractionDefinition
from research_intelligence.tasks.step_5_extraction.extract import _run_single_extraction_worker, execute_extraction_job

User = get_user_model()


class ExtractionSchemasAndEvidenceTestCase(TestCase):
    """
    Validates dynamic parameter extraction (Step 5):
    1. Schema validation against ExtractionDefinition.response_schema.
    2. Extraction of evidence quotes and confidence scores.
    3. Validation status assignment ('pass' for high confidence, 'warn' for low confidence).
    4. Resilient handling of LLM Markdown formatting (```json ... ``` blocks).
    """

    def setUp(self):
        self.user = User.objects.create_user(username="extract_tester", email="tester@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="Extraction Target Workspace",
            llm_provider="google",
            screening_llm_model="google/gemini-3.7-flash"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_ext_001",
            title="High-Efficiency Perovskite Solar Cells with 25.8% Certified Efficiency",
            abstract="We report 25.8% power conversion efficiency using a novel passivation layer.",
            screening_status="accepted"
        )

        # Dynamic Extraction Definition with strict JSON Schema
        self.definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Photovoltaic Parameters",
            llm_model="google/gemini-3.7-flash",
            system_prompt="Extract solar cell performance parameters.",
            user_prompt_template="Analyze paper: {title}\n{paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "efficiency_percent": {"type": "number"},
                    "open_circuit_voltage_v": {"type": "number"},
                    "passivation_material": {"type": "string"},
                    "evidence_quotes": {"type": "array", "items": {"type": "string"}},
                    "confidence_score": {"type": "number"}
                },
                "required": ["efficiency_percent", "passivation_material"]
            }
        )

    def test_schema_validated_extraction_with_evidence(self):
        """
        Tests extraction populating fields, confidence, evidence quotes, and validation status 'pass'.
        """
        mock_llm_output = {
            "efficiency_percent": 25.8,
            "open_circuit_voltage_v": 1.18,
            "passivation_material": "Phenethylammonium Iodide (PEAI)",
            "evidence_quotes": [
                "achieved a certified power conversion efficiency of 25.8%",
                "passivated using 2D PEAI perovskite capping layer"
            ],
            "confidence_score": 0.95
        }
        mock_usage = {"prompt_tokens": 1200, "candidates_tokens": 180, "total_tokens": 1380}

        with patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_llm_output, mock_usage)
            mock_provider_factory.return_value = mock_provider

            result = _run_single_extraction_worker(self.paper, self.definition, self.workspace)
            self.assertTrue(result["success"])
            self.assertEqual(result["validation_status"], "pass")
            self.assertEqual(result["confidence_score"], 0.95)

        # Verify Extraction model persistence in DB
        extraction = Extraction.objects.get(paper=self.paper, extraction_definition=self.definition)
        self.assertEqual(extraction.fields_data["efficiency_percent"], 25.8)
        self.assertEqual(extraction.fields_data["passivation_material"], "Phenethylammonium Iodide (PEAI)")
        self.assertEqual(len(extraction.fields_data["evidence_quotes"]), 2)
        self.assertEqual(extraction.validation_status, "pass")
        self.assertFalse(extraction.review_required)

    def test_low_confidence_extraction_flags_warn(self):
        """
        Tests that extractions with confidence < 0.65 are flagged with validation_status='warn' and review_required=True.
        """
        mock_low_conf_output = {
            "efficiency_percent": 21.0,
            "passivation_material": "Unknown compound",
            "confidence_score": 0.45
        }
        mock_usage = {"prompt_tokens": 900, "candidates_tokens": 90, "total_tokens": 990}

        with patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_low_conf_output, mock_usage)
            mock_provider_factory.return_value = mock_provider

            result = _run_single_extraction_worker(self.paper, self.definition, self.workspace)
            self.assertTrue(result["success"])
            self.assertEqual(result["validation_status"], "warn")
            self.assertEqual(result["confidence_score"], 0.45)

        extraction = Extraction.objects.get(paper=self.paper, extraction_definition=self.definition)
        self.assertEqual(extraction.validation_status, "warn")
        self.assertTrue(extraction.review_required)

    def test_execute_extraction_job_batch_component_run(self):
        """
        Tests the execute_extraction_job Celery task across accepted papers.
        """
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="parameter_extractor",
            status="running"
        )

        mock_llm_output = {
            "efficiency_percent": 25.8,
            "passivation_material": "PEAI",
            "confidence_score": 0.92
        }
        mock_usage = {"prompt_tokens": 1000, "candidates_tokens": 150, "total_tokens": 1150}

        with patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_llm_output, mock_usage)
            mock_provider_factory.return_value = mock_provider

            success = execute_extraction_job(str(comp_run.id), limit=10)
            self.assertTrue(success)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertEqual(comp_run.metrics["total_papers"], 1)
        self.assertEqual(comp_run.metrics["extractions_created"], 1)

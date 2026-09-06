import json
from unittest.mock import patch, MagicMock
from django.test import TestCase

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    PaperMetric,
    ComponentRun,
    ExtractionDefinition,
    Extraction,
)
from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job, _run_single_extraction_worker
from research_intelligence.tasks.step_5_extraction.node import ExtractionNode


class ExtractionTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Extraction Test Project",
            abstract_acceptance_criteria="Active learning",
            abstract_rejection_criteria="Heuristics"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            system_prompt="Extract TRL level with exact quote.",
            user_prompt_template="Analyze this text: {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "trl_level": {"type": "integer", "minimum": 1, "maximum": 9},
                    "reasoning": {"type": "string"},
                    "evidence_quote": {"type": "string"}
                },
                "required": ["trl_level", "reasoning", "evidence_quote"]
            },
            is_active=True
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_accepted_101",
            title="Field Testing Autonomous Rovers in Antarctic Conditions",
            authors="Dr. Scott",
            abstract="We deployed autonomous rovers in Antarctica for 30 days."
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )
        self.component_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="parameter_extractor",
            status="pending"
        )

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_execute_extraction_job_success(self, mock_get_provider):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (
            {
                "trl_level": 7,
                "reasoning": "Demonstrated prototype in operational environment (Antarctica).",
                "evidence_quote": "We deployed autonomous rovers in Antarctica for 30 days with full telemetry.",
                "confidence_score": 0.95
            },
            {"prompt_tokens": 1200, "candidates_tokens": 250, "total_tokens": 1450}
        )
        mock_get_provider.return_value = mock_llm

        result = execute_extraction_job(str(self.component_run.id))
        self.assertTrue(result)

        extractions = Extraction.objects.filter(paper=self.paper, extraction_definition=self.definition)
        self.assertEqual(extractions.count(), 1)
        ext = extractions.first()
        self.assertEqual(ext.fields_data.get("trl_level"), 7)
        self.assertEqual(ext.validation_status, "pass")
        self.assertAlmostEqual(ext.confidence_score, 0.95)

        # Assert reasoning_effort is passed to llm_provider.generate
        self.assertEqual(mock_llm.generate.call_args.kwargs.get("reasoning_effort"), "medium")

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_execute_extraction_job_warn_on_schema_fallback(self, mock_get_provider):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (
            {
                "trl_level": 4,
                "reasoning": "Lab validation only.",
                "confidence_score": 0.50
            },
            {"prompt_tokens": 500, "candidates_tokens": 100, "total_tokens": 600}
        )
        mock_get_provider.return_value = mock_llm

        result = execute_extraction_job(str(self.component_run.id))
        self.assertTrue(result)

        ext = Extraction.objects.filter(paper=self.paper, extraction_definition=self.definition).first()
        self.assertIsNotNone(ext)
        self.assertEqual(ext.fields_data.get("trl_level"), 4)
        self.assertEqual(ext.validation_status, "warn")

    def test_extraction_node_contracts_and_dependencies(self):
        node = ExtractionNode()
        self.assertEqual(node.name, "extraction")
        self.assertEqual(node.dependencies, ["full_text_screening"])
        self.assertIn("extraction_definitions", node.input_contract)
        self.assertIn("extractions", node.output_contract)

        self.component_run.metrics = {"extractions_created": 8, "total_papers": 4}
        summary = node.generate_stage_summary(self.component_run, status="completed")
        self.assertIn("8 parameters extracted", summary)

    @patch("research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick")
    def test_execute_extraction_job_no_active_definitions(self, mock_notify):
        """Test extraction job completes cleanly and notifies orchestrator when no active definitions exist."""
        self.definition.is_active = False
        self.definition.save()

        result = execute_extraction_job(str(self.component_run.id))
        self.assertTrue(result)

        self.component_run.refresh_from_db()
        self.assertEqual(self.component_run.status, "completed")
        self.assertEqual(self.component_run.metrics.get("total_definitions"), 0)
        mock_notify.assert_called_once_with(self.pipeline_run)

    def test_schema_validated_extraction_with_evidence(self):
        mock_llm_output = {
            "trl_level": 8,
            "reasoning": "Flight-proven operational system.",
            "evidence_quote": "Flight-proven operational system over 12 months.",
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

        extraction = Extraction.objects.get(paper=self.paper, extraction_definition=self.definition)
        self.assertEqual(extraction.fields_data["trl_level"], 8)
        self.assertEqual(extraction.validation_status, "pass")
        self.assertFalse(extraction.review_required)

    def test_low_confidence_extraction_flags_warn(self):
        mock_low_conf_output = {
            "trl_level": 3,
            "reasoning": "Preliminary concept only.",
            "evidence_quote": "Analytical proof.",
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


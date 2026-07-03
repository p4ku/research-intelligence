import json
from django.test import TestCase
from unittest.mock import patch, MagicMock
from ...models import Workspace, PipelineRun, Paper, Extraction, ExtractionDefinition, AuditTrail
from ...tasks.step_5_extraction.extract import extract_custom_variables, run_extraction_for_definition

class DynamicExtractionTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Deep Tech Scan",
            llm_provider="google"
        )
        
        self.def_ml_methods = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="ML Methods",
            system_prompt="Identify ML Methods used in the text.",
            user_prompt_template="Analyze: {paper_text}",
            llm_model="google/gemini-1.5-pro",
            version=2,
            requires_consensus=False,
            response_schema={
                "type": "object",
                "properties": {
                    "ml_method": {"type": "string"}
                }
            }
        )

        self.pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="running")
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="test_hash_12345",
            title="A Survey of Agentic AI Reasoning Loops",
            authors="John Doe",
            abstract="This paper introduces a new agentic loop with 95% accuracy.",
            source_database="arxiv"
        )

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_run_extraction_for_definition_success(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        
        # Mock LLM returning a valid Pydantic JSON string
        mock_response = {
            "fields": {
                "ml_method": {
                    "value": "ReACT agent loop",
                    "normalized_value": "react",
                    "confidence": 0.85,
                    "evidence": [
                        {"quote": "agentic loop", "rationale": "Mentions loop type."}
                    ]
                }
            }
        }
        mock_provider.generate.return_value = json.dumps(mock_response)

        # Run extraction task
        result = run_extraction_for_definition(self.paper.id, self.def_ml_methods.id)

        # Assert task output
        self.assertTrue(result)

        # Assert Extraction model was created with advanced fields
        extraction = Extraction.objects.get(paper=self.paper, extraction_definition=self.def_ml_methods)
        
        self.assertEqual(extraction.category, "ML Methods")
        self.assertEqual(extraction.fields_data["ml_method"]["value"], "ReACT agent loop")
        self.assertEqual(extraction.confidence_score, 0.85)
        self.assertEqual(extraction.validation_status, "pass")
        self.assertFalse(extraction.review_required)
        self.assertEqual(extraction.confidence_method, "single_pass")
        self.assertEqual(extraction.version_info["version"], 2)

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_run_extraction_for_definition_low_confidence_warn(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        
        mock_response = {
            "fields": {
                "ml_method": {
                    "value": "Unknown",
                    "normalized_value": "",
                    "confidence": 0.20,
                    "evidence": []
                }
            }
        }
        mock_provider.generate.return_value = json.dumps(mock_response)

        result = run_extraction_for_definition(self.paper.id, self.def_ml_methods.id)
        self.assertTrue(result)

        extraction = Extraction.objects.get(paper=self.paper, extraction_definition=self.def_ml_methods)
        
        # Because confidence is 0.20 and evidence is empty, it should warn and require review
        self.assertEqual(extraction.validation_status, "warn")
        self.assertTrue(extraction.review_required)

    @patch("research_intelligence.tasks.step_5_extraction.extract.group")
    def test_extract_custom_variables_orchestrator(self, mock_group):
        mock_group_instance = MagicMock()
        mock_group.return_value = mock_group_instance
        
        result = extract_custom_variables(self.paper.id, self.workspace.id)
        
        self.assertTrue(result)
        mock_group.assert_called_once()
        mock_group_instance.apply_async.assert_called_once()

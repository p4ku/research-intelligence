import json
from unittest.mock import MagicMock
from django.test import TestCase

from research_intelligence.tasks.step_5_extraction.engine import (
    ExtractionEngine,
    ExtractionResponse,
    FieldExtraction,
    EvidenceChunk
)


class ExtractionConsensusEngineTestCase(TestCase):
    """
    Unit tests for Step 5 Extraction Engine, Pydantic schema validation, and consensus resolution.
    """

    def setUp(self):
        self.mock_provider = MagicMock()
        self.engine = ExtractionEngine(llm_provider=self.mock_provider, max_retries=2)
        self.sample_schema = {
            "type": "object",
            "properties": {
                "efficiency": {"type": "number"}
            }
        }

    def test_build_system_prompt_includes_schema_and_critical_instructions(self):
        prompt = self.engine.build_system_prompt("Extract Solar Cell Metrics.", self.sample_schema)
        self.assertIn("Extract Solar Cell Metrics.", prompt)
        self.assertIn('"efficiency"', prompt)
        self.assertIn("CRITICAL INSTRUCTIONS", prompt)
        self.assertIn('"evidence"', prompt)

    def test_parse_and_validate_clean_json(self):
        raw = json.dumps({
            "fields": {
                "efficiency": {
                    "value": 24.5,
                    "normalized_value": "24.5%",
                    "confidence": 0.95,
                    "evidence": [{"quote": "achieved 24.5% PCE", "rationale": "Direct claim"}]
                }
            }
        })
        resp = self.engine.parse_and_validate(raw)
        self.assertIsNotNone(resp)
        self.assertIn("efficiency", resp.fields)
        self.assertEqual(resp.fields["efficiency"].value, 24.5)
        self.assertEqual(resp.fields["efficiency"].confidence, 0.95)

    def test_parse_and_validate_markdown_code_fences_stripping(self):
        raw = '```json\n{"fields": {"efficiency": {"value": 22.0, "confidence": 0.9, "evidence": [{"quote": "22%", "rationale": "Test"}]}}}\n```'
        resp = self.engine.parse_and_validate(raw)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.fields["efficiency"].value, 22.0)

    def test_parse_and_validate_direct_dictionary_without_fields_wrapper(self):
        raw = json.dumps({
            "efficiency": {
                "value": 19.8,
                "confidence": 0.85,
                "evidence": [{"quote": "19.8% PCE", "rationale": "PCE reported"}]
            }
        })
        resp = self.engine.parse_and_validate(raw)
        self.assertIsNotNone(resp)
        self.assertIn("efficiency", resp.fields)

    def test_parse_and_validate_invalid_json_returns_none(self):
        resp = self.engine.parse_and_validate("{broken: json, not quote}")
        self.assertIsNone(resp)

    def test_run_single_pass_retries_on_initial_validation_failure(self):
        valid_response = json.dumps({
            "fields": {
                "efficiency": {
                    "value": 25.1,
                    "confidence": 0.99,
                    "evidence": [{"quote": "25.1% under AM1.5G", "rationale": "Certified result"}]
                }
            }
        })
        # Attempt 1 fails, Attempt 2 succeeds
        self.mock_provider.generate.side_effect = ["Invalid text response", valid_response]

        res = self.engine.run_single_pass("Paper text", "System Prompt", "User Prompt")
        self.assertIsNotNone(res)
        self.assertEqual(res.fields["efficiency"].value, 25.1)
        self.assertEqual(self.mock_provider.generate.call_count, 2)

    def test_run_self_consistency_consensus_flow(self):
        sample1 = json.dumps({"fields": {"efficiency": {"value": 24.0, "confidence": 0.8, "evidence": [{"quote": "24%", "rationale": "s1"}]}}})
        sample2 = json.dumps({"fields": {"efficiency": {"value": 24.5, "confidence": 0.9, "evidence": [{"quote": "24.5%", "rationale": "s2"}]}}})
        sample3 = json.dumps({"fields": {"efficiency": {"value": 24.5, "confidence": 0.95, "evidence": [{"quote": "24.5%", "rationale": "s3"}]}}})
        consensus_final = json.dumps({"fields": {"efficiency": {"value": 24.5, "confidence": 0.95, "evidence": [{"quote": "24.5%", "rationale": "Majority consensus"}]}}})

        # 3 calls for samples (temp 0.7) + 1 call for consensus resolution (temp 0.0)
        self.mock_provider.generate.side_effect = [sample1, sample2, sample3, consensus_final]

        res = self.engine.run_self_consistency("Paper Text", "Sys Prompt", "User Prompt", num_samples=3)
        self.assertIsNotNone(res)
        self.assertEqual(res.fields["efficiency"].value, 24.5)
        self.assertEqual(self.mock_provider.generate.call_count, 4)

    def test_execute_dispatches_correctly_based_on_consensus_flag(self):
        valid_response = json.dumps({
            "fields": {
                "efficiency": {
                    "value": 30.0,
                    "confidence": 0.88,
                    "evidence": [{"quote": "30% theoretical limit", "rationale": "Limit"}]
                }
            }
        })
        self.mock_provider.generate.return_value = valid_response

        # Single pass
        res1, method1 = self.engine.execute("Text", "Sys", "User", self.sample_schema, requires_consensus=False)
        self.assertEqual(method1, "single_pass")
        self.assertIsNotNone(res1)

        # Consensus pass
        self.mock_provider.generate.side_effect = [valid_response, valid_response, valid_response, valid_response]
        res2, method2 = self.engine.execute("Text", "Sys", "User", self.sample_schema, requires_consensus=True)
        self.assertEqual(method2, "self_consistency")
        self.assertIsNotNone(res2)

"""
Unit tests for State-of-the-Art & Architectural Improvements:
1. Django STORAGES dictionary modernization.
2. Gemini context caching discounted pricing (75% discount on cached prompt tokens),
   including handling whether Google returns or omits cached_content_token_count.
3. Google Provider usage_metadata extraction for cached tokens.
4. Concurrent execution of self-consistency extraction consensus samples.
"""

import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.conf import settings

from research_intelligence.llm_providers.pricing import calculate_llm_cost, MODEL_PRICING
from research_intelligence.llm_providers.google import GoogleAgentAPIProvider
from research_intelligence.tasks.step_5_extraction.engine import ExtractionEngine, ExtractionResponse, FieldExtraction


class StateOfTheArtArchitectureTestCase(TestCase):
    # -------------------------------------------------------------------------
    # 1. DJANGO STORAGES DICTIONARY TESTS
    # -------------------------------------------------------------------------

    def test_modern_storages_configuration_exists(self):
        """
        Verify that settings.STORAGES is configured according to Django 4.2+/5.x/6.0 standards
        with 'default' and 'staticfiles' keys, and DEFAULT_FILE_STORAGE alias is preserved.
        """
        self.assertTrue(hasattr(settings, "STORAGES"))
        self.assertIn("default", settings.STORAGES)
        self.assertIn("staticfiles", settings.STORAGES)
        self.assertIn("BACKEND", settings.STORAGES["default"])
        self.assertIn("BACKEND", settings.STORAGES["staticfiles"])

        # Backward compatibility alias
        self.assertTrue(hasattr(settings, "DEFAULT_FILE_STORAGE"))
        self.assertEqual(settings.DEFAULT_FILE_STORAGE, settings.STORAGES["default"]["BACKEND"])

    # -------------------------------------------------------------------------
    # 2. CONTEXT CACHING PRICING TESTS (ROBUST TO WHETHER GOOGLE RETURNS CACHE)
    # -------------------------------------------------------------------------

    def test_gemini_context_caching_discount_pricing(self):
        """
        Verify that cached prompt tokens receive a 75% discount ($0.1875 / 1M tokens)
        compared to standard input tokens ($0.75 / 1M tokens) on gemini-3.8-flash.
        """
        # 1. Standard uncached cost
        standard_cost = calculate_llm_cost("gemini-3.8-flash", tokens_in=1_000_000, tokens_out=1_000_000)
        # $0.75 (in) + $3.75 (out) = $4.50
        self.assertEqual(standard_cost, Decimal("4.5000"))

        # 2. Pure cached prompt cost (1M cached tokens)
        cached_cost = calculate_llm_cost("gemini-3.8-flash", tokens_in=0, tokens_out=0, tokens_cached=1_000_000)
        # 1M * 0.1875 = $0.1875
        self.assertEqual(cached_cost, Decimal("0.1875"))

    def test_gemini_pricing_when_google_returns_cached_content_token_count_within_prompt_tokens(self):
        """
        In Google Gemini API specifications, prompt_token_count is the TOTAL number of prompt tokens,
        which includes cached_content_token_count.
        Verify that when prompt_tokens=1,000,000 and cached_tokens=800,000:
        - Uncached prompt tokens = 200,000 (200k * $0.75 / 1M = $0.1500)
        - Cached prompt tokens = 800,000 (800k * $0.1875 / 1M = $0.1500)
        - Candidates tokens = 100,000 (100k * $3.75 / 1M = $0.3750)
        Total cost = $0.1500 + $0.1500 + $0.3750 = $0.6750.
        Cached tokens are NOT double-billed.
        """
        cost = calculate_llm_cost(
            "google/gemini-3.8-flash",
            tokens_in=1_000_000,      # total prompt_token_count from Google
            tokens_out=100_000,       # candidates_token_count
            tokens_cached=800_000     # cached_content_token_count from Google
        )
        self.assertEqual(cost, Decimal("0.6750"))

    def test_gemini_pricing_when_google_omits_or_returns_zero_or_none_cache(self):
        """
        Verify that when Google API does not return cache metadata (tokens_cached=0, None, or omitted),
        the system bills standard input tokens cleanly without error.
        """
        # Case A: tokens_cached omitted (defaults to 0)
        cost_omitted = calculate_llm_cost("gemini-3.8-flash", tokens_in=1_000_000, tokens_out=0)
        self.assertEqual(cost_omitted, Decimal("0.7500"))

        # Case B: tokens_cached is None
        cost_none = calculate_llm_cost("gemini-3.8-flash", tokens_in=1_000_000, tokens_out=0, tokens_cached=None)
        self.assertEqual(cost_none, Decimal("0.7500"))

        # Case C: tokens_cached is 0
        cost_zero = calculate_llm_cost("gemini-3.8-flash", tokens_in=1_000_000, tokens_out=0, tokens_cached=0)
        self.assertEqual(cost_zero, Decimal("0.7500"))

    def test_gemini_pricing_100_percent_cache_hit(self):
        """
        Verify cost calculation when 100% of the prompt is served from cache
        (prompt_token_count == cached_content_token_count).
        """
        cost = calculate_llm_cost(
            "gemini-3.8-flash",
            tokens_in=1_000_000,
            tokens_out=0,
            tokens_cached=1_000_000
        )
        # 0 uncached in ($0.0) + 1M cached ($0.1875) = $0.1875
        self.assertEqual(cost, Decimal("0.1875"))

    def test_context_caching_fallback_model_discount(self):
        """
        Verify that unknown or default models apply a 25% rate (75% discount) on cached prompt tokens.
        """
        cost = calculate_llm_cost("unknown-model", tokens_in=0, tokens_out=0, tokens_cached=1_000_000)
        self.assertEqual(cost, Decimal("0.1875"))

    # -------------------------------------------------------------------------
    # 3. GOOGLE PROVIDER USAGE METADATA EXTRACTION TESTS
    # -------------------------------------------------------------------------

    def test_google_provider_extracts_cached_tokens_when_present(self):
        """
        Verify that GoogleProvider correctly extracts cached_content_token_count
        into usage['cached_tokens'] when returned by the API.
        """
        provider = GoogleAgentAPIProvider(api_key="mock_key")

        mock_response = MagicMock()
        mock_response.text = '{"status": "ok"}'
        mock_meta = MagicMock()
        mock_meta.prompt_token_count = 1500
        mock_meta.candidates_token_count = 200
        mock_meta.cached_content_token_count = 1200
        mock_meta.total_token_count = 1700
        mock_response.usage_metadata = mock_meta

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(provider, '_get_client', return_value=mock_client):
            result, usage = provider.generate("Test prompt", return_usage=True)

        self.assertEqual(usage["prompt_tokens"], 1500)
        self.assertEqual(usage["candidates_tokens"], 200)
        self.assertEqual(usage["cached_tokens"], 1200)
        self.assertEqual(usage["total_tokens"], 1700)

    def test_google_provider_gracefully_handles_missing_cache_metadata(self):
        """
        Verify that when Google API does NOT return cached_content_token_count,
        usage['cached_tokens'] defaults cleanly to 0.
        """
        provider = GoogleAgentAPIProvider(api_key="mock_key")

        mock_response = MagicMock()
        mock_response.text = '{"status": "ok"}'
        mock_meta = MagicMock(spec=['prompt_token_count', 'candidates_token_count', 'total_token_count'])
        mock_meta.prompt_token_count = 500
        mock_meta.candidates_token_count = 50
        mock_meta.total_token_count = 550
        mock_response.usage_metadata = mock_meta

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(provider, '_get_client', return_value=mock_client):
            result, usage = provider.generate("Test prompt", return_usage=True)

        self.assertEqual(usage["prompt_tokens"], 500)
        self.assertEqual(usage["candidates_tokens"], 50)
        self.assertEqual(usage["cached_tokens"], 0)
        self.assertEqual(usage["total_tokens"], 550)

    # -------------------------------------------------------------------------
    # 4. PARALLEL CONSENSUS SAMPLING TESTS
    # -------------------------------------------------------------------------

    def test_run_self_consistency_executes_samples_in_parallel(self):
        """
        Verify that ExtractionEngine.run_self_consistency generates samples concurrently
        using ThreadPoolExecutor, taking significantly less time than sequential execution.
        """
        mock_provider = MagicMock()
        call_timestamps = []

        def mock_generate(prompt, system_prompt, context_data=None, temperature=0.7):
            if temperature == 0.7:
                # Sample generation
                time.sleep(0.05)
                call_timestamps.append(time.time())
                return '{"fields": {"metric": {"value": 42, "confidence": 0.9, "evidence": []}}}'
            else:
                # Consensus resolution
                return '{"fields": {"metric": {"value": 42, "confidence": 0.95, "evidence": []}}}'

        mock_provider.generate.side_effect = mock_generate

        engine = ExtractionEngine(llm_provider=mock_provider)

        t0 = time.time()
        result = engine.run_self_consistency(
            text_chunk="Source paper text about efficiency.",
            system_prompt="Extract metrics.",
            user_prompt="Extract parameters.",
            num_samples=3
        )
        duration = time.time() - t0

        # Assert result was parsed and returned
        self.assertIsNotNone(result)
        self.assertIn("metric", result.fields)
        self.assertEqual(result.fields["metric"].value, 42)

        # 3 sequential calls of 0.05s would take >= 0.15s
        # In parallel with 3 workers, sample generation completes in ~0.05-0.08s
        self.assertTrue(duration < 0.14, f"Execution took {duration:.3f}s, expected < 0.14s with concurrency")
        # 3 sample calls + 1 consensus resolution call = 4 calls total
        self.assertEqual(mock_provider.generate.call_count, 4)

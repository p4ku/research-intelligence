import json
from decimal import Decimal
from unittest.mock import MagicMock, patch
from django.test import TestCase, override_settings

from research_intelligence.llm_providers import get_llm_provider
from research_intelligence.llm_providers.google import GoogleAgentAPIProvider
from research_intelligence.llm_providers.openrouter import OpenRouterAPIProvider, _clean_model_name
from research_intelligence.llm_providers.pricing import calculate_llm_cost



class OpenRouterModelNameCleanTestCase(TestCase):
    def test_clean_model_name_defaults(self):
        self.assertEqual(_clean_model_name(None, "google/gemini-2.5-flash"), "google/gemini-2.5-flash")
        self.assertEqual(_clean_model_name("", "google/gemini-2.5-flash"), "google/gemini-2.5-flash")
        self.assertEqual(_clean_model_name("mock-model", "google/gemini-2.5-flash"), "google/gemini-2.5-flash")

    def test_clean_model_name_maps_legacy_google_slugs(self):
        self.assertEqual(_clean_model_name("google/gemini-3.8-flash", "default"), "google/gemini-3.8-flash")
        self.assertEqual(_clean_model_name("gemini-3.8-flash", "default"), "google/gemini-3.8-flash")
        self.assertEqual(_clean_model_name("gemini-2.5-pro", "default"), "google/gemini-2.5-pro")
        self.assertEqual(_clean_model_name("claude-3.5-sonnet", "default"), "anthropic/claude-3.5-sonnet")
        self.assertEqual(_clean_model_name("llama-3.3-70b-instruct", "default"), "meta-llama/llama-3.3-70b-instruct")

    def test_clean_model_name_preserves_valid_slugs(self):
        self.assertEqual(_clean_model_name("meta-llama/llama-3.3-70b-instruct", "default"), "meta-llama/llama-3.3-70b-instruct")
        self.assertEqual(_clean_model_name("deepseek/deepseek-r1", "default"), "deepseek/deepseek-r1")


class OpenRouterFactoryTestCase(TestCase):
    @override_settings(OPENROUTER_API_KEY="test-sk-key-from-settings", OPENROUTER_DEFAULT_MODEL="meta-llama/llama-3.3-70b-instruct")
    def test_factory_resolves_openrouter_from_settings(self):
        provider = get_llm_provider("openrouter")
        self.assertIsInstance(provider, OpenRouterAPIProvider)
        self.assertEqual(provider.api_key, "test-sk-key-from-settings")
        self.assertEqual(provider.model_name, "meta-llama/llama-3.3-70b-instruct")

    @patch.dict("os.environ", {
        "OPENROUTER_API_KEY": "sk-or-real-openrouter-key",
        "GOOGLE_SERVICE_ACCOUNT_JSON": '{"project_id": "google-proj"}'
    })
    def test_factory_does_not_mix_keys_when_both_present(self):
        # OpenRouter provider request resolves cleanly
        op_provider = get_llm_provider("openrouter")
        self.assertIsInstance(op_provider, OpenRouterAPIProvider)
        self.assertEqual(op_provider.api_key, "sk-or-real-openrouter-key")

        # Google provider request resolves cleanly without switching to OpenRouter
        g_provider = get_llm_provider("google")
        self.assertIsInstance(g_provider, GoogleAgentAPIProvider)


class OpenRouterGenerationTestCase(TestCase):

    def setUp(self):
        self.provider = OpenRouterAPIProvider(api_key="sk-or-test-12345", model_name="google/gemini-2.5-flash")

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_text_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "This paper presents a novel transformer."}}],
            "usage": {"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200}
        }
        mock_post.return_value = mock_resp

        result = self.provider.generate(
            prompt="Summarize paper abstract",
            system_instruction="Be concise.",
            temperature=0.3
        )

        self.assertEqual(result, "This paper presents a novel transformer.")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-or-test-12345")
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "google/gemini-2.5-flash")
        self.assertEqual(payload["temperature"], 0.3)
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["role"], "user")

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_structured_output_returns_dict(self, mock_post):
        """CRITICAL: Ensures response is parsed into dict, not returned as raw string."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "passed": True,
                        "reasoning": "Fits inclusion criteria.",
                        "decision_category": "ACCEPTED"
                    })
                }
            }],
            "usage": {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230}
        }
        mock_post.return_value = mock_resp

        schema = {
            "type": "object",
            "required": ["passed", "reasoning"],
            "properties": {
                "passed": {"type": "boolean"},
                "reasoning": {"type": "string"},
            }
        }

        result = self.provider.generate(
            prompt="Evaluate abstract",
            response_schema=schema
        )

        # Must be a Python dict, NOT a str!
        self.assertIsInstance(result, dict)
        self.assertTrue(result["passed"])
        self.assertEqual(result["decision_category"], "ACCEPTED")

        # Verify correct OpenRouter json_schema response_format
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertIn("response_format", payload)
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        self.assertEqual(payload["response_format"]["json_schema"]["schema"], schema)

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_structured_output_handles_markdown_codeblock(self, mock_post):
        """Ensures markdown ```json fences are cleanly stripped before json.loads."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": "```json\n{\"passed\": false, \"reasoning\": \"Outside clinical scope\"}\n```"
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125}
        }
        mock_post.return_value = mock_resp

        result = self.provider.generate(
            prompt="Evaluate abstract",
            response_schema={"type": "object"}
        )

        self.assertIsInstance(result, dict)
        self.assertFalse(result["passed"])
        self.assertEqual(result["reasoning"], "Outside clinical scope")

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_return_usage_tuple(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Synthesized briefing",
                    "reasoning": "Step 1: Analyzed results. Step 2: Corroborated benchmarks."
                }
            }],
            "usage": {"prompt_tokens": 500, "completion_tokens": 120, "total_tokens": 620}
        }
        mock_post.return_value = mock_resp

        result, usage = self.provider.generate(
            prompt="Synthesize briefing",
            return_usage=True
        )

        self.assertEqual(result, "Synthesized briefing")
        self.assertEqual(usage["prompt_tokens"], 500)
        self.assertEqual(usage["candidates_tokens"], 120)
        self.assertEqual(usage["total_tokens"], 620)
        self.assertIn("Step 1", usage["thought_process"])

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_with_reasoning_effort(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Reasoned result"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        }
        mock_post.return_value = mock_resp

        self.provider.generate(
            prompt="Analyze complex logic",
            reasoning_effort="high"
        )

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertIn("reasoning", payload)
        self.assertEqual(payload["reasoning"]["effort"], "high")

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_with_provider_routing_sort(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Fast routed response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        }
        mock_post.return_value = mock_resp

        self.provider.generate(
            prompt="Need fast response",
            provider_sort="throughput"
        )

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertIn("provider", payload)
        self.assertEqual(payload["provider"]["sort"], "throughput")
        self.assertTrue(payload["provider"]["allow_fallbacks"])

    @patch("research_intelligence.utils.pdf_extractor.extract_text_from_pdf_bytes")
    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_with_pdf_bytes_extracts_text(self, mock_post, mock_extract):
        mock_extract.return_value = "Page 1: Deep learning methods for cancer classification."
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Verified full-text."}}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 40, "total_tokens": 340}
        }
        mock_post.return_value = mock_resp

        self.provider.generate(
            prompt="Attached PDF document for full-text screening.",
            pdf_bytes=b"%PDF-1.4 dummy"
        )

        mock_extract.assert_called_once_with(b"%PDF-1.4 dummy", max_chars=120000)
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        user_msg = payload["messages"][-1]["content"]
        self.assertIn("Deep learning methods for cancer classification", user_msg)

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_with_native_pdf_payload(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Summary from native PDF."}}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 50, "total_tokens": 550}
        }
        mock_post.return_value = mock_resp

        res = self.provider.generate(
            prompt="Summarize this PDF",
            pdf_bytes=b"%PDF-1.4 dummy binary content",
            native_pdf=True,
            filename="sample.pdf"
        )
        self.assertEqual(res, "Summary from native PDF.")
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        user_msg = payload["messages"][-1]["content"]
        self.assertIsInstance(user_msg, list)
        self.assertEqual(user_msg[0]["type"], "text")
        self.assertEqual(user_msg[0]["text"], "Summarize this PDF")
        self.assertEqual(user_msg[1]["type"], "file")
        self.assertEqual(user_msg[1]["file"]["filename"], "sample.pdf")
        self.assertTrue(user_msg[1]["file"]["file_data"].startswith("data:application/pdf;base64,"))

    @patch("research_intelligence.llm_providers.openrouter.time.sleep")
    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_retries_on_429_rate_limit(self, mock_post, mock_sleep):
        err_resp = MagicMock()
        err_resp.status_code = 429

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "choices": [{"message": {"content": "Success after rate limit backoff"}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}
        }

        mock_post.side_effect = [err_resp, ok_resp]

        res = self.provider.generate("Test prompt", max_retries=3)
        self.assertEqual(res, "Success after rate limit backoff")
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_stream_yields_deltas_and_usage(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            'data: {"choices":[{"delta":{"content":" world!"}}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}',
            'data: [DONE]'
        ]
        mock_post.return_value = mock_resp

        stream_gen = self.provider.generate_stream(prompt="Hi")
        chunks = list(stream_gen)

        self.assertEqual(chunks[0][0], "Hello")
        self.assertEqual(chunks[1][0], " world!")
        # Last chunk has usage
        last_usage = chunks[2][1]
        self.assertIsNotNone(last_usage)
        self.assertEqual(last_usage["total_tokens"], 12)

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_stream_reasoning_and_fallback_usage(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"reasoning":"Analyzing hypothesis..."}}]}',
            'data: {"choices":[{"delta":{"content":"Conclusion reached."}}]}',
            'data: [DONE]'
        ]
        mock_post.return_value = mock_resp

        chunks = list(self.provider.generate_stream(prompt="Evaluate data"))
        # First chunk is thought
        self.assertEqual(chunks[0][0], "")
        self.assertEqual(chunks[0][1], {"thought": "Analyzing hypothesis..."})

        # Second chunk is text
        self.assertEqual(chunks[1][0], "Conclusion reached.")

        # Third chunk is fallback token usage (since API sent no usage metadata)
        self.assertEqual(chunks[2][0], "")
        self.assertIn("prompt_tokens", chunks[2][1])
        self.assertIn("candidates_tokens", chunks[2][1])
        self.assertGreater(chunks[2][1]["total_tokens"], 0)

    @patch("research_intelligence.llm_providers.openrouter.requests.post")
    def test_generate_usage_fallback_when_tokens_zero(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Sample output"}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
        mock_post.return_value = mock_resp

        result, usage = self.provider.generate(
            prompt="A longer prompt to calculate tokens",
            return_usage=True
        )
        self.assertEqual(result, "Sample output")
        self.assertGreater(usage["prompt_tokens"], 0)
        self.assertGreater(usage["candidates_tokens"], 0)
        self.assertEqual(usage["total_tokens"], usage["prompt_tokens"] + usage["candidates_tokens"])


class OpenRouterPricingTestCase(TestCase):

    def test_openrouter_model_pricing_rates(self):
        # meta-llama/llama-3.3-70b-instruct: $0.13 in / $0.40 out per 1M tokens
        cost_llama = calculate_llm_cost("meta-llama/llama-3.3-70b-instruct", tokens_in=1000000, tokens_out=1000000)
        self.assertEqual(cost_llama, Decimal("0.5300"))

        # anthropic/claude-3.5-sonnet: $3.00 in / $15.00 out per 1M tokens
        cost_claude = calculate_llm_cost("anthropic/claude-3.5-sonnet", tokens_in=1000000, tokens_out=1000000)
        self.assertEqual(cost_claude, Decimal("18.0000"))

        # openai/gpt-4o: $2.50 in / $10.00 out per 1M tokens
        cost_gpt4o = calculate_llm_cost("openai/gpt-4o", tokens_in=1000000, tokens_out=1000000)
        self.assertEqual(cost_gpt4o, Decimal("12.5000"))

        # google/gemini-2.5-flash via OpenRouter: $0.30 in / $2.50 out
        cost_gemini = calculate_llm_cost("google/gemini-2.5-flash", tokens_in=1000000, tokens_out=1000000)
        self.assertEqual(cost_gemini, Decimal("2.8000"))

        # google/gemini-3.8-flash: $0.75 in / $3.75 out per 1M tokens ($0.1875 cached)
        cost_gemini38 = calculate_llm_cost("google/gemini-3.8-flash", tokens_in=1000000, tokens_out=1000000)
        self.assertEqual(cost_gemini38, Decimal("4.5000"))

        # openrouter/fusion/google/gemini-3.8-flash: $0.825 in / $4.125 out per 1M tokens
        cost_fusion = calculate_llm_cost("openrouter/fusion/google/gemini-3.8-flash", tokens_in=1000000, tokens_out=1000000)
        self.assertEqual(cost_fusion, Decimal("4.9500"))

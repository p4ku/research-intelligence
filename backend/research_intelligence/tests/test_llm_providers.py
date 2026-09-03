import json
from unittest.mock import MagicMock, patch
from django.test import TestCase
from pathlib import Path

from google.genai import types
from research_intelligence.llm_providers.google import GoogleAgentAPIProvider

class GoogleLLMProviderTestCase(TestCase):


    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.service_account.Credentials.from_service_account_info")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    @patch.dict("os.environ", {"GOOGLE_SERVICE_ACCOUNT_JSON": '{"type": "service_account", "project_id": "test-project"}', "GOOGLE_CLOUD_PROJECT": "", "GOOGLE_CLOUD_LOCATION": "", "LOCATION": ""})
    def test_client_initialization_with_env_credentials(self, mock_client_cls, mock_from_service_account_info, mock_exists):
        mock_exists.return_value = False
        mock_creds = MagicMock()
        mock_from_service_account_info.return_value = mock_creds

        provider = GoogleAgentAPIProvider(api_key="some-key")
        client = provider._get_client()

        mock_from_service_account_info.assert_called_once_with(
            {"type": "service_account", "project_id": "test-project"},
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        http_opt = types.HttpOptions(timeout=120000) if hasattr(types, 'HttpOptions') else None
        expected_kwargs = {
            "credentials": mock_creds,
            "vertexai": True,
            "project": "test-project"
        }
        if http_opt:
            expected_kwargs["http_options"] = http_opt
        mock_client_cls.assert_called_once_with(**expected_kwargs)
        self.assertEqual(client, mock_client_cls.return_value)

    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    @patch.dict("os.environ", {"GOOGLE_SERVICE_ACCOUNT_JSON": "", "GOOGLE_APPLICATION_CREDENTIALS": ""}, clear=True)
    def test_client_initialization_without_credentials_api_key(self, mock_client_cls, mock_exists):
        # Setup mock so credentials file is not found
        mock_exists.return_value = False
        
        provider = GoogleAgentAPIProvider(api_key="real-api-key")
        client = provider._get_client()
        
        http_opt = types.HttpOptions(timeout=120000) if hasattr(types, 'HttpOptions') else None
        expected_kwargs = {"api_key": "real-api-key"}
        if http_opt:
            expected_kwargs["http_options"] = http_opt
        mock_client_cls.assert_called_once_with(**expected_kwargs)
        self.assertEqual(client, mock_client_cls.return_value)

    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    def test_generate_text_success(self, mock_client_cls, mock_exists):
        mock_exists.return_value = False
        mock_client = mock_client_cls.return_value
        
        # Setup standard response
        mock_response = MagicMock()
        mock_response.text = "This is a systematic review description."
        mock_client.models.generate_content.return_value = mock_response
        
        provider = GoogleAgentAPIProvider(api_key="some-key")
        res = provider.generate(
            prompt="What is a systematic review?",
            system_instruction="Explain to grad student.",
            temperature=0.7
        )
        
        # Verify result
        self.assertEqual(res, "This is a systematic review description.")
        
        # Verify call arguments
        mock_client.models.generate_content.assert_called_once()
        called_kwargs = mock_client.models.generate_content.call_args.kwargs
        
        self.assertEqual(called_kwargs["model"], "gemini-3.8-flash")
        self.assertEqual(called_kwargs["contents"], "What is a systematic review?")
        
        config = called_kwargs["config"]
        self.assertEqual(config.temperature, 0.7)
        self.assertEqual(config.system_instruction, "Explain to grad student.")

    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    @patch.dict("os.environ", {"GOOGLE_SERVICE_ACCOUNT_JSON": "", "GOOGLE_APPLICATION_CREDENTIALS": ""}, clear=True)
    def test_generate_pdf_bytes_success(self, mock_client_cls, mock_exists):
        mock_exists.return_value = False
        mock_client = mock_client_cls.return_value
        
        mock_response = MagicMock()
        mock_response.text = "Assessment result."
        mock_client.models.generate_content.return_value = mock_response
        
        provider = GoogleAgentAPIProvider(api_key="mock-agent-key")
        pdf_data = b"dummy pdf data"
        
        res = provider.generate(
            prompt="Assess TRL.",
            pdf_bytes=pdf_data
        )
        
        self.assertEqual(res, "Assessment result.")
        
        # Verify client recreation with "eu" location for PDFs
        http_opt = types.HttpOptions(timeout=120000) if hasattr(types, 'HttpOptions') else None
        expected_kwargs = {
            "vertexai": True,
            "location": "eu"
        }
        if http_opt:
            expected_kwargs["http_options"] = http_opt
        mock_client_cls.assert_called_with(**expected_kwargs)
        
        # Verify content formatting
        mock_client.models.generate_content.assert_called_once()
        called_kwargs = mock_client.models.generate_content.call_args.kwargs
        
        # PDF defaults model to gemini-3.8-flash
        self.assertEqual(called_kwargs["model"], "gemini-3.8-flash")
        
        contents = called_kwargs["contents"]
        self.assertEqual(len(contents), 2)
        self.assertTrue(isinstance(contents[0], types.Part))
        self.assertEqual(contents[0].inline_data.data, pdf_data)
        self.assertEqual(contents[0].inline_data.mime_type, "application/pdf")
        self.assertEqual(contents[1], "Assess TRL.")

    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    def test_generate_structured_output_success(self, mock_client_cls, mock_exists):
        mock_exists.return_value = False
        mock_client = mock_client_cls.return_value
        
        # Mock structured response
        mock_response = MagicMock()
        mock_response.parsed = None # Fallback to text parsing
        mock_response.text = '{"trl": 3, "confidence": "high", "evidence": "text", "reasoning": "valid"}'
        mock_client.models.generate_content.return_value = mock_response
        
        provider = GoogleAgentAPIProvider(api_key="some-key")
        schema = {
            "type": "object",
            "properties": {
                "trl": {"type": "integer"}
            }
        }
        
        res = provider.generate(
            prompt="Assess TRL.",
            response_schema=schema
        )
        
        # Assert result is dict
        self.assertEqual(res, {"trl": 3, "confidence": "high", "evidence": "text", "reasoning": "valid"})
        
        config = mock_client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.response_json_schema, schema)

    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    def test_generate_generic_file_success(self, mock_client_cls, mock_exists):
        mock_exists.return_value = False
        mock_client = mock_client_cls.return_value
        
        mock_response = MagicMock()
        mock_response.text = "Success parsing image."
        mock_client.models.generate_content.return_value = mock_response
        
        provider = GoogleAgentAPIProvider(api_key="mock-agent-key")
        image_data = b"dummy png data"
        
        res = provider.generate(
            prompt="Analyze this image.",
            file_bytes=image_data,
            mime_type="image/png"
        )
        
        self.assertEqual(res, "Success parsing image.")
        
        called_kwargs = mock_client.models.generate_content.call_args.kwargs
        contents = called_kwargs["contents"]
        self.assertEqual(len(contents), 2)
        self.assertTrue(isinstance(contents[0], types.Part))
        self.assertEqual(contents[0].inline_data.data, image_data)
        self.assertEqual(contents[0].inline_data.mime_type, "image/png")
        self.assertEqual(contents[1], "Analyze this image.")

    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    def test_generate_with_reasoning_effort_configurations(self, mock_client_cls, mock_exists):
        mock_exists.return_value = False
        mock_client = mock_client_cls.return_value
        mock_response = MagicMock()
        mock_response.text = "Reasoned answer"
        mock_client.models.generate_content.return_value = mock_response

        provider = GoogleAgentAPIProvider(api_key="mock-agent-key")

        # 1. Default (no reasoning_effort provided, gemini-3.8-flash -> default medium with budget 2048)
        provider.generate(prompt="Explain quantum teleportation", model="google/gemini-3.8-flash")
        config = mock_client.models.generate_content.call_args.kwargs["config"]
        self.assertIsNotNone(config.thinking_config)
        self.assertEqual(config.thinking_config.thinking_budget, 2048)

        # 2. Explicit 'high' reasoning effort (budget 8192)
        provider.generate(prompt="Prove quantum complexity", model="google/gemini-3.8-flash", reasoning_effort="high")
        config_high = mock_client.models.generate_content.call_args.kwargs["config"]
        self.assertIsNotNone(config_high.thinking_config)
        self.assertEqual(config_high.thinking_config.thinking_budget, 8192)

        # 3. Explicit 'off' reasoning effort (budget 0)
        provider.generate(prompt="Quick summary", model="google/gemini-3.8-flash", reasoning_effort="off")
        config_off = mock_client.models.generate_content.call_args.kwargs["config"]
        self.assertIsNotNone(config_off.thinking_config)
        self.assertEqual(config_off.thinking_config.thinking_budget, 0)

    @patch("research_intelligence.llm_providers.google.time.sleep")
    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    def test_generate_retry_on_429_resource_exhausted_and_recovery(self, mock_client_cls, mock_exists, mock_sleep):
        mock_exists.return_value = False
        mock_client = mock_client_cls.return_value
        success_response = MagicMock()
        success_response.text = "Recovered after rate limit backoff"

        # First call fails with 429 RESOURCE_EXHAUSTED, second succeeds
        mock_client.models.generate_content.side_effect = [
            RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded for quota metric"),
            success_response
        ]

        provider = GoogleAgentAPIProvider(api_key="mock-key")
        result = provider.generate(prompt="Retry test", max_retries=3)

        self.assertEqual(result, "Recovered after rate limit backoff")
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("research_intelligence.llm_providers.google.time.sleep")
    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    def test_generate_retry_exhaustion_on_503_raises(self, mock_client_cls, mock_exists, mock_sleep):
        mock_exists.return_value = False
        mock_client = mock_client_cls.return_value

        mock_client.models.generate_content.side_effect = RuntimeError("503 Service Unavailable: Model is overloaded")

        provider = GoogleAgentAPIProvider(api_key="mock-key")
        with self.assertRaises(RuntimeError):
            provider.generate(prompt="Failing call", max_retries=2)

        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("research_intelligence.llm_providers.google.time.sleep")
    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    def test_generate_retries_on_dns_name_resolution_failure(self, mock_client_cls, mock_exists, mock_sleep):
        mock_exists.return_value = False
        mock_client = mock_client_cls.return_value

        # First call fails with DNS name resolution error, second succeeds
        succ_resp = MagicMock()
        succ_resp.text = "DNS recovered"
        mock_client.models.generate_content.side_effect = [
            RuntimeError("[Errno -3] Temporary failure in name resolution"),
            succ_resp
        ]

        provider = GoogleAgentAPIProvider(api_key="mock-key")
        result = provider.generate(prompt="DNS test", max_retries=3)

        self.assertEqual(result, "DNS recovered")
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    def test_generate_stream_yields_chunks_and_usage(self, mock_client_cls, mock_exists):
        mock_exists.return_value = False
        mock_client = mock_client_cls.return_value

        chunk1 = MagicMock()
        chunk1.text = "First chunk "
        chunk1.usage_metadata = None

        chunk2 = MagicMock()
        chunk2.text = "second chunk."
        chunk2.usage_metadata = MagicMock(prompt_token_count=100, candidates_token_count=20, total_token_count=120)

        mock_client.models.generate_content_stream.return_value = iter([chunk1, chunk2])

        provider = GoogleAgentAPIProvider(api_key="mock-key")
        stream_results = list(provider.generate_stream(prompt="Stream test"))

        self.assertEqual(len(stream_results), 2)
        self.assertEqual(stream_results[0][0], "First chunk ")
        self.assertEqual(stream_results[1][0], "second chunk.")
        self.assertIsNotNone(stream_results[1][1])
        self.assertEqual(stream_results[1][1]["prompt_tokens"], 100)
        self.assertEqual(stream_results[1][1]["candidates_tokens"], 20)


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
        mock_client_cls.assert_called_once_with(
            credentials=mock_creds,
            vertexai=True,
            project="test-project"
        )
        self.assertEqual(client, mock_client_cls.return_value)

    @patch("research_intelligence.llm_providers.google.Path.exists")
    @patch("research_intelligence.llm_providers.google.genai.Client")
    @patch.dict("os.environ", {"GOOGLE_SERVICE_ACCOUNT_JSON": "", "GOOGLE_APPLICATION_CREDENTIALS": ""}, clear=True)
    def test_client_initialization_without_credentials_api_key(self, mock_client_cls, mock_exists):
        # Setup mock so credentials file is not found
        mock_exists.return_value = False
        
        provider = GoogleAgentAPIProvider(api_key="real-api-key")
        client = provider._get_client()
        
        mock_client_cls.assert_called_once_with(api_key="real-api-key")
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
        
        self.assertEqual(called_kwargs["model"], "gemini-3.7-flash")
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
        mock_client_cls.assert_called_with(
            vertexai=True,
            location="eu"
        )
        
        # Verify content formatting
        mock_client.models.generate_content.assert_called_once()
        called_kwargs = mock_client.models.generate_content.call_args.kwargs
        
        # PDF defaults model to gemini-3.7-flash
        self.assertEqual(called_kwargs["model"], "gemini-3.7-flash")
        
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

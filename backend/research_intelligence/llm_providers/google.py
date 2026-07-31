import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from google.oauth2 import service_account

from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class GoogleAgentAPIProvider(BaseLLMProvider):
    """
    Client driver for Google GenAI / Vertex AI using the google-genai SDK.
    Supports structured outputs (JSON schema) and multi-modal elements (PDF).
    """

    def __init__(self, api_key: str = None, endpoint_url: str = None, location: str = None, project_id: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_AGENT_API_KEY")
        self.endpoint_url = endpoint_url
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
        self.location = location or os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("LOCATION")
        self._client = None

    def _get_client(self, location: str = None):
        """
        Lazily initialize the google-genai client.
        Detects credentials from env var GOOGLE_SERVICE_ACCOUNT_JSON or credentials file.
        """
        target_location = location or self.location
        
        # If client already exists for this location, return it
        if self._client is not None and getattr(self, "_client_location", None) == target_location:
            return self._client

        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials = None
        sa_project_id = None

        # Attempt to load from GOOGLE_SERVICE_ACCOUNT_JSON environment variable
        google_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if google_json_str:
            try:
                info = json.loads(google_json_str)
                sa_project_id = info.get("project_id")
                credentials = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=scopes,
                )
                logger.info("Loaded credentials from environment variable GOOGLE_SERVICE_ACCOUNT_JSON")
            except Exception as e:
                logger.warning(f"Failed to load credentials from GOOGLE_SERVICE_ACCOUNT_JSON env var: {str(e)}")

        target_project_id = self.project_id or sa_project_id

        try:
            if credentials is not None:
                client_kwargs = {"credentials": credentials, "vertexai": True}
                if target_project_id:
                    client_kwargs["project"] = target_project_id
                if target_location:
                    client_kwargs["location"] = target_location
                self._client = genai.Client(**client_kwargs)
            elif self.api_key and self.api_key != "mock-agent-key":
                self._client = genai.Client(
                    api_key=self.api_key
                )
            else:
                client_kwargs = {"vertexai": True}
                if target_project_id:
                    client_kwargs["project"] = target_project_id
                if target_location:
                    client_kwargs["location"] = target_location
                self._client = genai.Client(**client_kwargs)
        except Exception as e:
            logger.warning(f"Vertex AI initialization failed: {str(e)}. Falling back to standard Client.")
            self._client = genai.Client()

        self._client_location = target_location
        return self._client

    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        response_schema: dict = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str = None,
        pdf_path: str = None,
        pdf_bytes: bytes = None,
        file_path: str = None,
        file_bytes: bytes = None,
        mime_type: str = None,
        **kwargs
    ) -> Any:
        """
        Generates content using the google-genai Client.
        Supports:
        - prompt (user prompt)
        - system_instruction / system_prompt kwargs
        - response_schema for structured output
        - file_bytes / pdf_bytes or file_path / pdf_path for multimodal ingestion
        """
        # 1. Clean model name
        model_name = model or "gemini-3.5-flash"
        if model_name.startswith("google/"):
            model_name = model_name.replace("google/", "", 1)
        elif model_name.startswith("google-agent/"):
            model_name = model_name.replace("google-agent/", "", 1)

        # Map non-existent/mock model names (e.g. 3.6-flash) to target model gemini-3.5-flash
        if "3.6" in model_name or "mock" in model_name:
            model_name = "gemini-3.5-flash"

        # 2. Determine location and construct client
        f_bytes = file_bytes or pdf_bytes
        f_path = file_path or pdf_path
        has_file = bool(f_bytes or f_path)
        client_location = kwargs.get("location") or self.location or "eu"

        if not model and has_file:
            model_name = "gemini-3.5-flash"

        client = self._get_client(location=client_location)

        # 3. Handle file ingestion
        contents = []
        if has_file:
            # Resolve mime type
            resolved_mime = mime_type
            if not resolved_mime:
                if f_path:
                    import mimetypes
                    resolved_mime, _ = mimetypes.guess_type(str(f_path))
                if not resolved_mime and f_bytes:
                    try:
                        import filetype
                        kind = filetype.guess(f_bytes)
                        if kind:
                            resolved_mime = kind.mime
                    except Exception:
                        pass
                if not resolved_mime:
                    resolved_mime = "application/pdf"  # Fallback

            # Resolve bytes
            resolved_bytes = f_bytes
            if not resolved_bytes and f_path:
                p = Path(f_path)
                if p.exists():
                    try:
                        with p.open("rb") as f:
                            resolved_bytes = f.read()
                    except Exception as e:
                        logger.error(f"Failed to read file at {f_path}: {str(e)}")

            if resolved_bytes:
                file_part = types.Part.from_bytes(
                    data=resolved_bytes,
                    mime_type=resolved_mime,
                )
                contents.append(file_part)

        contents.append(prompt)

        if len(contents) == 1:
            contents = prompt

        # 4. Construct configuration
        config_args = {
            "temperature": temperature,
        }

        if max_tokens:
            config_args["max_output_tokens"] = max_tokens

        # Resolve system instruction
        sys_instruction = system_instruction or kwargs.get("system_prompt")
        if sys_instruction:
            config_args["system_instruction"] = sys_instruction

        if response_schema:
            config_args["response_mime_type"] = "application/json"
            config_args["response_json_schema"] = response_schema

        config = types.GenerateContentConfig(**config_args)

        # 5. Call API with Exponential Backoff Retry Strategy for 429 / RESOURCE_EXHAUSTED
        max_retries = kwargs.get("max_retries", 5)
        response = None

        for attempt in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                break
            except Exception as e:
                err_str = str(e)
                is_rate_limit = (
                    "429" in err_str or
                    "RESOURCE_EXHAUSTED" in err_str or
                    "Resource exhausted" in err_str or
                    "Quota" in err_str or
                    "rate limit" in err_str.lower()
                )

                if is_rate_limit and attempt < max_retries:
                    delay = (2 ** attempt) + (0.2 * attempt)
                    logger.warning(f"⚠️ [RESOURCE_EXHAUSTED / 429] Rate limit hit on attempt {attempt}/{max_retries} for model '{model_name}'. Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    logger.exception(f"Error during Google LLM generation (attempt {attempt}/{max_retries}): {err_str}")
                    raise

        # 6. Parse response if schema was requested
        parsed_result = response.text
        if response_schema:
            try:
                result = response.parsed
                if result is not None:
                    if hasattr(result, "model_dump"):
                        parsed_result = result.model_dump()
                    else:
                        parsed_result = result
                elif response.text:
                    raw_json = response.text
                    if "```json" in raw_json:
                        raw_json = raw_json.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw_json:
                        raw_json = raw_json.split("```")[1].split("```")[0].strip()
                    parsed_result = json.loads(raw_json)
            except Exception as pe:
                logger.warning(f"Failed to parse JSON response: {str(pe)}. Returning raw response text.")

        # Extract token usage metadata
        usage = {
            "prompt_tokens": 0,
            "candidates_tokens": 0,
            "total_tokens": 0
        }
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            p_tok = getattr(meta, "prompt_token_count", 0) or 0
            c_tok = getattr(meta, "candidates_token_count", 0) or 0
            t_tok = getattr(meta, "total_token_count", 0) or (p_tok + c_tok)
            usage = {
                "prompt_tokens": p_tok,
                "candidates_tokens": c_tok,
                "total_tokens": t_tok
            }

        if kwargs.get("return_usage"):
            return parsed_result, usage

        return parsed_result

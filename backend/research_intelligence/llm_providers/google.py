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

def _resolve_thinking_config(kwargs: dict, model_name: str):
    """
    Resolves ThinkingConfig for Gemini models supporting Chain of Thought reasoning.
    Supports reasoning_effort ('off', 'low', 'medium', 'high'), thinking_budget (int),
    thinking_level (str), and deep_thinking (bool).
    Defaults to 'medium' (thinking_budget=2048) for reasoning-capable models (e.g. gemini-3.7, gemini-2.5).
    """
    reasoning_effort = kwargs.get("reasoning_effort")
    deep_thinking = kwargs.get("deep_thinking", False)
    thinking_budget = kwargs.get("thinking_budget")
    thinking_level = kwargs.get("thinking_level")
    include_thoughts = kwargs.get("include_thoughts", False)

    # Default to 'medium' if no reasoning/thinking parameter is explicitly specified
    if reasoning_effort is None and not deep_thinking and thinking_budget is None and thinking_level is None:
        if "3.7" in model_name or "2.5" in model_name or "thinking" in model_name or "flash" in model_name or "pro" in model_name:
            reasoning_effort = "medium"

    if reasoning_effort is not None:
        effort_str = str(reasoning_effort).strip().lower()
        if effort_str in ("off", "none", "0", "false"):
            thinking_budget = 0
            thinking_level = None
        elif effort_str == "low":
            thinking_budget = 1024
            thinking_level = "low"
        elif effort_str == "high":
            thinking_budget = 8192
            thinking_level = "high"
        elif effort_str in ("medium", "true", "default"):
            thinking_budget = 2048
            thinking_level = "medium"

    if deep_thinking and thinking_budget is None:
        thinking_budget = 2048

    if thinking_budget is not None or thinking_level is not None or include_thoughts:
        try:
            thinking_kwargs = {}
            if include_thoughts or deep_thinking:
                thinking_kwargs["include_thoughts"] = True
            if thinking_budget is not None:
                thinking_kwargs["thinking_budget"] = thinking_budget
            elif thinking_level is not None:
                thinking_kwargs["thinking_level"] = thinking_level

            if thinking_kwargs and hasattr(types, 'ThinkingConfig'):
                return types.ThinkingConfig(**thinking_kwargs)
        except Exception as te:
            logger.debug(f"ThinkingConfig resolution note: {te}")
    return None


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
                
                # Workaround for google-genai SDK bug where credentials passed in Client constructor are not utilized.
                # We write the service account JSON to a temporary file and point GOOGLE_APPLICATION_CREDENTIALS to it.
                if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                    import tempfile
                    temp_dir = tempfile.gettempdir()
                    sa_path = os.path.join(temp_dir, "gcp_service_account.json")
                    with open(sa_path, "w") as f:
                        f.write(google_json_str)
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path
                    logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS to temporary file: {sa_path}")
            except Exception as e:
                logger.warning(f"Failed to load credentials from GOOGLE_SERVICE_ACCOUNT_JSON env var: {str(e)}")

        target_project_id = self.project_id or sa_project_id
        # Note: google-genai SDK types.HttpOptions expects timeout in milliseconds (120,000 ms = 2 minutes).
        # A 2-minute ceiling prevents threads from hanging for 5+ minutes on stalled TCP/DNS connections.
        http_options = types.HttpOptions(timeout=120000) if hasattr(types, 'HttpOptions') else None

        try:
            if credentials is not None:
                client_kwargs = {"credentials": credentials, "vertexai": True}
                if target_project_id:
                    client_kwargs["project"] = target_project_id
                if target_location:
                    client_kwargs["location"] = target_location
                if http_options:
                    client_kwargs["http_options"] = http_options
                self._client = genai.Client(**client_kwargs)
            elif self.api_key and self.api_key != "mock-agent-key":
                client_kwargs = {"api_key": self.api_key}
                if http_options:
                    client_kwargs["http_options"] = http_options
                self._client = genai.Client(**client_kwargs)
            else:
                client_kwargs = {"vertexai": True}
                if target_project_id:
                    client_kwargs["project"] = target_project_id
                if target_location:
                    client_kwargs["location"] = target_location
                if http_options:
                    client_kwargs["http_options"] = http_options
                self._client = genai.Client(**client_kwargs)
        except Exception as e:
            logger.warning(f"Vertex AI initialization failed: {str(e)}. Falling back to standard Client.")
            try:
                self._client = genai.Client(http_options=http_options) if http_options else genai.Client()
            except Exception:
                self._client = genai.Client()

        self._client_location = target_location
        return self._client

    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        response_schema: dict = None,
        temperature: float = 0.0,
        max_tokens: int = 8192,
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
        model_name = model or "gemini-3.8-flash"
        if model_name.startswith("google/"):
            model_name = model_name.replace("google/", "", 1)
        elif model_name.startswith("google-agent/"):
            model_name = model_name.replace("google-agent/", "", 1)

        # Map non-existent/mock model names to target model gemini-3.8-flash
        if "mock" in model_name:
            model_name = "gemini-3.8-flash"

        # 2. Determine location and construct client
        f_bytes = file_bytes or pdf_bytes
        f_path = file_path or pdf_path
        has_file = bool(f_bytes or f_path)
        client_location = kwargs.get("location") or self.location or "eu"

        if not model and has_file:
            model_name = "gemini-3.8-flash"

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
                # Pre-check: If PDF is larger than 15MB, Gemini inline data API will fail with 400 INVALID_ARGUMENT
                # (inline limit is 20MB base64 payload) or cause huge memory spikes. Extract text directly!
                if resolved_mime == "application/pdf" and len(resolved_bytes) > 15 * 1024 * 1024:
                    logger.info(f"📄 PDF binary is large ({len(resolved_bytes)/(1024*1024):.1f} MB > 15 MB). Extracting text to avoid 400 INVALID_ARGUMENT inline limit.")
                    try:
                        from ..utils.pdf_extractor import extract_text_from_pdf_bytes
                        pdf_text = extract_text_from_pdf_bytes(resolved_bytes, max_chars=120000)
                        if pdf_text:
                            contents.append(f"<DOCUMENT_TEXT>\n{pdf_text}\n</DOCUMENT_TEXT>")
                            resolved_bytes = None
                    except Exception as ext_err:
                        logger.warning(f"Could not pre-extract large PDF text: {ext_err}")

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

        cached_content = kwargs.get("cached_content")
        if cached_content:
            config_args["cached_content"] = cached_content

        # Native Gemini Thinking / Reasoning Configuration
        thinking_cfg = _resolve_thinking_config(kwargs, model_name)
        if thinking_cfg:
            config_args["thinking_config"] = thinking_cfg

        # Explicitly disable automatic function calling (AFC) to silence SDK warning for direct generation
        if hasattr(types, "AutomaticFunctionCallingConfig"):
            config_args["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)

        config = types.GenerateContentConfig(**config_args)

        # 5. Call API with Exponential Backoff Retry Strategy for 429, 503, Timeouts, and Network Drop
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
                # Resilient fallback: If Gemini rejects binary PDF with 400 INVALID_ARGUMENT (e.g. font error, >1000 pages, corruption),
                # automatically extract text from bytes and retry generation as text prompt immediately instead of failing the job.
                if ("400" in err_str or "INVALID_ARGUMENT" in err_str) and has_file and resolved_bytes:
                    logger.warning(
                        f"⚠️ [GEMINI 400 FALLBACK] Gemini API rejected binary payload with 400 INVALID_ARGUMENT. "
                        f"Extracting text from PDF and retrying generation as text prompt..."
                    )
                    try:
                        from ..utils.pdf_extractor import extract_text_from_pdf_bytes
                        pdf_text = extract_text_from_pdf_bytes(resolved_bytes, max_chars=120000)
                    except Exception:
                        pdf_text = ""
                    if pdf_text:
                        contents = [f"<DOCUMENT_TEXT>\n{pdf_text}\n</DOCUMENT_TEXT>", prompt]
                    else:
                        contents = prompt
                    resolved_bytes = None
                    has_file = False
                    continue
                is_transient = (
                    "429" in err_str or
                    "RESOURCE_EXHAUSTED" in err_str or
                    "Resource exhausted" in err_str or
                    "Quota" in err_str or
                    "rate limit" in err_str.lower() or
                    "timed out" in err_str.lower() or
                    "timeout" in err_str.lower() or
                    "503" in err_str or
                    "500" in err_str or
                    "unavailable" in err_str.lower() or
                    "connection" in err_str.lower() or
                    "connect" in err_str.lower() or
                    "name resolution" in err_str.lower() or
                    "temporary failure" in err_str.lower() or
                    "errno -3" in err_str.lower() or
                    "eai_again" in err_str.lower() or
                    "dns" in err_str.lower() or
                    "deadline" in err_str.lower() or
                    "reset by peer" in err_str.lower() or
                    "broken pipe" in err_str.lower() or
                    "remote end closed" in err_str.lower() or
                    "network" in err_str.lower()
                )

                if is_transient and attempt < max_retries:
                    delay = (2 ** attempt) + (0.5 * attempt)
                    logger.warning(f"⚠️ [TRANSIENT RETRY {attempt}/{max_retries}] Google LLM call failed for model '{model_name}': {err_str}. Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    logger.exception(f"Error during Google LLM generation (attempt {attempt}/{max_retries}): {err_str}")
                    raise

        # 6. Parse response if schema was requested
        thought_parts = []
        answer_parts = []
        if hasattr(response, 'candidates') and response.candidates:
            cand = response.candidates[0]
            if hasattr(cand, 'content') and cand.content and hasattr(cand.content, 'parts'):
                for part in cand.content.parts:
                    p_text = getattr(part, 'text', '') or ''
                    if getattr(part, 'thought', False):
                        thought_parts.append(p_text)
                    elif p_text:
                        answer_parts.append(p_text)

        thought_text = "".join(thought_parts)
        parsed_result = "".join(answer_parts) if answer_parts else (response.text if hasattr(response, 'text') else str(response))

        if response_schema:
            try:
                result = getattr(response, 'parsed', None)
                if result is not None:
                    if hasattr(result, "model_dump"):
                        parsed_result = result.model_dump()
                    else:
                        parsed_result = result
                elif parsed_result and isinstance(parsed_result, str):
                    raw_json = parsed_result
                    if "```json" in raw_json:
                        raw_json = raw_json.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw_json:
                        raw_json = raw_json.split("```")[1].split("```")[0].strip()
                    parsed_result = json.loads(raw_json)
            except Exception as pe:
                logger.warning(f"Failed to parse JSON response: {str(pe)}. Returning raw response text.")

        # Extract token usage metadata & thoughts
        usage = {
            "prompt_tokens": 0,
            "candidates_tokens": 0,
            "total_tokens": 0,
            "thought_process": thought_text
        }
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            p_tok = getattr(meta, "prompt_token_count", 0) or 0
            c_tok = getattr(meta, "candidates_token_count", 0) or 0
            cached_tok = getattr(meta, "cached_content_token_count", 0) or 0
            t_tok = getattr(meta, "total_token_count", 0) or (p_tok + c_tok)
            usage["prompt_tokens"] = p_tok
            usage["candidates_tokens"] = c_tok
            usage["cached_tokens"] = cached_tok
            usage["total_tokens"] = t_tok

        # Robust fallback estimation if provider API omitted token metrics
        if usage["prompt_tokens"] == 0:
            prompt_str = prompt if isinstance(prompt, str) else str(contents)
            usage["prompt_tokens"] = max(len(prompt_str) // 4, 1)
        if usage["candidates_tokens"] == 0 and (parsed_result or thought_text):
            out_str = (str(parsed_result) if parsed_result else "") + thought_text
            usage["candidates_tokens"] = max(len(out_str) // 4, 1)
        usage["total_tokens"] = usage["prompt_tokens"] + usage["candidates_tokens"]

        if kwargs.get("return_usage"):
            return parsed_result, usage

        return parsed_result

    def generate_stream(
        self,
        prompt: str,
        system_instruction: str = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        model: str = None,
        file_bytes: bytes = None,
        pdf_bytes: bytes = None,
        mime_type: str = None,
        cached_content: str = None,
        **kwargs
    ):
        """
        Streams response chunks from Gemini generate_content_stream.
        Yields (chunk_text, usage_dict).
        """
        model_name = model or "gemini-3.8-flash"
        if model_name.startswith("google/"):
            model_name = model_name.replace("google/", "", 1)
        if "mock" in model_name:
            model_name = "gemini-3.8-flash"

        client_location = kwargs.get("location") or self.location or "eu"
        client = self._get_client(location=client_location)

        contents = []
        f_bytes = file_bytes or pdf_bytes
        if f_bytes:
            resolved_mime = mime_type or "application/pdf"
            file_part = types.Part.from_bytes(data=f_bytes, mime_type=resolved_mime)
            contents.append(file_part)

        contents.append(prompt)
        if len(contents) == 1:
            contents = prompt

        config_args = {"temperature": temperature}
        if max_tokens:
            config_args["max_output_tokens"] = max_tokens
        if system_instruction:
            config_args["system_instruction"] = system_instruction
        if cached_content:
            config_args["cached_content"] = cached_content

        # Native Gemini Thinking / Reasoning Configuration
        thinking_cfg = _resolve_thinking_config(kwargs, model_name)
        if thinking_cfg:
            config_args["thinking_config"] = thinking_cfg

        # Explicitly disable automatic function calling (AFC) to silence SDK warning for direct generation
        if hasattr(types, "AutomaticFunctionCallingConfig"):
            config_args["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)

        config = types.GenerateContentConfig(**config_args)

        try:
            response_stream = client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=config,
            )
            accumulated_text_len = 0
            accumulated_thought_len = 0
            final_captured_usage = None

            for chunk in response_stream:
                chunk_thought = ""
                chunk_answer = ""
                if hasattr(chunk, 'candidates') and chunk.candidates:
                    cand = chunk.candidates[0]
                    if hasattr(cand, 'content') and cand.content and hasattr(cand.content, 'parts'):
                        for part in cand.content.parts:
                            p_text = getattr(part, 'text', '') or ''
                            if getattr(part, 'thought', False):
                                chunk_thought += p_text
                            elif p_text:
                                chunk_answer += p_text

                chunk_text = chunk_answer if chunk_answer else (getattr(chunk, 'text', '') or '')
                if chunk_text:
                    accumulated_text_len += len(chunk_text)
                if chunk_thought:
                    accumulated_thought_len += len(chunk_thought)

                usage = None
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    meta = chunk.usage_metadata
                    p_tok = getattr(meta, "prompt_token_count", 0) or 0
                    c_tok = getattr(meta, "candidates_token_count", 0) or 0
                    cached_tok = getattr(meta, "cached_content_token_count", 0) or 0
                    t_tok = getattr(meta, "total_token_count", 0) or (p_tok + c_tok)
                    if p_tok > 0 or c_tok > 0 or t_tok > 0:
                        usage = {"prompt_tokens": p_tok, "candidates_tokens": c_tok, "cached_tokens": cached_tok, "total_tokens": t_tok}
                        final_captured_usage = usage

                if chunk_thought:
                    usage_with_thought = (usage or {}).copy()
                    usage_with_thought["thought"] = chunk_thought
                    yield "", usage_with_thought
                if chunk_text:
                    yield chunk_text, usage

            # Check if response_stream itself has final usage_metadata attached
            if not final_captured_usage and hasattr(response_stream, 'usage_metadata') and response_stream.usage_metadata:
                meta = response_stream.usage_metadata
                p_tok = getattr(meta, "prompt_token_count", 0) or 0
                c_tok = getattr(meta, "candidates_token_count", 0) or 0
                cached_tok = getattr(meta, "cached_content_token_count", 0) or 0
                t_tok = getattr(meta, "total_token_count", 0) or (p_tok + c_tok)
                if p_tok > 0 or c_tok > 0:
                    final_captured_usage = {"prompt_tokens": p_tok, "candidates_tokens": c_tok, "cached_tokens": cached_tok, "total_tokens": t_tok}
                    yield "", final_captured_usage

            # Fallback estimation if stream produced output but no token usage was reported
            if not final_captured_usage or (final_captured_usage.get("prompt_tokens", 0) == 0 and final_captured_usage.get("candidates_tokens", 0) == 0):
                prompt_str = prompt if isinstance(prompt, str) else str(contents)
                p_est = max(len(prompt_str) // 4, 1)
                c_est = max((accumulated_text_len + accumulated_thought_len) // 4, 1) if (accumulated_text_len or accumulated_thought_len) else 0
                fallback_usage = {"prompt_tokens": p_est, "candidates_tokens": c_est, "total_tokens": p_est + c_est}
                yield "", fallback_usage

        except Exception as e:
            logger.exception(f"Error during streaming generate_content_stream: {e}")
            raise

    def create_context_cache(
        self,
        model: str,
        contents: list | Any,
        ttl: str = "3600s",
        display_name: str = None,
        system_instruction: str = None,
        **kwargs
    ) -> str | None:
        """
        Creates a server-side Gemini CachedContent resource.
        Returns the unique cached content resource name (e.g. 'cachedContents/12345') or None on failure.
        """
        model_name = model or "gemini-3.8-flash"
        if model_name.startswith("google/"):
            model_name = model_name.replace("google/", "", 1)
        if "mock" in model_name:
            model_name = "gemini-3.8-flash"

        client_location = kwargs.get("location") or self.location or "eu"
        client = self._get_client(location=client_location)
        try:
            cache_config = types.CreateCachedContentConfig(
                contents=contents if isinstance(contents, list) else [contents],
                ttl=ttl,
                display_name=display_name,
                system_instruction=system_instruction
            )
            cached_content = client.caches.create(
                model=model_name,
                config=cache_config
            )
            return getattr(cached_content, 'name', None)
        except Exception as e:
            logger.warning(f"Failed to create Gemini context cache: {e}")
            return None

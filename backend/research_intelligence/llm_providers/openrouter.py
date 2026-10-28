import json
import logging
import os
import time
from typing import Any, Dict, Generator, Optional, Tuple
import requests
from django.conf import settings

from .base import BaseLLMProvider

logger = logging.getLogger(__name__)


def _clean_model_name(model_name: Optional[str], default_model: str) -> str:
    """
    Normalizes model slug for OpenRouter.
    OpenRouter expects '<provider>/<model-name>' (e.g. 'google/gemini-3.8-flash',
    'meta-llama/llama-3.3-70b-instruct', 'anthropic/claude-3.5-sonnet').
    """
    if not model_name or "mock" in model_name:
        return default_model

    clean = str(model_name).strip()
    if clean.startswith("google-agent/"):
        clean = clean.replace("google-agent/", "google/", 1)

    # If no provider slash is present, add the appropriate provider prefix
    if "/" not in clean:
        if clean.startswith("gemini"):
            return f"google/{clean}"
        if clean.startswith("llama"):
            return f"meta-llama/{clean}"
        if clean.startswith("claude"):
            return f"anthropic/{clean}"
        if clean.startswith("gpt"):
            return f"openai/{clean}"

    return clean


class OpenRouterAPIProvider(BaseLLMProvider):
    """
    Enterprise-grade client driver for OpenRouter API Gateway.
    Supports:
    - 400+ models (including google/gemini-3.8-flash, Claude, Llama 3.3, DeepSeek, GPT-4o)
    - Native Structured Outputs (JSON Schema validation & automatic parsing to dict)
    - In-memory PDF / Document text extraction (PyPDF fallback)
    - Reasoning / Thinking models (effort: low / medium / high)
    - Full-turn SSE streaming (generate_stream) for real-time Paper Chat
    - Exponential backoff retry loop for 429 (rate limits) & 502/503/504 gateway errors
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        endpoint_url: str = "https://openrouter.ai/api/v1/chat/completions"
    ):
        self.api_key = (
            api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or getattr(settings, 'OPENROUTER_API_KEY', None)
            or "mock-openrouter-key"
        )
        self.model_name = (
            model_name
            or os.environ.get("OPENROUTER_DEFAULT_MODEL")
            or getattr(settings, 'OPENROUTER_DEFAULT_MODEL', None)
            or "google/gemini-3.8-flash"
        )
        self.endpoint_url = endpoint_url

    def _get_headers(self) -> Dict[str, str]:
        app_name = getattr(settings, 'APP_NAME', 'Schwarz Research Intelligence')
        referer_url = (
            os.getenv("OPENROUTER_HTTP_REFERER")
            or getattr(settings, 'OPENROUTER_HTTP_REFERER', None)
            or getattr(settings, 'SITE_URL', None)
            or "http://localhost:8000"
        )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": referer_url,
            "X-Title": app_name,
        }

    def _prepare_content_with_pdf(
        self,
        prompt: str,
        pdf_bytes: Optional[bytes] = None,
        file_bytes: Optional[bytes] = None
    ) -> str:
        """
        If PDF binary bytes are provided, extracts full plain text via PyPDF
        and injects it into the prompt so models on OpenRouter receive the document body.
        """
        raw_bytes = pdf_bytes or file_bytes
        if not raw_bytes:
            return prompt

        try:
            from ..utils.pdf_extractor import extract_text_from_pdf_bytes
            extracted_text = extract_text_from_pdf_bytes(raw_bytes, max_chars=120000)
            if extracted_text:
                doc_block = f"<UNTRUSTED_DOCUMENT_CONTENT>\n{extracted_pdf_header(extracted_text)}\n</UNTRUSTED_DOCUMENT_CONTENT>\n\n"
                # If prompt already has UNTRUSTED_DOCUMENT_CONTENT, replace or prepend
                if "Attached PDF document" in prompt or "Please analyze the attached" in prompt:
                    return f"{doc_block}\n{prompt}"
                return f"{doc_block}{prompt}"
        except Exception as e:
            logger.warning(f"Could not extract text from PDF bytes for OpenRouter prompt: {e}")

        return prompt

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        response_schema: Optional[dict] = None,
        temperature: float = 0.0,
        max_tokens: int = 8192,
        model: Optional[str] = None,
        pdf_path: Optional[str] = None,
        pdf_bytes: Optional[bytes] = None,
        file_path: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Executes a prompt generation via OpenRouter API.
        When response_schema is provided, automatically enforces JSON Schema and
        parses the JSON response into a Python dict.
        """
        target_model = _clean_model_name(model, self.model_name)
        f_bytes = file_bytes or pdf_bytes
        f_path = file_path or pdf_path or kwargs.get("pdf_path") or kwargs.get("file_path")
        resolved_bytes = f_bytes
        if not resolved_bytes and f_path:
            p = Path(f_path)
            if p.exists():
                try:
                    with p.open("rb") as f:
                        resolved_bytes = f.read()
                except Exception as e:
                    logger.error(f"Failed to read file at {f_path}: {e}")

        raw_bytes = resolved_bytes
        native_pdf = kwargs.get("native_pdf", False)
        filename = kwargs.get("filename") or (Path(f_path).name if f_path else "document.pdf")
        resolved_mime = mime_type or kwargs.get("mime_type")
        if not resolved_mime and f_path:
            import mimetypes
            resolved_mime, _ = mimetypes.guess_type(str(f_path))
        if not resolved_mime:
            resolved_mime = "application/pdf"

        if native_pdf and raw_bytes and isinstance(raw_bytes, bytes) and raw_bytes[:4] == b"%PDF":
            import base64
            b64_pdf = base64.b64encode(raw_bytes).decode("utf-8")
            user_content = [
                {"type": "text", "text": prompt},
                {
                    "type": "file",
                    "file": {
                        "filename": filename,
                        "file_data": f"data:{resolved_mime};base64,{b64_pdf}"
                    }
                }
            ]
        else:
            user_content = self._prepare_content_with_pdf(
                prompt,
                pdf_bytes=raw_bytes
            )

        sys_prompt = system_instruction or kwargs.get("system_prompt")
        if response_schema:
            schema_instruction = (
                "CRITICAL OUTPUT INSTRUCTION:\n"
                "You must output ONLY a valid JSON object matching the requested schema. "
                "Do NOT include markdown fences, preambles, or explanations."
            )
            if sys_prompt:
                sys_prompt = f"{sys_prompt}\n\n{schema_instruction}"
            else:
                sys_prompt = schema_instruction

        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": user_content})

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 8192,
        }

        # Structured Outputs formatting
        if response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "strict": True,
                    "schema": response_schema
                }
            }

        # Reasoning effort support for CoT models (e.g. Gemini 3.8/2.5, DeepSeek R1, OpenAI o-series)
        reasoning_effort = kwargs.get("reasoning_effort")
        if not reasoning_effort and kwargs.get("deep_thinking"):
            reasoning_effort = "medium"
        if kwargs.get("thinking_budget") is not None:
            tb = int(kwargs.get("thinking_budget") or 0)
            if tb <= 0:
                reasoning_effort = "none"
            elif tb <= 1024:
                reasoning_effort = "low"
            elif tb <= 4096:
                reasoning_effort = "medium"
            else:
                reasoning_effort = "high"

        if reasoning_effort and str(reasoning_effort).lower() in ("low", "medium", "high", "none"):
            payload["reasoning"] = {"effort": str(reasoning_effort).lower()}

        # Provider routing & performance optimization (throughput / latency / price)
        provider_routing = kwargs.get("provider") or {}
        provider_sort = kwargs.get("provider_sort") or os.getenv("OPENROUTER_PROVIDER_SORT")
        if not provider_routing and provider_sort:
            provider_routing = {"sort": str(provider_sort).lower(), "allow_fallbacks": True}
        if provider_routing:
            payload["provider"] = provider_routing

        headers = self._get_headers()
        max_retries = kwargs.get("max_retries", 3)
        timeout = kwargs.get("timeout", (10.0, 120.0))  # 10s connect, 120s read

        last_error = None
        data = None

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    self.endpoint_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )

                # If model rejected "json_schema", retry with "json_object" fallback
                if response.status_code == 400 and response_schema and payload.get("response_format", {}).get("type") == "json_schema":
                    err_msg = response.text.lower()
                    if "schema" in err_msg or "response_format" in err_msg or "unsupported" in err_msg:
                        logger.warning(f"OpenRouter model '{target_model}' rejected json_schema; retrying with json_object.")
                        payload["response_format"] = {"type": "json_object"}
                        continue

                # If model rejected native PDF payload with 400, fallback to in-memory text extraction and retry
                if response.status_code == 400 and native_pdf and raw_bytes:
                    logger.warning(f"OpenRouter model '{target_model}' rejected native PDF payload with 400. Retrying with extracted text...")
                    native_pdf = False
                    user_content = self._prepare_content_with_pdf(prompt, pdf_bytes=raw_bytes)
                    messages[-1]["content"] = user_content
                    continue

                # Rate limiting or temporary gateway unavailability
                if response.status_code in (429, 502, 503, 504):
                    sleep_time = min(1.0 * (2 ** (attempt - 1)), 8.0)
                    logger.warning(
                        f"OpenRouter API returned {response.status_code} (attempt {attempt}/{max_retries}). "
                        f"Backing off for {sleep_time:.1f}s..."
                    )
                    time.sleep(sleep_time)
                    continue

                response.raise_for_status()
                data = response.json()
                break

            except requests.exceptions.RequestException as req_err:
                last_error = req_err
                if attempt < max_retries:
                    sleep_time = min(1.0 * (2 ** (attempt - 1)), 8.0)
                    logger.warning(f"OpenRouter request error on attempt {attempt}/{max_retries}: {req_err}. Retrying in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                else:
                    raise RuntimeError(f"OpenRouter generation failed after {max_retries} attempts: {req_err}") from req_err

        if not data:
            raise RuntimeError(f"OpenRouter returned no data after {max_retries} attempts. Last error: {last_error}")

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        raw_content = msg.get("content") or ""
        thought_process = msg.get("reasoning") or ""

        # Parse JSON output when response_schema is present
        parsed_result: Any = raw_content
        if response_schema:
            parsed_result = self._parse_json_content(raw_content)

        # Token accounting
        raw_usage = data.get("usage", {})
        p_tok = int(raw_usage.get("prompt_tokens", 0) or 0)
        c_tok = int(raw_usage.get("completion_tokens", 0) or 0)
        t_tok = int(raw_usage.get("total_tokens", 0) or (p_tok + c_tok))

        prompt_details = raw_usage.get("prompt_tokens_details") or {}
        cached_tok = int(prompt_details.get("cached_tokens", 0) or 0)
        api_cost = raw_usage.get("cost")

        prompt_str = prompt if isinstance(prompt, str) else str(user_content)
        if p_tok == 0:
            p_tok = max(len(prompt_str) // 4, 1)
        if c_tok == 0 and raw_content:
            c_tok = max(len(raw_content) // 4, 1)

        usage = {
            "prompt_tokens": p_tok,
            "candidates_tokens": c_tok,
            "total_tokens": t_tok or (p_tok + c_tok),
            "cached_tokens": cached_tok,
            "api_cost": api_cost,
            "thought_process": thought_process
        }

        if kwargs.get("return_usage"):
            return parsed_result, usage

        return parsed_result

    def generate_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        model: Optional[str] = None,
        pdf_path: Optional[str] = None,
        pdf_bytes: Optional[bytes] = None,
        file_path: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        **kwargs
    ) -> Generator[Tuple[str, Optional[Dict[str, Any]]], None, None]:
        """
        Streams response chunks from OpenRouter chat completions via SSE.
        Yields (chunk_text, chunk_usage_dict).
        """
        target_model = _clean_model_name(model, self.model_name)
        f_bytes = file_bytes or pdf_bytes
        f_path = file_path or pdf_path or kwargs.get("pdf_path") or kwargs.get("file_path")
        resolved_bytes = f_bytes
        if not resolved_bytes and f_path:
            p = Path(f_path)
            if p.exists():
                try:
                    with p.open("rb") as f:
                        resolved_bytes = f.read()
                except Exception as e:
                    logger.error(f"Failed to read file at {f_path}: {e}")

        raw_bytes = resolved_bytes
        native_pdf = kwargs.get("native_pdf", False)
        filename = kwargs.get("filename") or (Path(f_path).name if f_path else "document.pdf")
        resolved_mime = mime_type or kwargs.get("mime_type")
        if not resolved_mime and f_path:
            import mimetypes
            resolved_mime, _ = mimetypes.guess_type(str(f_path))
        if not resolved_mime:
            resolved_mime = "application/pdf"

        if native_pdf and raw_bytes and isinstance(raw_bytes, bytes) and raw_bytes[:4] == b"%PDF":
            import base64
            b64_pdf = base64.b64encode(raw_bytes).decode("utf-8")
            user_content = [
                {"type": "text", "text": prompt},
                {
                    "type": "file",
                    "file": {
                        "filename": filename,
                        "file_data": f"data:{resolved_mime};base64,{b64_pdf}"
                    }
                }
            ]
        else:
            user_content = self._prepare_content_with_pdf(
                prompt,
                pdf_bytes=raw_bytes
            )

        sys_prompt = system_instruction or kwargs.get("system_prompt")
        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            "stream": True,
            "stream_options": {"include_usage": True}
        }

        reasoning_effort = kwargs.get("reasoning_effort")
        if not reasoning_effort and kwargs.get("deep_thinking"):
            reasoning_effort = "medium"
        if kwargs.get("thinking_budget") is not None:
            tb = int(kwargs.get("thinking_budget") or 0)
            if tb <= 0:
                reasoning_effort = "none"
            elif tb <= 1024:
                reasoning_effort = "low"
            elif tb <= 4096:
                reasoning_effort = "medium"
            else:
                reasoning_effort = "high"

        if reasoning_effort and str(reasoning_effort).lower() in ("low", "medium", "high", "none"):
            payload["reasoning"] = {"effort": str(reasoning_effort).lower()}

        # Provider routing & performance optimization (throughput / latency / price)
        provider_routing = kwargs.get("provider") or {}
        provider_sort = kwargs.get("provider_sort") or os.getenv("OPENROUTER_PROVIDER_SORT")
        if not provider_routing and provider_sort:
            provider_routing = {"sort": str(provider_sort).lower(), "allow_fallbacks": True}
        if provider_routing:
            payload["provider"] = provider_routing

        headers = self._get_headers()
        timeout = kwargs.get("timeout", (10.0, 120.0))

        response = requests.post(
            self.endpoint_url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=timeout
        )
        response.raise_for_status()

        accumulated_text_len = 0
        accumulated_thought_len = 0
        final_captured_usage = None

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            clean_line = line.strip()
            if not clean_line.startswith("data:"):
                continue

            data_str = clean_line[5:].strip()
            if data_str == "[DONE]":
                break

            try:
                chunk_obj = json.loads(data_str)
            except Exception:
                continue

            delta_text = ""
            reasoning_chunk = ""

            choices = chunk_obj.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                delta_text = delta.get("content") or ""
                reasoning_chunk = delta.get("reasoning") or ""

            if delta_text:
                accumulated_text_len += len(delta_text)
            if reasoning_chunk:
                accumulated_thought_len += len(reasoning_chunk)

            usage_in_chunk = None
            if "usage" in chunk_obj and chunk_obj["usage"]:
                u = chunk_obj["usage"]
                p_tok = int(u.get("prompt_tokens", 0) or 0)
                c_tok = int(u.get("completion_tokens", 0) or 0)
                cached_tok = int((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)
                usage_in_chunk = {
                    "prompt_tokens": p_tok,
                    "candidates_tokens": c_tok,
                    "cached_tokens": cached_tok,
                    "total_tokens": int(u.get("total_tokens", 0) or (p_tok + c_tok)),
                }
                final_captured_usage = usage_in_chunk

            if reasoning_chunk:
                yield ("", {"thought": reasoning_chunk})
            if delta_text:
                yield (delta_text, usage_in_chunk)
            elif usage_in_chunk:
                yield ("", usage_in_chunk)

        # Fallback estimation if stream produced output but no token usage was reported
        if not final_captured_usage or (final_captured_usage.get("prompt_tokens", 0) == 0 and final_captured_usage.get("candidates_tokens", 0) == 0):
            prompt_str = prompt if isinstance(prompt, str) else str(user_content)
            p_est = max(len(prompt_str) // 4, 1)
            c_est = max((accumulated_text_len + accumulated_thought_len) // 4, 1) if (accumulated_text_len or accumulated_thought_len) else 0
            fallback_usage = {"prompt_tokens": p_est, "candidates_tokens": c_est, "total_tokens": p_est + c_est}
            yield ("", fallback_usage)


    @staticmethod
    def _parse_json_content(content: str) -> Dict[str, Any]:
        """
        Robustly parses a JSON string, stripping markdown code block fences if present.
        """
        if not content:
            return {}

        clean = content.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return parsed
            return {"result": parsed}
        except Exception as direct_err:
            # Fallback: extract substring between first '{' and last '}'
            if "{" in clean and "}" in clean:
                try:
                    start_idx = clean.find("{")
                    end_idx = clean.rfind("}")
                    extracted = clean[start_idx : end_idx + 1]
                    parsed = json.loads(extracted)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass
            logger.warning(f"Could not parse LLM JSON response from OpenRouter: {direct_err}. Raw content: {content[:200]}")
            return {"raw_content": content, "parse_error": str(direct_err)}


def extracted_pdf_header(text: str) -> str:
    """Helper to format extracted PDF content."""
    return f"DOCUMENT FULL-TEXT EXTRACT (PDF):\n{text}"

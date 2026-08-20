import requests
from .base import BaseLLMProvider

class OpenRouterAPIProvider(BaseLLMProvider):
    """
    Client driver for OpenRouter API fallback execution.
    Allows routing tasks to Llama, Mistral, or Qwen models as needed.
    """

    def __init__(self, api_key: str, model_name: str = "meta-llama/llama-3-70b-instruct"):
        self.api_key = api_key
        self.model_name = model_name
        self.endpoint_url = "https://openrouter.ai/api/v1/chat/completions"

    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        response_schema: dict = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str = None,
        **kwargs
    ):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://schwarz-group.com/research-intelligence",
            "X-Title": "Schwarz Research Intelligence MVP"
        }
        
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model or self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        if response_schema:
            payload["response_format"] = {
                "type": "json_object",
                "schema": response_schema
            }
            
        response = requests.post(self.endpoint_url, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        raw_usage = data.get("usage", {})
        usage = {
            "prompt_tokens": int(raw_usage.get("prompt_tokens", 0) or 0),
            "candidates_tokens": int(raw_usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(raw_usage.get("total_tokens", 0) or 0)
        }
        content = data["choices"][0]["message"]["content"]
        if kwargs.get("return_usage"):
            return content, usage
        return content

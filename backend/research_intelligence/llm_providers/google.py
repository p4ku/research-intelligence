import requests
from .base import BaseLLMProvider

class GoogleAgentAPIProvider(BaseLLMProvider):
    """
    Client driver for the Schwarz Digits / Google Agent API.
    Designed for high-throughput, low-latency sovereign processing.
    """

    def __init__(self, api_key: str, endpoint_url: str = None):
        self.api_key = api_key
        self.endpoint_url = endpoint_url or "https://api.digits.schwarz/v1/google-agent"

    def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        response_schema: dict = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str = None
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Prepare Schwarz Digits payload structure
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }
        
        if model:
            payload["model"] = model
        
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
            
        if response_schema:
            payload["generationConfig"]["responseMimeType"] = "application/json"
            payload["generationConfig"]["responseSchema"] = response_schema
            
        # Execute post request to Google Agent API
        response = requests.post(self.endpoint_url, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        # Parse return payload structure
        return data["candidates"][0]["content"]["parts"][0]["text"]

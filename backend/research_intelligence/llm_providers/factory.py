from django.conf import settings
from .base import BaseLLMProvider
from .google import GoogleAgentAPIProvider
from .openrouter import OpenRouterAPIProvider

def get_llm_provider(provider_name: str) -> BaseLLMProvider:
    """
    Factory pattern method to return the configured LLM provider instance.
    Handles credential resolution from project settings.
    """
    normalized_name = (provider_name or "google").strip().lower()
    
    if normalized_name == "google":
        api_key = getattr(settings, "GOOGLE_AGENT_API_KEY", "mock-agent-key")
        return GoogleAgentAPIProvider(api_key=api_key)
    elif normalized_name == "openrouter":
        api_key = getattr(settings, "OPENROUTER_API_KEY", "mock-openrouter-key")
        return OpenRouterAPIProvider(api_key=api_key)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider_name}")

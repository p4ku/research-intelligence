import os
from django.conf import settings
from .base import BaseLLMProvider
from .google import GoogleAgentAPIProvider
from .openrouter import OpenRouterAPIProvider

def get_llm_provider(provider_name: str = None) -> BaseLLMProvider:
    """
    Factory pattern method to return the configured LLM provider instance.
    Directly initializes the requested provider ('google' or 'openrouter')
    using its own respective credentials without cross-fallback.
    """
    normalized_name = (provider_name or getattr(settings, "DEFAULT_LLM_PROVIDER", None) or "google").strip().lower()

    if normalized_name in ("google", "gemini", "vertex"):
        api_key = (
            getattr(settings, "GOOGLE_AGENT_API_KEY", None)
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or "mock-agent-key"
        )
        return GoogleAgentAPIProvider(api_key=api_key)
    elif normalized_name == "openrouter":
        api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or getattr(settings, "OPENROUTER_API_KEY", None)
            or "mock-openrouter-key"
        )
        default_model = (
            os.environ.get("OPENROUTER_DEFAULT_MODEL")
            or getattr(settings, "OPENROUTER_DEFAULT_MODEL", None)
            or "google/gemini-3.8-flash"
        )
        return OpenRouterAPIProvider(api_key=api_key, model_name=default_model)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider_name}")



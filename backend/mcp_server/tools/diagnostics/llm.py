import os
import json
import logging
from research_intelligence.llm_providers.google import GoogleAgentAPIProvider

logger = logging.getLogger(__name__)


def test_google_llm_logic(
    user,
    prompt: str | None = None,
    model: str | None = None,
    location: str | None = None
) -> str:
    """
    Test execution of Google GenAI / Vertex AI LLM model (e.g. gemini-3.8-flash) and verify API credentials & response generation.
    """
    test_prompt = prompt or "Hello! Please reply with 'Google LLM connectivity test successful' and state your active model name in 1 sentence."
    target_model = model or "gemini-3.8-flash"
    target_location = location or "eu"

    # Credentials diagnostics
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    google_key = os.environ.get("GOOGLE_API_KEY")
    agent_key = os.environ.get("GOOGLE_AGENT_API_KEY")

    creds_info = {
        "has_service_account_json": bool(sa_json),
        "has_gemini_api_key": bool(gemini_key),
        "has_google_api_key": bool(google_key),
        "has_agent_api_key": bool(agent_key),
        "service_account_email": None,
        "service_account_project": None
    }

    if sa_json:
        try:
            parsed_sa = json.loads(sa_json)
            creds_info["service_account_email"] = parsed_sa.get("client_email")
            creds_info["service_account_project"] = parsed_sa.get("project_id")
        except Exception as e:
            creds_info["sa_parse_error"] = str(e)

    try:
        provider = GoogleAgentAPIProvider(location=target_location)
        response = provider.generate(
            prompt=test_prompt,
            model=target_model,
            location=target_location
        )


        response_text = str(response)

        return json.dumps({
            "success": True,
            "message": "Google LLM connectivity test passed successfully.",
            "requested_model": target_model,
            "requested_location": target_location,
            "resolved_project_id": getattr(provider, "project_id", None),
            "resolved_location": getattr(provider, "location", None),
            "credentials_diagnostics": creds_info,
            "llm_response": response_text
        }, indent=2)

    except Exception as e:
        logger.exception(f"Error testing Google LLM: {str(e)}")
        return json.dumps({
            "success": False,
            "error": str(e),
            "requested_model": target_model,
            "requested_location": target_location,
            "credentials_diagnostics": creds_info
        }, indent=2)


def test_openrouter_llm_logic(
    user,
    prompt: str | None = None,
    model: str | None = None
) -> str:
    """
    Test execution of OpenRouter Gateway LLM model (e.g. google/gemini-3.8-flash) and verify API credentials & response generation.
    """
    test_prompt = prompt or "Hello! Please reply with 'OpenRouter LLM connectivity test successful' and state your active model name in 1 sentence."
    from research_intelligence.llm_providers.factory import get_llm_provider
    try:
        provider = get_llm_provider("openrouter")
        target_model = model or provider.model_name
        response = provider.generate(prompt=test_prompt, model=target_model)
        return json.dumps({
            "success": True,
            "message": "OpenRouter LLM connectivity test passed successfully.",
            "requested_model": target_model,
            "provider": "openrouter",
            "llm_response": str(response)
        }, indent=2)
    except Exception as e:
        logger.exception(f"Error testing OpenRouter LLM: {str(e)}")
        return json.dumps({
            "success": False,
            "error": str(e),
            "provider": "openrouter"
        }, indent=2)


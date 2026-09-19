from typing import Optional
from .arxiv import ArxivScraperProvider
from .openalex import OpenAlexScraperProvider
from .lens import LensScraperProvider
from .google_patents import GooglePatentsScraperProvider

def get_scraper_provider(provider_name: str, n_last_days: int = 7, api_key: Optional[str] = None, **kwargs):
    """
    Factory Method to resolve and instantiate a scraper provider.
    Supports optional provider-specific api_key and provider kwargs (workspace, workspace_id).
    Wisely resolves api_key from the Scraper model if not provided.
    """
    provider_name = provider_name.lower().strip()
    if not api_key:
        try:
            from research_intelligence.models import Scraper
            api_key = Scraper.resolve_api_key_for_provider(
                provider_name,
                workspace=kwargs.get("workspace"),
                workspace_id=kwargs.get("workspace_id"),
            )
        except Exception:
            pass

    if provider_name == 'arxiv':
        return ArxivScraperProvider(n_last_days=n_last_days)
    elif provider_name == 'openalex':
        return OpenAlexScraperProvider(n_last_days=n_last_days)
    elif provider_name == 'lens':
        return LensScraperProvider(n_last_days=n_last_days, api_key=api_key, **kwargs)
    elif provider_name in ('google_patents', 'google patents', 'google-patents', 'patents'):
        return GooglePatentsScraperProvider(n_last_days=n_last_days, api_key=api_key, **kwargs)
    else:
        raise ValueError(f"Unknown academic scraper provider: '{provider_name}'")

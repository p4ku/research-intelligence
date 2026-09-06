from .arxiv import ArxivScraperProvider
from .openalex import OpenAlexScraperProvider
from .lens import LensScraperProvider

def get_scraper_provider(provider_name: str, n_last_days: int = 7):
    """
    Factory Method to resolve and instantiate a scraper provider.
    """
    provider_name = provider_name.lower().strip()
    if provider_name == 'arxiv':
        return ArxivScraperProvider(n_last_days=n_last_days)
    elif provider_name == 'openalex':
        return OpenAlexScraperProvider(n_last_days=n_last_days)
    elif provider_name == 'lens':
        return LensScraperProvider(n_last_days=n_last_days)
    else:
        raise ValueError(f"Unknown academic scraper provider: '{provider_name}'")

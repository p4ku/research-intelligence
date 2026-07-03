from .arxiv import ArxivScraperProvider
from .openalex import OpenAlexScraperProvider
from .lens import LensScraperProvider

def get_scraper_provider(provider_name: str):
    """
    Factory Method to resolve and instantiate a scraper provider.
    """
    provider_name = provider_name.lower().strip()
    if provider_name == 'arxiv':
        return ArxivScraperProvider()
    elif provider_name == 'openalex':
        return OpenAlexScraperProvider()
    elif provider_name == 'lens':
        return LensScraperProvider()
    else:
        raise ValueError(f"Unknown academic scraper provider: '{provider_name}'")

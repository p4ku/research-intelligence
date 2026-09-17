from .base import BaseScraperProvider
from .factory import get_scraper_provider
from .google_patents import GooglePatentsScraperProvider

__all__ = ["BaseScraperProvider", "get_scraper_provider", "GooglePatentsScraperProvider"]

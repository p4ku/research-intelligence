import urllib.request
import urllib.parse
import json
import logging
from django.conf import settings
from .base import BaseScraperProvider

logger = logging.getLogger(__name__)

class LensScraperProvider(BaseScraperProvider):
    """
    Scraper provider implementing Lens.org scholarly API search and paper download.
    """

    def search(self, query: str, limit: int = 10, sort_by: str = "relevance", sort_order: str = "desc") -> list[dict]:
        api_key = getattr(settings, "LENS_API_KEY", None)
        if not api_key:
            logger.warning("LENS_API_KEY not configured in settings. Returning empty results.")
            return []
            
        url = "https://api.lens.org/scholarly/search"
        payload = {
            "query": {
                "query_string": {
                    "query": query
                }
            },
            "size": limit
        }
        if sort_by == "date":
            payload["sort"] = [{"date_published": sort_order}]
        
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                },
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                
            results = []
            for item in data.get("data", []):
                title = item.get("title") or "Unknown Title"
                abstract = item.get("abstract") or ""
                lens_id = item.get("lens_id") or ""
                hash_id = lens_id.replace('-', '_')
                
                authors_list = []
                for auth in item.get("authors", []):
                    author_name = auth.get("display_name")
                    if author_name:
                        authors_list.append(author_name)
                authors = ", ".join(authors_list)
                
                published = item.get("date_published") or ""
                
                pdf_url = ""
                for source in item.get("source_urls", []):
                    url_str = source.get("url")
                    if url_str and url_str.endswith(".pdf"):
                        pdf_url = url_str
                        break
                
                if not pdf_url:
                    external_links = item.get("external_ids", [])
                    for ext in external_links:
                        if ext.get("type") == "doi":
                            pdf_url = f"https://doi.org/{ext.get('value')}"
                            break
                            
                other_url = f"https://www.lens.org/lens/scholar/article/{lens_id}"
                
                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "hash_id": hash_id,
                    "pdf_url": pdf_url,
                    "other_url": other_url,
                    "source_database": "lens",
                    "published_date": published
                })
            return results
        except Exception as e:
            logger.exception(f"Error querying Lens.org API: {str(e)}")
            return []

    def download_file(self, url: str) -> bytes:
        if not url or not url.lower().startswith(('http://', 'https://')):
            raise ValueError(f"Invalid URL scheme for download: '{url}'")
        from ..utils.url_guard import is_safe_external_url
        if not is_safe_external_url(url):
            raise ValueError(f"Disallowed private/internal IP URL: '{url}'")
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read()
        except Exception as e:
            logger.exception(f"Error downloading file from {url}: {str(e)}")
            raise e

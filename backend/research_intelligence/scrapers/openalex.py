import urllib.request
import urllib.parse
import json
import logging
from .base import BaseScraperProvider

logger = logging.getLogger(__name__)

class OpenAlexScraperProvider(BaseScraperProvider):
    """
    Scraper provider implementing OpenAlex API search and paper download.
    """

    def search(self, query: str, limit: int = 10) -> list[dict]:
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.openalex.org/works?search={encoded_query}&per_page={limit}"
        
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64); mailto:agentic-scanner@example.com'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            results = []
            for item in data.get("results", []):
                title = item.get("title") or "Unknown Title"
                published = item.get("publication_date") or ""
                
                # Reconstruct abstract from inverted index
                abstract = ""
                inv_index = item.get("abstract_inverted_index")
                if isinstance(inv_index, dict):
                    word_positions = []
                    for word, positions in inv_index.items():
                        for pos in positions:
                            word_positions.append((pos, word))
                    word_positions.sort()
                    abstract = " ".join([word for _, word in word_positions])
                
                openalex_id = item.get("id") or ""
                hash_id = openalex_id.split('/')[-1] if '/' in openalex_id else openalex_id
                
                authors_list = []
                for auth in item.get("authorships", []):
                    author_name = auth.get("author", {}).get("display_name")
                    if author_name:
                        authors_list.append(author_name)
                authors = ", ".join(authors_list)
                
                pdf_url = ""
                best_oa = item.get("best_oa_location") or {}
                if best_oa:
                    pdf_url = best_oa.get("pdf_url") or ""
                
                if not pdf_url:
                    oa_info = item.get("open_access") or {}
                    pdf_url = oa_info.get("oa_url") or ""
                
                other_url = item.get("doi") or item.get("id") or ""
                
                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "hash_id": hash_id,
                    "pdf_url": pdf_url,
                    "other_url": other_url,
                    "source_database": "openalex",
                    "published_date": published
                })
            return results
        except Exception as e:
            logger.exception(f"Error querying OpenAlex API: {str(e)}")
            return []

    def download_file(self, url: str) -> bytes:
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

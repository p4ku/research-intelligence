import urllib.request
import urllib.parse
import json
import logging
from datetime import datetime
from .base import BaseScraperProvider

logger = logging.getLogger(__name__)

class OpenAlexScraperProvider(BaseScraperProvider):
    """
    Scraper provider implementing OpenAlex API search and paper download.
    """

    def search(
        self,
        query: str,
        limit: int = 10,
        sort_by: str = "relevance",
        sort_order: str = "desc",
        start_date: str | datetime | None = None,
        end_date: str | datetime | None = None,
        n_last_days: int | None = None,
    ) -> list[dict]:
        effective_limit = int(limit or 10)
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.openalex.org/works?search={encoded_query}&per_page={effective_limit}"
        if sort_by == "date":
            url += f"&sort=publication_date:{sort_order}"
        
        start_dt, end_dt = self.resolve_date_range(start_date, end_date, n_last_days)
        from_date, to_date = self.format_iso_date_range(start_dt, end_dt)
        date_filter = f"from_publication_date:{from_date},to_publication_date:{to_date}"
        if "from_publication_date" not in query and "from_publication_date" not in url:
            if "filter=" in url:
                url += f",{date_filter}"
            else:
                url += f"&filter={date_filter}"
        
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
                
                raw_doi = (item.get("doi") or "").strip()
                if raw_doi.lower().startswith(("https://doi.org/", "http://doi.org/")):
                    source_url = raw_doi
                elif raw_doi:
                    clean_doi = raw_doi
                    for prefix in ("doi.org/", "doi:"):
                        if clean_doi.lower().startswith(prefix):
                            clean_doi = clean_doi[len(prefix):]
                    source_url = f"https://doi.org/{clean_doi}"
                else:
                    prim_loc = item.get("primary_location") or {}
                    source_url = prim_loc.get("landing_page_url") or item.get("id") or (f"https://openalex.org/{hash_id}" if hash_id.startswith("W") else "")

                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "hash_id": hash_id,
                    "pdf_url": pdf_url,
                    "other_url": other_url,
                    "source_url": source_url,
                    "source_database": "openalex",
                    "published_date": published,
                    "meta": item
                })
            return results
        except Exception as e:
            logger.exception(f"Error querying OpenAlex API: {str(e)}")
            return []

    def download_file(self, url: str) -> bytes:
        if not url or not url.lower().startswith(('http://', 'https://')):
            raise ValueError(f"Invalid URL scheme for download: '{url}'")
        from ..utils.url_guard import is_safe_external_url, safe_download_url
        if not is_safe_external_url(url):
            raise ValueError(f"Disallowed private/internal IP URL: '{url}'")
        try:
            return safe_download_url(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
                max_bytes=100 * 1024 * 1024,
                timeout=15.0
            )
        except Exception as e:
            logger.exception(f"Error downloading file from {url}: {str(e)}")
            raise e

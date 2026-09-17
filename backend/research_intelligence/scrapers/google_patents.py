import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any, Dict, List, Optional, Tuple, Union
from django.conf import settings

from .base import BaseScraperProvider
from ..utils.url_guard import is_safe_external_url, safe_download_url

logger = logging.getLogger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
SERPAPI_DOCS_URL = "https://serpapi.com/google-patents-api"
USER_AGENT = "SchwarzResearchIntelligencePatentRetriever/1.0 (+https://serpapi.com/google-patents-api)"
MAX_SERPAPI_PAGES = 100


def clean_text(value: Any) -> str:
    """Turn Google Patents snippets/titles into readable plain text."""
    if not isinstance(value, str):
        return ""
    text = unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def patent_country(patent_id: str, publication_number: str) -> Optional[str]:
    for value in (publication_number, patent_id):
        if value:
            match = re.search(r"(?:^|/)([A-Z]{2})(?:[-_]?(?=\d))", value.upper())
            if match:
                return match.group(1)
    return None


def canonical_patent_id(raw: Dict[str, Any], position: int = 0) -> str:
    for field in ("publication_number", "patent_id", "patent_link"):
        val = clean_text(raw.get(field))
        if val:
            # normalize punctuation/dashes e.g. US-11234567-B2 -> US11234567B2 or clean slug
            return re.sub(r"[^A-Za-z0-9]+", "", val).upper() or val
    raw_title = clean_text(raw.get("title", ""))
    return f"patent_{position}_{raw_title[:30]}"


class GooglePatentsScraperProvider(BaseScraperProvider):
    """
    Scraper provider implementing Google Patents retrieval via SerpApi.
    Retrieves patent listings, bibliographic metadata, dates, and direct PDF links.
    """

    def __init__(self, n_last_days: int = 7, api_key: Optional[str] = None):
        super().__init__(n_last_days=n_last_days)
        self.api_key = (
            api_key
            or getattr(settings, "SERPAPI_API_KEY", "")
            or os.environ.get("SERPAPI_API_KEY", "")
        )

    def _request_json(self, params: Dict[str, str], timeout: int = 30) -> Dict[str, Any]:
        """Calls SerpApi with retries for transient HTTP failures."""
        url = f"{SERPAPI_ENDPOINT}?{urllib.parse.urlencode(params)}"
        last_error = None
        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("SerpApi returned a non-object JSON response.")
                return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                    try:
                        detail = exc.read().decode("utf-8", errors="replace")[:500]
                    except Exception:
                        detail = ""
                    raise RuntimeError(f"SerpApi HTTP {exc.code}: {detail or exc.reason}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == 3:
                    raise RuntimeError(f"SerpApi request failed: {exc}") from exc
            time.sleep(2 ** (attempt - 1))
        raise RuntimeError(f"SerpApi request failed after 3 attempts: {last_error}")

    def search(
        self,
        query: str,
        limit: int = 10,
        sort_by: str = "relevance",
        sort_order: str = "desc",
        start_date: Optional[Union[str, date, datetime]] = None,
        end_date: Optional[Union[str, date, datetime]] = None,
        n_last_days: Optional[int] = None,
        date_type: str = "publication",
        **kwargs,
    ) -> List[Dict[str, Any]]:
        effective_key = (
            kwargs.get("api_key")
            or self.api_key
            or getattr(settings, "SERPAPI_API_KEY", "")
            or os.environ.get("SERPAPI_API_KEY", "")
        )
        if not effective_key:
            logger.warning("SERPAPI_API_KEY is not configured. Google Patents search returning empty results.")
            return []

        start_dt, end_dt = self.resolve_date_range(start_date, end_date, n_last_days)
        target_limit = int(limit) if limit else 10
        page_size = min(max(10, target_limit), 100)

        # SerpApi after/before syntax: publication:YYYYMMDD
        after_val = f"{date_type}:{start_dt.strftime('%Y%m%d')}"
        before_val = f"{date_type}:{end_dt.strftime('%Y%m%d')}"

        params: Dict[str, str] = {
            "engine": "google_patents",
            "q": query,
            "after": after_val,
            "before": before_val,
            "sort": "new" if sort_by == "date" else "relevance",
            "dups": "language",
            "patents": "true",
            "scholar": "false",
            "num": str(page_size),
            "api_key": effective_key,
        }

        results: List[Dict[str, Any]] = []
        pages_fetched = 0
        seen_keys = set()

        while pages_fetched < MAX_SERPAPI_PAGES and len(results) < target_limit:
            try:
                payload = self._request_json(params)
            except Exception as exc:
                logger.error(f"Error querying SerpApi Google Patents API: {exc}")
                break

            pages_fetched += 1
            organic_results = payload.get("organic_results", [])
            if not organic_results:
                break

            for raw in organic_results:
                if not isinstance(raw, dict):
                    continue

                title = clean_text(raw.get("title"))
                if not title:
                    title = clean_text(raw.get("patent_id")) or "Untitled Patent"

                patent_id = clean_text(raw.get("patent_id"))
                pub_num = clean_text(raw.get("publication_number"))
                hash_id = canonical_patent_id(raw, len(results) + 1)

                if hash_id.lower() in seen_keys:
                    continue
                seen_keys.add(hash_id.lower())

                patent_link = clean_text(raw.get("patent_link"))
                pdf_url = clean_text(raw.get("pdf"))
                snippet = clean_text(raw.get("snippet"))

                inventor = clean_text(raw.get("inventor"))
                assignee = clean_text(raw.get("assignee"))
                authors = inventor if inventor else assignee
                if inventor and assignee and assignee.lower() not in inventor.lower():
                    authors = f"{inventor} (Assignee: {assignee})"

                pub_date = (
                    clean_text(raw.get("publication_date"))
                    or clean_text(raw.get("filing_date"))
                    or clean_text(raw.get("priority_date"))
                    or ""
                )

                meta = {
                    "patent_id": patent_id,
                    "publication_number": pub_num,
                    "patent_link": patent_link,
                    "serpapi_details_link": clean_text(raw.get("serpapi_link")),
                    "priority_date": clean_text(raw.get("priority_date")),
                    "filing_date": clean_text(raw.get("filing_date")),
                    "grant_date": clean_text(raw.get("grant_date")),
                    "publication_date": clean_text(raw.get("publication_date")),
                    "inventor": inventor,
                    "assignee": assignee,
                    "language": clean_text(raw.get("language")),
                    "country": patent_country(patent_id, pub_num),
                    "country_status": raw.get("country_status") if isinstance(raw.get("country_status"), dict) else {},
                    "figures": raw.get("figures") if isinstance(raw.get("figures"), list) else [],
                    "thumbnail": clean_text(raw.get("thumbnail")),
                    "source": "SerpApi Google Patents API",
                }

                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": snippet,
                    "hash_id": hash_id,
                    "pdf_url": pdf_url,
                    "other_url": patent_link,
                    "source_url": patent_link or pdf_url,
                    "source_database": "google_patents",
                    "published_date": pub_date,
                    "meta": meta,
                })

                if len(results) >= target_limit:
                    break

            next_url = payload.get("serpapi_pagination", {}).get("next")
            if not next_url or not isinstance(next_url, str):
                break

            # Parse next cursor URL
            parsed_next = urllib.parse.urlparse(next_url)
            next_params = dict(urllib.parse.parse_qsl(parsed_next.query, keep_blank_values=True))
            next_params["api_key"] = effective_key
            next_params.setdefault("engine", "google_patents")
            params = next_params

        return results

    def download_file(self, url: str) -> bytes:
        """Downloads patent PDF binary safely with size limits and SSRF guard."""
        if not url or not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme for download: '{url}'")
        if not is_safe_external_url(url):
            raise ValueError(f"Disallowed private/internal IP URL: '{url}'")
        try:
            return safe_download_url(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
                },
                max_bytes=100 * 1024 * 1024,
                timeout=30.0,
            )
        except Exception as e:
            logger.exception(f"Error downloading patent document from {url}: {e}")
            raise e

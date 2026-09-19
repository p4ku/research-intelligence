import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any, Dict, List, Optional, Tuple, Union
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
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


@dataclass
class GooglePatentData:
    publication_number: str = ""
    country: str = ""
    country_code: str = ""
    title: str = ""
    pdf_url: Optional[str] = None
    has_pdf: bool = False
    current_assignee: Optional[str] = None
    inventors: List[str] = field(default_factory=list)
    other_languages: List[Dict[str, str]] = field(default_factory=list)
    status: str = ""
    application_number: str = ""
    priority_date: str = ""
    filing_date: str = ""
    publication_date: str = ""
    grant_date: str = ""
    anticipated_expiration: str = ""
    events: List[Dict[str, str]] = field(default_factory=list)
    abstract: str = ""
    claims: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "publication_number": self.publication_number,
            "country": self.country,
            "country_code": self.country_code,
            "title": self.title,
            "pdf_url": self.pdf_url,
            "has_pdf": self.has_pdf,
            "current_assignee": self.current_assignee,
            "inventors": self.inventors,
            "other_languages": self.other_languages,
            "status": self.status,
            "application_number": self.application_number,
            "priority_date": self.priority_date,
            "filing_date": self.filing_date,
            "publication_date": self.publication_date,
            "grant_date": self.grant_date,
            "anticipated_expiration": self.anticipated_expiration,
            "events": self.events,
            "claims_count": len(self.claims),
            "abstract_length": len(self.abstract),
            "description_length": len(self.description),
        }

    def to_markdown(self) -> str:
        lines: List[str] = []
        heading = f"# {self.publication_number}"
        if self.title:
            heading += f": {self.title}"
        lines.append(heading)
        lines.append("")

        if self.current_assignee:
            lines.append(f"**Current Assignee:** {self.current_assignee}")
        if self.inventors:
            lines.append(f"**Inventors:** {', '.join(self.inventors)}")

        meta_parts: List[str] = []
        if self.country or self.country_code:
            meta_parts.append(f"**Country/Jurisdiction:** {self.country or self.country_code}")
        if self.status:
            meta_parts.append(f"**Status:** {self.status}")
        if self.application_number:
            meta_parts.append(f"**Application:** {self.application_number}")
        if meta_parts:
            lines.append(" | ".join(meta_parts))

        dates_parts: List[str] = []
        if self.filing_date:
            dates_parts.append(f"**Filing Date:** {self.filing_date}")
        if self.publication_date:
            dates_parts.append(f"**Publication Date:** {self.publication_date}")
        if self.priority_date:
            dates_parts.append(f"**Priority Date:** {self.priority_date}")
        if self.grant_date:
            dates_parts.append(f"**Grant Date:** {self.grant_date}")
        if self.anticipated_expiration:
            dates_parts.append(f"**Anticipated Expiration:** {self.anticipated_expiration}")
        if dates_parts:
            lines.append(" | ".join(dates_parts))

        if self.events:
            lines.append("")
            lines.append("## Timeline Events")
            for ev in self.events:
                d = ev.get("date", "")
                t = ev.get("title", "")
                tp = ev.get("type", "")
                if tp:
                    lines.append(f"- **{d}**: {t} (*{tp}*)" if d else f"- {t} (*{tp}*)")
                else:
                    lines.append(f"- **{d}**: {t}" if d else f"- {t}")

        if self.abstract:
            lines.append("")
            lines.append("## Abstract")
            lines.append(self.abstract)

        if self.claims:
            lines.append("")
            lines.append("## Claims")
            for claim in self.claims:
                lines.append(claim)
                lines.append("")

        if self.description:
            lines.append("")
            lines.append("## Detailed Description")
            lines.append(self.description)

        return "\n".join(lines).strip()


class GooglePatentPageParser:
    """
    Parser for Google Patents HTML pages (patents.google.com).
    Extracts direct PDF URLs, bibliographic data, inventors, current assignee,
    timeline events, abstract, claims, and detailed description using Schema.org
    microdata and Dublin Core metadata tags.
    """

    @classmethod
    def parse(cls, html: str, source_url: str = "") -> GooglePatentData:
        if BeautifulSoup is None:
            logger.warning("beautifulsoup4 is not installed in the current environment; falling back to regex extraction.")
            pdf_url = None
            match = re.search(r'href=["\'](https://patentimages\.storage\.googleapis\.com/[^"\']+\.pdf)["\']', html or "", re.IGNORECASE)
            if match:
                pdf_url = match.group(1).strip()
            return GooglePatentData(
                pdf_url=pdf_url,
                raw_html=html or "",
            )

        soup = BeautifulSoup(html, "html.parser")

        # 1. PDF URL
        pdf_url = None
        citation_meta = soup.find("meta", {"name": "citation_pdf_url"})
        if citation_meta and citation_meta.get("content"):
            pdf_url = citation_meta["content"].strip()
        if not pdf_url:
            link_el = soup.find("a", {"itemprop": "pdfLink"})
            if link_el and link_el.get("href"):
                pdf_url = link_el["href"].strip()
        if not pdf_url:
            match = re.search(r'href=["\'](https://patentimages\.storage\.googleapis\.com/[^"\']+\.pdf)["\']', html, re.IGNORECASE)
            if match:
                pdf_url = match.group(1).strip()

        # 2. Publication Number
        pub_el = soup.find(["dd", "span"], {"itemprop": "publicationNumber"})
        pub_num = clean_text(pub_el.get_text()) if pub_el else ""
        if not pub_num and source_url:
            m = re.search(r"/patent/([A-Z0-9]+)", source_url)
            pub_num = m.group(1) if m else ""

        # 3. Country / Office
        country_name_el = soup.find(["dd", "span"], {"itemprop": "countryName"})
        country_name = clean_text(country_name_el.get_text()) if country_name_el else ""
        country_code_el = soup.find(["dd", "span"], {"itemprop": "countryCode"})
        country_code = clean_text(country_code_el.get_text()) if country_code_el else ""
        if not country_code and pub_num:
            m_c = re.match(r"^([A-Z]{2})", pub_num)
            if m_c:
                country_code = m_c.group(1)

        # 4. Title
        title_el = soup.find(["span", "h1"], {"itemprop": "title"})
        if not title_el:
            title_el = soup.find("meta", {"name": "DC.title"})
            title = clean_text(title_el.get("content")) if title_el else ""
        else:
            title = clean_text(title_el.get_text())

        # 5. Status
        status_el = soup.find(["dd", "span"], {"itemprop": "legalStatusIfi"})
        status = clean_text(status_el.get_text()) if status_el else ""
        if not status:
            stat_span = soup.find("span", {"itemprop": "status"})
            status = clean_text(stat_span.get_text()) if stat_span else ""

        # 6. Current Assignee (Specifically assigneeCurrent to avoid pulling similar/cited assignees)
        curr_assignee_el = soup.find(["dd", "span"], {"itemprop": "assigneeCurrent"})
        current_assignee = clean_text(curr_assignee_el.get_text()) if curr_assignee_el else ""
        if not current_assignee:
            meta_assignee = soup.find("meta", {"scheme": "assignee"})
            if meta_assignee and meta_assignee.get("content"):
                current_assignee = clean_text(meta_assignee.get("content"))

        # 7. Inventors
        inventors = [clean_text(el.get_text()) for el in soup.find_all(["dd", "span"], {"itemprop": "inventor"}) if clean_text(el.get_text())]
        if not inventors:
            inventors = [clean_text(el.get("content")) for el in soup.find_all("meta", {"scheme": "inventor"}) if clean_text(el.get("content"))]
        inventors = list(dict.fromkeys(inventors))

        # 8. Other Languages
        other_languages: List[Dict[str, str]] = []
        for dd in soup.find_all(["dd", "span"], {"itemprop": "otherLanguages"}):
            for a in dd.find_all("a"):
                lang_name = clean_text(a.get_text())
                href = a.get("href", "")
                if lang_name:
                    full_href = f"https://patents.google.com{href}" if href.startswith("/") else href
                    other_languages.append({"language": lang_name, "url": full_href})

        # 9. Dates and Application Number
        app_el = soup.find(["dd", "span"], {"itemprop": "applicationNumber"})
        app_num = clean_text(app_el.get_text()) if app_el else ""

        priority_el = soup.find(["time", "dd"], {"itemprop": "priorityDate"})
        priority_date = clean_text(priority_el.get("datetime") or priority_el.get_text()) if priority_el else ""

        filing_el = soup.find(["time", "dd"], {"itemprop": "filingDate"})
        filing_date = clean_text(filing_el.get("datetime") or filing_el.get_text()) if filing_el else ""

        pub_date_el = soup.find(["time", "dd"], {"itemprop": "publicationDate"})
        pub_date = clean_text(pub_date_el.get("datetime") or pub_date_el.get_text()) if pub_date_el else ""

        grant_date_el = soup.find(["time", "dd"], {"itemprop": "grantDate"})
        grant_date = clean_text(grant_date_el.get("datetime") or grant_date_el.get_text()) if grant_date_el else ""

        # 10. Timeline Events
        events: List[Dict[str, str]] = []
        anticipated_expiration = ""
        for ev in soup.find_all(["dd", "div", "tr"], {"itemprop": "events"}):
            d_el = ev.find(itemprop="date")
            t_el = ev.find(itemprop="title")
            tp_el = ev.find(itemprop="type")
            date_str = clean_text(d_el.get("datetime") or d_el.get_text()) if d_el else ""
            title_str = clean_text(t_el.get_text()) if t_el else ""
            type_str = clean_text(tp_el.get_text()) if tp_el else ""
            if "anticipated expiration" in title_str.lower():
                anticipated_expiration = date_str
            if date_str or title_str:
                events.append({"date": date_str, "type": type_str, "title": title_str})

        # 11. Abstract (ignore non-translated raw source spans if translation exists)
        abs_sec = soup.find(["section", "div"], {"itemprop": "abstract"})
        abstract_text = ""
        if abs_sec:
            p_els = [p for p in abs_sec.find_all("p") if "google-src-text" not in [c for parent in p.parents for c in parent.get("class", [])]]
            if p_els:
                abstract_text = "\n\n".join(clean_text(p.get_text()) for p in p_els if clean_text(p.get_text()))
            if not abstract_text:
                content_div = abs_sec.find("div", {"itemprop": "content"}) or abs_sec
                abstract_text = clean_text(content_div.get_text())

        # 12. Claims
        claims_sec = soup.find(["section", "div"], {"itemprop": "claims"})
        claims: List[str] = []
        if claims_sec:
            content_div = claims_sec.find("div", {"itemprop": "content"}) or claims_sec
            for c in content_div.find_all(["div", "dd", "p"], class_=lambda x: x and "claim" in x):
                num = c.get("num") or ""
                txt = clean_text(c.get_text())
                if txt:
                    claims.append(f"{num}. {txt}" if num and not txt.startswith(num) else txt)
            if not claims:
                raw_claims = content_div.get_text(separator="\n", strip=True)
                if raw_claims:
                    claims = [clean_text(l) for l in raw_claims.split("\n") if clean_text(l)]

        # 13. Detailed Description
        desc_sec = soup.find(["section", "div"], {"itemprop": "description"})
        description_text = ""
        if desc_sec:
            content_div = desc_sec.find("div", {"itemprop": "content"}) or desc_sec
            description_text = content_div.get_text(separator="\n\n", strip=True)

        return GooglePatentData(
            publication_number=pub_num,
            country=country_name or country_code,
            country_code=country_code,
            title=title,
            pdf_url=pdf_url,
            has_pdf=bool(pdf_url),
            current_assignee=current_assignee,
            inventors=inventors,
            other_languages=other_languages,
            status=status,
            application_number=app_num,
            priority_date=priority_date,
            filing_date=filing_date,
            publication_date=pub_date,
            grant_date=grant_date,
            anticipated_expiration=anticipated_expiration,
            events=events,
            abstract=abstract_text,
            claims=claims,
            description=description_text,
        )

    @classmethod
    def fetch_and_parse(cls, url: str, timeout: float = 20.0) -> GooglePatentData:
        if not is_safe_external_url(url):
            raise ValueError(f"Disallowed private/internal IP URL: '{url}'")
        page_bytes = safe_download_url(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"},
            max_bytes=10 * 1024 * 1024,
            timeout=timeout,
        )
        html_text = page_bytes.decode("utf-8", errors="replace")
        return cls.parse(html_text, source_url=url)


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

    def __init__(
        self,
        n_last_days: int = 7,
        api_key: Optional[str] = None,
        workspace: Optional[Any] = None,
        workspace_id: Optional[Union[str, Any]] = None,
        **kwargs,
    ):
        super().__init__(n_last_days=n_last_days)
        self.workspace = workspace
        self.workspace_id = workspace_id or (getattr(workspace, "id", None) if workspace else None)
        self.api_key = self._resolve_api_key(
            explicit_key=api_key,
            workspace=self.workspace,
            workspace_id=self.workspace_id,
        )

    @classmethod
    def _resolve_api_key(
        cls,
        explicit_key: Optional[str] = None,
        instance_key: Optional[str] = None,
        workspace: Optional[Any] = None,
        workspace_id: Optional[Union[str, Any]] = None,
    ) -> str:
        """
        Resolves SERPAPI_API_KEY with cascading priority:
        1. Explicitly passed key (method argument or kwargs)
        2. Instance key (set during __init__)
        3. django.conf.settings.SERPAPI_API_KEY
        4. os.environ["SERPAPI_API_KEY"]
        5. Active Scraper model instance in database (filtered by workspace if available, or globally)
        """
        if explicit_key and str(explicit_key).strip():
            return str(explicit_key).strip()
        if instance_key and str(instance_key).strip():
            return str(instance_key).strip()

        settings_key = getattr(settings, "SERPAPI_API_KEY", "")
        if settings_key and str(settings_key).strip():
            return str(settings_key).strip()

        env_key = os.environ.get("SERPAPI_API_KEY", "")
        if env_key and str(env_key).strip():
            return str(env_key).strip()

        # Fallback: Query database Scraper model
        try:
            from research_intelligence.models import Scraper
            model_key = Scraper.resolve_api_key_for_provider(
                "google_patents",
                workspace=workspace,
                workspace_id=workspace_id,
            )
            if model_key:
                return model_key
        except Exception as exc:
            logger.debug(f"Could not query Scraper model for SERPAPI_API_KEY: {exc}")

        return ""

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
        target_ws = kwargs.get("workspace") or self.workspace
        target_ws_id = kwargs.get("workspace_id") or self.workspace_id
        effective_key = self._resolve_api_key(
            explicit_key=kwargs.get("api_key"),
            instance_key=self.api_key,
            workspace=target_ws,
            workspace_id=target_ws_id,
        )
        if not effective_key:
            logger.warning(
                "SERPAPI_API_KEY is not configured in settings, environment, or Scraper model. "
                "Google Patents search returning empty results."
            )
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
            "dups": "language",
            "patents": "true",
            "scholar": "false",
            "num": str(page_size),
            "api_key": effective_key,
        }

        # SerpApi Google Patents only supports 'new' or 'old' for sort.
        # Relevance sort is Google Patents default and must NOT be explicitly passed as 'relevance'.
        if sort_by in ("date", "new", "old"):
            params["sort"] = "old" if (sort_order == "asc" or sort_by == "old") else "new"

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
                # Prefer direct PDF URL; fall back to patent landing page if direct PDF is omitted
                document_url = pdf_url or patent_link
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
                    "pdf_url": pdf_url,
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
                    "pdf_url": document_url,
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
        """Downloads patent document safely with size limits and SSRF guard.
        If URL points to a Google Patents landing page (e.g. patents.google.com/patent):
          - Parses page metadata using GooglePatentPageParser.
          - If a direct PDF URL exists on Google Storage, downloads and returns the PDF binary.
          - If no PDF scan exists (e.g. US20260098257A1), returns the complete patent text
            rendered as structured Markdown (.md) encoded in UTF-8 bytes.
        If URL is already a direct PDF URL:
          - Downloads the PDF binary.
        """
        if not url or not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme for download: '{url}'")
        if not is_safe_external_url(url):
            raise ValueError(f"Disallowed private/internal IP URL: '{url}'")

        target_url = url
        # If the URL is a landing page rather than a direct PDF, parse the page
        if "patents.google.com/patent" in target_url and not target_url.lower().endswith(".pdf"):
            try:
                patent_data = GooglePatentPageParser.fetch_and_parse(target_url, timeout=20.0)
                if patent_data.pdf_url and is_safe_external_url(patent_data.pdf_url):
                    target_url = patent_data.pdf_url
                else:
                    # Patent has no scanned PDF; return full-text Markdown for downstream screening
                    logger.info(f"Patent at {target_url} has no PDF scan. Returning structured Markdown document.")
                    return patent_data.to_markdown().encode("utf-8")
            except Exception as e:
                logger.warning(f"Could not parse patent landing page {target_url}: {e}")

        try:
            return safe_download_url(
                target_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
                },
                max_bytes=100 * 1024 * 1024,
                timeout=30.0,
            )
        except Exception as e:
            logger.exception(f"Error downloading patent document from {target_url}: {e}")
            raise e

    def fetch_patent_document(self, url: str) -> Tuple[bytes, str, Dict[str, Any]]:
        """
        Retrieves patent document content and its full parsed metadata dictionary.
        Returns:
            Tuple[bytes, str, Dict[str, Any]]: (content_bytes, format, metadata_dict)
            where format is 'pdf' or 'markdown'.
        """
        if not url or not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme: '{url}'")
        if not is_safe_external_url(url):
            raise ValueError(f"Disallowed private/internal IP URL: '{url}'")

        if "patents.google.com/patent" in url and not url.lower().endswith(".pdf"):
            patent_data = GooglePatentPageParser.fetch_and_parse(url, timeout=20.0)
            meta_dict = patent_data.to_dict()
            if patent_data.pdf_url and is_safe_external_url(patent_data.pdf_url):
                pdf_bytes = safe_download_url(
                    patent_data.pdf_url,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"},
                    max_bytes=100 * 1024 * 1024,
                    timeout=30.0,
                )
                return pdf_bytes, "pdf", meta_dict
            else:
                md_bytes = patent_data.to_markdown().encode("utf-8")
                return md_bytes, "markdown", meta_dict

        # Direct PDF or URL
        file_bytes = self.download_file(url)
        is_pdf = file_bytes.startswith(b"%PDF-")
        return file_bytes, "pdf" if is_pdf else "binary", {}


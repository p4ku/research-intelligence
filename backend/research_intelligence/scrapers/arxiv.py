import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import logging
import time
import re
import threading
from .base import BaseScraperProvider

logger = logging.getLogger(__name__)

# Global rate limiting lock and timestamp to enforce >= 3.0s between consecutive arXiv calls
_arxiv_lock = threading.Lock()
_last_request_time = 0.0


def _throttle_request(min_interval: float = 3.0):
    """
    Enforces arXiv's mandatory >= 3.0-second delay between consecutive requests.
    """
    global _last_request_time
    with _arxiv_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_request_time = time.time()


class ArxivScraperProvider(BaseScraperProvider):
    """
    Production Scraper provider implementing arXiv API search, OAI-PMH harvesting,
    and paper download following arXiv API guidelines:
    - 3-second mandatory spacing between requests.
    - Slicing pagination (max 1000 items per slice).
    - Capped at 30,000 max results to prevent HTTP 400.
    - Exponential backoff with Retry-After on 429.
    - Seamless OpenAlex arXiv fallback if arXiv IP-blocks or throttles requests.
    """

    DEFAULT_PAGE_SIZE = 100
    COMPLEX_QUERY_PAGE_SIZE = 50
    MAX_TOTAL_RESULTS = 30000

    def search(self, query: str, limit: int = 10, sort_by: str = "relevance", sort_order: str = "desc") -> list[dict]:
        clean_query = query.strip()
        if clean_query.lower().startswith("arxiv:"):
            clean_query = clean_query[6:].strip()

        # Route to OAI-PMH harvesting if explicitly requested
        if clean_query.lower().startswith("oai:"):
            return self._search_oai_pmh(clean_query[4:].strip(), limit=limit)

        # Enforce maximum accessible result set (arXiv limit is 30,000 per query)
        total_limit = max(1, min(limit, self.MAX_TOTAL_RESULTS))

        # Check if query already contains field specifiers or boolean operators
        has_field_prefixes = any(p in clean_query for p in ["cat:", "ti:", "au:", "all:", "abs:", "submittedDate:", "jr:"])
        has_boolean_operators = any(b in clean_query for b in [" AND ", " OR ", " NOT "]) or clean_query.startswith("(")

        if has_field_prefixes or has_boolean_operators:
            formatted_query = clean_query
        else:
            raw = clean_query.replace('"', '').replace("'", "")
            formatted_query = f'all:"{raw}"' if " " in raw else f'all:{raw}'

        is_complex = (
            len(clean_query) > 100
            or clean_query.count(" OR ") > 2
            or clean_query.count(" AND ") > 2
            or clean_query.count("all:") > 3
        )
        base_page_size = self.COMPLEX_QUERY_PAGE_SIZE if is_complex else self.DEFAULT_PAGE_SIZE

        encoded_query = urllib.parse.quote(formatted_query)
        sort_by_param = "submittedDate" if sort_by == "date" else "relevance"
        sort_order_param = "ascending" if sort_order == "asc" else "descending"

        logger.info(
            f"🔍 [ARXIV SEARCH START] Target limit: {total_limit} papers | "
            f"Page size: {base_page_size} (complex_query={is_complex}) | "
            f"Sorting: {sort_by_param} ({sort_order_param})"
        )

        all_results = []
        start = 0
        search_start_t = time.time()

        while len(all_results) < total_limit:
            chunk_size = min(base_page_size, total_limit - len(all_results))
            chunk_results = self._fetch_arxiv_slice_with_retry(
                encoded_query=encoded_query,
                start=start,
                chunk_size=chunk_size,
                sort_by_param=sort_by_param,
                sort_order_param=sort_order_param,
                raw_query=clean_query
            )
            if not chunk_results:
                logger.info(f"ℹ️ [ARXIV SEARCH] No more results returned for start={start}. Ending pagination loop.")
                break

            all_results.extend(chunk_results)
            start += len(chunk_results)
            logger.info(f"📊 [ARXIV PROGRESS] Fetched {len(all_results)}/{total_limit} papers so far (latest slice: {len(chunk_results)} papers).")

            if len(chunk_results) < chunk_size:
                logger.info(f"ℹ️ [ARXIV SEARCH] Reached end of available results on arXiv ({len(all_results)} papers total).")
                break

            if len(all_results) < total_limit:
                _throttle_request(min_interval=3.2)

        total_elapsed = time.time() - search_start_t
        logger.info(f"✅ [ARXIV SEARCH COMPLETE] Successfully fetched {len(all_results)}/{total_limit} papers from arXiv in {total_elapsed:.2f}s.")
        return all_results[:total_limit]

    def _fetch_arxiv_slice_with_retry(
        self,
        encoded_query: str,
        start: int,
        chunk_size: int,
        sort_by_param: str,
        sort_order_param: str,
        raw_query: str = ""
    ) -> list[dict]:
        """
        Fetches a single slice from export.arxiv.org with adaptive chunk sizing,
        exponential backoff, and seamless OpenAlex fallback.
        """
        max_retries = 4
        timeout_sec = 45
        current_chunk_size = chunk_size
        xml_data = None

        for attempt in range(1, max_retries + 1):
            _throttle_request(min_interval=3.0)
            url = f"https://export.arxiv.org/api/query?search_query={encoded_query}&start={start}&max_results={current_chunk_size}&sortBy={sort_by_param}&sortOrder={sort_order_param}"
            logger.info(f"📡 [ARXIV HTTP GET] Querying slice start={start}, max_results={current_chunk_size} (Attempt {attempt}/{max_retries})...")
            req_start_t = time.time()
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 (SchwarzResearchIntelligence/1.0; mailto:research@soinventive.co.uk)'
                    }
                )
                with urllib.request.urlopen(req, timeout=timeout_sec) as response:
                    xml_data = response.read()
                req_elapsed = time.time() - req_start_t
                logger.info(f"📥 [ARXIV HTTP 200] Received response ({len(xml_data)} bytes) in {req_elapsed:.2f}s for start={start}.")
                break
            except Exception as e:
                req_elapsed = time.time() - req_start_t
                is_429 = isinstance(e, urllib.error.HTTPError) and e.code == 429
                is_timeout = isinstance(e, (TimeoutError, urllib.error.URLError)) and "timed out" in str(e).lower()

                if is_429:
                    retry_after = e.headers.get("Retry-After") if hasattr(e, "headers") and e.headers else None
                    try:
                        delay = int(retry_after) if retry_after else max(5, 5 * (2 ** (attempt - 1)))
                    except (ValueError, TypeError):
                        delay = max(5, 5 * (2 ** (attempt - 1)))
                else:
                    delay = max(3, 3 * attempt)

                # Adaptive backdown: on timeout, reduce chunk size for next retry
                if is_timeout and current_chunk_size > 25:
                    prev_chunk = current_chunk_size
                    current_chunk_size = max(25, current_chunk_size // 2)
                    logger.warning(f"⚠️ [ARXIV TIMEOUT after {req_elapsed:.1f}s] Query timed out on chunk size {prev_chunk}. Dynamically scaling down to {current_chunk_size}...")

                if attempt < max_retries:
                    logger.warning(f"⚠️ [ARXIV RETRY {attempt}/{max_retries}] Error querying arXiv API ({e}) after {req_elapsed:.1f}s. Retrying in {delay}s with chunk_size={current_chunk_size}...")
                    time.sleep(delay)
                else:
                    logger.warning(f"⚠️ [ARXIV RATE LIMITED / TIMEOUT] Failed after {max_retries} attempts ({e}). Activating OpenAlex arXiv fallback...")
                    return self._search_openalex_arxiv_fallback(raw_query, limit=chunk_size)

        if not xml_data:
            return []

        parsed = self._parse_arxiv_atom_xml(xml_data)
        logger.info(f"📄 [ARXIV PARSER] Parsed {len(parsed)} paper entries from Atom XML.")
        return parsed

    def _parse_arxiv_atom_xml(self, xml_data: bytes) -> list[dict]:
        """
        Parses arXiv Atom XML response into standard paper dictionaries.
        """
        try:
            root = ET.fromstring(xml_data)
            entry_tag = "{http://www.w3.org/2005/Atom}entry"
            title_tag = "{http://www.w3.org/2005/Atom}title"
            summary_tag = "{http://www.w3.org/2005/Atom}summary"
            id_tag = "{http://www.w3.org/2005/Atom}id"
            published_tag = "{http://www.w3.org/2005/Atom}published"
            author_tag = "{http://www.w3.org/2005/Atom}author"
            name_tag = "{http://www.w3.org/2005/Atom}name"
            link_tag = "{http://www.w3.org/2005/Atom}link"

            results = []
            for entry in root.findall(entry_tag):
                title = entry.find(title_tag).text.strip().replace("\n", " ") if entry.find(title_tag) is not None else "Unknown Title"
                summary = entry.find(summary_tag).text.strip() if entry.find(summary_tag) is not None else ""
                raw_id = entry.find(id_tag).text.strip() if entry.find(id_tag) is not None else ""
                published = entry.find(published_tag).text.strip() if entry.find(published_tag) is not None else ""

                hash_id = raw_id.split('/abs/')[-1] if '/abs/' in raw_id else raw_id
                clean_hash_id = hash_id.split('v')[0] if 'v' in hash_id else hash_id

                authors_list = []
                for author in entry.findall(author_tag):
                    name_el = author.find(name_tag)
                    if name_el is not None and name_el.text:
                        authors_list.append(name_el.text.strip())
                authors = ", ".join(authors_list)

                pdf_url = ""
                other_url = raw_id
                for link in entry.findall(link_tag):
                    rel = link.attrib.get("rel")
                    title_attr = link.attrib.get("title")
                    href = link.attrib.get("href")
                    if rel == "related" and title_attr == "pdf":
                        pdf_url = href
                    elif href and href.endswith(".pdf"):
                        pdf_url = href

                if not pdf_url and clean_hash_id:
                    pdf_url = f"https://arxiv.org/pdf/{clean_hash_id}.pdf"

                comment_tag = "{http://arxiv.org/schemas/atom}comment"
                comment_el = entry.find(comment_tag)
                comment_text = comment_el.text.strip() if comment_el is not None and comment_el.text else ""

                is_withdrawn = False
                withdrawn_reason = ""
                full_search_text = f"{title} {summary} {comment_text}".lower()
                if "withdrawn" in full_search_text or "has been withdrawn" in full_search_text:
                    is_withdrawn = True
                    withdrawn_reason = comment_text or "Paper has been withdrawn by authors."

                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": summary,
                    "hash_id": clean_hash_id,
                    "pdf_url": pdf_url,
                    "other_url": other_url,
                    "source_database": "arxiv",
                    "published_date": published,
                    "is_withdrawn": is_withdrawn,
                    "withdrawn_reason": withdrawn_reason
                })
            return results
        except Exception as e:
            logger.exception(f"Error parsing arXiv XML response: {str(e)}")
            raise e

    def _search_openalex_arxiv_fallback(self, query: str, limit: int = 10) -> list[dict]:
        """
        Seamless fallback harvesting arXiv papers via OpenAlex's indexed repository source.
        Used when export.arxiv.org rate limits or blocks requests.
        """
        # OpenAlex per_page is strictly capped at 200
        openalex_limit = max(1, min(limit, 200))

        # Extract search keywords or phrases from complex arXiv queries
        phrases = re.findall(r'\"([^\"]+)\"', query)
        if phrases:
            clean_search = " OR ".join(phrases[:6])
        else:
            clean = re.sub(r'\b(cat|ti|au|all|abs|jr):[^\s\)]+', '', query)
            clean = re.sub(r'submittedDate:\[.*?\]', '', clean)
            clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', clean)
            clean_search = " ".join(clean.split()[:8])

        encoded = urllib.parse.quote(clean_search or "quantum")

        url = f"https://api.openalex.org/works?filter=locations.source.id:s4306400194&search={encoded}&per_page={openalex_limit}"
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7); mailto:research@soinventive.co.uk'}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            results = []
            for item in data.get("results", []):
                title = item.get("title") or "Unknown Title"
                published = item.get("publication_date") or ""

                abstract = ""
                inv_index = item.get("abstract_inverted_index")
                if isinstance(inv_index, dict):
                    word_positions = []
                    for word, positions in inv_index.items():
                        for pos in positions:
                            word_positions.append((pos, word))
                    word_positions.sort()
                    abstract = " ".join([word for _, word in word_positions])

                arxiv_id = (item.get("ids") or {}).get("arxiv") or ""
                if arxiv_id:
                    clean_hash_id = arxiv_id.split('/')[-1]
                else:
                    openalex_id = item.get("id") or ""
                    clean_hash_id = openalex_id.split('/')[-1] if '/' in openalex_id else openalex_id

                authors_list = []
                for auth in item.get("authorships", []):
                    author_name = auth.get("author", {}).get("display_name")
                    if author_name:
                        authors_list.append(author_name)
                authors = ", ".join(authors_list)

                pdf_url = f"https://arxiv.org/pdf/{clean_hash_id}.pdf" if arxiv_id else ""
                if not pdf_url:
                    best_oa = item.get("best_oa_location") or {}
                    pdf_url = best_oa.get("pdf_url") or ""

                other_url = arxiv_id or item.get("doi") or item.get("id") or ""

                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "hash_id": clean_hash_id,
                    "pdf_url": pdf_url,
                    "other_url": other_url,
                    "source_database": "arxiv",
                    "published_date": published,
                    "is_withdrawn": False,
                    "withdrawn_reason": ""
                })
            logger.info(f"✅ [ARXIV FALLBACK] Successfully retrieved {len(results)} arXiv papers via OpenAlex index.")
            return results
        except Exception as e:
            logger.warning(f"⚠️ OpenAlex fallback query failed for '{clean_search}': {e}")
            return []

    def _search_oai_pmh(self, oai_params: str, limit: int = 10) -> list[dict]:
        """
        Harvests metadata from arXiv OAI-PMH interface (https://export.arxiv.org/oai2).
        Supports params like 'set=cs&from=2024-01-01&until=2024-01-31'.
        """
        _throttle_request(min_interval=3.0)
        url = f"https://export.arxiv.org/oai2?verb=ListRecords&metadataPrefix=arXiv&{oai_params}"
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'SchwarzResearchIntelligence/1.0 (mailto:research@soinventive.co.uk)'}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_data = resp.read()

            root = ET.fromstring(xml_data)
            records = root.findall(".//{http://www.openarchives.org/OAI/2.0/}record")
            results = []
            for rec in records:
                header = rec.find("{http://www.openarchives.org/OAI/2.0/}header")
                if header is not None and header.attrib.get("status") == "deleted":
                    continue

                metadata = rec.find("{http://www.openarchives.org/OAI/2.0/}metadata")
                if metadata is None:
                    continue

                arxiv_el = metadata.find("{http://arxiv.org/OAI/arXiv/}arXiv")
                if arxiv_el is None:
                    continue

                raw_id = arxiv_el.findtext("{http://arxiv.org/OAI/arXiv/}id", "").strip()
                clean_hash_id = raw_id.split('v')[0] if 'v' in raw_id else raw_id
                title = arxiv_el.findtext("{http://arxiv.org/OAI/arXiv/}title", "Unknown Title").strip().replace("\n", " ")
                abstract = arxiv_el.findtext("{http://arxiv.org/OAI/arXiv/}abstract", "").strip()
                published = arxiv_el.findtext("{http://arxiv.org/OAI/arXiv/}created", "").strip()

                authors_els = arxiv_el.findall(".//{http://arxiv.org/OAI/arXiv/}author")
                authors_list = []
                for a in authors_els:
                    keyname = a.findtext("{http://arxiv.org/OAI/arXiv/}keyname", "")
                    forenames = a.findtext("{http://arxiv.org/OAI/arXiv/}forenames", "")
                    authors_list.append(f"{forenames} {keyname}".strip() if forenames else keyname)
                authors = ", ".join([a for a in authors_list if a])

                pdf_url = f"https://arxiv.org/pdf/{clean_hash_id}.pdf"
                other_url = f"https://arxiv.org/abs/{clean_hash_id}"

                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "hash_id": clean_hash_id,
                    "pdf_url": pdf_url,
                    "other_url": other_url,
                    "source_database": "arxiv",
                    "published_date": published,
                    "is_withdrawn": False,
                    "withdrawn_reason": ""
                })
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            logger.exception(f"OAI-PMH harvesting failed: {e}")
            return []

    def download_file(self, url: str) -> bytes:
        if not url or not url.lower().startswith(('http://', 'https://')):
            raise ValueError(f"Invalid URL scheme for download: '{url}'")
        from ..utils.url_guard import is_safe_external_url, safe_download_url
        if not is_safe_external_url(url):
            raise ValueError(f"Disallowed private/internal IP URL: '{url}'")
        urls_to_try = [url]

        # Build arXiv fallback URL variants if applicable
        if "arxiv.org/pdf/" in url:
            base_url = url.rstrip('/')
            if not base_url.endswith(".pdf"):
                urls_to_try.append(f"{base_url}.pdf")

            unversioned = re.sub(r'v\d+(?:\.pdf)?$', '', base_url)
            if unversioned != base_url:
                urls_to_try.append(f"{unversioned}.pdf")
                urls_to_try.append(unversioned)

        unique_urls = []
        for u in urls_to_try:
            if u not in unique_urls:
                unique_urls.append(u)

        last_exception = None
        for candidate_url in unique_urls:
            try:
                data = safe_download_url(
                    candidate_url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                    },
                    max_bytes=100 * 1024 * 1024,
                    timeout=15.0
                )
                if data and len(data) > 100:
                    return data
            except Exception as e:
                last_exception = e
                logger.warning(f"Download attempt failed for {candidate_url}: {e}")

        if last_exception:
            raise last_exception
        raise ValueError(f"Unable to download PDF from {url}")

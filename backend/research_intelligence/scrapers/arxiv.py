import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import logging
import time
from .base import BaseScraperProvider

logger = logging.getLogger(__name__)

class ArxivScraperProvider(BaseScraperProvider):
    """
    Scraper provider implementing arXiv API search and paper download.
    """

    def search(self, query: str, limit: int = 10, sort_by: str = "relevance", sort_order: str = "desc") -> list[dict]:
        clean_query = query.strip()
        if clean_query.lower().startswith("arxiv:"):
            clean_query = clean_query[6:].strip()

        # Check if query already contains field specifiers or boolean operators
        has_field_prefixes = any(p in clean_query for p in ["cat:", "ti:", "au:", "all:", "abs:", "submittedDate:", "jr:"])
        has_boolean_operators = any(b in clean_query for b in [" AND ", " OR ", " NOT "]) or clean_query.startswith("(")

        if has_field_prefixes or has_boolean_operators:
            formatted_query = clean_query
        else:
            # Strip quotes if wrapping as all:"..."
            raw = clean_query.replace('"', '').replace("'", "")
            formatted_query = f'all:"{raw}"' if " " in raw else f'all:{raw}'

        encoded_query = urllib.parse.quote(formatted_query)
        sort_by_param = "submittedDate" if sort_by == "date" else "relevance"
        sort_order_param = "ascending" if sort_order == "asc" else "descending"
        url = f"https://export.arxiv.org/api/query?search_query={encoded_query}&max_results={limit}&sortBy={sort_by_param}&sortOrder={sort_order_param}"

        max_retries = 5
        timeout_sec = 35
        xml_data = None
        last_exc = None

        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 (SchwarzResearchIntelligence/1.0; mailto:research@soinventive.co.uk)'
                    }
                )
                with urllib.request.urlopen(req, timeout=timeout_sec) as response:
                    xml_data = response.read()
                break
            except Exception as e:
                last_exc = e
                if attempt < max_retries:
                    # If 429 Too Many Requests, calculate backoff with minimum 5s or respect Retry-After
                    if isinstance(e, urllib.error.HTTPError) and e.code == 429:
                        retry_after = e.headers.get("Retry-After") if hasattr(e, "headers") and e.headers else None
                        try:
                            delay = int(retry_after) if retry_after else max(5, 5 * (2 ** (attempt - 1)))
                        except (ValueError, TypeError):
                            delay = max(5, 5 * (2 ** (attempt - 1)))
                    else:
                        delay = max(3, 3 * attempt)

                    logger.warning(f"⚠️ [ARXIV RETRY {attempt}/{max_retries}] Error querying arXiv API: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"❌ [ARXIV FAILED] Error querying arXiv API after {max_retries} attempts: {e}")
                    raise e

        if not xml_data:
            return []

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
                # Remove version suffixes if present
                clean_hash_id = hash_id.split('v')[0] if 'v' in hash_id else hash_id

                authors_list = []
                for author in entry.findall(author_tag):
                    name_el = author.find(name_tag)
                    if name_el is not None:
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

    def download_file(self, url: str) -> bytes:
        urls_to_try = [url]
        
        # Build arXiv fallback URL variants if applicable
        if "arxiv.org/pdf/" in url:
            base_url = url.rstrip('/')
            if not base_url.endswith(".pdf"):
                urls_to_try.append(f"{base_url}.pdf")
            
            import re
            unversioned = re.sub(r'v\d+(?:\.pdf)?$', '', base_url)
            if unversioned != base_url:
                urls_to_try.append(f"{unversioned}.pdf")
                urls_to_try.append(unversioned)

        # Deduplicate while preserving order
        unique_urls = []
        for u in urls_to_try:
            if u not in unique_urls:
                unique_urls.append(u)

        last_exception = None
        for candidate_url in unique_urls:
            try:
                req = urllib.request.Request(
                    candidate_url, 
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                    }
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = response.read()
                    if data and len(data) > 100:
                        return data
            except Exception as e:
                last_exception = e
                logger.warning(f"Download attempt failed for {candidate_url}: {e}")

        if last_exception:
            raise last_exception
        raise ValueError(f"Unable to download PDF from {url}")

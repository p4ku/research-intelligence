import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import logging
from .base import BaseScraperProvider

logger = logging.getLogger(__name__)

class ArxivScraperProvider(BaseScraperProvider):
    """
    Scraper provider implementing arXiv API search and paper download.
    """

    def search(self, query: str, limit: int = 10) -> list[dict]:
        # Simple query string parsing. Remove complex quotes if present.
        clean_query = query.replace('"', '').replace("'", "")
        encoded_query = urllib.parse.quote(f'all:{clean_query}')
        url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&max_results={limit}"
        
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()
            
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
                
                results.append({
                    "title": title,
                    "authors": authors,
                    "abstract": summary,
                    "hash_id": clean_hash_id,
                    "pdf_url": pdf_url,
                    "other_url": other_url,
                    "source_database": "arxiv",
                    "published_date": published
                })
            return results
        except Exception as e:
            logger.exception(f"Error querying arXiv API: {str(e)}")
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

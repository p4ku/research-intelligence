import urllib.request
import urllib.parse
import json
import logging
from datetime import datetime
from django.conf import settings
from .base import BaseScraperProvider

logger = logging.getLogger(__name__)

class LensScraperProvider(BaseScraperProvider):
    """
    Scraper provider implementing Lens.org scholarly API search and paper download.
    """

    def __init__(
        self,
        n_last_days: int = 7,
        api_key: str | None = None,
        workspace: object | None = None,
        workspace_id: str | None = None,
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
        explicit_key: str | None = None,
        instance_key: str | None = None,
        workspace: object | None = None,
        workspace_id: str | None = None,
    ) -> str | None:
        """Resolves LENS_API_KEY from args, instance, settings, env, or database Scraper model."""
        if explicit_key and str(explicit_key).strip():
            return str(explicit_key).strip()
        if instance_key and str(instance_key).strip():
            return str(instance_key).strip()

        settings_key = getattr(settings, "LENS_API_KEY", "")
        if settings_key and str(settings_key).strip():
            return str(settings_key).strip()

        import os
        env_key = os.environ.get("LENS_API_KEY", "")
        if env_key and str(env_key).strip():
            return str(env_key).strip()

        try:
            from research_intelligence.models import Scraper
            qs = Scraper.objects.filter(provider="lens").exclude(api_key="").exclude(api_key__isnull=True)
            if workspace:
                ws_scraper = qs.filter(workspace=workspace, is_active=True).first() or qs.filter(workspace=workspace).first()
                if ws_scraper and ws_scraper.api_key and ws_scraper.api_key.strip():
                    return ws_scraper.api_key.strip()
            elif workspace_id:
                ws_scraper = qs.filter(workspace_id=workspace_id, is_active=True).first() or qs.filter(workspace_id=workspace_id).first()
                if ws_scraper and ws_scraper.api_key and ws_scraper.api_key.strip():
                    return ws_scraper.api_key.strip()

            active_scraper = qs.filter(is_active=True).first()
            if active_scraper and active_scraper.api_key and active_scraper.api_key.strip():
                return active_scraper.api_key.strip()

            any_scraper = qs.first()
            if any_scraper and any_scraper.api_key and any_scraper.api_key.strip():
                return any_scraper.api_key.strip()
        except Exception as exc:
            logger.debug(f"Could not query Scraper model for LENS_API_KEY: {exc}")

        return None

    def search(
        self,
        query: str,
        limit: int = 10,
        sort_by: str = "relevance",
        sort_order: str = "desc",
        start_date: str | datetime | None = None,
        end_date: str | datetime | None = None,
        n_last_days: int | None = None,
        **kwargs,
    ) -> list[dict]:
        target_ws = kwargs.get("workspace") or self.workspace
        target_ws_id = kwargs.get("workspace_id") or self.workspace_id
        api_key = self._resolve_api_key(
            explicit_key=kwargs.get("api_key"),
            instance_key=self.api_key,
            workspace=target_ws,
            workspace_id=target_ws_id,
        )
        if not api_key:
            logger.warning("LENS_API_KEY not configured in settings, environment, or Scraper model. Returning empty results.")
            return []
            
        start_dt, end_dt = self.resolve_date_range(start_date, end_date, n_last_days)
        start_iso, end_iso = self.format_iso_date_range(start_dt, end_dt)

        url = "https://api.lens.org/scholarly/search"
        payload = {
            "query": {
                "bool": {
                    "must": [
                        {"query_string": {"query": query}},
                        {"range": {"date_published": {"gte": start_iso, "lte": end_iso}}}
                    ]
                }
            },
            "size": int(limit or 10)
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
                    "source_url": other_url,
                    "source_database": "lens",
                    "published_date": published
                })
            return results
        except Exception as e:
            logger.exception(f"Error querying Lens.org API: {str(e)}")
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(e)
            except Exception:
                pass
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

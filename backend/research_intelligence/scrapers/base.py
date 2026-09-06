import abc
from datetime import datetime, date, timedelta
from typing import Optional, Union, List, Dict, Any, Tuple

try:
    from django.utils import timezone
except ImportError:
    timezone = None


class BaseScraperProvider(abc.ABC):
    """
    Abstract base class for academic database search and document retrievers.
    Includes unified publication date window resolution and query formatting.
    """
    DEFAULT_N_LAST_DAYS = 7

    def __init__(self, n_last_days: int = 7):
        self.n_last_days = n_last_days if n_last_days is not None else self.DEFAULT_N_LAST_DAYS

    def _now(self) -> datetime:
        if timezone and hasattr(timezone, "now"):
            return timezone.now()
        return datetime.now()

    def parse_date(self, val: Optional[Union[str, date, datetime]]) -> Optional[datetime]:
        """
        Parses string, date, or datetime into a datetime object.
        Supports YYYY-MM-DD, ISO timestamps, and YYYYMMDD.
        """
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        if isinstance(val, date):
            return datetime.combine(val, datetime.min.time())
        val_str = str(val).strip()
        if not val_str:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y%m%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(val_str)
        except Exception:
            pass
        return None

    def resolve_date_range(
        self,
        start_date: Optional[Union[str, date, datetime]] = None,
        end_date: Optional[Union[str, date, datetime]] = None,
        n_last_days: Optional[int] = None
    ) -> Tuple[datetime, datetime]:
        """
        Resolves start and end datetimes for scraper search queries.
        - If neither start_date nor end_date is provided, defaults to:
            end_date = now()
            start_date = now() - timedelta(days=effective_n_last_days)
        - If only start_date is provided:
            end_date = now()
        - If only end_date is provided:
            start_date = end_date - timedelta(days=effective_n_last_days)
        - If both are provided:
            parses both and ensures start_date <= end_date.
        effective_n_last_days defaults to n_last_days if specified, else self.n_last_days (default 7).
        """
        effective_n = n_last_days if n_last_days is not None else self.n_last_days
        try:
            effective_n = int(effective_n)
            if effective_n <= 0:
                effective_n = self.DEFAULT_N_LAST_DAYS
        except (ValueError, TypeError):
            effective_n = self.DEFAULT_N_LAST_DAYS

        parsed_start = self.parse_date(start_date)
        parsed_end = self.parse_date(end_date)
        current_now = self._now()

        if timezone and hasattr(timezone, "is_aware"):
            if timezone.is_aware(current_now):
                if parsed_start is not None and timezone.is_naive(parsed_start):
                    parsed_start = timezone.make_aware(parsed_start, timezone.get_current_timezone())
                if parsed_end is not None and timezone.is_naive(parsed_end):
                    parsed_end = timezone.make_aware(parsed_end, timezone.get_current_timezone())
            else:
                if parsed_start is not None and timezone.is_aware(parsed_start):
                    parsed_start = timezone.make_naive(parsed_start, timezone.get_current_timezone())
                if parsed_end is not None and timezone.is_aware(parsed_end):
                    parsed_end = timezone.make_naive(parsed_end, timezone.get_current_timezone())

        if parsed_start is None and parsed_end is None:
            parsed_end = current_now
            parsed_start = parsed_end - timedelta(days=effective_n)
        elif parsed_start is not None and parsed_end is None:
            parsed_end = current_now
        elif parsed_start is None and parsed_end is not None:
            parsed_start = parsed_end - timedelta(days=effective_n)

        # Ensure start <= end
        if parsed_start > parsed_end:
            parsed_start, parsed_end = parsed_end, parsed_start

        return parsed_start, parsed_end

    def format_iso_date_range(self, start_dt: datetime, end_dt: datetime) -> Tuple[str, str]:
        """
        Returns (start_str, end_str) formatted as 'YYYY-MM-DD'.
        """
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")

    def format_arxiv_date_filter(self, start_dt: datetime, end_dt: datetime) -> str:
        """
        Returns arXiv API submittedDate filter string:
        'submittedDate:[YYYYMMDD000000 TO YYYYMMDD235959]'
        """
        s_str = start_dt.strftime("%Y%m%d000000")
        e_str = end_dt.strftime("%Y%m%d235959")
        return f"submittedDate:[{s_str} TO {e_str}]"

    @abc.abstractmethod
    def search(
        self,
        query: str,
        limit: int = 10,
        sort_by: str = "relevance",
        sort_order: str = "desc",
        start_date: Optional[Union[str, date, datetime]] = None,
        end_date: Optional[Union[str, date, datetime]] = None,
        n_last_days: Optional[int] = None,
        **kwargs
    ) -> list[dict]:
        """
        Executes a search query against the provider and returns a list of standardized dicts.
        Standard schema:
        [
            {
                "title": str,
                "authors": str,
                "abstract": str,
                "hash_id": str,
                "pdf_url": str,
                "other_url": str, # optional XML/HTML or link
                "source_database": str,
                "published_date": str
            }
        ]
        """
        pass

    @abc.abstractmethod
    def download_file(self, url: str) -> bytes:
        """
        Downloads the file content (PDF or other formats) from a target URL.
        """
        pass

import abc

class BaseScraperProvider(abc.ABC):
    """
    Abstract base class for academic database search and document retrievers.
    """

    @abc.abstractmethod
    def search(self, query: str, limit: int = 10) -> list[dict]:
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

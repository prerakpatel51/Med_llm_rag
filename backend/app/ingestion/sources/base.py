"""
base.py – abstract base class for all source fetchers.

Every fetcher (PubMed, CDC, WHO, …) must implement the `fetch` method,
which returns a list of document dicts in a common format.
"""
from abc import ABC, abstractmethod


class BaseFetcher(ABC):
    """
    Abstract fetcher.  Subclass this and implement `fetch()`.

    Each document dict returned by `fetch()` must contain:
      - source       (str): "pubmed", "cdc", "who", "fda", etc.
      - source_id    (str): unique ID for deduplication (PMID, URL, etc.)
      - title        (str)
      - authors      (str): comma-separated author names
      - journal      (str)
      - doi          (str)
      - url          (str): link to the original article
      - published_at (datetime | None)
      - publication_type (str): "Review", "Randomized Controlled Trial", etc.
      - text         (str): the full abstract / body text to chunk and embed
      - citation_count (int): 0 if unknown
    """

    @abstractmethod
    async def fetch(self, query: str, max_results: int = 50) -> list[dict]:
        """Fetch documents matching `query`. Returns a list of document dicts."""
        ...

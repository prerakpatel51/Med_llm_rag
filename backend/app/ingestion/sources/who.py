"""
who.py – fetches health topic content from WHO IRIS (the WHO repository).

Uses the OAI-PMH or the IRIS REST API.
No API key required.

API docs: https://iris.who.int/rest
"""
import httpx
from app.ingestion.sources.base import BaseFetcher

WHO_IRIS_URL = "https://iris.who.int/rest/items"


class WHOFetcher(BaseFetcher):
    """Fetches publications from the WHO IRIS document repository."""

    async def fetch(self, query: str, max_results: int = 20) -> list[dict]:
        params = {
            "query": query,
            "scope": "/",           # search entire repository
            "configuration": "defaultConfiguration",
            "limit": max_results,
            "sort_by": "score",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(WHO_IRIS_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                return []

        documents = []
        for item in data.get("_embedded", {}).get("items", []):
            metadata = item.get("metadata", {})
            title = self._get_first(metadata, "dc.title")
            abstract = self._get_first(metadata, "dc.description.abstract")
            if not abstract:
                abstract = self._get_first(metadata, "dc.description")
            if not abstract:
                continue

            handle = item.get("handle", "")
            url = f"https://iris.who.int/handle/{handle}" if handle else "https://iris.who.int"
            authors_list = metadata.get("dc.contributor.author", [])
            authors = ", ".join(v.get("value", "") for v in authors_list[:5])

            documents.append({
                "source": "who",
                "source_id": handle or url,
                "title": title,
                "authors": authors or "World Health Organization",
                "journal": "World Health Organization",
                "doi": self._get_first(metadata, "dc.identifier.doi"),
                "url": url,
                "published_at": None,
                "publication_type": "government guideline",
                "text": f"{title}. {abstract}",
                "citation_count": 0,
            })

        return documents

    def _get_first(self, metadata: dict, key: str) -> str:
        """Extract the first string value for a metadata key."""
        values = metadata.get(key, [])
        if values and isinstance(values, list):
            return values[0].get("value", "") if isinstance(values[0], dict) else str(values[0])
        return ""

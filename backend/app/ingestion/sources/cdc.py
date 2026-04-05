"""
cdc.py – fetches health topic content from the CDC syndication API.

CDC provides a public content API that returns structured JSON.
No API key required.

Docs: https://tools.cdc.gov/api/v2/resources/
"""
import httpx
from app.ingestion.sources.base import BaseFetcher

CDC_SEARCH_URL = "https://tools.cdc.gov/api/v2/resources/media"


class CDCFetcher(BaseFetcher):
    """Fetches health topic pages from CDC's public content API."""

    async def fetch(self, query: str, max_results: int = 20) -> list[dict]:
        documents = []
        params = {
            "q": query,
            "max": max_results,
            "mediaType": "html",     # limit to web pages
            "language": "english",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(CDC_SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                return []   # Don't crash if CDC API is unavailable

        for item in data.get("results", []):
            text = item.get("description", "").strip()
            if not text:
                continue

            documents.append({
                "source": "cdc",
                "source_id": item.get("sourceUrl", item.get("id", "")),
                "title": item.get("name", "CDC Health Topic"),
                "authors": "CDC",
                "journal": "Centers for Disease Control and Prevention",
                "doi": "",
                "url": item.get("sourceUrl", "https://www.cdc.gov"),
                "published_at": None,
                "publication_type": "government guideline",
                "text": item.get("name", "") + ". " + text,
                "citation_count": 0,
            })

        return documents

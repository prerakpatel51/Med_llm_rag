"""
fda.py – fetches drug label information from the openFDA API.

openFDA is a free, public API that provides access to FDA drug labels.
No API key required (rate limit: 240 requests/minute without key).

Docs: https://open.fda.gov/apis/drug/label/
"""
import httpx
from app.ingestion.sources.base import BaseFetcher

OPENFDA_URL = "https://api.fda.gov/drug/label.json"


class FDAFetcher(BaseFetcher):
    """Fetches drug label information from openFDA."""

    async def fetch(self, query: str, max_results: int = 10) -> list[dict]:
        params = {
            "search": f'indications_and_usage:"{query}"',
            "limit": max_results,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(OPENFDA_URL, params=params)
                if resp.status_code == 404:
                    return []   # No results found
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                return []

        documents = []
        for result in data.get("results", []):
            openfda = result.get("openfda", {})
            brand_names = openfda.get("brand_name", [])
            generic_names = openfda.get("generic_name", [])
            name = brand_names[0] if brand_names else (generic_names[0] if generic_names else "Unknown Drug")

            # Combine the most useful label sections into one text
            sections = []
            for field in ["indications_and_usage", "warnings", "dosage_and_administration"]:
                value = result.get(field, [])
                if value:
                    sections.append(value[0])

            text = " ".join(sections).strip()
            if not text:
                continue

            set_id = result.get("set_id", "")
            documents.append({
                "source": "fda",
                "source_id": set_id or name,
                "title": f"FDA Drug Label: {name}",
                "authors": "U.S. Food and Drug Administration",
                "journal": "U.S. Food and Drug Administration",
                "doi": "",
                "url": f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm",
                "published_at": None,
                "publication_type": "government guideline",
                "text": f"FDA Drug Label: {name}. {text}",
                "citation_count": 0,
            })

        return documents

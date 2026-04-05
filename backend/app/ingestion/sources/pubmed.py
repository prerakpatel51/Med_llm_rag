"""
pubmed.py – fetches abstracts from PubMed using the NCBI E-utilities REST API.

Two-step process:
  1. esearch: find PMIDs matching the query
  2. efetch:  download the XML records for those PMIDs

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25497/
Free API key: https://www.ncbi.nlm.nih.gov/account/
"""
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import httpx
from app.config import get_settings
from app.ingestion.sources.base import BaseFetcher

settings = get_settings()

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class PubMedFetcher(BaseFetcher):
    """Fetches PubMed abstracts via NCBI E-utilities."""

    async def fetch(self, query: str, max_results: int = 50) -> list[dict]:
        pmids = await self._search(query, max_results)
        if not pmids:
            return []
        documents = await self._fetch_details(pmids)
        return documents

    async def _search(self, query: str, max_results: int) -> list[str]:
        """Run esearch to get a list of PMIDs."""
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "usehistory": "n",
        }
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(ESEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        pmids = data.get("esearchresult", {}).get("idlist", [])
        return pmids

    async def _fetch_details(self, pmids: list[str]) -> list[dict]:
        """Run efetch in batches of 100 to get full XML records."""
        documents = []
        # Process in batches so we don't exceed URL length limits
        batch_size = 100
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]
            batch_docs = await self._fetch_batch(batch)
            documents.extend(batch_docs)
            # Be polite to NCBI: 0.11 s between batches = ~9 req/sec
            await asyncio.sleep(0.11)
        return documents

    async def _fetch_batch(self, pmids: list[str]) -> list[dict]:
        """Fetch a single batch of PMIDs and parse the XML."""
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(EFETCH_URL, params=params)
            resp.raise_for_status()
            xml_text = resp.text

        return self._parse_xml(xml_text)

    def _parse_xml(self, xml_text: str) -> list[dict]:
        """Parse PubMed XML and extract the fields we care about."""
        documents = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        for article in root.findall(".//PubmedArticle"):
            try:
                doc = self._parse_article(article)
                if doc:
                    documents.append(doc)
            except Exception:
                # Skip malformed articles rather than crashing the whole batch
                continue

        return documents

    def _parse_article(self, article: ET.Element) -> dict | None:
        """Extract one article's fields from its XML element."""
        pmid_el = article.find(".//PMID")
        if pmid_el is None or not pmid_el.text:
            return None
        pmid = pmid_el.text.strip()

        # Title
        title_el = article.find(".//ArticleTitle")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        # Abstract (may have multiple AbstractText elements)
        abstract_parts = article.findall(".//AbstractText")
        abstract = " ".join(
            (el.text or "").strip() for el in abstract_parts
        ).strip()

        if not abstract:
            return None   # Skip articles without abstracts

        # Authors
        author_els = article.findall(".//Author")
        author_names = []
        for author in author_els[:5]:   # Cap at 5 authors for display
            last = (author.findtext("LastName") or "").strip()
            first = (author.findtext("ForeName") or "").strip()
            if last:
                author_names.append(f"{last} {first}".strip())
        authors = ", ".join(author_names)

        # Journal
        journal = article.findtext(".//Journal/Title") or ""

        # DOI
        doi = ""
        for id_el in article.findall(".//ArticleId"):
            if id_el.get("IdType") == "doi":
                doi = id_el.text or ""
                break

        # Publication date
        pub_date = None
        year_el = article.find(".//PubDate/Year")
        if year_el is not None and year_el.text:
            try:
                pub_date = datetime(int(year_el.text), 1, 1, tzinfo=timezone.utc)
            except ValueError:
                pass

        # Publication types (MeSH controlled vocabulary)
        pub_types = [
            el.text.strip()
            for el in article.findall(".//PublicationType")
            if el.text
        ]
        publication_type = pub_types[0] if pub_types else "unknown"

        return {
            "source": "pubmed",
            "source_id": pmid,
            "title": title,
            "authors": authors,
            "journal": journal,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "published_at": pub_date,
            "publication_type": publication_type,
            "text": f"{title}. {abstract}",
            "citation_count": 0,   # PubMed API doesn't return citation counts
        }

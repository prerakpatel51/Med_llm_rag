"""
schemas.py – Pydantic models for API request and response bodies.
These are what FastAPI validates and serializes automatically.
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Incoming query ────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000,
                       description="Your medical literature question")
    session_id: str = Field(default="default",
                            description="Optional session ID for memory grouping")
    model: Optional[str] = Field(default=None,
                                 description="Override LLM model for this request")


# ── Citation shown alongside the answer ──────────────────────────────────────

class Citation(BaseModel):
    chunk_id: int
    source: str          # "pubmed", "cdc", "who", …
    source_id: str       # PMID, URL, etc.
    title: str
    authors: str
    journal: str
    doi: str
    url: str
    published_at: Optional[datetime]
    trust_score: float   # 0.0 – 1.0
    trust_tier: str      # "A", "B", or "C"
    excerpt: str         # the actual chunk text shown to the user


class SourceSummary(BaseModel):
    source: str
    source_id: str
    title: str
    url: str = ""
    journal: str = ""
    published_at: Optional[datetime] = None


# ── Full response from the assistant ─────────────────────────────────────────

class QueryResponse(BaseModel):
    answer: str
    summary: str = ""
    citations: list[Citation]
    sources: list[SourceSummary] = []
    judge_flagged: bool = False      # True if the judge found unsupported claims
    judge_notes: str = ""            # human-readable explanation of any flags
    retrieval_latency: float = 0.0   # seconds
    generation_latency: float = 0.0
    total_latency: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0


# ── Memory list ───────────────────────────────────────────────────────────────

class MemoryEntry(BaseModel):
    id: int
    session_id: str
    query_text: str
    response_text: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Health endpoints ──────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str          # "ok" or "error"
    version: str


class ReadyResponse(BaseModel):
    status: str          # "ready" or "not_ready"
    checks: dict         # name → "ok" / error message


class UploadedPdfSummary(BaseModel):
    file_name: str
    source_id: str
    chunk_count: int
    size_bytes: int
    title: str


class PdfUploadResponse(BaseModel):
    session_id: str
    uploaded: list[UploadedPdfSummary]


class TopicIngestRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200)
    max_results: int = Field(default=10, ge=1, le=25)
    source: Literal["pubmed", "all"] = "pubmed"


class TopicIngestResponse(BaseModel):
    topic: str
    source: str
    new_documents: int
    documents: list[SourceSummary]

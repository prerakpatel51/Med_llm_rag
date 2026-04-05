"""
config.py – all app settings come from environment variables.
Pydantic BaseSettings reads them automatically.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "Medical Literature Assistant"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://medlit:medlit@postgres:5432/medlit"

    # ── LLM (Groq API — Llama 3.1 70B) ──────────────────────────────────────
    groq_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    max_new_tokens: int = 1024
    temperature: float = 0.1            # low = more factual, less creative

    # ── Embedding model ───────────────────────────────────────────────────────
    # all-MiniLM-L6-v2: 22 MB, 384-dim, fast on CPU
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # ── Retrieval settings ────────────────────────────────────────────────────
    semantic_top_k: int = 20            # candidates from vector search
    bm25_top_k: int = 20               # candidates from full-text search
    rerank_top_k: int = 5              # final chunks sent to LLM
    max_context_tokens: int = 1800     # cap on prompt context

    # ── Chunking ──────────────────────────────────────────────────────────────
    chunk_size: int = 256              # tokens per chunk
    chunk_overlap: int = 32            # overlapping tokens between chunks

    # ── Memory ────────────────────────────────────────────────────────────────
    memory_similarity_threshold: float = 0.75
    memory_retention_days: int = 90
    memory_boost: float = 0.1

    # ── Safety ────────────────────────────────────────────────────────────────
    enable_judge: bool = True
    max_query_length: int = 1000

    # ── AWS ───────────────────────────────────────────────────────────────────
    aws_region: str = "us-east-1"

    # ── External APIs ─────────────────────────────────────────────────────────
    ncbi_api_key: str = ""             # free at ncbi.nlm.nih.gov/account
    ncbi_email: str = "medlit@example.com"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton Settings object."""
    return Settings()

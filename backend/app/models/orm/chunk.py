"""
chunk.py – ORM model for a text chunk from a document.
Each chunk stores:
  - the raw text
  - a pgvector embedding for semantic search
  - a tsvector column for full-text (BM25-style) search
"""
from sqlalchemy import (
    Column, Integer, String, Float, Text, ForeignKey,
    Index
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from pgvector.sqlalchemy import Vector
from app.models.database import Base
from app.config import get_settings

settings = get_settings()


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)

    # The actual text of this chunk
    content = Column(Text, nullable=False)

    # Position within the document (0-indexed)
    chunk_index = Column(Integer, default=0)

    # 384-dimensional vector from all-MiniLM-L6-v2
    # pgvector stores and indexes this for approximate nearest-neighbor search
    embedding = Column(Vector(settings.embedding_dim))

    # PostgreSQL full-text search vector (auto-maintained via trigger)
    content_tsv = Column(TSVECTOR)

    # Trust score copied from the parent document for easy access at query time
    trust_score = Column(Float, default=0.5)

    # Source metadata duplicated here so retrieval doesn't need a JOIN
    source = Column(String(50), default="")
    source_id = Column(String(100), default="")

    # Indexes for fast retrieval
    # The IVFFLAT index speeds up approximate vector search
    __table_args__ = (
        Index(
            "ix_chunks_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_content_tsv", "content_tsv", postgresql_using="gin"),
    )

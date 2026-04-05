"""
memory_service.py – read and write conversation memory.

When a user submits a query:
  1. We search memory for semantically similar past queries.
  2. If found, we boost the chunks that were previously useful.
  3. After generating the answer, we save this Q+A to memory.
"""
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings

settings = get_settings()


async def find_similar_memories(
    db: AsyncSession,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    """
    Return past Q+A pairs whose query embedding is close to the current query.
    Only returns memories above the similarity threshold in settings.
    """
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    result = await db.execute(
        text("""
            SELECT
                id,
                session_id,
                query_text,
                response_text,
                retrieved_chunk_ids,
                1 - (query_embedding <=> CAST(:qe AS vector)) AS similarity
            FROM conversation_memory
            WHERE 1 - (query_embedding <=> CAST(:qe AS vector)) >= :threshold
            ORDER BY query_embedding <=> CAST(:qe AS vector)
            LIMIT :top_k
        """),
        {
            "qe": embedding_str,
            "threshold": settings.memory_similarity_threshold,
            "top_k": top_k,
        },
    )
    rows = result.mappings().all()
    return [dict(row) for row in rows]


async def save_memory(
    db: AsyncSession,
    session_id: str,
    query_text: str,
    response_text: str,
    query_embedding: list[float],
    retrieved_chunk_ids: list[int],
) -> None:
    """Save a Q+A pair to memory after a successful query."""
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    await db.execute(
        text("""
            INSERT INTO conversation_memory
                (session_id, query_text, response_text,
                 query_embedding, retrieved_chunk_ids)
            VALUES
                (:session_id, :query_text, :response_text,
                 CAST(:qe AS vector), :chunk_ids)
        """),
        {
            "session_id": session_id,
            "query_text": query_text,
            "response_text": response_text[:2000],  # trim very long responses
            "qe": embedding_str,
            "chunk_ids": retrieved_chunk_ids,
        },
    )
    await db.commit()


async def list_memories(
    db: AsyncSession,
    session_id: str,
    limit: int = 50,
) -> list[dict]:
    """Return recent memories for a given session (for the history page)."""
    result = await db.execute(
        text("""
            SELECT
                id,
                session_id,
                query_text,
                response_text,
                COALESCE(created_at, NOW()) AS created_at
            FROM conversation_memory
            WHERE session_id = :session_id
            ORDER BY COALESCE(created_at, NOW()) DESC
            LIMIT :limit
        """),
        {"session_id": session_id, "limit": limit},
    )
    rows = result.mappings().all()
    return [dict(row) for row in rows]


async def delete_old_memories(db: AsyncSession) -> int:
    """Delete memories older than the configured retention period. Returns count deleted."""
    cutoff = datetime.utcnow() - timedelta(days=settings.memory_retention_days)
    result = await db.execute(
        text("DELETE FROM conversation_memory WHERE created_at < :cutoff"),
        {"cutoff": cutoff},
    )
    await db.commit()
    return result.rowcount

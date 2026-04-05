"""
vector_store.py – functions for saving and searching chunks in pgvector.

Semantic search uses cosine distance (<=> operator) on the embedding column.
Full-text search uses PostgreSQL tsvector / ts_rank_cd.
Results from both are combined using Reciprocal Rank Fusion (RRF).
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def save_chunks(db: AsyncSession, chunks: list[dict]) -> None:
    """
    Insert a batch of chunks into the database.

    Each chunk dict must have:
      document_id, content, chunk_index, embedding (list[float]),
      trust_score, source, source_id
    """
    for chunk in chunks:
        embedding_str = "[" + ",".join(str(v) for v in chunk["embedding"]) + "]"
        await db.execute(
            text("""
                INSERT INTO chunks
                    (document_id, content, chunk_index, embedding,
                     trust_score, source, source_id, content_tsv)
                VALUES
                    (:document_id, :content, :chunk_index, CAST(:embedding AS vector),
                     :trust_score, :source, :source_id,
                     to_tsvector('english', :content))
                ON CONFLICT DO NOTHING
            """),
            {
                "document_id": chunk["document_id"],
                "content": chunk["content"],
                "chunk_index": chunk["chunk_index"],
                "embedding": embedding_str,
                "trust_score": chunk["trust_score"],
                "source": chunk["source"],
                "source_id": chunk["source_id"],
            },
        )
    await db.commit()


async def semantic_search(
    db: AsyncSession,
    query_embedding: list[float],
    session_id: str | None = None,
    top_k: int = 20,
) -> list[dict]:
    """
    Find the top_k chunks closest to the query embedding using cosine distance.
    Returns a list of dicts with chunk fields plus a similarity score.
    """
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    # ivfflat.probes = 10 trades a little recall for speed
    await db.execute(text("SET LOCAL ivfflat.probes = 10"))

    result = await db.execute(
        text("""
            SELECT
                c.id,
                c.document_id,
                c.content,
                c.chunk_index,
                c.trust_score,
                c.source,
                c.source_id,
                1 - (c.embedding <=> CAST(:query_embedding AS vector)) AS similarity
            FROM chunks c
            WHERE c.source != 'upload' OR c.source_id LIKE :upload_source_prefix
            ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
        """),
        {
            "query_embedding": embedding_str,
            "top_k": top_k,
            "upload_source_prefix": f"upload:{session_id or '__no_session__'}:%",
        },

    )
    rows = result.mappings().all()
    return [dict(row) for row in rows]


async def bm25_search(
    db: AsyncSession,
    query_text: str,
    session_id: str | None = None,
    top_k: int = 20,
) -> list[dict]:
    """
    Find chunks that match the query using PostgreSQL full-text search.
    Uses ts_rank_cd for BM25-like ranking.
    """
    result = await db.execute(
        text("""
            SELECT
                c.id,
                c.document_id,
                c.content,
                c.chunk_index,
                c.trust_score,
                c.source,
                c.source_id,
                (
                    ts_rank_cd(c.content_tsv, websearch_to_tsquery('english', :query))
                    + CASE
                        WHEN to_tsvector('english', COALESCE(d.title, ''))
                             @@ websearch_to_tsquery('english', :query)
                        THEN 2.0
                        ELSE 0.0
                      END
                ) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE (
                c.content_tsv @@ websearch_to_tsquery('english', :query)
                OR to_tsvector('english', COALESCE(d.title, '')) @@ websearch_to_tsquery('english', :query)
            )
              AND (c.source != 'upload' OR c.source_id LIKE :upload_source_prefix)
            ORDER BY similarity DESC
            LIMIT :top_k
        """),
        {
            "query": query_text,
            "top_k": top_k,
            "upload_source_prefix": f"upload:{session_id or '__no_session__'}:%",
        },
    )
    rows = result.mappings().all()
    return [dict(row) for row in rows]


def reciprocal_rank_fusion(
    semantic_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Merge two ranked lists using Reciprocal Rank Fusion.
    RRF score = 1/(k + rank).  Higher is better.
    k=60 is the standard default that works well in practice.
    """
    scores: dict[int, float] = {}
    chunk_map: dict[int, dict] = {}

    for rank, chunk in enumerate(semantic_results, start=1):
        chunk_id = chunk["id"]
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
        chunk_map[chunk_id] = chunk

    for rank, chunk in enumerate(bm25_results, start=1):
        chunk_id = chunk["id"]
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
        chunk_map[chunk_id] = chunk

    # Sort by combined RRF score, highest first
    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)

    merged = []
    for cid in sorted_ids:
        chunk = dict(chunk_map[cid])
        chunk["rrf_score"] = scores[cid]
        merged.append(chunk)
    return merged

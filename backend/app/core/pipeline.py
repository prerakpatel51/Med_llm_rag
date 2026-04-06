"""
pipeline.py – the main RAG pipeline.
"""
import time
import asyncio
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import get_settings
from app.models.schemas import QueryRequest, QueryResponse, Citation, SourceSummary
from app.models.database import AsyncSessionLocal
from app.ingestion.embedder import embed_text
from app.services.vector_store import semantic_search, bm25_search, reciprocal_rank_fusion
from app.services.memory_service import find_similar_memories, save_memory
from app.services.trust_scorer import trust_tier
from app.core.judge import check_query, check_answer
from app.core.generation import generate

settings = get_settings()


async def run_pipeline(request: QueryRequest, db: AsyncSession) -> QueryResponse:
    total_start = time.perf_counter()
    return await _pipeline(request, db, total_start)


async def _pipeline(request: QueryRequest, db: AsyncSession, total_start: float) -> QueryResponse:
    query = request.query.strip()
    session_id = request.session_id

    # ── Step 1: Safety pre-filter ─────────────────────────────────────────────
    is_safe, block_reason = check_query(query)
    if not is_safe:
        return QueryResponse(
            answer=block_reason,
            citations=[],
            judge_flagged=True,
            judge_notes=block_reason,
        )

    # ── Step 2: Embed the query ───────────────────────────────────────────────
    query_embedding = embed_text(query)

    # ── Step 3: Retrieval ─────────────────────────────────────────────────────
    retrieval_start = time.perf_counter()

    # Memory lookup — run sequentially to avoid concurrent use of same session
    past_memories = await find_similar_memories(db, query_embedding)
    boosted_chunk_ids = set()
    for mem in past_memories:
        boosted_chunk_ids.update(mem.get("retrieved_chunk_ids") or [])

    # Run semantic and BM25 search sequentially (same session, avoid concurrency issues)
    semantic_results = await semantic_search(
        db,
        query_embedding,
        session_id=session_id,
        top_k=settings.semantic_top_k,
    )
    bm25_results = await bm25_search(
        db,
        query,
        session_id=session_id,
        top_k=settings.bm25_top_k,
    )

    # Merge with Reciprocal Rank Fusion
    merged = reciprocal_rank_fusion(semantic_results, bm25_results)

    # ── Step 4: Re-rank ───────────────────────────────────────────────────────
    for chunk in merged:
        rrf = chunk.get("rrf_score", 0.0)
        trust = chunk.get("trust_score", 0.5)
        memory_boost = settings.memory_boost if chunk["id"] in boosted_chunk_ids else 0.0
        upload_boost = settings.upload_result_boost if chunk.get("source") == "upload" else 0.0
        chunk["final_score"] = 0.70 * rrf + 0.30 * trust + memory_boost + upload_boost

    merged.sort(key=lambda c: c["final_score"], reverse=True)
    top_chunks = merged[: settings.rerank_top_k]
    top_chunks = await _enrich_chunks(db, top_chunks)

    retrieval_latency = time.perf_counter() - retrieval_start

    if not top_chunks:
        return QueryResponse(
            answer=(
                "I could not find any relevant medical literature for your query. "
                "Try rephrasing or using more specific medical terminology."
            ),
            summary="No relevant evidence was retrieved for this query.",
            citations=[],
            sources=[],
        )

    # ── Step 5: Generate ──────────────────────────────────────────────────────
    gen_start = time.perf_counter()
    try:
        model_override = getattr(request, "model", None)
        answer, tokens_in, tokens_out = await generate(query, top_chunks, model_override=model_override)
    except Exception as e:
        raise RuntimeError(f"LLM generation failed: {e}") from e

    generation_latency = time.perf_counter() - gen_start

    # ── Step 6: Judge ─────────────────────────────────────────────────────────
    judge_flagged, judge_notes = False, ""
    if settings.enable_judge:
        judge_flagged, judge_notes = check_answer(answer, top_chunks)

    # ── Step 7: Citations ─────────────────────────────────────────────────────
    citations = _build_citations(top_chunks)

    # ── Step 8: Metrics ───────────────────────────────────────────────────────
    total_latency = time.perf_counter() - total_start

    # ── Step 9: Save memory in background with its OWN session ───────────────
    chunk_ids = [c["id"] for c in top_chunks]
    asyncio.create_task(
        _save_memory_background(session_id, query, answer, query_embedding, chunk_ids)
    )

    return QueryResponse(
        answer=answer,
        summary=_build_summary(answer),
        citations=citations,
        sources=_build_sources(top_chunks),
        judge_flagged=judge_flagged,
        judge_notes=judge_notes,
        retrieval_latency=round(retrieval_latency, 3),
        generation_latency=round(generation_latency, 3),
        total_latency=round(total_latency, 3),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


async def _save_memory_background(
    session_id: str,
    query: str,
    answer: str,
    query_embedding: list[float],
    chunk_ids: list[int],
) -> None:
    """Save conversation memory using its own fresh DB session."""
    try:
        async with AsyncSessionLocal() as db:
            await save_memory(db, session_id, query, answer, query_embedding, chunk_ids)
    except Exception as e:
        print(f"[pipeline] memory save error (non-fatal): {e}")


async def _enrich_chunks(db: AsyncSession, chunks: list[dict]) -> list[dict]:
    if not chunks:
        return []
    chunk_ids = [c["id"] for c in chunks]
    placeholders = ", ".join(f":id_{i}" for i in range(len(chunk_ids)))
    params = {f"id_{i}": cid for i, cid in enumerate(chunk_ids)}

    result = await db.execute(
        text(f"""
            SELECT
                c.id, c.content, c.trust_score, c.source, c.source_id,
                c.document_id,
                d.title, d.authors, d.journal, d.doi, d.url, d.published_at
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.id IN ({placeholders})
        """),
        params,
    )
    rows = result.mappings().all()
    row_map = {row["id"]: dict(row) for row in rows}

    enriched = []
    for chunk in chunks:
        full = row_map.get(chunk["id"], {})
        if not full:
            continue
        full["final_score"] = chunk.get("final_score", 0.0)
        # Carry over the embedding from the retrieval result for the judge
        full["embedding"] = chunk.get("embedding", [])
        enriched.append(full)

    return enriched


def _build_citations(chunks: list[dict]) -> list[Citation]:
    citations = []
    for chunk in chunks:
        score = chunk.get("trust_score", 0.5)
        citations.append(Citation(
            chunk_id=chunk["id"],
            source=chunk.get("source", ""),
            source_id=chunk.get("source_id", ""),
            title=chunk.get("title", ""),
            authors=chunk.get("authors", ""),
            journal=chunk.get("journal", ""),
            doi=chunk.get("doi", ""),
            url=chunk.get("url", ""),
            published_at=chunk.get("published_at"),
            trust_score=score,
            trust_tier=trust_tier(score),
            excerpt=chunk.get("content", "")[:300],
        ))
    return citations


def _build_sources(chunks: list[dict]) -> list[SourceSummary]:
    seen: set[str] = set()
    sources: list[SourceSummary] = []
    for chunk in chunks:
        key = chunk.get("source_id", "")
        if not key or key in seen:
            continue
        seen.add(key)
        sources.append(SourceSummary(
            source=chunk.get("source", ""),
            source_id=key,
            title=chunk.get("title", ""),
            url=chunk.get("url", ""),
            journal=chunk.get("journal", ""),
            published_at=chunk.get("published_at"),
        ))
    return sources


def _build_summary(answer: str) -> str:
    fallback_pattern = re.compile(
        r"The retrieved literature does not directly answer this question",
        flags=re.IGNORECASE,
    )
    if fallback_pattern.search(answer):
        return "No grounded answer was found in the retrieved evidence."

    cleaned = re.sub(
        r"This information is for educational purposes only\..*$",
        "",
        answer,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    cleaned = re.sub(r"\[\d+\]", "", cleaned)
    cleaned = re.sub(r"^According to (the )?evidence chunks,?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", cleaned)
        if part.strip()
    ]
    if not sentences:
        return cleaned[:180]
    return " ".join(sentences[:2])[:180].strip()

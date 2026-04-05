"""
ingest.py – manually trigger ingestion and topic-specific PubMed imports.
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.coordinator import fetch_topic_documents, _store_document
from app.models.database import get_db
from app.models.schemas import SourceSummary, TopicIngestRequest, TopicIngestResponse

router = APIRouter()


@router.post("/api/v1/ingest", tags=["admin"])
async def trigger_ingest(background_tasks: BackgroundTasks):
    """
    Trigger a full ingestion run in the background.
    Returns immediately — check logs for progress.
    """
    background_tasks.add_task(_run_ingestion)
    return {"status": "ingestion started in background — check logs for progress"}


@router.post("/api/v1/ingest/topic", response_model=TopicIngestResponse, tags=["admin"])
async def ingest_topic_from_source(
    request: TopicIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a user-provided topic from PubMed or all supported sources."""
    source_names = None if request.source == "all" else [request.source]
    fetched_batches = await fetch_topic_documents(
        request.topic,
        max_per_source=request.max_results,
        source_names=source_names,
    )

    new_documents = 0
    documents: list[SourceSummary] = []

    for batch in fetched_batches:
        if isinstance(batch, Exception):
            print(f"[ingest topic] fetch error: {batch}")
            continue

        for doc_data in batch:
            if await _store_document(db, doc_data):
                new_documents += 1
            documents.append(SourceSummary(
                source=doc_data["source"],
                source_id=doc_data["source_id"],
                title=doc_data.get("title", ""),
                url=doc_data.get("url", ""),
                journal=doc_data.get("journal", ""),
                published_at=doc_data.get("published_at"),
            ))

    deduped_documents: list[SourceSummary] = []
    seen: set[str] = set()
    for document in documents:
        if document.source_id in seen:
            continue
        seen.add(document.source_id)
        deduped_documents.append(document)

    return TopicIngestResponse(
        topic=request.topic,
        source=request.source,
        new_documents=new_documents,
        documents=deduped_documents[:request.max_results],
    )


async def _run_ingestion():
    from app.ingestion.coordinator import ingest_all_topics
    from app.models.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            # 50 articles per source per topic
            await ingest_all_topics(db, max_per_source=50)
        except Exception as e:
            print(f"[ingest endpoint] error: {e}")

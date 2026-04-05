"""
ingest.py – manually trigger ingestion via POST /api/v1/ingest
Useful on first run to seed the knowledge base without waiting 6 hours.
"""
from fastapi import APIRouter, BackgroundTasks

router = APIRouter()


@router.post("/api/v1/ingest", tags=["admin"])
async def trigger_ingest(background_tasks: BackgroundTasks):
    """
    Trigger a full ingestion run in the background.
    Returns immediately — check logs for progress.
    """
    background_tasks.add_task(_run_ingestion)
    return {"status": "ingestion started in background — check logs for progress"}


async def _run_ingestion():
    from app.ingestion.coordinator import ingest_all_topics
    from app.models.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            # 50 articles per source per topic
            await ingest_all_topics(db, max_per_source=50)
        except Exception as e:
            print(f"[ingest endpoint] error: {e}")

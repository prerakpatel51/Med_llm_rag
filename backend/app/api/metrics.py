"""
metrics.py – /metrics endpoint for Prometheus scraping.
Also updates the document/chunk count gauges from the database on each scrape.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models.database import get_db
import app.services.metrics_service as metrics

router = APIRouter()


@router.get("/metrics", response_class=PlainTextResponse, tags=["monitoring"])
async def get_metrics(db: AsyncSession = Depends(get_db)):
    """
    Expose Prometheus metrics.
    Updates document/chunk counts from DB on every scrape (every 15s).
    """
    # Update document and chunk counts from the database
    try:
        result = await db.execute(text("SELECT COUNT(*) FROM documents"))
        doc_count = result.scalar() or 0

        result = await db.execute(text("SELECT COUNT(*) FROM chunks"))
        chunk_count = result.scalar() or 0

        # Set the gauges (these replace the previous value, not increment)
        metrics.documents_stored_total.set(doc_count)
        metrics.chunks_stored_total.set(chunk_count)
    except Exception:
        pass  # Don't fail metrics scrape if DB is temporarily unavailable

    data = generate_latest()
    return PlainTextResponse(content=data, media_type=CONTENT_TYPE_LATEST)

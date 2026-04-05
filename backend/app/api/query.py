"""
query.py – POST /api/v1/query endpoint.

This is the main endpoint users call with their medical literature questions.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import QueryRequest, QueryResponse
from app.models.database import get_db
from app.core.pipeline import run_pipeline
import app.services.metrics_service as metrics

router = APIRouter()


@router.post("/api/v1/query", response_model=QueryResponse, tags=["assistant"])
async def query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a medical literature question.

    The system will:
    - Check the query for safety (no personal diagnosis requests)
    - Search the knowledge base (semantic + full-text retrieval)
    - Generate a citation-grounded answer using Gemma 3 1B
    - Validate the answer against the retrieved evidence

    Returns the answer with numbered citations and trust scores.
    """
    try:
        response = await run_pipeline(request, db)
        return response
    except RuntimeError as e:
        metrics.errors_total.labels(error_type="pipeline_error").inc()
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        metrics.errors_total.labels(error_type="internal_error").inc()
        raise HTTPException(status_code=500, detail="Internal server error")

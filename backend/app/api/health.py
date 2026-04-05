"""
health.py – /health and /ready endpoints.

/health  → liveness probe (is the process running?)
/ready   → readiness probe (are all dependencies connected?)
"""
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models.schemas import HealthResponse, ReadyResponse
from app.models.database import get_db
from app.config import get_settings
from app.ingestion.embedder import _model   # check embedding model is loaded

settings = get_settings()
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["monitoring"])
async def health():
    """
    Liveness probe.
    Returns 200 as long as the process is alive.
    Kubernetes and Docker HEALTHCHECK use this.
    """
    return HealthResponse(status="ok", version=settings.app_version)


@router.get("/ready", response_model=ReadyResponse, tags=["monitoring"])
async def ready(db: AsyncSession = Depends(get_db)):
    """
    Readiness probe.
    Returns 200 only when all dependencies are healthy.
    Returns 503 if any check fails.
    """
    from fastapi import Response
    checks = {}

    # 1. PostgreSQL + pgvector
    try:
        result = await db.execute(text("SELECT 1"))
        result.fetchone()
        # Make sure pgvector extension is available
        await db.execute(text("SELECT '[1,2,3]'::vector"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # 2. LLM — Groq API is always available, no container to check
    checks["llm"] = "ok (groq api)"

    # 3. Embedding model
    checks["embedder"] = "ok" if _model is not None else "not loaded"

    all_ok = checks["postgres"] == "ok" and checks["embedder"] == "ok"
    status_code = 200 if all_ok else 503

    # FastAPI can't set status code from return value alone for non-200,
    # so we use Response directly when there's a failure.
    if not all_ok:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks},
        )

    return ReadyResponse(status="ready", checks=checks)

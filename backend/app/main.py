import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.config import get_settings
from app.models.database import engine, Base
from app.models.database import AsyncSessionLocal
from app.ingestion.embedder import load_model

# Import ORM models so SQLAlchemy sees them before create_all()
from app.models.orm import document, chunk, query_log, memory  # noqa: F401

from app.api import health, metrics, query, memory as memory_api, status, ingest, uploads

settings = get_settings()
scheduler = AsyncIOScheduler()


async def _run_ingestion():
    """Run ingestion with its own session — called by scheduler only."""
    from app.ingestion.coordinator import ingest_all_topics
    async with AsyncSessionLocal() as db:
        try:
            await ingest_all_topics(db)
        except Exception as e:
            print(f"[ingestion] scheduler job error: {e}")


async def _warm_embedding_model():
    """Warm the embedder after startup without blocking health checks."""
    try:
        print("[startup] Warming embedding model in background…")
        await asyncio.to_thread(load_model)
        print("[startup] Embedding model ready.")
    except Exception as e:
        print(f"[startup] Embedding warmup failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    print("[startup] Ensuring database schema…")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    print("[startup] Database schema ready.")

    # Schedule ingestion every 6 hours — does NOT run at startup
    scheduler.add_job(
        _run_ingestion,
        trigger="cron",
        hour="*/6",
        id="ingest_all",
        replace_existing=True,
    )
    scheduler.start()
    print("[startup] Scheduler started (ingestion runs every 6 hours).")
    print("[startup] To trigger ingestion now: POST /api/v1/ingest")
    asyncio.create_task(_warm_embedding_model())

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    print("[shutdown] Scheduler stopped.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(query.router)
app.include_router(memory_api.router)
app.include_router(status.router)
app.include_router(ingest.router)
app.include_router(uploads.router)

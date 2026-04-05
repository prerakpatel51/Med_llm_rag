"""
memory.py – GET /api/v1/memory endpoint for browsing conversation history.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.schemas import MemoryEntry
from app.services.memory_service import list_memories

router = APIRouter()


@router.get("/api/v1/memory", response_model=list[MemoryEntry], tags=["memory"])
async def get_memory(
    session_id: str = Query(default="default", description="Session ID to filter by"),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Return recent conversation memory entries for a session.
    Useful for the history page in the frontend.
    """
    memories = await list_memories(db, session_id=session_id, limit=limit)
    return [MemoryEntry(**m) for m in memories]

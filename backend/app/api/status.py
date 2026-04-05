"""
status.py – GET /api/v1/status

Returns the LLM provider status. With Groq, it's always ready (no cold start).
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/status", tags=["assistant"])
async def status():
    return {
        "ollama_running": True,      # Groq is always available
        "cold_start_warning": False,  # no cold start with Groq
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
    }

"""
status.py – GET /api/v1/status

The frontend polls this before the user submits a query so it can show
"Model ready" vs "Model will warm up (~15s)" in the UI.
"""
from fastapi import APIRouter
from app.config import get_settings

settings = get_settings()

# Use EC2 GPU manager in production, Docker manager locally
if settings.gpu_ami_id:
    from app.services.ec2_gpu_manager import get_ollama_status
else:
    from app.services.ollama_manager import get_ollama_status

router = APIRouter()


@router.get("/api/v1/status", tags=["assistant"])
async def status():
    """
    Returns the current state of the Ollama container.

    Frontend uses this to show a warm/cold indicator to the user.

    Response:
      {
        "ollama_running": true/false,
        "idle_seconds": 142.3,          # null if never used this session
        "idle_timeout_seconds": 600,
        "cold_start_warning": true/false # true = user should expect ~15s delay
      }
    """
    info = await get_ollama_status()
    return {
        "ollama_running": info["running"],
        "idle_seconds": info["idle_seconds"],
        "idle_timeout_seconds": info["idle_timeout_seconds"],
        "cold_start_warning": not info["running"],
    }

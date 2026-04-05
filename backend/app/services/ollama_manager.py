"""
ollama_manager.py – starts and stops the Ollama Docker container on demand.

How it works:
  - The Ollama container is NOT started at boot.
  - When a query comes in, the backend calls `ensure_ollama_running()`.
  - If the container is stopped, it starts it and waits until ready (~10-15s).
  - A background task tracks the last request time.
  - If no requests arrive for OLLAMA_IDLE_TIMEOUT minutes, the container is stopped.

The frontend shows a "warming up model..." message during the cold start.
"""

import asyncio
import time
import httpx
import docker
from docker.errors import NotFound

from app.config import get_settings

settings = get_settings()

# Name must match the container_name in docker-compose.yml
OLLAMA_CONTAINER_NAME = "medlit-ollama"

# How long (seconds) to wait with no queries before stopping the container
IDLE_TIMEOUT_SECONDS = int(getattr(settings, "ollama_idle_timeout", 600))  # 10 min default

# How often the idle checker runs (seconds)
IDLE_CHECK_INTERVAL = 60

# Timestamp of the last query that needed Ollama
_last_used_at: float = 0.0

# Lock so two simultaneous requests don't both try to start the container
_start_lock = asyncio.Lock()

# Flag so the idle checker loop runs only once
_idle_checker_started = False


def _get_docker_client():
    """Return a Docker client connected to the local Docker socket."""
    return docker.from_env()


def _get_container():
    """Return the Ollama container object, or None if it doesn't exist."""
    client = _get_docker_client()
    try:
        return client.containers.get(OLLAMA_CONTAINER_NAME)
    except NotFound:
        return None


def _container_is_running() -> bool:
    """Return True if the Ollama container is currently running."""
    container = _get_container()
    return container is not None and container.status == "running"


def _start_container() -> None:
    """Start the Ollama container (blocking, runs in a thread pool)."""
    container = _get_container()
    if container is None:
        raise RuntimeError(
            f"Container '{OLLAMA_CONTAINER_NAME}' not found. "
            "Make sure you started the stack with: docker compose up -d"
        )
    if container.status != "running":
        container.start()


def _stop_container() -> None:
    """Stop the Ollama container (blocking, runs in a thread pool)."""
    container = _get_container()
    if container is not None and container.status == "running":
        container.stop(timeout=10)
        print("[ollama_manager] Container stopped due to idle timeout.")


async def _wait_for_ollama_ready(timeout: int = 300) -> None:
    """
    Poll Ollama's /api/tags endpoint until it responds or we time out.
    300s timeout covers the case where the model is still downloading.
    """
    deadline = time.time() + timeout
    async with httpx.AsyncClient(timeout=5) as client:
        while time.time() < deadline:
            try:
                resp = await client.get(f"{settings.ollama_base_url}/api/tags")
                if resp.status_code == 200:
                    print("[ollama_manager] Ollama is responding.")
                    return
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            await asyncio.sleep(3)
    raise RuntimeError("Ollama did not become ready within 5 minutes.")


async def ensure_ollama_running() -> bool:
    """
    Call this before every generation request.

    Returns:
        True  – Ollama was already running (fast path)
        False – Ollama had to be started (cold start, ~10-15s extra latency)

    Raises RuntimeError if the container can't be started.
    """
    global _last_used_at, _idle_checker_started

    _last_used_at = time.time()

    # Fast path: already running, nothing to do
    if _container_is_running():
        return True

    # Slow path: need to start the container
    # Use a lock so concurrent requests don't all try to start it at once
    async with _start_lock:
        # Check again inside the lock (another request may have started it)
        if _container_is_running():
            return False

        print("[ollama_manager] Cold start: starting Ollama container...")
        # Run the blocking Docker API call in a thread so we don't block the event loop
        await asyncio.to_thread(_start_container)
        await _wait_for_ollama_ready()
        print("[ollama_manager] Ollama is ready.")

    # Start the idle checker the first time Ollama is launched
    if not _idle_checker_started:
        _idle_checker_started = True
        asyncio.create_task(_idle_checker_loop())

    return False   # was a cold start


def record_usage() -> None:
    """Call this after every successful generation to reset the idle timer."""
    global _last_used_at
    _last_used_at = time.time()


async def _idle_checker_loop() -> None:
    """
    Background task: stop Ollama if it has been idle for IDLE_TIMEOUT_SECONDS.
    Runs every IDLE_CHECK_INTERVAL seconds forever.
    """
    while True:
        await asyncio.sleep(IDLE_CHECK_INTERVAL)
        try:
            idle_seconds = time.time() - _last_used_at
            if idle_seconds >= IDLE_TIMEOUT_SECONDS and _container_is_running():
                print(
                    f"[ollama_manager] Idle for {idle_seconds:.0f}s "
                    f"(limit {IDLE_TIMEOUT_SECONDS}s). Stopping container..."
                )
                await asyncio.to_thread(_stop_container)
        except Exception as e:
            # Never let the checker crash — just log and continue
            print(f"[ollama_manager] idle checker error: {e}")


async def get_ollama_status() -> dict:
    """Return current status info for the /ready endpoint and frontend."""
    running = _container_is_running()
    idle_seconds = time.time() - _last_used_at if _last_used_at > 0 else None
    return {
        "running": running,
        "idle_seconds": round(idle_seconds, 1) if idle_seconds is not None else None,
        "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
    }

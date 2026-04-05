"""
ec2_gpu_manager.py – manages a spot g4dn.xlarge GPU instance on demand.

How it works:
  1. User sends a query → backend calls `ensure_ollama_running()`
  2. If no GPU instance exists → launch a spot g4dn.xlarge from a custom AMI
  3. Wait for Ollama to be ready on the GPU instance (~2-3 min cold start)
  4. Backend sends generation request to the GPU instance's Ollama
  5. After GPU_IDLE_TIMEOUT seconds with no queries → terminate the instance
  6. Cost: only pay for the minutes the GPU is actually running

Prerequisites:
  - A custom AMI with Ollama installed and qwen2.5:14b already pulled
  - Security group allowing inbound port 11434 from the backend
  - IAM role on the backend EC2 with ec2:RunInstances, ec2:TerminateInstances, etc.
"""

import asyncio
import time
import httpx
import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

settings = get_settings()

# ── State ─────────────────────────────────────────────────────────────────────
_instance_id: str | None = None
_instance_ip: str | None = None
_last_used_at: float = 0.0
_start_lock = asyncio.Lock()
_idle_checker_started = False

# Tag used to find our GPU instance
GPU_TAG = "med-llm-rag-gpu"


def _get_ec2_client():
    """Return a boto3 EC2 client."""
    return boto3.client("ec2", region_name=settings.aws_region)


def _get_ec2_resource():
    """Return a boto3 EC2 resource."""
    return boto3.resource("ec2", region_name=settings.aws_region)


def _find_running_instance() -> dict | None:
    """Check if a GPU instance is already running (tagged with our name)."""
    ec2 = _get_ec2_client()
    try:
        resp = ec2.describe_instances(
            Filters=[
                {"Name": "tag:Name", "Values": [GPU_TAG]},
                {"Name": "instance-state-name", "Values": ["running", "pending"]},
            ]
        )
        for reservation in resp.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                return {
                    "instance_id": instance["InstanceId"],
                    "public_ip": instance.get("PublicIpAddress"),
                    "state": instance["State"]["Name"],
                }
    except ClientError as e:
        print(f"[ec2_gpu] Error checking instances: {e}")
    return None


def _launch_spot_instance() -> str:
    """Launch a spot g4dn.xlarge and return instance ID."""
    ec2 = _get_ec2_client()

    # User data script that starts Ollama on boot
    user_data = """#!/bin/bash
# Start Ollama server
/usr/local/bin/ollama serve &

# Wait for Ollama to be ready, then ensure model is loaded
sleep 5
/usr/local/bin/ollama pull {model}
""".format(model=settings.ollama_model)

    launch_params = {
        "ImageId": settings.gpu_ami_id,
        "InstanceType": settings.gpu_instance_type,
        "MinCount": 1,
        "MaxCount": 1,
        "KeyName": settings.gpu_key_name,
        "UserData": user_data,
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": GPU_TAG}],
            }
        ],
        "InstanceMarketOptions": {
            "MarketType": "spot",
            "SpotOptions": {
                "MaxPrice": settings.gpu_spot_max_price,
                "SpotInstanceType": "one-time",
                "InstanceInterruptionBehavior": "terminate",
            },
        },
    }

    # Add security group if configured
    if settings.gpu_security_group:
        launch_params["SecurityGroupIds"] = [settings.gpu_security_group]

    # Add subnet if configured
    if settings.gpu_subnet_id:
        launch_params["SubnetId"] = settings.gpu_subnet_id

    resp = ec2.run_instances(**launch_params)
    instance_id = resp["Instances"][0]["InstanceId"]
    print(f"[ec2_gpu] Launched spot instance: {instance_id}")
    return instance_id


def _wait_for_instance_running(instance_id: str, timeout: int = 300) -> str:
    """Wait for instance to enter 'running' state and return public IP."""
    ec2 = _get_ec2_client()
    deadline = time.time() + timeout

    while time.time() < deadline:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        instance = resp["Reservations"][0]["Instances"][0]
        state = instance["State"]["Name"]
        public_ip = instance.get("PublicIpAddress")

        if state == "running" and public_ip:
            print(f"[ec2_gpu] Instance {instance_id} running at {public_ip}")
            return public_ip
        elif state in ("terminated", "shutting-down"):
            raise RuntimeError(f"GPU instance {instance_id} was terminated unexpectedly")

        time.sleep(5)

    raise RuntimeError(f"GPU instance {instance_id} did not start within {timeout}s")


def _terminate_instance(instance_id: str) -> None:
    """Terminate the GPU instance."""
    ec2 = _get_ec2_client()
    try:
        ec2.terminate_instances(InstanceIds=[instance_id])
        print(f"[ec2_gpu] Terminated instance: {instance_id}")
    except ClientError as e:
        print(f"[ec2_gpu] Error terminating {instance_id}: {e}")


async def _wait_for_ollama_ready(ip: str, timeout: int = 300) -> None:
    """Poll Ollama on the GPU instance until it responds."""
    url = f"http://{ip}:11434/api/tags"
    deadline = time.time() + timeout

    async with httpx.AsyncClient(timeout=5) as client:
        while time.time() < deadline:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    # Check if model is loaded
                    data = resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    if any(settings.ollama_model in m for m in models):
                        print(f"[ec2_gpu] Ollama ready with model at {ip}")
                        return
                    else:
                        print(f"[ec2_gpu] Ollama up but model still loading... ({models})")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
                pass
            await asyncio.sleep(5)

    raise RuntimeError(f"Ollama on {ip} did not become ready within {timeout}s")


async def ensure_ollama_running() -> bool:
    """
    Ensure a GPU instance with Ollama is running.
    Updates settings.ollama_base_url to point at the GPU instance.

    Returns:
        True  – already running (fast path)
        False – had to start (cold start, ~2-3 min)
    """
    global _instance_id, _instance_ip, _last_used_at, _idle_checker_started

    _last_used_at = time.time()

    # Fast path: we know an instance is running
    if _instance_id and _instance_ip:
        # Quick health check
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"http://{_instance_ip}:11434/api/tags")
                if resp.status_code == 200:
                    settings.ollama_base_url = f"http://{_instance_ip}:11434"
                    return True
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
            # Instance may have been terminated by AWS (spot interruption)
            print("[ec2_gpu] Instance no longer responding, will re-launch")
            _instance_id = None
            _instance_ip = None

    # Check if there's already a tagged instance running (from previous session)
    existing = await asyncio.to_thread(_find_running_instance)
    if existing and existing.get("public_ip"):
        _instance_id = existing["instance_id"]
        _instance_ip = existing["public_ip"]
        settings.ollama_base_url = f"http://{_instance_ip}:11434"

        try:
            await _wait_for_ollama_ready(_instance_ip, timeout=30)
            if not _idle_checker_started:
                _idle_checker_started = True
                asyncio.create_task(_idle_checker_loop())
            return True
        except RuntimeError:
            # Instance exists but Ollama not ready — wait longer
            await _wait_for_ollama_ready(_instance_ip, timeout=270)
            if not _idle_checker_started:
                _idle_checker_started = True
                asyncio.create_task(_idle_checker_loop())
            return False

    # Slow path: launch new spot instance
    async with _start_lock:
        # Double-check inside lock
        if _instance_id and _instance_ip:
            settings.ollama_base_url = f"http://{_instance_ip}:11434"
            return True

        print("[ec2_gpu] Cold start: launching spot GPU instance...")
        _instance_id = await asyncio.to_thread(_launch_spot_instance)
        _instance_ip = await asyncio.to_thread(
            _wait_for_instance_running, _instance_id
        )
        await _wait_for_ollama_ready(_instance_ip)

        settings.ollama_base_url = f"http://{_instance_ip}:11434"
        print(f"[ec2_gpu] GPU ready at {_instance_ip}")

    # Start idle checker
    if not _idle_checker_started:
        _idle_checker_started = True
        asyncio.create_task(_idle_checker_loop())

    return False


def record_usage() -> None:
    """Call after every generation to reset the idle timer."""
    global _last_used_at
    _last_used_at = time.time()


async def _idle_checker_loop() -> None:
    """Background loop: terminate GPU instance after idle timeout."""
    global _instance_id, _instance_ip

    while True:
        await asyncio.sleep(30)  # check every 30s
        try:
            if not _instance_id:
                continue

            idle_seconds = time.time() - _last_used_at
            if idle_seconds >= settings.gpu_idle_timeout:
                print(
                    f"[ec2_gpu] GPU idle for {idle_seconds:.0f}s "
                    f"(limit {settings.gpu_idle_timeout}s). Terminating..."
                )
                await asyncio.to_thread(_terminate_instance, _instance_id)
                _instance_id = None
                _instance_ip = None
        except Exception as e:
            print(f"[ec2_gpu] idle checker error: {e}")


async def get_ollama_status() -> dict:
    """Return current GPU instance status for the frontend."""
    running = _instance_id is not None and _instance_ip is not None
    idle_seconds = time.time() - _last_used_at if _last_used_at > 0 else None

    return {
        "running": running,
        "instance_id": _instance_id,
        "instance_ip": _instance_ip,
        "idle_seconds": round(idle_seconds, 1) if idle_seconds is not None else None,
        "idle_timeout_seconds": settings.gpu_idle_timeout,
        "instance_type": settings.gpu_instance_type,
        "cold_start_warning": not running,
    }

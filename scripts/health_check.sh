#!/usr/bin/env bash
# health_check.sh – quick check of all service health endpoints.
set -euo pipefail

BASE_URL="${1:-http://localhost}"

echo "Checking /health  …"
curl -sf "${BASE_URL}:8000/health" | python3 -m json.tool

echo ""
echo "Checking /ready   …"
curl -sf "${BASE_URL}:8000/ready" | python3 -m json.tool

#!/usr/bin/env bash
# setup.sh – first-run setup for the Medical Literature Assistant.
#
# What this script does:
#   1. Checks that Docker and Docker Compose are installed
#   2. Creates the .env file from .env.example if it doesn't exist
#   3. Builds images and starts all containers
#   4. Waits for all services to be healthy
#   5. Prints the URLs to access the app

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Medical Literature Assistant – First-Time Setup ===${NC}"

# Check Docker
if ! command -v docker &>/dev/null; then
  echo "ERROR: Docker is not installed. Please install Docker first."
  echo "  https://docs.docker.com/get-docker/"
  exit 1
fi

# Check Docker Compose
if ! docker compose version &>/dev/null; then
  echo "ERROR: Docker Compose v2 is not installed."
  echo "  https://docs.docker.com/compose/install/"
  exit 1
fi

# Create .env from example if it doesn't exist
if [ ! -f .env ]; then
  echo -e "${YELLOW}Creating .env from .env.example…${NC}"
  cp .env.example .env
  echo "  Edit .env to set your NCBI_API_KEY and change passwords before going to production."
fi

# Build images
echo -e "\n${GREEN}Building Docker images…${NC}"
docker compose build

# Start all containers in detached mode
echo -e "\n${GREEN}Starting containers…${NC}"
docker compose up -d

# Wait for backend to be healthy (max 5 minutes)
echo -e "\n${GREEN}Waiting for backend to be ready…${NC}"
MAX_WAIT=300
WAITED=0
until docker compose exec -T backend curl -sf http://localhost:8000/health > /dev/null 2>&1; do
  if [ "$WAITED" -ge "$MAX_WAIT" ]; then
    echo "ERROR: Backend did not become healthy within ${MAX_WAIT}s."
    echo "Check logs: docker compose logs backend"
    exit 1
  fi
  echo "  Still starting… (${WAITED}s elapsed)"
  sleep 10
  WAITED=$((WAITED + 10))
done

echo -e "\n${GREEN}✓ All services are running!${NC}"
echo ""
echo "  App:       http://localhost:3000"
echo "  API docs:  http://localhost:8000/docs"
echo "  Grafana:   http://localhost:3001  (admin / see GF_SECURITY_ADMIN_PASSWORD in .env)"
echo "  Prometheus: http://localhost:9090"
echo ""
echo "  View logs:  docker compose logs -f"
echo "  Stop:       docker compose down"

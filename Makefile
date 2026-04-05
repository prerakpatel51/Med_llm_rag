# Makefile – convenience targets for the Medical Literature Assistant

.PHONY: setup up down logs build shell-backend psql test

# First-time setup
setup:
	bash scripts/setup.sh

# Start all services
up:
	docker compose up -d

# Stop all services (data is preserved in volumes)
down:
	docker compose down

# Stop and delete all data (WARNING: destroys the database and model cache)
down-volumes:
	docker compose down -v

# Rebuild images after code changes, then restart
build:
	docker compose build && docker compose up -d

# Follow logs for all services (Ctrl+C to stop)
logs:
	docker compose logs -f

# Follow logs for just the backend
logs-backend:
	docker compose logs -f backend

# Open a shell in the backend container (for debugging)
shell-backend:
	docker compose exec backend bash

# Connect to PostgreSQL
psql:
	docker compose exec postgres psql -U medlit -d medlit

# Run health check
health:
	bash scripts/health_check.sh

# Run the test suite inside the backend container
test:
	docker compose exec backend python -m pytest tests/ -v

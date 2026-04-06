# Medical Literature Assistant

Medical Literature Assistant is a retrieval-augmented research app for grounded medical Q&A. It combines a FastAPI backend, a Next.js frontend, PostgreSQL with `pgvector`, session-scoped PDF uploads, topic-based PubMed ingestion, and Groq-hosted generation.

This repository currently supports two practical modes:

- local development with Docker Compose
- AWS deployment with `S3 + CloudFront` for the frontend and a scalable backend path of `CloudFront -> ALB -> Auto Scaling Group -> RDS`

This project is for literature research and education. It is not a diagnosis or treatment tool.

## What The App Does

- Answers questions using retrieved evidence from the indexed database and uploaded PDFs.
- Lets users upload up to `5` PDFs per batch with a combined limit of `40 MB`.
- Lets users ingest a topic from `PubMed` or from `all` configured sources before asking follow-up questions.
- Returns:
  - a direct answer
  - a short summary
  - a source list
  - evidence passages with trust tiers
- Stores conversation history per session for the history page.

## Current Production Links

- Main site: `https://d3jhehgg6t7to2.cloudfront.net`
- History page: `https://d3jhehgg6t7to2.cloudfront.net/history/`
- Health check: `https://d3jhehgg6t7to2.cloudfront.net/health`
- API base: `https://d3jhehgg6t7to2.cloudfront.net/api/v1/`
- Direct ALB health check: `http://med-llm-rag-backend-alb-202945636.us-east-1.elb.amazonaws.com/health`

CloudFront details:

- Distribution ID: `E21OVYP1USAXXX`
- CloudFront domain: `d3jhehgg6t7to2.cloudfront.net`
- Custom domain: not configured

If you need to look up the site URL later:

```bash
aws cloudfront list-distributions \
  --query 'DistributionList.Items[].{Id:Id,Domain:DomainName,Aliases:Aliases.Items}' \
  --output table
```

## Architecture

### Local Development

Local development uses:

- `frontend`: Next.js
- `backend`: FastAPI
- `postgres`: PostgreSQL 16 with `pgvector`

Local Compose file:

- [docker-compose.yml](/Users/prerak/Desktop/pk/docker-compose.yml)

### Current Production

Current production uses:

- `S3 + CloudFront` for static frontend hosting
- `CloudFront` path routing for `/api/*` and `/health`
- `Application Load Balancer`
- `Auto Scaling Group` for backend EC2 instances
- `RDS PostgreSQL`

The live production path is:

`CloudFront -> ALB -> ASG backend -> RDS`

The old self-hosted Grafana/Prometheus stack is no longer part of the active deployment or this repository.

## Core Stack

- Backend: FastAPI
- Frontend: Next.js App Router
- Database: PostgreSQL 16 + `pgvector`
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`
- Generation: Groq API, default model `llama-3.3-70b-versatile`
- Scheduler: APScheduler
- Infra: AWS CloudFront, ALB, Auto Scaling Group, RDS, ECR, S3

## Main Features

- Grounded question answering over stored medical literature
- Session-scoped PDF upload retrieval
- Topic-specific ingestion via `POST /api/v1/ingest/topic`
- Stored session memory for the history page
- Short summary plus evidence-backed answer format
- Health and readiness endpoints for deployment checks

## Local Setup

### Requirements

- Docker
- Docker Compose v2
- A Groq API key

Optional but recommended:

- NCBI API key
- NCBI email

### 1. Create The Environment File

```bash
cp .env.example .env
```

Set at least:

- `GROQ_API_KEY`
- `SECRET_KEY`

Optional but useful:

- `NCBI_API_KEY`
- `NCBI_EMAIL`

Reference file:

- [.env.example](/Users/prerak/Desktop/pk/.env.example)

### 2. Start The App

```bash
bash scripts/setup.sh
```

That script:

- creates `.env` if missing
- builds the Docker images
- starts the local stack
- waits for the backend to answer `/health`

Script:

- [setup.sh](/Users/prerak/Desktop/pk/scripts/setup.sh)

### 3. Open The App

- App: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Ready: `http://localhost:8000/ready`

### 4. Run A Health Check

```bash
bash scripts/health_check.sh
```

Script:

- [health_check.sh](/Users/prerak/Desktop/pk/scripts/health_check.sh)

## Local Services And Ports

- Frontend: `3000`
- Backend: `8000`
- PostgreSQL: `5432`

## Environment Variables

Key backend settings live in:

- [config.py](/Users/prerak/Desktop/pk/backend/app/config.py)

Important env vars:

- `DATABASE_URL`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `GROQ_API_KEY`
- `LLM_MODEL`
- `NCBI_API_KEY`
- `NCBI_EMAIL`
- `SECRET_KEY`
- `DEBUG`
- `LOG_LEVEL`

Runtime limits currently enforced by config:

- max query length: `1000`
- max PDF upload files: `5`
- max PDF upload size: `40 MB`

## API Surface

Key routes:

- `GET /health`
- `GET /ready`
- `POST /api/v1/query`
- `GET /api/v1/memory`
- `POST /api/v1/ingest`
- `POST /api/v1/ingest/topic`
- `POST /api/v1/uploads/pdfs`

Relevant backend files:

- [main.py](/Users/prerak/Desktop/pk/backend/app/main.py)
- [query.py](/Users/prerak/Desktop/pk/backend/app/api/query.py)
- [memory.py](/Users/prerak/Desktop/pk/backend/app/api/memory.py)
- [ingest.py](/Users/prerak/Desktop/pk/backend/app/api/ingest.py)
- [uploads.py](/Users/prerak/Desktop/pk/backend/app/api/uploads.py)
- [schemas.py](/Users/prerak/Desktop/pk/backend/app/models/schemas.py)

## Frontend Behavior

The frontend uses same-origin API paths in the browser so CloudFront can front both static content and backend routes without mixed-content issues.

Relevant frontend files:

- [api.ts](/Users/prerak/Desktop/pk/frontend/src/lib/api.ts)
- [types.ts](/Users/prerak/Desktop/pk/frontend/src/lib/types.ts)
- [ChatWindow.tsx](/Users/prerak/Desktop/pk/frontend/src/components/chat/ChatWindow.tsx)

User-facing pages:

- `/`
- `/history/`

## Deployment

The GitHub Actions workflow deploys on every push to `main`.

Workflow:

- [deploy.yml](/Users/prerak/Desktop/pk/.github/workflows/deploy.yml)

What it does:

1. runs backend tests if a `backend/tests` directory exists
2. builds and pushes the backend Docker image to ECR
3. builds the static frontend
4. uploads the frontend to S3
5. ensures CloudFront routes `/api/*` and `/health`
6. refreshes the backend Auto Scaling Group, or falls back to the legacy single-EC2 path if no ASG is found
7. invalidates CloudFront

Required GitHub secrets:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `EC2_HOST`
- `EC2_SSH_KEY`
- `EC2_USER`
- `S3_BUCKET`
- `CLOUDFRONT_DISTRIBUTION`
- `DB_PASSWORD`
- `SECRET_KEY`
- `NCBI_API_KEY`
- `NCBI_EMAIL`

## AWS Notes

### Cheapest Correct Scalable Setup

If you want one backend instance normally and a second only during higher load, the practical architecture is:

- `S3 + CloudFront` for frontend
- `CloudFront /api/* -> ALB`
- `ALB -> Auto Scaling Group`
- `RDS PostgreSQL`

Recommended ASG settings:

- `min = 1`
- `desired = 1`
- `max = 2`

### Current Infra Helpers

Relevant infra files:

- [setup_aws.sh](/Users/prerak/Desktop/pk/infra/setup_aws.sh)
- [create_iam_user.sh](/Users/prerak/Desktop/pk/infra/create_iam_user.sh)
- [provision_scalable_backend.sh](/Users/prerak/Desktop/pk/infra/provision_scalable_backend.sh)
- [migrate_postgres_to_rds.sh](/Users/prerak/Desktop/pk/infra/migrate_postgres_to_rds.sh)
- [backend-compose.yml](/Users/prerak/Desktop/pk/infra/backend-compose.yml)

## Kubernetes

The `k8s/` directory still exists as a secondary/demo deployment path. It is not the primary production path.

## Repo Structure

```text
pk/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── ingestion/
│   │   ├── models/
│   │   └── services/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── store/
│   └── Dockerfile
├── infra/
├── k8s/
├── scripts/
├── docker-compose.yml
├── docker-compose.prod.yml
└── .github/workflows/deploy.yml
```

## Operational Notes

- The backend warms the embedding model in the background after startup.
- `/health` is a liveness check.
- `/ready` verifies database access and embedding model readiness.
- Uploaded PDFs are scoped to the current session.
- The frontend history page reads from `GET /api/v1/memory`.
- There is no custom domain configured right now.

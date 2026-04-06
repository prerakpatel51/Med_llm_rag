# Medical Literature Assistant

A low-cost, retrieval-augmented medical literature assistant that runs on a single EC2 instance (or your local machine). It searches PubMed, CDC, WHO, FDA, and NIH to give you citation-grounded answers using **Gemma 3 1B** — a tiny open-source LLM that runs entirely on CPU.

> ⚕️ **Research use only.** This tool summarizes published literature. It is not a substitute for professional medical advice, diagnosis, or treatment.

## Product capabilities

- Ask questions against the shared literature database and your session-scoped uploaded PDFs in one query.
- Upload up to **5 PDF files** per batch with a **40 MB combined size limit**.
- Ingest a user-provided topic from **PubMed only** or from **all supported sources** before asking follow-up questions.
- Every answer returns a direct answer, a short summary, and the source list used to ground the response.
- Topic-ingested sources appear in the UI immediately so users can review what was added before querying.

---

## Architecture

```
User Query
    │
    ▼
[FastAPI Backend]
    │
    ├── [Safety pre-filter] – blocks personal diagnosis requests
    │
    ├── [Query embedding]   – all-MiniLM-L6-v2 (22 MB, CPU, 384-dim)
    │
    ├── [Memory lookup]     – find similar past queries in pgvector
    │
    ├── [Dual retrieval]
    │     ├── Semantic search  – pgvector cosine ANN
    │     └── Full-text search – PostgreSQL tsvector (BM25-style)
    │
    ├── [Reciprocal Rank Fusion] – merge both result lists
    │
    ├── [Re-ranking] – 70% RRF score + 30% trust score + memory boost
    │
    ├── [Gemma 3 1B via Ollama] – evidence-only generation
    │
    ├── [Judge] – checks every sentence is grounded in retrieved evidence
    │
    └── [Response] – answer + numbered citations + trust tier badges
```

### Key design choices

| Decision | Why |
|---|---|
| **Gemma 3 1B** | Runs on CPU, <800 MB RAM in Q4_K_M quantization |
| **all-MiniLM-L6-v2** | 22 MB, 384-dim, fast CPU inference, no API cost |
| **Retrieval-first** | LLM never generates from memory alone |
| **Dual retrieval + RRF** | Semantic search finds related concepts; BM25 finds exact terms |
| **Trust scoring** | Source authority + publication type + recency + citations |
| **Stateless judge** | Regex + embedding similarity — no extra LLM call, zero cost |
| **Docker Compose** | Runs on a single node, all services wired together |

### Trust tiers

| Tier | Score | Examples |
|---|---|---|
| **A** (green) | ≥ 0.80 | CDC, WHO, FDA guidelines; PubMed RCTs |
| **B** (amber) | 0.60–0.79 | PubMed reviews, PMC articles |
| **C** (red) | < 0.60 | Preprints, unknown publication type |

---

## Services

| Service | Port | Description |
|---|---|---|
| Frontend | 3000 | Next.js chat UI |
| Backend | 8000 | FastAPI (+ Swagger at `/docs`) |
| PostgreSQL | 5432 | Database + pgvector |

---

## Local deployment

### Prerequisites

- Docker ≥ 24 and Docker Compose v2
- 6 GB free disk (model weights + database)
- 4 GB RAM minimum (8 GB recommended)

### Step 1 – Clone and configure

```bash
git clone <repo-url> medical-lit-assistant
cd medical-lit-assistant

# Copy the example env file and edit if needed
cp .env.example .env
# Optional: add your free NCBI API key for higher PubMed rate limits
# Get one at: https://www.ncbi.nlm.nih.gov/account/
```

### Step 2 – Start everything

```bash
# First-time setup (builds images, starts containers, waits for health)
bash scripts/setup.sh

# Or manually:
docker compose up -d
```

Gemma 3 1B (~800 MB) downloads automatically on first start. This takes 1–3 minutes depending on your internet connection.

### Step 3 – Open the app

| URL | What |
|---|---|
| http://localhost:3000 | Chat interface |
| http://localhost:8000/docs | Interactive API docs |

### Useful commands

```bash
make logs          # follow all logs
make logs-backend  # follow backend only
make health        # check /health and /ready
make psql          # connect to PostgreSQL
make shell-backend # bash inside the backend container
make down          # stop (data preserved)
make down-volumes  # stop AND delete all data
```

---

## AWS deployment (single EC2 instance)

### Recommended instance

| Use case | Instance | Notes |
|---|---|---|
| Development / light traffic | t3.medium (4 GB RAM) | Use Q4_0 quantization for Ollama |
| Production | t3.large (8 GB RAM) | Comfortable headroom |

### Step 1 – Launch EC2

1. Go to EC2 → Launch Instance
2. Choose **Ubuntu 24.04 LTS**
3. Instance type: **t3.large**
4. Storage: **30 GB gp3** (default 8 GB is too small)
5. Security group — open inbound:
   - Port 22 (SSH)
   - Port 3000 (frontend)
   - Port 8000 (backend API, optional)

### Step 2 – Install Docker

```bash
# SSH into your instance
ssh -i your-key.pem ubuntu@<EC2-PUBLIC-IP>

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
newgrp docker

# Verify
docker --version
docker compose version
```

### Step 3 – Deploy the app

```bash
# Copy the project to EC2 (from your local machine)
scp -i your-key.pem -r medical-lit-assistant ubuntu@<EC2-PUBLIC-IP>:~/

# On the EC2 instance
cd ~/medical-lit-assistant
cp .env.example .env
# Edit .env: set strong passwords and your NCBI API key
nano .env

bash scripts/setup.sh
```

### Step 4 – (Optional) Add a domain + HTTPS with Nginx

```bash
sudo apt install -y nginx certbot python3-certbot-nginx

# Create Nginx config
sudo tee /etc/nginx/sites-available/medlit > /dev/null <<'EOF'
server {
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_read_timeout 120s;
    }

}
EOF

sudo ln -s /etc/nginx/sites-available/medlit /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Get a free TLS certificate
sudo certbot --nginx -d your-domain.com
```

If you serve the frontend from `https://` (for example S3 + CloudFront), do not point the browser directly at `http://<EC2-IP>:8000`. Modern browsers will block that as mixed content or fail the network request. Route `/api` and `/health` through the same HTTPS domain, or put the backend behind its own HTTPS endpoint.

### Estimated AWS cost

| Resource | Cost |
|---|---|
| t3.large on-demand | ~$0.08/hr (~$60/month) |
| 30 GB gp3 EBS | ~$2.40/month |
| Data transfer | Minimal for personal use |
| **Total** | **~$62/month** |

To reduce cost: stop the instance when not in use, or use a t3.medium (~$30/month) with reduced Ollama memory limits.

## Cheapest Correct Scalable Architecture

If you want to keep **one EC2 instance normally** and scale out only when user traffic increases, the low-cost production-safe target architecture is:

- `S3 + CloudFront` for the frontend
- `CloudFront /api/* -> ALB`
- `ALB -> Auto Scaling Group of backend-only EC2 instances`
- `RDS PostgreSQL` shared by all backend instances
- optional observability added separately later, if needed

### Why this change is required

- The old `docker-compose.prod.yml` layout bundled too many services on one box.
- Adding another backend container on the same instance does **not** solve memory pressure if memory is already high.
- Multiple EC2 instances require a **shared database** and a **load balancer** or traffic will still hit only one server.

### Practical order for scaling

1. Create `RDS PostgreSQL`.
2. Split the backend out from the all-in-one EC2 compose layout.
3. Create an `ALB` and backend target group.
4. Create a launch template and `Auto Scaling Group`.
5. Update CloudFront `/api/*` to point to the ALB.
6. Add a scaling policy, typically CPU first and memory second.

## Live URLs

Current production links:

| URL | Purpose |
|---|---|
| https://d3jhehgg6t7to2.cloudfront.net | Main site |
| https://d3jhehgg6t7to2.cloudfront.net/history/ | History page |
| https://d3jhehgg6t7to2.cloudfront.net/health | Public health check through CloudFront |
| https://d3jhehgg6t7to2.cloudfront.net/api/v1/ | API base through CloudFront |
| http://med-llm-rag-backend-alb-202945636.us-east-1.elb.amazonaws.com/health | Direct ALB health check |

CloudFront details:

- Distribution ID: `E21OVYP1USAXXX`
- CloudFront domain: `d3jhehgg6t7to2.cloudfront.net`
- Custom domain: not configured

If you need to look the site URL up later, run:

```bash
aws cloudfront list-distributions \
  --query 'DistributionList.Items[].{Id:Id,Domain:DomainName,Aliases:Aliases.Items}' \
  --output table
```

### Recommended autoscaling settings

- `min = 1`
- `desired = 1`
- `max = 2`

That keeps one instance running normally and launches a second backend instance only when the scaling threshold is crossed.

---

## Kubernetes deployment (portfolio/demo)

The `k8s/` directory contains plain YAML manifests. Apply them in order:

```bash
# 1. Create namespace
kubectl apply -f k8s/namespace.yaml

# 2. Create config and secrets (edit secrets.yaml first!)
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml

# 3. Database
kubectl apply -f k8s/postgres/

# 4. Ollama (LLM server)
kubectl apply -f k8s/ollama/

# 5. Backend and frontend
kubectl apply -f k8s/backend/
kubectl apply -f k8s/frontend/

# 6. Ingress (edit hostname in ingress.yaml first)
kubectl apply -f k8s/ingress/
```

> Note: The k8s manifests are for portfolio demonstration. The Docker Compose setup is the optimized primary deployment target.

---

## Project structure

```
medical-lit-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, startup/shutdown
│   │   ├── config.py             # All settings (from env vars)
│   │   ├── api/
│   │   │   ├── health.py         # /health, /ready
│   │   │   ├── query.py          # POST /api/v1/query
│   │   │   ├── ingest.py         # topic ingestion + background seeding
│   │   │   ├── uploads.py        # PDF upload ingestion
│   │   │   └── memory.py         # GET /api/v1/memory
│   │   ├── core/
│   │   │   ├── pipeline.py       # Main RAG orchestrator ← start here
│   │   │   ├── generation.py     # Ollama client
│   │   │   └── judge.py          # Safety + claim grounding
│   │   ├── ingestion/
│   │   │   ├── coordinator.py    # Orchestrates all fetchers
│   │   │   ├── chunker.py        # Text splitting
│   │   │   ├── embedder.py       # all-MiniLM-L6-v2
│   │   │   └── sources/          # PubMed, CDC, WHO, FDA
│   │   ├── models/
│   │   │   ├── database.py       # SQLAlchemy async engine
│   │   │   ├── schemas.py        # Pydantic request/response
│   │   │   └── orm/              # ORM table definitions
│   │   └── services/
│   │       ├── vector_store.py   # pgvector search + RRF
│   │       ├── memory_service.py # Conversation memory
│   │       ├── pdf_ingestion.py  # session-scoped PDF extraction + storage
│   │       └── trust_scorer.py   # Trust score computation
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/                  # Next.js App Router pages
│   │   ├── components/chat/      # Chat UI components
│   │   ├── lib/                  # API client, TypeScript types
│   │   └── store/                # Zustand chat state
│   ├── Dockerfile
│   └── package.json
├── k8s/                          # Kubernetes manifests (portfolio)
├── scripts/                      # setup.sh, health_check.sh
├── docker-compose.yml            # Primary deployment
├── Makefile                      # Convenience targets
└── .env.example                  # Configuration template
```

---

## Safety design

The system has two safety layers:

**1. Pre-generation filter** (in `core/judge.py`)
- Blocks personal diagnosis requests ("do I have...", "am I sick...")
- Blocks treatment prescription requests ("should I take...")
- Blocks out-of-scope queries (legal, financial)
- Uses regex — no LLM call, zero latency overhead

**2. Post-generation claim validator** (in `core/judge.py`)
- Embeds each sentence in the answer
- Computes cosine similarity against the retrieved chunks
- Flags sentences with similarity < 0.35 as "potentially unsupported"
- Adds a warning banner in the UI if flagged

---

## Adding new medical sources

1. Create a new file in `backend/app/ingestion/sources/`
2. Subclass `BaseFetcher` and implement `fetch(query, max_results)`
3. Return a list of dicts matching the schema in `base.py`
4. Import and add your fetcher to the `fetchers` list in `coordinator.py`

The trust scorer automatically assigns appropriate scores based on the `source` field you return.

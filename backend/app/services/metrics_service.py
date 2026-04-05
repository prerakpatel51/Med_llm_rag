"""
metrics_service.py – Prometheus metrics definitions.

All metrics are module-level singletons.
Import and call these functions from the pipeline to record measurements.
"""
from prometheus_client import Counter, Histogram, Gauge

# ── Counters (always increasing) ─────────────────────────────────────────────

requests_total = Counter(
    "medlit_requests_total",
    "Total number of query requests",
    ["status"],   # label: "success" or "error"
)

errors_total = Counter(
    "medlit_errors_total",
    "Total number of errors",
    ["error_type"],  # label: e.g. "judge_block", "ollama_timeout", "db_error"
)

tokens_in_total = Counter(
    "medlit_tokens_in_total",
    "Total input tokens sent to the LLM",
)

tokens_out_total = Counter(
    "medlit_tokens_out_total",
    "Total output tokens received from the LLM",
)

topic_queries_total = Counter(
    "medlit_topic_queries_total",
    "Queries by top MeSH topic category",
    ["topic"],
)

# ── Histograms (distributions with buckets) ───────────────────────────────────
# Buckets in seconds: 0.1s, 0.5s, 1s, 2s, 5s, 10s, 30s, 60s

LATENCY_BUCKETS = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]

request_latency = Histogram(
    "medlit_request_latency_seconds",
    "Total end-to-end request latency",
    buckets=LATENCY_BUCKETS,
)

retrieval_latency = Histogram(
    "medlit_retrieval_latency_seconds",
    "Time spent on retrieval (vector + BM25 + rerank)",
    buckets=LATENCY_BUCKETS,
)

generation_latency = Histogram(
    "medlit_generation_latency_seconds",
    "Time spent waiting for the LLM to respond",
    buckets=LATENCY_BUCKETS,
)

# ── Gauges (can go up or down) ────────────────────────────────────────────────

active_requests = Gauge(
    "medlit_active_requests",
    "Number of requests currently being processed",
)

memory_records_total = Gauge(
    "medlit_memory_records_total",
    "Total number of conversation memory records in the database",
)

documents_ingested_total = Gauge(
    "medlit_documents_ingested_total",
    "Total documents ingested per source",
    ["source"],
)

documents_stored_total = Gauge(
    "medlit_documents_stored_total",
    "Total documents currently stored in the database",
)

chunks_stored_total = Gauge(
    "medlit_chunks_stored_total",
    "Total chunks currently stored in the database",
)

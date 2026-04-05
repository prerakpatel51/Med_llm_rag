// api.ts – typed wrappers around the FastAPI backend.
// Query calls go directly to the backend (port 8000) to avoid Next.js proxy timeout.
// All other calls use the /api proxy rewrite.

import type { QueryResponse, MemoryEntry } from "./types";

// Backend URL — uses env var in production (S3/CloudFront), falls back to same-host for local dev
const BACKEND_DIRECT = typeof window !== "undefined"
  ? (process.env.NEXT_PUBLIC_BACKEND_URL || `${window.location.protocol}//${window.location.hostname}:8000`)
  : "http://backend:8000";

const BASE = "/api/v1";

export async function submitQuery(
  query: string,
  sessionId: string = "default"
): Promise<QueryResponse> {
  // Use direct backend URL — bypasses Next.js proxy which has a short timeout
  const res = await fetch(`${BACKEND_DIRECT}/api/v1/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    const msg = Array.isArray(err.detail)
      ? err.detail.map((e: { msg: string }) => e.msg).join(", ")
      : err.detail || `HTTP ${res.status}`;
    throw new Error(msg);
  }

  return res.json();
}

export async function fetchMemory(
  sessionId: string = "default",
  limit: number = 50
): Promise<MemoryEntry[]> {
  const res = await fetch(
    `${BACKEND_DIRECT}/api/v1/memory?session_id=${encodeURIComponent(sessionId)}&limit=${limit}`
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function checkHealth(): Promise<{ status: string }> {
  const res = await fetch(`${BACKEND_DIRECT}/health`);
  if (!res.ok) return { status: "error" };
  return res.json();
}

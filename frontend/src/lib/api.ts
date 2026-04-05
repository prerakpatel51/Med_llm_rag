// api.ts – typed wrappers around the FastAPI backend.
// Query calls go directly to the backend (port 8000) to avoid Next.js proxy timeout.
// All other calls use the /api proxy rewrite.

import type { QueryResponse, MemoryEntry } from "./types";

// Direct backend URL for long-running requests (avoids Next.js proxy timeout)
const BACKEND_DIRECT = typeof window !== "undefined"
  ? `${window.location.protocol}//${window.location.hostname}:8000`
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
    `${BASE}/memory?session_id=${encodeURIComponent(sessionId)}&limit=${limit}`
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function checkHealth(): Promise<{ status: string }> {
  const res = await fetch("/health");
  if (!res.ok) return { status: "error" };
  return res.json();
}

// api.ts – typed wrappers around the FastAPI backend.

import type { QueryResponse, MemoryEntry } from "./types";

// In the browser, prefer same-origin paths so a reverse proxy/CDN can front both
// the static app and the backend API without mixed-content issues.
const BACKEND_BASE = typeof window === "undefined"
  ? (process.env.BACKEND_URL || "http://backend:8000")
  : (process.env.NEXT_PUBLIC_BACKEND_URL || "");

export async function submitQuery(
  query: string,
  sessionId: string = "default",
  model?: string
): Promise<QueryResponse> {
  const body: Record<string, string> = { query, session_id: sessionId };
  if (model) body.model = model;

  const res = await fetch(`${BACKEND_BASE}/api/v1/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
    `${BACKEND_BASE}/api/v1/memory?session_id=${encodeURIComponent(sessionId)}&limit=${limit}`
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function checkHealth(): Promise<{ status: string }> {
  const res = await fetch(`${BACKEND_BASE}/health`);
  if (!res.ok) return { status: "error" };
  return res.json();
}

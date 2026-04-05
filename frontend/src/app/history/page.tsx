// history/page.tsx – browse past conversation memory entries.

"use client";

import { useEffect, useState } from "react";
import { fetchMemory } from "@/lib/api";
import type { MemoryEntry } from "@/lib/types";
import { useChatStore } from "@/store/chatStore";

export default function HistoryPage() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { sessionId } = useChatStore();

  useEffect(() => {
    fetchMemory(sessionId, 100)
      .then(setEntries)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) return <p className="p-6 text-gray-400">Loading history…</p>;
  if (error) return <p className="p-6 text-red-500">Error: {error}</p>;
  if (entries.length === 0)
    return <p className="p-6 text-gray-400">No conversation history yet.</p>;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <h1 className="text-xl font-semibold text-gray-800">Conversation History</h1>
      {entries.map((entry) => (
        <div key={entry.id} className="bg-white border border-gray-200 rounded-lg p-4 space-y-2">
          <p className="text-xs text-gray-400">{new Date(entry.created_at).toLocaleString()}</p>
          <p className="font-medium text-gray-800 text-sm">{entry.query_text}</p>
          <p className="text-gray-500 text-sm line-clamp-3">{entry.response_text}</p>
        </div>
      ))}
    </div>
  );
}

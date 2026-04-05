// MessageBubble.tsx – renders one chat message (user or assistant).

import type { ChatMessage } from "@/lib/types";
import { CitationCard } from "./CitationCard";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2 text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  // Assistant message
  const resp = message.response;

  if (message.isLoading) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[75%] bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-500 animate-pulse">
          Searching literature and generating answer… (if the model was idle, allow ~15s for warm-up)
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-3">
        {/* Answer text */}
        <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-900 whitespace-pre-wrap">
          {message.content}
        </div>

        {/* Judge warning banner */}
        {resp?.judge_flagged && (
          <div className="bg-amber-50 border border-amber-300 text-amber-800 rounded-lg px-3 py-2 text-xs">
            ⚠️ <strong>Note:</strong> {resp.judge_notes}
          </div>
        )}

        {/* Citations */}
        {resp?.citations && resp.citations.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Sources
            </p>
            {resp.citations.map((citation, i) => (
              <CitationCard key={citation.chunk_id} citation={citation} index={i + 1} />
            ))}
          </div>
        )}

        {/* Latency info (small, unobtrusive) */}
        {resp && (
          <p className="text-xs text-gray-400">
            {resp.total_latency.toFixed(1)}s · {resp.tokens_in}↑ {resp.tokens_out}↓ tokens
          </p>
        )}
      </div>
    </div>
  );
}

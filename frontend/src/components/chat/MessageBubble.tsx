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
  const shouldShowSummary = !!resp?.summary && resp.summary.trim() !== message.content.trim();

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
      <div className="max-w-[88%] space-y-3">
        {shouldShowSummary && (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50/80 px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-emerald-700">
              Summary
            </p>
            <p className="mt-2 text-sm leading-6 text-emerald-950">{resp?.summary}</p>
          </div>
        )}

        <div className="rounded-[24px] rounded-tl-sm border border-slate-200 bg-white px-4 py-4 shadow-sm">
          <p className="text-sm leading-7 text-slate-900 whitespace-pre-wrap">
            {message.content}
          </p>
        </div>

        {resp?.judge_flagged && (
          <div className="rounded-2xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <strong>Note:</strong> {resp.judge_notes}
          </div>
        )}

        {resp?.sources && resp.sources.length > 0 && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
              Source List
            </p>
            <div className="mt-3 grid gap-2">
              {resp.sources.map((source) => (
                <a
                  key={source.source_id}
                  href={source.url || undefined}
                  target={source.url ? "_blank" : undefined}
                  rel={source.url ? "noopener noreferrer" : undefined}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-3 transition hover:border-slate-300"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {source.source}
                    </span>
                    {source.published_at && (
                      <span className="text-xs text-slate-400">
                        {source.published_at.slice(0, 10)}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm font-medium text-slate-900">{source.title}</p>
                  {source.journal && (
                    <p className="mt-1 text-xs text-slate-500">{source.journal}</p>
                  )}
                </a>
              ))}
            </div>
          </div>
        )}

        {resp?.citations && resp.citations.length > 0 && (
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
              Evidence Passages
            </p>
            {resp.citations.map((citation, i) => (
              <CitationCard key={citation.chunk_id} citation={citation} index={i + 1} />
            ))}
          </div>
        )}

        {resp && (
          <p className="text-xs text-slate-400">
            {resp.total_latency.toFixed(1)}s · {resp.tokens_in}↑ {resp.tokens_out}↓ tokens
          </p>
        )}
      </div>
    </div>
  );
}

// ChatWindow.tsx – main chat UI component.

"use client";

import { useEffect, useRef, useState } from "react";
import { useChatStore } from "@/store/chatStore";
import { submitQuery } from "@/lib/api";
import { MessageBubble } from "./MessageBubble";
import type { ChatMessage } from "@/lib/types";

// Poll /api/v1/status to know if Ollama is warm or cold
async function fetchOllamaStatus(): Promise<{ cold: boolean }> {
  try {
    const res = await fetch("/api/v1/status");
    if (!res.ok) return { cold: false };
    const data = await res.json();
    return { cold: data.cold_start_warning };
  } catch {
    return { cold: false };
  }
}

export function ChatWindow() {
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCold, setIsCold] = useState(false);   // true = Ollama is stopped, expect warm-up
  const { messages, sessionId, addMessage, updateLastMessage } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Poll Ollama status when the user starts typing so the warning is timely
  useEffect(() => {
    if (input.length === 1) {   // triggers on first keystroke only
      fetchOllamaStatus().then(({ cold }) => setIsCold(cold));
    }
    if (input.length === 0) setIsCold(false);
  }, [input]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const query = input.trim();
    if (!query || isSubmitting) return;

    setInput("");
    setIsSubmitting(true);

    // Add user message immediately
    const userId = `user-${Date.now()}`;
    addMessage({ id: userId, role: "user", content: query });

    // Add a loading placeholder for the assistant response
    const assistantId = `assistant-${Date.now()}`;
    addMessage({ id: assistantId, role: "assistant", content: "", isLoading: true });

    try {
      const response = await submitQuery(query, sessionId);
      updateLastMessage({
        content: response.answer,
        response,
        isLoading: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Request failed";
      updateLastMessage({
        content: `Error: ${message}`,
        isLoading: false,
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-20 space-y-2">
            <p className="text-4xl">🔬</p>
            <p className="text-lg font-medium">Medical Literature Assistant</p>
            <p className="text-sm max-w-md mx-auto">
              Ask questions about medical research. I search PubMed, CDC, WHO, FDA,
              and NIH to give you citation-grounded answers.
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input form */}
      <div className="border-t border-gray-200 bg-white px-4 py-3">
        {/* Cold-start warning – shown as soon as user starts typing */}
        {isCold && (
          <p className="text-xs text-amber-600 mb-2 text-center">
            ⏳ Model is idle — first response will take ~15s to warm up.
          </p>
        )}
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a medical literature question…"
            disabled={isSubmitting}
            className="flex-1 border border-gray-300 rounded-full px-4 py-2 text-sm
                       focus:outline-none focus:ring-2 focus:ring-blue-500
                       disabled:bg-gray-50 disabled:text-gray-400"
          />
          <button
            type="submit"
            disabled={isSubmitting || !input.trim()}
            className="bg-blue-600 text-white rounded-full px-5 py-2 text-sm font-medium
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors"
          >
            {isSubmitting ? "…" : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}

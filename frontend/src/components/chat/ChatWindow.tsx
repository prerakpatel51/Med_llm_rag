// ChatWindow.tsx – main chat UI component.

"use client";

import { useEffect, useRef, useState } from "react";
import { useChatStore, AVAILABLE_MODELS } from "@/store/chatStore";
import { submitQuery } from "@/lib/api";
import { MessageBubble } from "./MessageBubble";
import type { ChatMessage } from "@/lib/types";

export function ChatWindow() {
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const {
    messages,
    sessionId,
    selectedModel,
    addMessage,
    updateLastMessage,
    clearMessages,
    setModel,
    loadFromStorage,
  } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [hydrated, setHydrated] = useState(false);

  // Load chat history from localStorage on first render
  useEffect(() => {
    loadFromStorage();
    setHydrated(true);
  }, [loadFromStorage]);

  // Auto-scroll to the bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
      const response = await submitQuery(query, sessionId, selectedModel);
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

  // Don't render messages until hydrated from localStorage (avoids mismatch)
  if (!hydrated) return null;

  return (
    <div className="flex flex-col h-full">
      {/* Model selector bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 font-medium">Model:</label>
          <select
            value={selectedModel}
            onChange={(e) => setModel(e.target.value)}
            className="text-xs border border-gray-300 rounded px-2 py-1 bg-white
                       focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {AVAILABLE_MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} — {m.desc}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={clearMessages}
          className="text-xs text-gray-400 hover:text-red-500 transition-colors"
        >
          Clear chat
        </button>
      </div>

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
            <p className="text-xs text-gray-300 mt-4">
              Using {AVAILABLE_MODELS.find((m) => m.id === selectedModel)?.name || selectedModel}
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
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a medical literature question..."
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
            {isSubmitting ? "..." : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}

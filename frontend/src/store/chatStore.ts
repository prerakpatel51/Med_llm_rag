// chatStore.ts – global chat state managed with Zustand.
// Zustand is like a simple Redux without the boilerplate.

import { create } from "zustand";
import type { ChatMessage } from "@/lib/types";

interface ChatStore {
  messages: ChatMessage[];
  sessionId: string;
  addMessage: (msg: ChatMessage) => void;
  updateLastMessage: (update: Partial<ChatMessage>) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  // Generate a session ID once per page load
  sessionId: `session-${Date.now()}`,

  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  // Used to replace the loading placeholder with the actual response
  updateLastMessage: (update) =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last) {
        messages[messages.length - 1] = { ...last, ...update };
      }
      return { messages };
    }),

  clearMessages: () => set({ messages: [] }),
}));

// chatStore.ts – global chat state managed with Zustand + localStorage persistence.

import { create } from "zustand";
import type { ChatMessage } from "@/lib/types";

interface ChatStore {
  messages: ChatMessage[];
  sessionId: string;
  selectedModel: string;
  addMessage: (msg: ChatMessage) => void;
  updateLastMessage: (update: Partial<ChatMessage>) => void;
  clearMessages: () => void;
  setModel: (model: string) => void;
  loadFromStorage: () => void;
}

// Available models on Groq free tier
export const AVAILABLE_MODELS = [
  { id: "llama-3.3-70b-versatile", name: "Llama 3.3 70B", desc: "Best quality" },
  { id: "llama-3.1-8b-instant", name: "Llama 3.1 8B", desc: "Fastest" },
  { id: "meta-llama/llama-4-scout-17b-16e-instruct", name: "Llama 4 Scout 17B", desc: "Newest" },
  { id: "qwen/qwen3-32b", name: "Qwen3 32B", desc: "Strong reasoning" },
];

const STORAGE_KEY = "medlit-chat-messages";
const MODEL_KEY = "medlit-selected-model";
const SESSION_KEY = "medlit-session-id";

function saveToStorage(messages: ChatMessage[]) {
  try {
    // Only save the last 100 messages to avoid localStorage limits
    const toSave = messages.slice(-100).map((m) => ({
      ...m,
      isLoading: false, // never persist loading state
    }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch {
    // localStorage full or unavailable — ignore
  }
}

function getSessionId(): string {
  if (typeof window === "undefined") return `session-${Date.now()}`;
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = `session-${Date.now()}`;
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  sessionId: getSessionId(),
  selectedModel: typeof window !== "undefined"
    ? localStorage.getItem(MODEL_KEY) || "llama-3.3-70b-versatile"
    : "llama-3.3-70b-versatile",

  addMessage: (msg) =>
    set((state) => {
      const messages = [...state.messages, msg];
      saveToStorage(messages);
      return { messages };
    }),

  updateLastMessage: (update) =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last) {
        messages[messages.length - 1] = { ...last, ...update };
      }
      saveToStorage(messages);
      return { messages };
    }),

  clearMessages: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ messages: [] });
  },

  setModel: (model) => {
    localStorage.setItem(MODEL_KEY, model);
    set({ selectedModel: model });
  },

  loadFromStorage: () => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const messages = JSON.parse(stored) as ChatMessage[];
        set({ messages });
      }
    } catch {
      // corrupted data — ignore
    }
  },
}));

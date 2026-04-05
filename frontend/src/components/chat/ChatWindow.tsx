// ChatWindow.tsx – main research workspace.

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useChatStore, AVAILABLE_MODELS } from "@/store/chatStore";
import { ingestTopic, submitQuery, uploadPdfs } from "@/lib/api";
import { MessageBubble } from "./MessageBubble";
import type { SourceSummary, UploadedPdfSummary } from "@/lib/types";

const MAX_FILES = 5;
const MAX_TOTAL_UPLOAD_BYTES = 40 * 1024 * 1024;

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function dedupeUploads(items: UploadedPdfSummary[]) {
  const seen = new Map<string, UploadedPdfSummary>();
  items.forEach((item) => seen.set(item.source_id, item));
  return Array.from(seen.values());
}

function dedupeSources(items: SourceSummary[]) {
  const seen = new Map<string, SourceSummary>();
  items.forEach((item) => seen.set(item.source_id, item));
  return Array.from(seen.values());
}

export function ChatWindow() {
  const [input, setInput] = useState("");
  const [topic, setTopic] = useState("");
  const [topicSource, setTopicSource] = useState<"pubmed" | "all">("pubmed");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [workspaceNotice, setWorkspaceNotice] = useState<string | null>(null);
  const [uploadedDocs, setUploadedDocs] = useState<UploadedPdfSummary[]>([]);
  const [topicDocs, setTopicDocs] = useState<SourceSummary[]>([]);
  const [lastTopic, setLastTopic] = useState("");
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    loadFromStorage();
    setHydrated(true);
  }, [loadFromStorage]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const uploadedSize = useMemo(
    () => uploadedDocs.reduce((sum, item) => sum + item.size_bytes, 0),
    [uploadedDocs],
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const query = input.trim();
    if (!query || isSubmitting) return;

    setInput("");
    setWorkspaceNotice(null);
    setIsSubmitting(true);

    addMessage({ id: `user-${Date.now()}`, role: "user", content: query });
    addMessage({
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      isLoading: true,
    });

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

  async function handlePdfSelection(e: React.ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(e.target.files || []);
    if (selectedFiles.length === 0 || isUploading) return;

    const totalBytes = selectedFiles.reduce((sum, file) => sum + file.size, 0);
    if (selectedFiles.length > MAX_FILES) {
      setWorkspaceNotice(`Upload up to ${MAX_FILES} PDFs per batch.`);
      e.target.value = "";
      return;
    }
    if (totalBytes > MAX_TOTAL_UPLOAD_BYTES) {
      setWorkspaceNotice("Combined upload size must stay under 40 MB.");
      e.target.value = "";
      return;
    }

    setWorkspaceNotice(null);
    setIsUploading(true);
    try {
      const response = await uploadPdfs(selectedFiles, sessionId);
      setUploadedDocs((current) => dedupeUploads([...current, ...response.uploaded]));
      setWorkspaceNotice(`Indexed ${response.uploaded.length} PDF file(s) for this session.`);
    } catch (err: unknown) {
      setWorkspaceNotice(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setIsUploading(false);
      e.target.value = "";
    }
  }

  async function handleTopicIngest() {
    const trimmed = topic.trim();
    if (!trimmed || isIngesting) return;

    setWorkspaceNotice(null);
    setIsIngesting(true);
    try {
      const response = await ingestTopic(trimmed, topicSource, 10);
      setTopicDocs(dedupeSources(response.documents));
      setLastTopic(response.topic);
      setWorkspaceNotice(
        `Ingested topic "${response.topic}" from ${response.source}. ${response.new_documents} new document(s) stored.`,
      );
    } catch (err: unknown) {
      setWorkspaceNotice(err instanceof Error ? err.message : "Topic ingestion failed.");
    } finally {
      setIsIngesting(false);
    }
  }

  if (!hydrated) return null;

  return (
    <div className="h-full overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(12,74,110,0.10),_transparent_30%),linear-gradient(180deg,_#f8fafc_0%,_#eef6ff_50%,_#f8fafc_100%)]">
      <div className="mx-auto flex h-full max-w-7xl flex-col gap-4 px-4 py-4 lg:grid lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col gap-4">
          <section className="rounded-[28px] border border-slate-200 bg-white/90 p-5 shadow-sm backdrop-blur">
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-sky-700">
              Research Workspace
            </p>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
              Ask across uploaded PDFs and indexed medical literature.
            </h1>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Session uploads stay scoped to this chat session. Topic ingest can pull new evidence
              from PubMed before you ask follow-up questions.
            </p>

            <div className="mt-5 grid grid-cols-3 gap-2">
              <div className="rounded-2xl bg-slate-900 px-3 py-3 text-white">
                <p className="text-[11px] uppercase tracking-wide text-slate-300">Uploads</p>
                <p className="mt-1 text-lg font-semibold">{uploadedDocs.length}</p>
              </div>
              <div className="rounded-2xl bg-white px-3 py-3 ring-1 ring-slate-200">
                <p className="text-[11px] uppercase tracking-wide text-slate-400">Topic Docs</p>
                <p className="mt-1 text-lg font-semibold text-slate-900">{topicDocs.length}</p>
              </div>
              <div className="rounded-2xl bg-white px-3 py-3 ring-1 ring-slate-200">
                <p className="text-[11px] uppercase tracking-wide text-slate-400">Session</p>
                <p className="mt-1 truncate text-sm font-semibold text-slate-900">{sessionId}</p>
              </div>
            </div>
          </section>

          <section className="rounded-[28px] border border-slate-200 bg-white/90 p-5 shadow-sm backdrop-blur">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
                  PDF Upload
                </p>
                <p className="mt-2 text-sm text-slate-600">
                  Up to 5 files, 40 MB total. Extracted text is indexed and merged with database retrieval.
                </p>
              </div>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                className="rounded-full bg-sky-700 px-4 py-2 text-xs font-semibold text-white transition hover:bg-sky-800 disabled:opacity-60"
              >
                {isUploading ? "Uploading..." : "Upload PDFs"}
              </button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              multiple
              className="hidden"
              onChange={handlePdfSelection}
            />

            <div className="mt-4 rounded-2xl bg-slate-50 px-3 py-3 text-xs text-slate-500 ring-1 ring-slate-200">
              Current indexed upload size: {formatBytes(uploadedSize)}
            </div>

            <div className="mt-4 space-y-2">
              {uploadedDocs.length === 0 ? (
                <p className="rounded-2xl border border-dashed border-slate-300 px-3 py-4 text-sm text-slate-400">
                  No PDFs uploaded in this workspace yet.
                </p>
              ) : (
                uploadedDocs.map((doc) => (
                  <div
                    key={doc.source_id}
                    className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3"
                  >
                    <p className="text-sm font-medium text-slate-900">{doc.title}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {doc.chunk_count} chunks · {formatBytes(doc.size_bytes)}
                    </p>
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="rounded-[28px] border border-slate-200 bg-white/90 p-5 shadow-sm backdrop-blur">
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
              Topic Ingest
            </p>
            <p className="mt-2 text-sm text-slate-600">
              Pull fresh literature for a topic before asking the question.
            </p>
            <div className="mt-4 space-y-3">
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="e.g. acute myocardial infarction management"
                className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-500"
              />
              <div className="flex gap-2">
                <select
                  value={topicSource}
                  onChange={(e) => setTopicSource(e.target.value as "pubmed" | "all")}
                  className="flex-1 rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none"
                >
                  <option value="pubmed">PubMed only</option>
                  <option value="all">All sources</option>
                </select>
                <button
                  type="button"
                  onClick={handleTopicIngest}
                  disabled={isIngesting || !topic.trim()}
                  className="rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
                >
                  {isIngesting ? "Ingesting..." : "Ingest"}
                </button>
              </div>
            </div>

            <div className="mt-4 space-y-2">
              {topicDocs.length === 0 ? (
                <p className="rounded-2xl border border-dashed border-slate-300 px-3 py-4 text-sm text-slate-400">
                  Ingested topic sources will appear here.
                </p>
              ) : (
                <>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    {lastTopic ? `Latest topic: ${lastTopic}` : "Latest topic"}
                  </p>
                  {topicDocs.map((doc) => (
                    <a
                      key={doc.source_id}
                      href={doc.url || undefined}
                      target={doc.url ? "_blank" : undefined}
                      rel={doc.url ? "noopener noreferrer" : undefined}
                      className="block rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          {doc.source}
                        </span>
                        {doc.published_at && (
                          <span className="text-xs text-slate-400">{doc.published_at.slice(0, 10)}</span>
                        )}
                      </div>
                      <p className="mt-1 text-sm font-medium text-slate-900">{doc.title}</p>
                    </a>
                  ))}
                </>
              )}
            </div>
          </section>
        </aside>

        <section className="flex min-h-0 flex-col overflow-hidden rounded-[32px] border border-slate-200 bg-white/90 shadow-sm backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
                Conversation
              </p>
              <p className="mt-1 text-sm text-slate-600">
                Every answer returns a concise summary, source list, and evidence passages.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                value={selectedModel}
                onChange={(e) => setModel(e.target.value)}
                className="rounded-full border border-slate-300 bg-white px-3 py-2 text-xs text-slate-700 outline-none"
              >
                {AVAILABLE_MODELS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} — {m.desc}
                  </option>
                ))}
              </select>
              <button
                onClick={clearMessages}
                className="rounded-full border border-slate-300 px-3 py-2 text-xs font-medium text-slate-500 transition hover:border-red-300 hover:text-red-600"
              >
                Clear chat
              </button>
            </div>
          </div>

          {workspaceNotice && (
            <div className="border-b border-slate-200 bg-sky-50 px-5 py-3 text-sm text-sky-900">
              {workspaceNotice}
            </div>
          )}

          <div className="flex-1 overflow-y-auto px-5 py-6">
            {messages.length === 0 ? (
              <div className="mx-auto mt-8 max-w-2xl rounded-[28px] border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center">
                <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500">
                  Start Here
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
                  Ask a research question, upload evidence, or ingest a fresh PubMed topic.
                </h2>
                <p className="mx-auto mt-4 max-w-xl text-sm leading-6 text-slate-600">
                  The assistant will blend indexed medical literature with any PDFs uploaded in this
                  session, then return a direct answer, a short summary, and the sources it relied on.
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                {messages.map((msg) => (
                  <MessageBubble key={msg.id} message={msg} />
                ))}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-slate-200 bg-slate-50/80 px-5 py-4">
            <form onSubmit={handleSubmit} className="space-y-3">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about your uploaded PDFs, the indexed database, or a topic you just ingested..."
                disabled={isSubmitting}
                rows={3}
                className="w-full resize-none rounded-[24px] border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-500 disabled:bg-slate-100"
              />
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-slate-500">
                  Session uploads are automatically merged into retrieval for this chat session.
                </p>
                <button
                  type="submit"
                  disabled={isSubmitting || !input.trim()}
                  className="rounded-full bg-sky-700 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-sky-800 disabled:opacity-60"
                >
                  {isSubmitting ? "Running..." : "Ask"}
                </button>
              </div>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}

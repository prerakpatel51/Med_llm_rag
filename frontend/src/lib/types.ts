// Shared TypeScript types that match the FastAPI response schemas

export interface Citation {
  chunk_id: number;
  source: string;
  source_id: string;
  title: string;
  authors: string;
  journal: string;
  doi: string;
  url: string;
  published_at: string | null;
  trust_score: number;
  trust_tier: "A" | "B" | "C";
  excerpt: string;
}

export interface SourceSummary {
  source: string;
  source_id: string;
  title: string;
  url: string;
  journal: string;
  published_at: string | null;
}

export interface QueryResponse {
  answer: string;
  summary: string;
  citations: Citation[];
  sources: SourceSummary[];
  judge_flagged: boolean;
  judge_notes: string;
  retrieval_latency: number;
  generation_latency: number;
  total_latency: number;
  tokens_in: number;
  tokens_out: number;
}

export interface MemoryEntry {
  id: number;
  session_id: string;
  query_text: string;
  response_text: string;
  created_at: string;
}

export interface UploadedPdfSummary {
  file_name: string;
  source_id: string;
  chunk_count: number;
  size_bytes: number;
  title: string;
}

export interface PdfUploadResponse {
  session_id: string;
  uploaded: UploadedPdfSummary[];
}

export interface TopicIngestResponse {
  topic: string;
  source: "pubmed" | "all";
  new_documents: number;
  documents: SourceSummary[];
}

// A message in the chat window (local state only, not stored in backend)
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: QueryResponse;  // full response data (for assistant messages)
  isLoading?: boolean;
}

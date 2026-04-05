"""
chunker.py – splits a document's text into overlapping chunks.

Strategy:
  - Split on sentence boundaries to avoid cutting mid-sentence.
  - Target ~256 words per chunk with 32-word overlap.
  - Each chunk carries the source document's metadata.
"""


def simple_sentence_split(text: str) -> list[str]:
    """
    Split text into sentences using basic punctuation rules.
    We avoid spaCy here to keep memory usage low.
    """
    import re
    # Split on ". ", "! ", "? " followed by a capital letter or end of string
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(
    text: str,
    chunk_size_words: int = 256,
    overlap_words: int = 32,
) -> list[str]:
    """
    Split `text` into overlapping chunks of approximately `chunk_size_words` words.

    Returns a list of chunk strings.
    """
    sentences = simple_sentence_split(text)

    chunks = []
    current_words: list[str] = []

    for sentence in sentences:
        sentence_words = sentence.split()

        # If adding this sentence would exceed the chunk size, finalize current chunk
        if len(current_words) + len(sentence_words) > chunk_size_words and current_words:
            chunks.append(" ".join(current_words))
            # Keep the last `overlap_words` words as the start of the next chunk
            current_words = current_words[-overlap_words:] if overlap_words else []

        current_words.extend(sentence_words)

    # Don't forget the last chunk
    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


def make_chunks_for_document(
    document_id: int,
    text: str,
    source: str,
    source_id: str,
    trust_score: float,
) -> list[dict]:
    """
    Chunk a document's text and return a list of dicts ready for vector_store.save_chunks().
    Embeddings are NOT added here; the ingestion coordinator adds them in a batch.
    """
    raw_chunks = chunk_text(text)
    result = []
    for i, chunk_text_str in enumerate(raw_chunks):
        result.append({
            "document_id": document_id,
            "content": chunk_text_str,
            "chunk_index": i,
            "embedding": [],        # filled in by embedder
            "trust_score": trust_score,
            "source": source,
            "source_id": source_id,
        })
    return result

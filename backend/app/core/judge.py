"""
judge.py – lightweight safety and claim-grounding layer.

The judge runs in two phases:

1. PRE-GENERATION (query filter)
   Blocks queries that ask for personal diagnosis, treatment prescriptions,
   or are clearly out of scope (legal, financial, etc.).
   This is done with simple regex patterns — no LLM needed.

2. POST-GENERATION (answer validator)
   Checks each sentence in the LLM's answer against the retrieved chunks
   using cosine similarity. Sentences with no supporting evidence are flagged.
   Again, no external LLM call — just embeddings we already computed.
"""
import re
from app.ingestion.embedder import embed_text

# ── Pre-generation: query patterns to block ───────────────────────────────────

# Phrases that indicate the user wants personal medical advice / diagnosis.
DIAGNOSIS_PATTERNS = [
    r"\b(do i have|am i sick|what disease do i|diagnose me|is my .{0,30} normal)\b",
    r"\b(should i take|can i take|what medication should)\b",
    r"\b(my symptoms|i have been feeling|i feel pain)\b.*\b(what|could|is it)\b",
]

TREATMENT_RECOMMENDATION_PATTERNS = [
    r"\byou should take\b",
    r"\brecommended dose for you\b",
    r"\bprescribe\b",
]

OUT_OF_SCOPE_PATTERNS = [
    r"\b(lawsuit|legal advice|sue|attorney)\b",
    r"\b(stock|invest|financial advice)\b",
    r"\b(hack|exploit|jailbreak)\b",
]

# Compile all patterns once at module load (faster than compiling per request)
_DIAGNOSIS_RE = [re.compile(p, re.IGNORECASE) for p in DIAGNOSIS_PATTERNS]
_TREATMENT_RE = [re.compile(p, re.IGNORECASE) for p in TREATMENT_RECOMMENDATION_PATTERNS]
_SCOPE_RE = [re.compile(p, re.IGNORECASE) for p in OUT_OF_SCOPE_PATTERNS]


def check_query(query: str) -> tuple[bool, str]:
    """
    Check whether the query should be blocked before retrieval.

    Returns:
        (is_safe, reason)
        is_safe = True  → query is fine, proceed
        is_safe = False → query is blocked; `reason` explains why
    """
    for pattern in _DIAGNOSIS_RE:
        if pattern.search(query):
            return False, (
                "This assistant provides medical literature summaries only. "
                "For personal health concerns, please consult a licensed healthcare provider."
            )

    for pattern in _SCOPE_RE:
        if pattern.search(query):
            return False, "This query is outside the scope of medical literature assistance."

    return True, ""


def check_answer(
    answer: str,
    retrieved_chunks: list[dict],
    similarity_threshold: float = 0.35,
) -> tuple[bool, str]:
    """
    Check whether the answer's sentences are grounded in the retrieved chunks.

    Each sentence in the answer is embedded and compared to all chunk embeddings.
    Sentences with max similarity below the threshold are flagged as unsupported.

    Returns:
        (is_flagged, notes)
        is_flagged = False → answer looks well-grounded
        is_flagged = True  → some sentences may not be supported by evidence
    """
    if not retrieved_chunks:
        return True, "No retrieved evidence to ground the answer against."

    # Collect chunk embeddings (already computed and stored in each chunk dict)
    chunk_embeddings = [c.get("embedding", []) for c in retrieved_chunks if c.get("embedding")]
    if not chunk_embeddings:
        return False, ""   # No embeddings to check against → skip

    # Split answer into sentences
    sentences = _split_into_sentences(answer)
    if not sentences:
        return False, ""

    unsupported = []
    for sentence in sentences:
        if len(sentence.split()) < 5:
            continue   # Skip very short sentences (e.g. "See above.")
        sentence_embedding = embed_text(sentence)
        max_similarity = _max_cosine_similarity(sentence_embedding, chunk_embeddings)
        if max_similarity < similarity_threshold:
            # Truncate long sentences for readability in the flag note
            snippet = sentence[:80] + "…" if len(sentence) > 80 else sentence
            unsupported.append(snippet)

    if unsupported:
        notes = (
            "The following claim(s) could not be directly verified in the retrieved evidence: "
            + "; ".join(f'"{s}"' for s in unsupported[:3])  # show at most 3
        )
        return True, notes

    # Also check if the answer recommends specific treatments
    for pattern in _TREATMENT_RE:
        if pattern.search(answer):
            return True, (
                "The response may contain a treatment recommendation. "
                "Please consult a healthcare provider before making any medical decisions."
            )

    return False, ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_into_sentences(text: str) -> list[str]:
    """Very simple sentence splitter."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _max_cosine_similarity(
    query_vec: list[float],
    chunk_vecs: list[list[float]],
) -> float:
    """
    Compute the cosine similarity between query_vec and each chunk_vec,
    return the highest similarity found.

    Since all-MiniLM-L6-v2 returns L2-normalized embeddings,
    cosine similarity = dot product.
    """
    if not query_vec or not chunk_vecs:
        return 0.0

    max_sim = 0.0
    for chunk_vec in chunk_vecs:
        if not chunk_vec:
            continue
        dot = sum(a * b for a, b in zip(query_vec, chunk_vec))
        max_sim = max(max_sim, dot)
    return max_sim

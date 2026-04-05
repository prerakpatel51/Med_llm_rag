"""
embedder.py – loads the sentence embedding model once at startup
and provides a function to embed text into a 384-dimensional vector.

Model: all-MiniLM-L6-v2
  - Size: ~22 MB
  - Dimensions: 384
  - Speed: ~50 ms per batch of 32 sentences on CPU
  - No GPU needed
"""
from sentence_transformers import SentenceTransformer
from app.config import get_settings

settings = get_settings()

# Module-level singleton: loaded once when the module is first imported.
# Subsequent calls to `embed_text` reuse the loaded model.
_model: SentenceTransformer | None = None


def load_model() -> None:
    """
    Pre-load the embedding model.
    Call this during application startup so the first request isn't slow.
    """
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)


def embed_text(text: str) -> list[float]:
    """
    Embed a single string. Returns a list of 384 floats.
    Automatically loads the model if it hasn't been loaded yet.
    """
    global _model
    if _model is None:
        load_model()
    # encode() returns a numpy array; tolist() converts it to plain Python floats
    return _model.encode(text, normalize_embeddings=True).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed multiple strings at once (faster than calling embed_text in a loop).
    Returns a list of 384-float vectors, one per input string.
    """
    global _model
    if _model is None:
        load_model()
    vectors = _model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.tolist() for v in vectors]

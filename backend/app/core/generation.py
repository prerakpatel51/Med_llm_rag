"""
generation.py – sends the prompt to Ollama and gets back a response.

Ollama is a local LLM server. We run Gemma 3 1B inside it.
The API is simple: POST /api/generate with the model name and prompt.

Docs: https://github.com/ollama/ollama/blob/main/docs/api.md
"""
import httpx
from app.config import get_settings

settings = get_settings()

# System prompt that tells the model to behave as a literature assistant
SYSTEM_PROMPT = """You are a medical literature research assistant. Answer STRICTLY from the numbered evidence chunks below. Do NOT use any knowledge from your training data.

STRICT RULES:
1. Read each evidence chunk carefully.
2. Only state facts that appear word-for-word or clearly implied in the chunks.
3. Cite every fact with its chunk number like [1] or [2].
4. If the chunks do NOT contain enough information to answer the question, respond ONLY with: "The retrieved literature does not directly answer this question. Please consult a healthcare provider."
5. Never list symptoms, treatments, or facts that are not in the chunks below.
6. Never diagnose or give personal medical advice.
7. End every response with: "This information is for educational purposes only. Consult a healthcare provider for personal medical decisions."

Evidence chunks:
{context}

Remember: If the answer is not in the chunks above, say you don't have enough evidence. Do not guess."""


def build_prompt(query: str, context_chunks: list[dict]) -> tuple[str, int]:
    """
    Build the full prompt string and estimate the input token count.

    Returns:
        (prompt_string, estimated_token_count)
    """
    # Format each chunk as a numbered citation block
    context_parts = []
    for i, chunk in enumerate(context_chunks, start=1):
        doc_info = f"[{i}] Source: {chunk['source'].upper()} | {chunk.get('title', '')}"
        context_parts.append(f"{doc_info}\n{chunk['content']}")

    context_text = "\n\n".join(context_parts)
    system_with_context = SYSTEM_PROMPT.format(context=context_text)

    full_prompt = f"{system_with_context}\n\nQuestion: {query}\n\nAnswer:"

    # Rough token estimate: 1 token ≈ 4 characters (good enough for monitoring)
    estimated_tokens = len(full_prompt) // 4

    return full_prompt, estimated_tokens


async def generate(query: str, context_chunks: list[dict]) -> tuple[str, int, int]:
    """
    Send the prompt to Ollama and return the model's answer.

    Starts the Ollama container on demand if it isn't running.
    The first call after idle may take 10-15 extra seconds for cold start.

    Returns:
        (answer_text, tokens_in, tokens_out)
    """
    # Use EC2 GPU manager in production, Docker manager locally
    if settings.gpu_ami_id:
        from app.services.ec2_gpu_manager import ensure_ollama_running, record_usage
    else:
        from app.services.ollama_manager import ensure_ollama_running, record_usage
    await ensure_ollama_running()   # no-op if already running, starts if stopped

    prompt, tokens_in = build_prompt(query, context_chunks)

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": settings.temperature,
            "num_predict": settings.max_new_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    answer = data.get("response", "").strip()
    tokens_out = data.get("eval_count", len(answer) // 4)

    # Reset the idle timer so the container stays alive during active use
    record_usage()

    return answer, tokens_in, tokens_out

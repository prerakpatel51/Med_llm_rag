"""
generation.py – sends the prompt to Groq and gets back a response.

Groq runs Llama 3.1 70B at ~500 tokens/sec for free.
API docs: https://console.groq.com/docs/api-reference
"""
import httpx
from app.config import get_settings

settings = get_settings()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

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

Remember: If the answer is not in the chunks above, say you don't have enough evidence. Do not guess."""


def build_context(context_chunks: list[dict]) -> str:
    """Format chunks into numbered citation blocks."""
    parts = []
    for i, chunk in enumerate(context_chunks, start=1):
        doc_info = f"[{i}] Source: {chunk['source'].upper()} | {chunk.get('title', '')}"
        parts.append(f"{doc_info}\n{chunk['content']}")
    return "\n\n".join(parts)


async def generate(query: str, context_chunks: list[dict], model_override: str | None = None) -> tuple[str, int, int]:
    """
    Send the prompt to Groq and return the answer.

    No cold start, no GPU management — just an API call.
    Typical response time: 2-3 seconds.

    Args:
        model_override: if set, use this model instead of the default.

    Returns:
        (answer_text, tokens_in, tokens_out)
    """
    context_text = build_context(context_chunks)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": f"Evidence chunks:\n{context_text}\n\nQuestion: {query}",
        },
    ]

    payload = {
        "model": model_override or settings.llm_model,
        "messages": messages,
        "temperature": settings.temperature,
        "max_tokens": settings.max_new_tokens,
    }

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GROQ_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    choice = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)

    return choice, tokens_in, tokens_out

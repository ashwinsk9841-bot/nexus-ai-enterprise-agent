"""AI service layer: OpenAI client, orchestration, RAG helpers."""

import json
import logging
import threading
import time
from datetime import datetime, timezone

from ..core.config import settings

logger = logging.getLogger("nexus.ai")

# The OpenAI SDK is expensive to import (hundreds of pydantic types). It is
# loaded lazily, only when an AI feature is actually used, so the login page
# never pays for AI initialization.
_CLIENT = None
_CLIENT_AVAILABLE = False
_CLIENT_LOCK = threading.Lock()

EMBEDDING_DIMENSIONS = 1536


def _ensure_client():
    """Import and build the OpenAI client once, on first AI use (post-auth)."""
    global _CLIENT, _CLIENT_AVAILABLE
    if _CLIENT is not None or _CLIENT_AVAILABLE:
        return _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None and not _CLIENT_AVAILABLE:
            try:
                from openai import OpenAI

                _CLIENT = (
                    OpenAI(api_key=settings.OPENAI_API_KEY)
                    if settings.OPENAI_API_KEY
                    else None
                )
                _CLIENT_AVAILABLE = _CLIENT is not None
            except Exception:
                _CLIENT = None
                _CLIENT_AVAILABLE = False
    return _CLIENT


def openai_available() -> bool:
    if not settings.OPENAI_API_KEY:
        return False
    _ensure_client()
    return _CLIENT_AVAILABLE


def get_openai_client():
    return _ensure_client()


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for a piece of text.

    Falls back to a deterministic hashing-based vector when OpenAI is
    unavailable so the RAG pipeline still functions in demo mode.
    """
    cleaned = text.strip()
    if openai_available():
        try:
            resp = get_openai_client().embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL, input=[cleaned[:8000]]
            )
            return resp.data[0].embedding
        except Exception:
            logger.exception("Embedding generation failed, using fallback")
    return _fallback_embedding(cleaned)


def _fallback_embedding(text: str) -> list[float]:
    import hashlib
    import math

    vec = [0.0] * EMBEDDING_DIMENSIONS
    tokens = text.lower().split()
    total = 0.0
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big")
        idx = seed % EMBEDDING_DIMENSIONS
        weight = 1.0
        vec[idx] += weight
        total += weight
    if total > 0:
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


def ai_chat(
    messages: list[dict],
    temperature: float = 0.5,
    max_tokens: int = 1500,
    response_json: bool = False,
) -> str:
    """Run an OpenAI chat completion. Returns best-effort text or a JSON string.

    When OpenAI is not configured, this raises an informative error that
    callers can choose to handle by returning a demo/local response instead.
    """
    if not openai_available():
        raise RuntimeError("OPENAI_API_KEY is not configured")

    kwargs = {}
    if response_json:
        kwargs["response_format"] = {"type": "json_object"}

    resp = get_openai_client().chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
    return resp.choices[0].message.content or ""


def safe_parse_json(text: str) -> dict:
    """Best-effort JSON parsing that tolerates markdown fences and prose."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
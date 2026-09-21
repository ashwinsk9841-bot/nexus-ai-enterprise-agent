"""RAG pipeline: ingest, chunk, embed, store, retrieve, and synthesize answers."""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select

from .service import (
    cosine_similarity,
    generate_embedding,
    openai_available,
    safe_parse_json,
    ai_chat,
)
from ..database.session import SessionLocal
from ..models import KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger("nexus.rag")

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150


def extract_text_from_bytes(data: bytes, doc_type: str) -> str:
    """Extract plain text from uploaded content."""
    if doc_type == "pdf":
        return _extract_pdf(data)
    return _decode_text(data)


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return ""


def _extract_pdf(data: bytes) -> str:
    text = ""
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
    except Exception:
        logger.exception("PDF extraction failed")
        try:
            text = _decode_text(data)
        except Exception:
            text = ""
    return text or ""


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks on paragraph/whitespace boundaries."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind(" ", start, end))
            if boundary > start:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def ingest_document(
    *,
    title: str,
    filename: str,
    doc_type: str,
    data: bytes,
    uploaded_by: str,
) -> int:
    """Process an uploaded document end-to-end and return the document ID."""
    raw_text = extract_text_from_bytes(data, doc_type)
    chunks = chunk_text(raw_text)

    db = SessionLocal()
    try:
        doc = KnowledgeDocument(
            title=title,
            filename=filename,
            doc_type=doc_type,
            size_bytes=len(data),
            status="PROCESSING",
            chunk_count=len(chunks),
            uploaded_by=uploaded_by,
            created_at=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.flush()

        for idx, chunk in enumerate(chunks):
            embedding = generate_embedding(chunk)
            db.add(
                KnowledgeChunk(
                    document_id=doc.id,
                    chunk_index=idx,
                    text=chunk,
                    embedding_id=_store_embedding(embedding),
                )
            )

        doc.status = "READY"
        db.commit()
        return doc.id
    except Exception:
        db.rollback()
        logger.exception("Knowledge ingestion failed")
        raise
    finally:
        db.close()


def _store_embedding(embedding: list[float]) -> str:
    """Store an embedding in an in-memory vector store for search."""
    import json

    from .vector_store import vector_store

    vec_id = vector_store.add(embedding)
    return vec_id


def retrieve_context(query: str, top_k: int = 4) -> list[dict]:
    """Retrieve the most relevant knowledge chunks for a query."""
    query_vec = generate_embedding(query)

    db = SessionLocal()
    try:
        docs = db.execute(select(KnowledgeDocument)).scalars().all()
        doc_map = {d.id: d for d in docs}
        chunks = db.execute(select(KnowledgeChunk)).scalars().all()
        candidates = []
        for chunk in chunks:
            stored = _load_embedding(chunk.embedding_id)
            sim = cosine_similarity(query_vec, stored)
            if sim > 0.12 or not openai_available():
                doc = doc_map.get(chunk.document_id)
                candidates.append(
                    {
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "document_title": doc.title if doc else "Unknown",
                        "text": chunk.text[:1200],
                        "score": round(sim, 4),
                        "chunk_index": chunk.chunk_index,
                    }
                )
        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:top_k]
    finally:
        db.close()


def _load_embedding(embedding_id: str) -> list[float]:
    from .vector_store import vector_store

    return vector_store.get(embedding_id) or []


def answer_with_knowledge(query: str, top_k: int = 4) -> dict:
    """Answer a question grounded in uploaded knowledge (RAG)."""
    context_docs = retrieve_context(query, top_k=top_k)

    if not context_docs:
        return {
            "answer": (
                "No relevant knowledge base content was found for this question. "
                "Upload runbooks, policies, or documentation to the Knowledge Center "
                "and try again."
            ),
            "sources": [],
            "grounded": False,
        }

    context_text = "\n\n".join(f"[DOC {i+1}: {d['document_title']}]\n{d['text']}" for i, d in enumerate(context_docs))

    if not openai_available():
        top = context_docs[0]
        answer = (
            f"Based on the matched knowledge source \"{top['document_title']}\", "
            f"here is the relevant guidance: {top['text'][:500]}..."
        )
        return {
            "answer": answer,
            "sources": context_docs,
            "grounded": True,
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You are NEXUS knowledge assistant. Answer the user's question strictly "
                "using the provided knowledge base excerpts. If the excerpts do not contain "
                "the answer, say so and provide general enterprise best practice. Be concise, "
                "factual, and cite the source document names."
            ),
        },
        {
            "role": "user",
            "content": f"QUESTION:\n{query}\n\nKNOWLEDGE BASE EXCERPTS:\n{context_text}",
        },
    ]
    try:
        answer = ai_chat(messages, temperature=0.3, max_tokens=900)
    except Exception as e:
        logger.warning("RAG AI call failed (%s), using extracted context", e)
        answer = context_docs[0]["text"][:600]

    return {
        "answer": answer,
        "sources": context_docs,
        "grounded": True,
    }


def synthesize_answer(query: str, agent_results: list[dict], context: str = "") -> dict:
    """Combine multi-agent findings into a unified executive answer."""
    if not openai_available():
        return _demo_synthesis(query, agent_results)

    messages = [
        {
            "role": "system",
            "content": (
                "You are NEXUS, an enterprise AI command center. Synthesize the findings "
                "from specialized agents into a clear, executive-level answer. Structure your "
                "response with a concise ANSWER, then EVIDENCE, then ROOT CAUSE, then "
                "RECOMMENDATIONS. Be specific and data-driven."
            ),
        },
        {
            "role": "user",
            "content": (
                f"USER QUERY:\n{query}\n\n"
                f"AGENT FINDINGS:\n{json.dumps(agent_results, indent=2, default=str)[:6000]}\n\n"
                f"EXTRA CONTEXT:\n{context[:2000]}"
            ),
        },
    ]
    try:
        return {"answer": ai_chat(messages, temperature=0.4, max_tokens=1200), "synthetic": False}
    except Exception as e:
        logger.warning("Synthesis AI failed (%s), using demo synthesis", e)
        return _demo_synthesis(query, agent_results)


def _demo_synthesis(query: str, agent_results: list[dict]) -> dict:
    lines = []
    for r in agent_results:
        if r.get("summary"):
            lines.append(r["summary"])
    answer = " ".join(l for l in lines if l) or (
        f"Analysis complete for: {query}. Data agents reviewed the available metrics; "
        "please connect live data sources for deeper insights."
    )
    return {"answer": answer, "synthetic": True}
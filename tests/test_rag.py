"""RAG pipeline tests: ingestion, storage, retrieval, Q&A."""

from app.ai.rag import ingest_document, retrieve_context, answer_with_knowledge
from app.ai.vector_store import vector_store
from app.database.session import SessionLocal
from app.models import KnowledgeChunk, KnowledgeDocument


def test_ingest_and_retrieve():
    vector_store.clear()
    content = (
        "Nexus incident runbook. When the database connection pool is exhausted, "
        "first rotate the pooled connections, then verify connection limits, "
        "and escalate to the DevOps team if latency stays above 300ms. "
    ) * 20

    doc_id = ingest_document(
        title="DB Runbook",
        filename="db.md",
        doc_type="markdown",
        data=content.encode("utf-8"),
        uploaded_by="tester",
    )
    assert doc_id is not None

    docs = retrieve_context("database connection pool exhausted", top_k=3)
    assert docs, "expected at least one matching chunk"
    assert docs[0]["document_title"] == "DB Runbook"


def test_answer_with_knowledge_demo_mode():
    vector_store.clear()
    content = (
        "Company policy: sensitive data exports require manager approval and "
        "must be logged to the audit trail before execution. "
    ) * 20
    ingest_document(
        title="Data Export Policy",
        filename="policy.txt",
        doc_type="txt",
        data=content.encode("utf-8"),
        uploaded_by="tester",
    )

    result = answer_with_knowledge("Do exports need approval?", top_k=2)
    assert "sources" in result
    assert result["grounded"] is True
    assert len(result["sources"]) > 0
    assert result["answer"]


def test_answer_without_knowledge_is_ungrounded():
    vector_store.clear()
    db = SessionLocal()
    db.query(KnowledgeChunk).delete()
    db.query(KnowledgeDocument).delete()
    db.commit()
    db.close()

    result = answer_with_knowledge("what is the meaning of life", top_k=2)
    assert result["grounded"] is False
    assert result["sources"] == []
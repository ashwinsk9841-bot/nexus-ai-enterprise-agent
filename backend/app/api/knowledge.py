"""Knowledge center: document upload + RAG-based Q&A endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..models import KnowledgeDocument
from ..ai.rag import ingest_document, answer_with_knowledge
from .deps import get_current_user

logger = logging.getLogger("nexus.knowledge")
router = APIRouter()


@router.get("/documents")
def list_documents(db: Session = Depends(get_db), _=Depends(get_current_user)):
    docs = db.query(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).all()
    return {
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "filename": d.filename,
                "doc_type": d.doc_type,
                "size_bytes": d.size_bytes,
                "status": d.status,
                "chunk_count": d.chunk_count,
                "uploaded_by": d.uploaded_by,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }


@router.post("/upload")
async def upload(
    files: list[UploadFile] = File(...),
    title: str = Form(default=""),
    user=Depends(get_current_user),
):
    results = []
    for file in files:
        content = await file.read()
        doc_type = _infer_type(file.filename or "")
        doc_title = title if title else (file.filename or "document").rsplit(".", 1)[0]

        try:
            doc_id = ingest_document(
                title=doc_title,
                filename=file.filename or "unnamed",
                doc_type=doc_type,
                data=content,
                uploaded_by=user.username,
            )
            results.append({"id": doc_id, "filename": file.filename, "status": "READY"})
        except Exception as e:
            logger.exception("Document ingestion failed: %s", file.filename)
            results.append({"filename": file.filename, "status": "FAILED", "error": str(e)})

    return {"uploaded": results, "count": len(results)}


class KBQuery(BaseModel):
    query: str


@router.post("/ask")
def ask(body: KBQuery, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    result = answer_with_knowledge(body.query, top_k=4)
    return {
        "answer": result["answer"],
        "sources": result.get("sources", []),
        "grounded": result.get("grounded", False),
    }


def _infer_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".md") or lower.endswith(".markdown"):
        return "markdown"
    return "txt"
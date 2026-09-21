"""Simple in-memory vector store used by the RAG pipeline.

In production this can be swapped for pgvector or a dedicated vector
database such as Qdrant or Pinecone via the same interface.
"""

import threading
import uuid
from typing import Optional


class InMemoryVectorStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._vectors: dict[str, list[float]] = {}

    def add(self, embedding: list[float]) -> str:
        vec_id = str(uuid.uuid4())
        with self._lock:
            self._vectors[vec_id] = embedding
        return vec_id

    def get(self, vec_id: str) -> Optional[list[float]]:
        with self._lock:
            return self._vectors.get(vec_id)

    def clear(self):
        with self._lock:
            self._vectors.clear()


vector_store = InMemoryVectorStore()
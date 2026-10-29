"""Persistent ChromaDB store. Upserts only IDs it has not seen, so weekly runs embed only new filings."""
from __future__ import annotations

from typing import Callable

from common.config import path, settings
from common.log import get_logger
from knowledge_base.chunker import Chunk

log = get_logger("store")


def client():
    import chromadb

    return chromadb.PersistentClient(path=str(path("chroma_dir")))


def collection(name: str | None = None, cl=None):
    cl = cl or client()
    return cl.get_or_create_collection(name or settings()["knowledge_base"]["collection"],
                                       metadata={"hnsw:space": "cosine"})


def add_chunks(col, chunks: list[Chunk], embed: Callable[[list[str]], list[list[float]]]) -> int:
    if not chunks:
        return 0
    ids = [c.id for c in chunks]
    existing = set()
    for i in range(0, len(ids), 500):
        existing |= set(col.get(ids=ids[i: i + 500], include=[])["ids"])
    new = [c for c in chunks if c.id not in existing]
    for i in range(0, len(new), 256):
        batch = new[i: i + 256]
        col.add(ids=[c.id for c in batch], documents=[c.text for c in batch],
                metadatas=[{k: v for k, v in c.meta.items() if v is not None} for c in batch],
                embeddings=embed([c.text for c in batch]))
    log.info("%s chunks: %s new, %s already stored", len(chunks), len(new), len(existing))
    return len(new)


def search(col, query_vec: list[float], k: int = 8, where: dict | None = None) -> list[dict]:
    r = col.query(query_embeddings=[query_vec], n_results=k, where=where or None,
                  include=["documents", "metadatas", "distances"])
    return [{"id": i, "score": round(1 - d, 4), "meta": m, "text": t}
            for i, d, m, t in zip(r["ids"][0], r["distances"][0], r["metadatas"][0], r["documents"][0])]

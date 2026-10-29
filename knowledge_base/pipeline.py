"""Module 3 entry points: ingest filings + notes, and query the corpus."""
from __future__ import annotations

import time
from pathlib import Path

from common.config import ROOT, settings
from common.log import get_logger
from knowledge_base import notes, store
from knowledge_base.chunker import chunk_filing, read_filing

log = get_logger("kb")
FILINGS = ROOT / "data" / "raw" / "filings"


def ingest_filings(tickers: list[str] | None = None, embed=None) -> int:
    from knowledge_base.embedder import embed_documents

    embed = embed or embed_documents
    cfg = settings()["knowledge_base"]
    col = store.collection(cfg["collection"])
    added = 0
    for f in sorted(FILINGS.glob("*.txt")):
        meta, text = read_filing(f)
        if tickers and meta["ticker"] not in tickers:
            continue
        added += store.add_chunks(col, chunk_filing(meta, text, cfg), embed)
    log.info("filings: %s new chunks | collection total %s", added, col.count())
    return added


def ingest_notes(embed=None) -> int:
    from knowledge_base.embedder import embed_documents

    embed = embed or embed_documents
    col = store.collection(settings()["knowledge_base"]["notes_collection"])
    chunks = notes.note_chunks()
    removed = notes.prune_stale(col, chunks)
    added = store.add_chunks(col, chunks, embed)
    log.info("notes: %s new chunks, %s stale removed | total %s", added, removed, col.count())
    return added


def watch_notes(interval: int = 30) -> None:
    """Poll the notes folder and ingest changes. Ctrl+C to stop."""
    folder = Path(ROOT / settings()["paths"]["user_notes_dir"])
    last = None
    log.info("watching %s every %ss", folder, interval)
    while True:
        state = sorted((p.name, p.stat().st_mtime) for p in folder.rglob("*") if p.is_file())
        if state != last:
            ingest_notes()
            last = state
        time.sleep(interval)


def query(text: str, ticker: str | None = None, section: str | None = None, k: int = 8) -> list[dict]:
    from knowledge_base.embedder import embed_query

    qv = embed_query(text)
    where = {"$and": [{"ticker": ticker}, {"section": section}]} if ticker and section else \
        ({"ticker": ticker} if ticker else ({"section": section} if section else None))
    cfg = settings()["knowledge_base"]
    hits = store.search(store.collection(cfg["collection"]), qv, k, where)
    if not ticker:
        hits += store.search(store.collection(cfg["notes_collection"]), qv, max(2, k // 4))
    return sorted(hits, key=lambda h: -h["score"])[:k]

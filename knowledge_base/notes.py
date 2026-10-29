"""Your own research: drop .md / .txt / .pdf files into knowledge_base/user_notes/.

IDs include a content hash, so an edited note is re-embedded and an unchanged one is skipped.
Old versions of an edited note are removed from the store.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from common.config import path, settings
from knowledge_base.chunker import Chunk, _split_narrative

EXTS = {".md", ".txt", ".pdf"}


def _read(p: Path) -> str:
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
    return p.read_text(errors="ignore")


def note_chunks() -> list[Chunk]:
    cfg = settings()["knowledge_base"]
    out = []
    for p in sorted(path("user_notes_dir").rglob("*")):
        if p.suffix.lower() not in EXTS or p.name.startswith("."):
            continue
        text = _read(p)
        h = hashlib.sha1(text.encode()).hexdigest()[:10]
        slug = "".join(ch if ch.isalnum() else "-" for ch in p.stem.lower())[:60]
        for i, c in enumerate(_split_narrative(text, cfg["chunk_chars"], cfg["chunk_overlap"])):
            out.append(Chunk(f"note_{slug}_{h}_n{i:03d}", c,
                             {"source": "user_note", "file": p.name, "note": slug, "hash": h}))
    return out


def prune_stale(col, current: list[Chunk]) -> int:
    """Delete chunks of notes whose content hash changed or whose file was removed."""
    keep = {c.id for c in current}
    stale = [i for i in col.get(where={"source": "user_note"}, include=[])["ids"] if i not in keep]
    if stale:
        col.delete(ids=stale)
    return len(stale)

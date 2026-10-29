import hashlib

import chromadb
import pytest

from common.config import settings
from knowledge_base import notes, pipeline, store
from knowledge_base.chunker import chunk_filing, split_sections

CFG = settings()["knowledge_base"]
RISK = "Our vessels are chartered to a small number of customers. " * 60
FILING = f"""FORM 10-K
Table of Contents
Item 1. Business 3
Item 1A. Risk Factors 10
Item 7. Management's Discussion 30

PART I
 Item 1. Business

We own and operate container ships. {"The fleet is chartered on long-term contracts. " * 40}

Item 1A. Risk Factors

{RISK}

Item 2. Properties
Offices in Athens.

Item 7. Management's Discussion and Analysis

Liquidity. Our senior notes mature in 2027. {"We expect to refinance using operating cash flow. " * 50}
[TABLE]
(in millions) | 2025 | 2024
Revenue | 1,020.5 | 980.1
Net income | 210.2 | 190.0
[/TABLE]
"""
META = {"ticker": "TEST", "cik": 1, "form": "10-K", "date": "2026-03-01", "url": "u"}


def fake_embed(texts):
    """Deterministic 16-dim vectors from a hash; good enough to test storage and IDs."""
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode()).digest()
        v = [b / 255 for b in h[:16]]
        n = sum(x * x for x in v) ** 0.5
        out.append([x / n for x in v])
    return out


def test_toc_lines_lose_to_real_sections():
    s = split_sections(FILING)
    assert s["1A"].count("chartered to a small number") == 60  # real body, not the TOC line


def test_chunks_are_sectioned_tabled_and_deterministic():
    a, b = chunk_filing(META, FILING, CFG), chunk_filing(META, FILING, CFG)
    assert [c.id for c in a] == [c.id for c in b]
    assert len({c.id for c in a}) == len(a)
    sections = {c.meta["section"] for c in a}
    assert {"item1_business", "item1a_risk_factors", "item7_mdna"} <= sections
    assert "item2_properties" not in sections
    tables = [c for c in a if c.meta["kind"] == "table"]
    assert len(tables) == 1 and "1,020.5" in tables[0].text
    assert all("[TABLE]" not in c.text for c in a if c.meta["kind"] == "narrative")
    assert all(len(c.text) <= CFG["chunk_chars"] + CFG["chunk_overlap"] + 5 for c in a)


@pytest.fixture
def mem(monkeypatch, tmp_path):
    cl = chromadb.EphemeralClient()
    for n in cl.list_collections():
        cl.delete_collection(n if isinstance(n, str) else n.name)
    monkeypatch.setattr(store, "client", lambda: cl)
    return cl


def test_rerun_embeds_nothing_new(mem):
    col = store.collection("test_col", mem)
    chunks = chunk_filing(META, FILING, CFG)
    assert store.add_chunks(col, chunks, fake_embed) == len(chunks)
    assert store.add_chunks(col, chunks, fake_embed) == 0
    hit = store.search(col, fake_embed([chunks[0].text])[0], k=1)[0]
    assert hit["id"] == chunks[0].id and hit["score"] > 0.99


def test_edited_note_replaces_old_version(mem, monkeypatch, tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    monkeypatch.setattr(notes, "path", lambda key: d)
    (d / "shipping thesis.md").write_text("Tanker rates stay high while the orderbook is thin. " * 20)
    pipeline.ingest_notes(embed=fake_embed)
    col = store.collection(CFG["notes_collection"])
    first = set(col.get()["ids"])
    (d / "shipping thesis.md").write_text("Container rates fall as new ships arrive in 2027. " * 20)
    pipeline.ingest_notes(embed=fake_embed)
    second = set(col.get()["ids"])
    assert first and second and not (first & second)


def test_10q_toc_part_ii_does_not_hide_part_i_mdna():
    q = (
        "PART I | FINANCIAL INFORMATION\nItem 1. | Financial Statements | 3\nItem 2. | MD&A | 20\n"
        "PART II | OTHER INFORMATION\nItem 1. | Legal Proceedings | 30\nItem 1A. | Risk Factors | 30\n\n"
        "Item 1. Financial Statements\n" + "Balance sheet line. " * 200 + "\n"
        "ITEM 2. Management's Discussion and Analysis\n" + "Charter revenue rose on higher rates. " * 80 + "\n"
        "PART II: OTHER INFORMATION\nItem 1 - Legal Proceedings\nNone.\nItem 1A - Risk Factors\nNo material changes.\n"
    )
    cs = chunk_filing(META | {"form": "10-Q"}, q, CFG)
    mdna = [c for c in cs if c.meta["section"] == "item2_mdna"]
    assert mdna and "Charter revenue" in mdna[0].text
    assert not any("Balance sheet line" in c.text for c in cs)  # Part I Item 1 (financials) is not kept

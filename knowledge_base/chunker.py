"""Section-aware chunking of SEC filings.

1. Split the filing by legal section headings ("Item 1A. Risk Factors", ...).
   A heading also appears in the table of contents, so for each item we keep the
   occurrence with the longest body (the real section, not the TOC line).
2. Keep only the sections the audit needs (KEEP below).
3. Inside a section, pull out [TABLE]...[/TABLE] blocks as separate table chunks,
   then split the narrative into overlapping chunks on paragraph boundaries.
4. Chunk IDs are deterministic: {ticker}_{form}_{date}_{section}_{kind}{n:03d},
   so re-running on the same filing produces the same IDs (no re-embedding).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Section labels per form. Foreign issuers (20-F) use different item numbers for the same content.
KEEP = {
    "10-K": {"1": "item1_business", "1A": "item1a_risk_factors", "3": "item3_legal", "7": "item7_mdna", "7A": "item7a_market_risk"},
    # 10-Q items repeat across parts (Part I Item 1 = financial statements, Part II Item 1 = legal),
    # so 10-Q keys are part-qualified.
    "10-Q": {"I-2": "item2_mdna", "I-3": "item3_market_risk", "II-1": "part2_item1_legal", "II-1A": "part2_item1a_risk_factors"},
    "20-F": {"3": "item3_key_info_risks", "4": "item4_company", "5": "item5_operating_review", "8": "item8_legal", "11": "item11_market_risk"},
}
HEADING = re.compile(r"^[ \t]*item[ \t]+(\d{1,2}[A-D]?)[\.:\s—–-]", re.I | re.M)
PART = re.compile(r"^[ \t]*part[ \t]+(I{1,2}|IV|III)\b", re.I | re.M)
TABLE = re.compile(r"\[TABLE\]\n(.*?)\n\[/TABLE\]", re.S)


@dataclass
class Chunk:
    id: str
    text: str
    meta: dict = field(default_factory=dict)


def read_filing(path: Path) -> tuple[dict, str]:
    first, _, body = path.read_text().partition("\n")
    return json.loads(first), body


def split_sections(text: str, by_part: bool = False) -> dict[str, str]:
    hits = [(m.start(), m.group(1).upper()) for m in HEADING.finditer(text)]
    if by_part:
        # The table of contents repeats "PART II", so only the LAST "PART II" heading marks
        # where Part II really starts; everything before it is Part I.
        p2 = [m.start() for m in PART.finditer(text) if m.group(1).upper() == "II"]
        cut = p2[-1] if p2 else len(text)
        hits = [(pos, f"{'II' if pos >= cut else 'I'}-{item}") for pos, item in hits]
    best: dict[str, str] = {}
    for i, (pos, item) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        body = text[pos:end]
        if len(body) > len(best.get(item, "")):
            best[item] = body
    return best


def _tail(text: str, overlap: int) -> str:
    """Last ~overlap chars, starting at a sentence (or at least a word) boundary."""
    tail = text[-overlap:]
    k = tail.find(". ")
    return tail[k + 2:] if k >= 0 else tail[tail.find(" ") + 1:]


def _split_narrative(text: str, size: int, overlap: int) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[A-Z][^\n]{0,80}\n)", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        while len(p) > size:  # very long paragraph: hard split at a sentence end near the limit
            cut = p.rfind(". ", 0, size)
            cut = cut + 1 if cut > size * 0.5 else size
            chunks.append((cur + "\n" + p[:cut]).strip() if cur else p[:cut].strip())
            cur, p = "", _tail(p[:cut], overlap) + " " + p[cut:]
        if len(cur) + len(p) + 1 > size and cur:
            chunks.append(cur.strip())
            cur = _tail(cur, overlap) + "\n" + p
        else:
            cur = (cur + "\n" + p) if cur else p
    if cur.strip():
        chunks.append(cur.strip())
    return [c for c in chunks if len(c) > 80]


def chunk_filing(meta: dict, text: str, cfg: dict) -> list[Chunk]:
    form = meta["form"]
    base = f"{meta['ticker']}_{form}_{meta['date']}"
    common = {k: meta[k] for k in ("ticker", "cik", "form", "date") if k in meta} | {"url": meta.get("url", "")}
    out: list[Chunk] = []

    if form in ("8-K", "6-K"):
        sections = {"current_report": text}
    else:
        found = split_sections(text, by_part=(form == "10-Q"))
        wanted = KEEP.get(form, {})
        sections = {label: found[item] for item, label in wanted.items() if item in found}
        if not sections:  # heading parse failed: keep the whole document rather than nothing
            sections = {"full_text": text}

    for label, body in sections.items():
        tables = TABLE.findall(body)
        narrative = TABLE.sub("\n", body)
        for i, t in enumerate(tables):
            if len(t) < 60:
                continue
            for j in range(0, len(t), cfg["table_chunk_chars"]):
                out.append(Chunk(f"{base}_{label}_t{i:03d}{'' if j == 0 else f'p{j // cfg["table_chunk_chars"]}'}",
                                 t[j: j + cfg["table_chunk_chars"]], common | {"section": label, "kind": "table"}))
        for i, c in enumerate(_split_narrative(narrative, cfg["chunk_chars"], cfg["chunk_overlap"])):
            out.append(Chunk(f"{base}_{label}_n{i:03d}", c, common | {"section": label, "kind": "narrative"}))
    return out

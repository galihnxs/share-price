"""Turn a saved browser-tool result into files under data/raw/.

Browser scripts wrap payloads as:
  <<<CSV>>>\n...\n<<<END>>>                      -> passed through as CSV
  <<<DOC {json meta}>>>\n...text...\n<<<END>>>  -> data/raw/filings/{ticker}_{form}_{date}_{acc}.txt
Each filing file starts with one JSON metadata line, then the plain text.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def load_text(result_file: str) -> str:
    """Tool results are a JSON list of parts; a string result is itself JSON-encoded,
    followed by a '(captured at origin ...)' footer."""
    raw = Path(result_file).read_text()
    try:
        parts = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    chunks = []
    for part in parts if isinstance(parts, list) else [parts]:
        t = part.get("text", "") if isinstance(part, dict) else str(part)
        if t.startswith('"'):
            t = json.loads(t[: t.rindex('"') + 1])
        chunks.append(t)
    return "\n".join(chunks)


def extract(result_file: str, out_root: str) -> list[Path]:
    text, out, root = load_text(result_file), [], Path(out_root)
    for meta, body in re.findall(r"<<<DOC (\{.*?\})>>>\n(.*?)\n<<<END>>>", text, re.S):
        m = json.loads(meta)
        acc = m.get("accession", "").replace("-", "")[-8:]
        p = root / "filings" / f"{m['ticker']}_{m['form']}_{m['date']}{'_' + acc if acc else ''}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(m) + "\n" + body)
        out.append(p)
    return out


if __name__ == "__main__":
    for p in extract(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "data/raw"):
        print(p, p.stat().st_size)

"""Turn a saved browser-tool result into files under data/raw/.

Browser scripts wrap payloads as:
  <<<CSV>>>\n...\n<<<END>>>                      -> passed through as CSV
  <<<DOC {json meta}>>>\n...text...\n<<<END>>>  -> data/raw/filings/{ticker}_{form}_{date}_{acc}.txt
  <<<PRICES {"symbol"}>>>\n...csv...\n<<<END>>> -> data/raw/prices/{SYMBOL}.csv (macro symbols -> data/raw/macro/)
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
    for meta, body in re.findall(r"<<<PRICES (\{.*?\})>>>\n(.*?)\n<<<END>>>", text, re.S):
        sym = json.loads(meta)["symbol"]
        p = root / "prices" / f"{sym}.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(drop_live_bar(body) + "\n")
        out.append(p)
    for body in re.findall(r"<<<CSV>>>\n(.*?)\n<<<END>>>", text, re.S):
        # Fundamentals CSV from 02_fundamentals.js (only kind of bare CSV payload).
        from datetime import date

        p = root / f"fundamentals_{date.today().isoformat()}.csv"
        p.write_text(body + "\n")
        out.append(p)
    out += write_macro(root)
    return out


def drop_live_bar(csv: str) -> str:
    """During the US session Yahoo returns today's bar so far. Keep only completed days
    (today's bar counts from 4:15 PM New York time)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("America/New_York"))
    today = now.date().isoformat()
    if now.hour * 60 + now.minute >= 16 * 60 + 15:
        return csv
    lines = csv.split("\n")
    return "\n".join(l for l in lines if not l.startswith(today))


# Yahoo macro symbols -> data/raw/macro/{name}.csv (date,value), the same format as the FRED fetcher.
YAHOO_MACRO = {"vix": "^VIX", "usd": "DX-Y.NYB", "oil": "CL=F"}
CURVE = ("^TNX", "2YY=F")  # 10Y yield and 2Y yield futures, both in percent


def write_macro(root: Path) -> list[Path]:
    import pandas as pd

    px, out = root / "prices", []
    (root / "macro").mkdir(parents=True, exist_ok=True)
    load = lambda s: pd.read_csv(px / f"{s}.csv", index_col="date")["close"] if (px / f"{s}.csv").exists() else None
    for name, sym in YAHOO_MACRO.items():
        s = load(sym)
        if s is not None:
            p = root / "macro" / f"{name}.csv"
            s.rename("value").rename_axis("date").to_csv(p)
            out.append(p)
    ten, two = (load(s) for s in CURVE)
    if ten is not None and two is not None:
        p = root / "macro" / "curve_10y2y.csv"
        (ten - two).dropna().rename("value").rename_axis("date").to_csv(p)
        out.append(p)
    return out


if __name__ == "__main__":
    for p in extract(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "data/raw"):
        print(p, p.stat().st_size)

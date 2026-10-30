"""SEC fetchers: universe by SIC, filing lists + text, XBRL companyfacts (point-in-time fundamentals).

Ports browser_fetch/01_universe.js and 03_filings.js. Output formats are unchanged:
  data/raw/universe_YYYY-MM-DD.csv                      ticker,cik,sic
  data/raw/filings/{ticker}_{form}_{date}_{acc8}.txt    one JSON meta line, then plain text
  data/raw/companyfacts/CIK##########.json              raw XBRL facts (cached)
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

from common.config import ROOT, cluster_of_sic, settings
from common.log import get_logger
from data_fetch.http import SEC

log = get_logger("sec")
RAW = ROOT / "data" / "raw"

# Foreign private issuers (many shippers) file 20-F / 6-K instead of 10-K / 8-K.
KIND = {"10-K": "annual", "20-F": "annual", "40-F": "annual", "10-Q": "quarterly", "8-K": "current", "6-K": "current"}
LIMITS = {"annual": 1, "quarterly": 2, "current": 4}
# 8-K items kept: material agreements, earnings, debt, impairments.
KEEP_8K_ITEMS = re.compile(r"1\.01|1\.02|2\.02|2\.03|2\.04|2\.06")


def _sector_of(sic: int) -> str | None:
    return cluster_of_sic(sic)


# ---------------------------------------------------------------- universe
def fetch_universe(sec: SEC | None = None, as_of: str | None = None) -> Path:
    """Exchange-listed tickers x companies registered under each target SIC code."""
    sec = sec or SEC()
    exchanges = set(settings()["sec"]["exchanges"])
    tj = sec.json("https://www.sec.gov/files/company_tickers_exchange.json")
    by_cik: dict[int, list[str]] = {}
    for cik, _name, ticker, ex in tj["data"]:
        if ex in exchanges and ticker:
            by_cik.setdefault(int(cik), []).append(ticker)

    html = sec.text("https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list")
    codes = sorted({int(t) for td in BeautifulSoup(html, "lxml").find_all("td")
                    if re.fullmatch(r"\d{4}", t := td.get_text(strip=True)) and _sector_of(int(t))})
    log.info("universe: %s exchange CIKs, %s target SIC codes", len(by_cik), len(codes))

    rows: list[tuple[str, int, int]] = []
    for i, sic in enumerate(codes, 1):
        for start in range(0, 5000, 100):
            url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC={sic}&owner=include"
                   f"&match=&start={start}&count=100&hidefilings=0")
            try:
                trs = BeautifulSoup(sec.text(url), "lxml").select("table.tableFile2 tr")[1:]
            except Exception as e:  # noqa: BLE001 - one bad page should not stop the crawl
                log.warning("SIC %s start %s: %s", sic, start, e)
                break
            for tr in trs:
                td = tr.find("td")
                if td and td.get_text(strip=True).isdigit():
                    cik = int(td.get_text(strip=True))
                    rows += [(t, cik, sic) for t in by_cik.get(cik, [])]
            if len(trs) < 100:
                break
        if i % 25 == 0:
            log.info("  %s/%s SIC codes, %s rows", i, len(codes), len(rows))

    # Drop preferreds/units/warrants, one row per ticker.
    seen, clean = set(), []
    for t, cik, sic in rows:
        if "-" in t or (len(t) >= 5 and t[-1] in "WUR") or t in seen:
            continue
        seen.add(t)
        clean.append((t, cik, sic))
    out = RAW / f"universe_{as_of or date.today().isoformat()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("ticker,cik,sic\n" + "\n".join(f"{t},{c},{s}" for t, c, s in clean) + "\n")
    log.info("universe: %s tickers -> %s", len(clean), out)
    return out


# ---------------------------------------------------------------- filings
def list_filings(cik: int, sec: SEC) -> dict:
    j = sec.json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    r, out, used = j["filings"]["recent"], [], dict.fromkeys(LIMITS, 0)
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    for i, form in enumerate(r["form"]):
        kind = KIND.get(form)
        if not kind or used[kind] >= LIMITS[kind]:
            continue
        if kind == "current" and r["filingDate"][i] < year_ago:
            continue
        if form == "8-K" and r["items"][i] and not KEEP_8K_ITEMS.search(r["items"][i]):
            continue
        used[kind] += 1
        acc = r["accessionNumber"][i]
        out.append({"form": form, "date": r["filingDate"][i], "period": r["reportDate"][i], "accession": acc,
                    "items": r["items"][i] or "",
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{r['primaryDocument'][i]}"})
    return {"name": j["name"], "sic": j["sic"], "tickers": j["tickers"], "filings": out}


def html_to_text(html: str) -> str:
    """Same rules as the browser version: hidden iXBRL facts removed, data tables fenced as [TABLE]."""
    soup = BeautifulSoup(html, "lxml")
    for e in soup(["script", "style", "head"]):
        e.decompose()
    for e in soup.select('[style*="display:none"], [style*="display: none"]'):
        e.decompose()
    for t in reversed(soup.find_all("table")):
        rows = [[re.sub(r"\s+", " ", c.get_text(" ")).strip() for c in tr.find_all(["td", "th"])] for tr in t.find_all("tr")]
        rows = [[c for c in r if c] for r in rows]
        rows = [r for r in rows if r]
        cells = [c for r in rows for c in r]
        numeric = sum(bool(re.search(r"\d", c)) for c in cells)
        is_data = len(rows) >= 2 and len(cells) >= 4 and numeric / len(cells) >= 0.3
        body = "\n[TABLE]\n" + "\n".join(" | ".join(r) for r in rows) + "\n[/TABLE]\n" if is_data \
            else "\n" + "\n".join(" ".join(r) for r in rows) + "\n"
        t.replace_with(soup.new_string(body))
    for e in soup.find_all(["p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"]):
        e.append("\n")
    text = (soup.body or soup).get_text().replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def filing_text(f: dict, sec: SEC) -> str:
    text = html_to_text(sec.text(f["url"]))
    # 8-K/6-K primary docs are often a cover page; the substance is in Exhibit 99.x.
    # 10-K/20-F may incorporate MD&A by reference into Exhibit 13 (e.g. SENEB).
    pat = r"ex(hibit)?[-_ ]?99" if KIND[f["form"]] == "current" else r"ex(hibit)?[-_ ]?13(\b|[-_.])"
    d = f["url"][: f["url"].rindex("/") + 1]
    try:
        items = sec.json(d + "index.json")["directory"]["item"]
        for n in [x["name"] for x in items if re.search(pat, x["name"], re.I) and re.search(r"\.html?$", x["name"], re.I)][:3]:
            text += f"\n\n[EXHIBIT {n}]\n" + html_to_text(sec.text(d + n))
    except Exception:  # noqa: BLE001 - index missing: keep primary doc only
        pass
    return text


def fetch_filings(tickers: dict[str, int], sec: SEC | None = None) -> list[Path]:
    """tickers: {ticker: cik}. Skips filings already on disk (same name as the browser layer wrote)."""
    sec = sec or SEC()
    out_dir = RAW / "filings"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for t, cik in tickers.items():
        try:
            lst = list_filings(cik, sec)
        except Exception as e:  # noqa: BLE001
            log.warning("%s: submissions failed: %s", t, e)
            continue
        for f in lst["filings"]:
            p = out_dir / f"{t}_{f['form']}_{f['date']}_{f['accession'].replace('-', '')[-8:]}.txt"
            if p.exists():
                continue
            try:
                body = filing_text(f, sec)
            except Exception as e:  # noqa: BLE001
                log.warning("%s %s %s: %s", t, f["form"], f["date"], e)
                continue
            p.write_text(json.dumps({"ticker": t, "cik": int(cik), **f}) + "\n" + body)
            written.append(p)
            log.info("  %s %s %s  %s chars", t, f["form"], f["date"], f"{len(body):,}")
    return written


# ---------------------------------------------------------------- XBRL companyfacts
def companyfacts(cik: int, sec: SEC | None = None, max_age_days: int = 7) -> dict:
    p = RAW / "companyfacts" / f"CIK{int(cik):010d}.json"
    if p.exists() and time.time() - p.stat().st_mtime < max_age_days * 86400:
        return json.loads(p.read_text())
    sec = sec or SEC()
    try:
        j = sec.json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")
    except Exception as e:  # noqa: BLE001 - some filers have no XBRL facts
        log.warning("companyfacts CIK %s: %s", cik, e)
        j = {}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(j))
    return j


# ---------------------------------------------------------------- 8-K watch (held + paper positions)
def recent_8k(cik: int, since: str, sec: SEC | None = None) -> list[dict]:
    """8-K/6-K filings since a date, with SEC acceptance time (Eastern) and item numbers."""
    sec = sec or SEC()
    r = sec.json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")["filings"]["recent"]
    out = []
    for i, form in enumerate(r["form"]):
        if form not in ("8-K", "6-K") or r["filingDate"][i] < since:
            continue
        acc = r["accessionNumber"][i]
        out.append({"form": form, "date": r["filingDate"][i], "accepted": r["acceptanceDateTime"][i],
                    "items": r["items"][i] or "", "accession": acc,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{r['primaryDocument'][i]}"})
    return out


def watch_8k(tickers: dict[str, int], since: str) -> dict[str, list[dict]]:
    sec = SEC()
    out = {}
    for t, cik in tickers.items():
        try:
            out[t] = recent_8k(cik, since, sec)
        except Exception as e:  # noqa: BLE001
            log.warning("8-K watch %s: %s", t, e)
    return out


def accepted_eastern(f: dict) -> str:
    """EDGAR acceptanceDateTime is UTC; return New York local time as YYYY-MM-DDTHH:MM:SS."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    utc = datetime.fromisoformat(f["accepted"].replace("Z", "+00:00"))
    return utc.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%dT%H:%M:%S")


def friday_after_hours(filings: dict[str, list[dict]], friday: str) -> dict[str, list[dict]]:
    """Filings accepted between 4:00 PM New York time on the given Friday and Monday's 9:30 AM open."""
    from datetime import date as _date, timedelta

    start = f"{friday}T16:00:00"
    end = f"{(_date.fromisoformat(friday) + timedelta(days=3)).isoformat()}T09:30:00"
    out = {}
    for t, fs in filings.items():
        hits = [{**f, "accepted_et": accepted_eastern(f)} for f in fs if start <= accepted_eastern(f) < end]
        if hits:
            out[t] = hits
    return out


# ---------------------------------------------------------------- company names (for display)
def company_names(max_age_days: int = 7) -> dict[str, dict]:
    """{ticker: {"name": ..., "exchange": ...}} from SEC company_tickers_exchange.json, cached in data/raw."""
    p = RAW / "company_names.json"
    if p.exists() and time.time() - p.stat().st_mtime < max_age_days * 86400:
        return json.loads(p.read_text())
    try:
        tj = SEC().json("https://www.sec.gov/files/company_tickers_exchange.json")
    except Exception as e:  # noqa: BLE001 - names are cosmetic; keep the old cache if SEC is down
        log.warning("company names: %s", e)
        return json.loads(p.read_text()) if p.exists() else {}
    out = {}
    for _cik, name, ticker, ex in tj["data"]:
        if ticker and ticker not in out:
            # SEC often stores names in capitals ("GENERAL MOTORS CO"); make those readable.
            name = re.sub(r"\s*/[A-Za-z]{2,3}/?\s*$", "", name)  # drop SEC state tags like "/DE/"
            out[ticker] = {"name": name.title() if name.isupper() else name, "exchange": ex or ""}
    p.write_text(json.dumps(out))
    return out

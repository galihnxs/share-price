"""Yahoo fetchers: screener fundamentals (port of browser_fetch/02_fundamentals.js) and daily OHLCV.

Outputs:
  data/raw/fundamentals_YYYY-MM-DD.csv   same columns as the browser layer (USD millions)
  data/raw/prices/{SYMBOL}.csv           date,open,high,low,close,adj_close,volume
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from common.config import ROOT, settings
from common.log import get_logger
from data_fetch.http import Yahoo

log = get_logger("yahoo")
RAW = ROOT / "data" / "raw"

KEYS = {"fcf": "annualFreeCashFlow", "ocf": "annualOperatingCashFlow", "tbv": "annualTangibleBookValue",
        "debt": "annualTotalDebt", "eq": "annualStockholdersEquity", "sh": "annualOrdinarySharesNumber",
        "eps": "annualDilutedEPS"}
HEADER = ["ticker", "price", "mcap", "fwd_pe", "pe_ttm", "fcf_ttm", "ocf_ttm", "currency", "fy_end"] + \
    [f"{k}_y{i}" for k in KEYS for i in range(1, 5)]


def _m(v):  # -> USD millions, 1dp
    return "" if v is None else round(v / 1e5) / 10


def _r(v, d=3):
    return "" if v is None else round(float(v), d)


def _raw(d: dict | None, k: str):
    return ((d or {}).get(k) or {}).get("raw")


def fundamentals_row(y: Yahoo, t: str) -> list | None:
    """None when the ticker fails the pre-filter (mcap >= $300M, OCF > 0, FCF yield > 3%)."""
    q = y.json(f"/v10/finance/quoteSummary/{quote(t)}",
               {"modules": "summaryDetail,defaultKeyStatistics,financialData,price"})
    r = ((q.get("quoteSummary") or {}).get("result") or [None])[0]
    if not r:
        raise ValueError("no quote")
    sd, ks, fd, pr = (r.get(k) or {} for k in ("summaryDetail", "defaultKeyStatistics", "financialData", "price"))
    mcap = _raw(sd, "marketCap") or _raw(pr, "marketCap")
    ocf, fcf = _raw(fd, "operatingCashflow"), _raw(fd, "freeCashflow")
    gate = settings()["screener"]["rules"]["market_cap_min"]
    if not (mcap and mcap >= gate and ocf and ocf > 0 and fcf and fcf / mcap > 0.03):
        return None
    p2 = int(time.time())
    ts = y.json(f"/ws/fundamentals-timeseries/v1/finance/timeseries/{quote(t)}",
                {"symbol": t, "type": ",".join(KEYS.values()), "period1": p2 - 6 * 365 * 86400, "period2": p2})
    by, fy = {}, ""
    for x in (ts.get("timeseries") or {}).get("result") or []:
        k = x["meta"]["type"][0]
        arr = sorted([a for a in x.get(k) or [] if a], key=lambda a: a["asOfDate"])[-4:]
        by[k] = arr
        if arr and arr[-1]["asOfDate"] > fy:
            fy = arr[-1]["asOfDate"]
    row = [t, _r(_raw(fd, "currentPrice"), 2), _m(mcap), _r(_raw(sd, "forwardPE") or _raw(ks, "forwardPE"), 2),
           _r(_raw(sd, "trailingPE"), 2), _m(fcf), _m(ocf), fd.get("financialCurrency") or pr.get("currency") or "", fy]
    for k, yk in KEYS.items():
        vals = [(a.get("reportedValue") or {}).get("raw") for a in by.get(yk, [])]
        for v in [None] * (4 - len(vals)) + vals:
            row.append(_r(v, 2) if k == "eps" else _m(v))
    return row


def fetch_fundamentals(tickers: list[str], as_of: str | None = None, workers: int = 3) -> Path:
    y = Yahoo()
    rows, errors = [], []

    def one(t: str):
        for a in range(3):
            try:
                return fundamentals_row(y, t)
            except Exception as e:  # noqa: BLE001
                if a == 2:
                    errors.append(f"{t}:{str(e)[:40]}")
                time.sleep(1.5 * (a + 1))
        return None

    with ThreadPoolExecutor(workers) as ex:
        for i, row in enumerate(ex.map(one, tickers), 1):
            if row:
                rows.append(row)
            if i % 200 == 0:
                log.info("  %s/%s done, %s kept", i, len(tickers), len(rows))
    out = RAW / f"fundamentals_{as_of or date.today().isoformat()}.csv"
    pd.DataFrame(rows, columns=HEADER).to_csv(out, index=False)
    log.info("fundamentals: %s kept of %s, %s errors -> %s", len(rows), len(tickers), len(errors), out)
    return out


def fetch_prices(symbols: list[str], years: int = 6, y: Yahoo | None = None) -> dict[str, Path]:
    """Daily bars from the chart API. Writes one CSV per symbol (overwrites: full history each time)."""
    y = y or Yahoo()
    out_dir = RAW / "prices"
    out_dir.mkdir(parents=True, exist_ok=True)
    p2 = int(time.time())
    done = {}
    for s in symbols:
        try:
            j = y.json(f"/v8/finance/chart/{quote(s)}",
                       {"period1": p2 - years * 365 * 86400, "period2": p2, "interval": "1d", "events": "div,split"})
            res = j["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
            df = pd.DataFrame({"date": pd.to_datetime(res["timestamp"], unit="s").normalize().date,
                               "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
                               "adj_close": adj, "volume": q["volume"]}).dropna(subset=["close"])
            p = out_dir / f"{s.replace('^', '_').replace('=', '_')}.csv"
            df.drop_duplicates("date", keep="last").to_csv(p, index=False)
            done[s] = p
        except Exception as e:  # noqa: BLE001
            log.warning("prices %s: %s", s, e)
        time.sleep(0.3)
    log.info("prices: %s/%s symbols -> %s", len(done), len(symbols), out_dir)
    return done

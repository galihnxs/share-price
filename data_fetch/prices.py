"""Daily prices (Tiingo) and macro series (FRED API), keys from .env.

Yahoo blocks plain Python requests from this Mac (HTTP 429), so prices come from Tiingo's free tier
(50 new symbols/hour, 1,000 requests/day). Macro comes from the FRED API; without FRED_API_KEY it
falls back to ETF proxies on Tiingo (see MACRO).

Outputs:
  data/raw/prices/{SYMBOL}.csv   date,open,high,low,close,adj_close,volume
  data/raw/macro/{NAME}.csv      date,value
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from common.config import ROOT
from common.log import get_logger

log = get_logger("prices")
RAW = ROOT / "data" / "raw"

# name -> (FRED series, Tiingo ETF proxy used when there is no FRED key)
MACRO = {
    "vix": ("VIXCLS", "VIXY"),          # VIX close | VIX short-term futures ETF
    "usd": ("DTWEXBGS", "UUP"),         # broad trade-weighted dollar (DXY stand-in) | dollar bull ETF
    "oil": ("DCOILWTICO", "USO"),       # WTI spot (CL=F stand-in) | oil fund ETF
    "curve_10y2y": ("T10Y2Y", None),    # 10Y-2Y spread | proxy: IEF vs SHY, built in ml_engine
}
CURVE_PROXY = ("IEF", "SHY")


def _key(name: str) -> str:
    return os.getenv(name, "").strip().strip('"')


def tiingo_symbol(t: str) -> str:
    return t.replace(".", "-")  # Tiingo writes share classes as BRK-B


def fetch_prices(symbols: list[str], years: int = 6, refresh: bool = False) -> dict[str, Path]:
    key = _key("TIINGO_API_KEY")
    if not key:
        raise RuntimeError("TIINGO_API_KEY is missing in .env (free key: https://www.tiingo.com/account/api/token)")
    out_dir = RAW / "prices"
    out_dir.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Token {key}"})
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    done = {}
    for sym in symbols:
        p = out_dir / f"{sym}.csv"
        if p.exists() and not refresh and time.time() - p.stat().st_mtime < 12 * 3600:
            done[sym] = p
            continue
        r = s.get(f"https://api.tiingo.com/tiingo/daily/{tiingo_symbol(sym)}/prices",
                  params={"startDate": start, "resampleFreq": "daily"}, timeout=60)
        if r.status_code == 429 or "hourly request" in r.text.lower():
            log.warning("Tiingo rate limit hit at %s; %s symbols done. Re-run later to resume.", sym, len(done))
            break
        if r.status_code != 200 or not r.text.startswith("["):
            log.warning("prices %s: %s %s", sym, r.status_code, r.text[:120])
            continue
        rows = r.json()
        if not rows:
            log.warning("prices %s: no rows", sym)
            continue
        df = pd.DataFrame(rows)
        df = pd.DataFrame({"date": df["date"].str[:10], "open": df["adjOpen"], "high": df["adjHigh"],
                           "low": df["adjLow"], "close": df["close"], "adj_close": df["adjClose"],
                           "volume": df["adjVolume"]})
        df.to_csv(p, index=False)
        done[sym] = p
        time.sleep(0.2)
    log.info("prices: %s/%s symbols in %s", len(done), len(symbols), out_dir)
    return done


def fetch_macro(years: int = 6) -> dict[str, Path]:
    """FRED when FRED_API_KEY is set, else ETF proxies through Tiingo."""
    out_dir = RAW / "macro"
    out_dir.mkdir(parents=True, exist_ok=True)
    key = _key("FRED_API_KEY")
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    done = {}
    if key:
        for name, (series, _) in MACRO.items():
            r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                             params={"series_id": series, "api_key": key, "file_type": "json",
                                     "observation_start": start}, timeout=60)
            r.raise_for_status()
            obs = pd.DataFrame(r.json()["observations"])
            obs["value"] = pd.to_numeric(obs["value"], errors="coerce")  # FRED marks holidays as "."
            p = out_dir / f"{name}.csv"
            obs[["date", "value"]].dropna().to_csv(p, index=False)
            done[name] = p
        log.info("macro (FRED): %s", ", ".join(done))
    else:
        proxies = [etf for _, etf in MACRO.values() if etf] + list(CURVE_PROXY)
        log.info("macro: no FRED_API_KEY, using ETF proxies %s", proxies)
        fetch_prices(proxies, years)
    return done

"""Module 1 runner: read browser-fetched CSVs from data/raw/, screen, write top 30."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from common.config import ROOT, path, sectors, settings
from common.log import get_logger
from screener.rules import add_metrics, apply_rules, score, select

log = get_logger("screener")
RAW = ROOT / "data" / "raw"

OUT_COLS = [
    "rank", "ticker", "cik", "sector", "sic", "pass_status", "rules_passed", "rules_total", "failed_rules",
    "flag", "score", "price", "mcap", "fwd_pe", "pe_ttm", "pe_pct_proxy", "ptbv", "fcf_yield", "ocf_used",
    "de_prev", "de_now", "share_growth", "fy_end",
]


def sector_of_sic(sic: int) -> str | None:
    for name, ranges in sectors().items():
        if any(lo <= int(sic) <= hi for lo, hi in ranges):
            return name
    return None


def latest_raw(prefix: str) -> Path:
    files = sorted(RAW.glob(f"{prefix}_*.csv"))
    if not files:
        raise FileNotFoundError(f"No data/raw/{prefix}_*.csv. Run the browser fetch step first (see browser_fetch/README.md).")
    return files[-1]


def run(as_of: str | None = None) -> pd.DataFrame:
    cfg = settings()["screener"]
    uni_f, fun_f = latest_raw("universe"), latest_raw("fundamentals")
    uni = pd.read_csv(uni_f).drop_duplicates("ticker")
    fun = pd.read_csv(fun_f).drop_duplicates("ticker")
    log.info("universe %s rows (%s) | fundamentals %s rows (%s)", len(uni), uni_f.name, len(fun), fun_f.name)

    uni["sector"] = uni["sic"].map(sector_of_sic)
    df = fun.merge(uni[["ticker", "cik", "sic", "sector"]], on="ticker", how="inner")
    # One row per company: multiple share classes (e.g. SENEA/SENEB) share a CIK. Keep the larger listing.
    df = df.sort_values("mcap", ascending=False).drop_duplicates("cik").reset_index(drop=True)
    # Captive-finance arms (GM Financial, Ford Credit) push lending cash flows into reported FCF.
    df["flag"] = df["ticker"].map(cfg.get("flags", {})).fillna("")
    df = add_metrics(df)
    df = apply_rules(df, cfg["rules"])
    df = score(df, cfg["score_weights"])
    top = select(df, cfg["top_n"])

    as_of = as_of or date.today().isoformat()
    out_dir = path("screener_out")
    df.to_csv(out_dir / f"screened_all_{as_of}.csv", index=False)
    top[[c for c in OUT_COLS if c in top]].to_csv(out_dir / f"candidates_{as_of}.csv", index=False)
    (out_dir / f"candidates_{as_of}.json").write_text(
        json.dumps({"as_of": as_of, "source_files": [uni_f.name, fun_f.name],
                    "hard_pass_count": int(df["hard_pass"].sum()),
                    "candidates": top[[c for c in OUT_COLS if c in top]].round(4).to_dict("records")}, indent=2, default=str)
    )
    log.info("hard passes: %s | output: %s candidates -> %s", int(df["hard_pass"].sum()), len(top), out_dir)
    return top

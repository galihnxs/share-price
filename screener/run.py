"""Module 1 runner: two-track screen per scenario cluster, regime-gated, top 6 per cluster (max 36) + held."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from common.config import ROOT, cluster_of_sic, path, scenarios, settings
from common.log import get_logger
from screener.rules import (add_metrics, add_track_b_metrics, apply_rules, apply_track_b, score, score_track_b,
                            select_by_cluster)

log = get_logger("screener")
RAW = ROOT / "data" / "raw"

OUT_COLS = [
    "rank", "ticker", "cik", "cluster", "track", "sector", "sic", "pass_status", "rules_passed", "rules_total",
    "failed_rules", "flag", "score", "price", "mcap", "fwd_pe", "pe_ttm", "pe_pct_proxy", "ptbv", "fcf_yield", "ocf_used",
    "de_prev", "de_now", "share_growth", "cash_to_debt", "runway_months", "price_to_book", "rnd_intensity", "fy_end",
]


def read_csv(p: Path) -> pd.DataFrame:
    # Tickers like "NA" must stay text; only empty cells are missing.
    return pd.read_csv(p, dtype={"ticker": str}, keep_default_na=False, na_values=[""])


def latest_raw(prefix: str) -> Path:
    files = sorted(RAW.glob(f"{prefix}_*.csv"))
    if not files:
        raise FileNotFoundError(f"No data/raw/{prefix}_*.csv. Run the fetch step first (see browser_fetch/README.md).")
    return files[-1]


def ai_gate(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """Scenario 1 gate: ai_hardware names pass only if that scenario is POST_RECOVERY or the stock is deep value."""
    from regime_engine.state_tracker import load

    st = load().get("scenarios", {}).get("ASIA_US_AI_DIVERGENCE", {}).get("state")
    deep = df["fwd_pe"].between(0, cfg["ai_hardware_max_fwd_pe"], inclusive="right")
    return (df["cluster"] != "ai_hardware") | (st == "POST_RECOVERY") | deep


def held_rows(df: pd.DataFrame, uni: pd.DataFrame) -> pd.DataFrame:
    """OPEN positions are always audited, even if they fail the screen now."""
    from portfolio_ledger.db import open_positions

    held = sorted({p["ticker"] for p in open_positions()})
    rows = df[df["ticker"].isin(held)].copy()
    missing = [t for t in held if t not in set(rows["ticker"])]
    if missing:
        extra = uni[uni["ticker"].isin(missing)][["ticker", "cik", "sic"]].copy()
        for t in set(missing) - set(extra["ticker"]):
            extra = pd.concat([extra, pd.DataFrame([{"ticker": t}])])
        extra["cluster"] = extra["sic"].map(lambda s: cluster_of_sic(s) if pd.notna(s) else None)
        rows = pd.concat([rows, extra])
    rows["pass_status"] = "HELD"
    return rows


def run(as_of: str | None = None) -> pd.DataFrame:
    cfg, sc = settings()["screener"], scenarios()
    uni_f, fun_f = latest_raw("universe"), latest_raw("fundamentals")
    uni = read_csv(uni_f).drop_duplicates("ticker")
    fun = read_csv(fun_f).drop_duplicates("ticker")
    log.info("universe %s rows (%s) | fundamentals %s rows (%s)", len(uni), uni_f.name, len(fun), fun_f.name)

    uni["cluster"] = uni["sic"].map(cluster_of_sic)
    df = fun.drop(columns=[c for c in ("track",) if c in fun]).merge(
        uni[["ticker", "cik", "sic", "cluster"]], on="ticker", how="inner")
    df = df[df["cluster"].notna()]
    df["track"] = df["cluster"].map(lambda c: sc["clusters"][c]["track"])
    df["sector"] = df["cluster"]
    # One row per company: multiple share classes (e.g. SENEA/SENEB) share a CIK. Keep the larger listing.
    df = df.sort_values("mcap", ascending=False).drop_duplicates("cik").reset_index(drop=True)
    # Captive-finance arms (GM Financial, Ford Credit) push lending cash flows into reported FCF.
    df["flag"] = df["ticker"].map(cfg.get("flags", {})).fillna("")
    df = add_metrics(df)

    a = df[df["track"] == "A"]
    a = score(apply_rules(a, cfg["track_a"]["rules"]), cfg["track_a"]["score_weights"])
    b = add_track_b_metrics(df[df["track"] == "B"])
    b = score_track_b(apply_track_b(b, cfg["track_b"]["rules"]), cfg["track_b"]["score_weights"])
    df = pd.concat([a, b], ignore_index=True)
    df["regime_gate"] = ai_gate(df, cfg)
    log.info("ai_hardware blocked by the scenario-1 gate: %s", int((~df["regime_gate"]).sum()))

    top = select_by_cluster(df[df["regime_gate"]], cfg["top_per_cluster"], cfg["max_candidates"])
    held = held_rows(df, uni)
    held = held[~held["ticker"].isin(top["ticker"])]
    if len(held):
        held.insert(0, "rank", range(len(top) + 1, len(top) + len(held) + 1))
        top = pd.concat([top, held], ignore_index=True)

    as_of = as_of or date.today().isoformat()
    out_dir = path("screener_out")
    df.to_csv(out_dir / f"screened_all_{as_of}.csv", index=False)
    top[[c for c in OUT_COLS if c in top]].to_csv(out_dir / f"candidates_{as_of}.csv", index=False)
    rec = top[[c for c in OUT_COLS if c in top]].replace([np.inf, -np.inf], None).round(4)
    (out_dir / f"candidates_{as_of}.json").write_text(
        json.dumps({"as_of": as_of, "source_files": [uni_f.name, fun_f.name],
                    "hard_pass_count": int(df["hard_pass"].sum()),
                    "per_cluster": top["cluster"].value_counts().to_dict(),
                    "candidates": json.loads(rec.to_json(orient="records"))}, indent=2, default=str)
    )
    log.info("hard passes: %s | output: %s candidates %s -> %s", int(df["hard_pass"].sum()), len(top),
             top["cluster"].value_counts().to_dict(), out_dir)
    return top

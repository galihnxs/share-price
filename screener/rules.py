"""Module 1 rules: hard deep-value filters + composite rank score.

Input: one row per ticker (see data/raw/fundamentals_*.csv, written by the
browser fetch step). Annual columns use suffixes _y1.._y4 (oldest -> newest).
All money columns are in USD millions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _latest(df: pd.DataFrame, key: str) -> pd.Series:
    """Most recent non-null annual value (y4, else y3, ...)."""
    cols = [f"{key}_y{i}" for i in (4, 3, 2, 1)]
    cols = [c for c in cols if c in df]
    return df[cols].bfill(axis=1).iloc[:, 0] if cols else pd.Series(np.nan, index=df.index)


def _prior(df: pd.DataFrame, key: str) -> pd.Series:
    """Second most recent non-null annual value."""
    vals = df[[f"{key}_y{i}" for i in (1, 2, 3, 4) if f"{key}_y{i}" in df]]

    def pick(row):
        v = row.dropna().values
        return v[-2] if len(v) >= 2 else np.nan

    return vals.apply(pick, axis=1)


def add_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    fcf = out["fcf_ttm"].where(out["fcf_ttm"].notna(), _latest(out, "fcf"))
    ocf = out["ocf_ttm"].where(out["ocf_ttm"].notna(), _latest(out, "ocf"))
    out["fcf_yield"] = fcf / out["mcap"]
    out["ocf_used"] = ocf
    out["tbv"] = _latest(out, "tbv")
    out["ptbv"] = np.where(out["tbv"] > 0, out["mcap"] / out["tbv"], np.nan)

    de_now = _latest(out, "debt") / _latest(out, "eq")
    de_prev = _prior(out, "debt") / _prior(out, "eq")
    out["de_now"], out["de_prev"] = de_now, de_prev
    # Stable = within +5% of last year's ratio. Zero-debt companies count as stable.
    out["de_ok"] = (de_now.fillna(0) <= de_prev.fillna(0) * 1.05 + 1e-9) | (_latest(out, "debt").fillna(0) == 0)

    out["share_growth"] = _latest(out, "sh") / _prior(out, "sh") - 1

    # P/E percentile proxy: today's trailing P/E vs P/E implied by each past
    # year's EPS at today's price. Only 4 points, so it is a rough proxy, labelled as such.
    eps_cols = [c for c in (f"eps_y{i}" for i in (1, 2, 3, 4)) if c in out]

    def pe_pct(row):
        eps = row[eps_cols].astype(float)
        eps = eps[eps > 0]
        if len(eps) < 3 or pd.isna(row["price"]) or pd.isna(row.get("pe_ttm")):
            return np.nan
        hist = row["price"] / eps
        return float((hist < row["pe_ttm"]).mean())

    out["pe_pct_proxy"] = out.apply(pe_pct, axis=1)
    return out


def apply_rules(df: pd.DataFrame, r: dict) -> pd.DataFrame:
    out = df.copy()
    out["r_valuation_pe"] = (out["fwd_pe"].between(0, r["forward_pe_max"], inclusive="neither")) | (
        out["pe_pct_proxy"] <= r["pe_percentile_max"]
    )
    out["r_valuation_ptbv"] = out["ptbv"].between(0, r["ptbv_max"], inclusive="neither")
    out["r_fcf_yield"] = out["fcf_yield"] > r["fcf_yield_min"]
    out["r_ocf_positive"] = out["ocf_used"] > 0
    out["r_debt_trend"] = out["de_ok"].astype(bool)
    out["r_mcap"] = out["mcap"] * 1e6 > r["market_cap_min"]
    out["r_dilution"] = out["share_growth"].fillna(0) < r["share_growth_max"]
    # Market cap is in USD; ratios are only valid if the statements are in USD too.
    out["r_usd_statements"] = out.get("currency", pd.Series("USD", index=out.index)).fillna("USD").eq("USD")

    rule_cols = [c for c in out if c.startswith("r_")]
    out["rules_passed"] = out[rule_cols].sum(axis=1)
    out["rules_total"] = len(rule_cols)
    out["hard_pass"] = out[rule_cols].all(axis=1)
    # Safety gates are never relaxed in the ranked fill: real company, cash positive, not diluting.
    out["safety_pass"] = out["r_mcap"] & out["r_ocf_positive"] & out["r_dilution"] & out["r_usd_statements"]
    out["failed_rules"] = out[rule_cols].apply(lambda s: ",".join(c[2:] for c, v in s.items() if not v), axis=1)
    return out


def _pct_rank(s: pd.Series, higher_is_better: bool) -> pd.Series:
    return s.rank(pct=True, ascending=higher_is_better).fillna(0.0)


def score(df: pd.DataFrame, w: dict) -> pd.DataFrame:
    out = df.copy()
    fpe = out["fwd_pe"].where(out["fwd_pe"] > 0)  # negative forward P/E = expected loss -> worst
    out["score"] = (
        w["fcf_yield"] * _pct_rank(out["fcf_yield"], True)
        + w["forward_pe"] * _pct_rank(fpe, False)
        + w["ptbv"] * _pct_rank(out["ptbv"], False)
        + w["debt_trend"] * _pct_rank(-(out["de_now"] - out["de_prev"]), True)
        + w["dilution"] * _pct_rank(out["share_growth"], False)
    )
    return out


def select(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Hard passes first (by score), then ranked fill from safety-passing names."""
    hard = df[df["hard_pass"]].sort_values("score", ascending=False)
    fill = df[~df["hard_pass"] & df["safety_pass"]].sort_values(["rules_passed", "score"], ascending=False)
    picked = pd.concat([hard, fill]).head(top_n).copy()
    picked["pass_status"] = np.where(picked["hard_pass"], "HARD_PASS", "RANKED_FILL")
    picked.insert(0, "rank", range(1, len(picked) + 1))
    return picked

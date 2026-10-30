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


def _finish(out: pd.DataFrame, rule_cols: list[str], safety_cols: list[str]) -> pd.DataFrame:
    out["rules_passed"] = out[rule_cols].sum(axis=1)
    out["rules_total"] = len(rule_cols)
    out["hard_pass"] = out[rule_cols].all(axis=1)
    # Safety gates are never relaxed in the ranked fill.
    out["safety_pass"] = out[safety_cols].all(axis=1)
    out["failed_rules"] = out[rule_cols].apply(lambda s: ",".join(c[2:] for c, v in s.items() if not v), axis=1)
    return out


def _usd(out: pd.DataFrame) -> pd.Series:
    # Market cap is in USD; ratios are only valid if the statements are in USD too.
    return out.get("currency", pd.Series("USD", index=out.index)).fillna("USD").eq("USD")


def apply_rules(df: pd.DataFrame, r: dict) -> pd.DataFrame:
    """Track A (hard assets): cheap on earnings or own history, high FCF yield, cash positive."""
    out = df.copy()
    out["r_valuation_pe"] = (out["fwd_pe"].between(0, r["forward_pe_max"], inclusive="neither")) | (
        out["pe_pct_proxy"] <= r["pe_percentile_max"]
    )
    out["r_fcf_yield"] = out["fcf_yield"] > r["fcf_yield_min"]
    out["r_ocf_positive"] = out["ocf_used"] > 0
    out["r_mcap"] = out["mcap"] * 1e6 > r["market_cap_min"]
    out["r_dilution"] = out["share_growth"].fillna(0) < r["share_growth_max"]
    out["r_usd_statements"] = _usd(out)
    rules = ["r_valuation_pe", "r_fcf_yield", "r_ocf_positive", "r_mcap", "r_dilution", "r_usd_statements"]
    return _finish(out, rules, ["r_mcap", "r_ocf_positive", "r_dilution", "r_usd_statements"])


def add_track_b_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    debt = out.get("total_debt", pd.Series(np.nan, index=out.index)).fillna(0)
    cash = out.get("cash", pd.Series(np.nan, index=out.index))
    out["cash_to_debt"] = np.where(debt > 0, cash / debt.where(debt > 0), np.inf)
    burn = -out["fcf_ttm"].where(out["fcf_ttm"] < 0)
    out["runway_months"] = np.where(out["ocf_used"] > 0, np.inf, cash / burn * 12)
    rev, rnd = _latest(out, "rev"), _latest(out, "rnd")
    out["rnd_intensity"] = np.where(rev.fillna(0) > 0, rnd / rev.where(rev > 0), np.where(rnd > 0, np.inf, np.nan))
    out["price_to_book"] = out.get("ptb", pd.Series(np.nan, index=out.index))
    return out


def apply_track_b(df: pd.DataFrame, r: dict) -> pd.DataFrame:
    """Track B (bio/tech): balance-sheet strength, cash runway, not expensive on book, real R&D."""
    out = df.copy()
    out["r_cash_to_debt"] = out["cash_to_debt"] > r["cash_to_debt_min"]
    # Cash flow positive, or enough cash to fund the burn for runway_months_min.
    out["r_ocf_or_runway"] = (out["ocf_used"] > 0) | (out["runway_months"] >= r["runway_months_min"])
    out["r_price_to_book"] = out["price_to_book"].between(0, r["price_to_book_max"], inclusive="neither")
    out["r_rnd_intensity"] = out["rnd_intensity"] >= r["rnd_intensity_min"]
    out["r_mcap"] = out["mcap"] * 1e6 > r["market_cap_min"]
    out["r_dilution"] = out["share_growth"].fillna(0) < r["share_growth_max"]
    out["r_usd_statements"] = _usd(out)
    rules = ["r_cash_to_debt", "r_ocf_or_runway", "r_price_to_book", "r_rnd_intensity", "r_mcap", "r_dilution",
             "r_usd_statements"]
    return _finish(out, rules, ["r_mcap", "r_ocf_or_runway", "r_dilution", "r_usd_statements"])


def _pct_rank(s: pd.Series, higher_is_better: bool) -> pd.Series:
    return s.rank(pct=True, ascending=higher_is_better).fillna(0.0)


def score_track_b(df: pd.DataFrame, w: dict) -> pd.DataFrame:
    out = df.copy()
    out["score"] = (
        w["cash_to_debt"] * _pct_rank(out["cash_to_debt"].replace(np.inf, 1e9), True)
        + w["price_to_book"] * _pct_rank(out["price_to_book"].where(out["price_to_book"] > 0), False)
        + w["rnd_intensity"] * _pct_rank(out["rnd_intensity"].replace(np.inf, 1e9), True)
        + w["fcf_yield"] * _pct_rank(out["fcf_yield"], True)
        + w["dilution"] * _pct_rank(out["share_growth"], False)
    )
    return out


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


def select_by_cluster(df: pd.DataFrame, per_cluster: int, max_total: int) -> pd.DataFrame:
    """Top `per_cluster` per scenario cluster (hard passes first), capped at `max_total`."""
    parts = []
    for _, g in df.groupby("cluster", sort=False):
        s = select(g, per_cluster).drop(columns="rank")
        s["cluster_rank"] = range(1, len(s) + 1)
        parts.append(s)
    if not parts:
        return df.head(0)
    picked = pd.concat(parts).sort_values(["cluster_rank", "hard_pass", "score"], ascending=[True, False, False])
    picked = picked.head(max_total).copy()
    picked.insert(0, "rank", range(1, len(picked) + 1))
    return picked

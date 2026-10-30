"""Daily (date, ticker) panel: price, Friday, point-in-time fundamental, macro and scenario features,
plus triple-barrier labels.

Everything on row t is known at the close of day t. Labels look forward h trading days.
Valuation and momentum features are cross-sectional Z-scores within the candidate group on each date.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from common.config import ROOT, scenarios, settings
from common.log import get_logger
from data_fetch.prices import CURVE_PROXY, MACRO
from ml_engine.fundamentals import pit_frame

log = get_logger("ml.features")
RAW = ROOT / "data" / "raw"
# Converted to cross-sectional Z-scores (relative to the other candidates that day), raw value dropped.
XS_FEATURES = ["ocf_yield", "fcf_yield", "earnings_yield", "book_to_price", "ret_5", "ret_21", "ret_63", "ret_126",
               "ret_252", "rsi_14", "obv_slope_21", "dist_52w_high", "friday_shakeout_z"]


def load_prices(sym: str) -> pd.DataFrame | None:
    p = RAW / "prices" / f"{sym}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    # Dividend/split-adjusted OHLC, so ex-dividend drops do not trip barriers.
    f = (df["adj_close"] / df["close"]).where(df["close"] > 0, 1.0)
    for c in ("open", "high", "low"):
        df[f"adj_{c}"] = df[c] * f
    return df


def atr(px: pd.DataFrame, n: int = 14, adjusted: bool = True) -> pd.Series:
    h, l, c = (px["adj_high"], px["adj_low"], px["adj_close"]) if adjusted else (px["high"], px["low"], px["close"])
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def triple_barrier(px: pd.DataFrame, h: int, up_mult: float, dn_mult: float) -> tuple[pd.Series, pd.Series]:
    """Label 1 if the upper barrier (close + up*ATR14) is touched before the lower one within h days.

    Same-day touch of both counts as a loss (conservative). Returns (label, trade return),
    where trade return is what the 1-share triple-barrier trade would have made.
    NaN where the h-day window is not complete yet.
    """
    c, hi, lo = (px[k].to_numpy(float) for k in ("adj_close", "adj_high", "adj_low"))
    a = atr(px).to_numpy(float)
    n = len(c)
    y, ret = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n - h):
        if np.isnan(a[i]) or a[i] <= 0:
            continue
        up, dn = c[i] + up_mult * a[i], c[i] - dn_mult * a[i]
        w_hi, w_lo = hi[i + 1:i + h + 1], lo[i + 1:i + h + 1]
        hit_up = np.flatnonzero(w_hi >= up)
        hit_dn = np.flatnonzero(w_lo <= dn)
        tu = hit_up[0] if len(hit_up) else h + 1
        td = hit_dn[0] if len(hit_dn) else h + 1
        if tu < td:
            y[i], ret[i] = 1.0, up / c[i] - 1
        elif td <= tu and td <= h:
            y[i], ret[i] = 0.0, dn / c[i] - 1
        else:
            y[i], ret[i] = 0.0, c[i + h] / c[i] - 1  # time barrier: not a win
    return pd.Series(y, index=px.index), pd.Series(ret, index=px.index)


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def friday_features(px: pd.DataFrame, a14: pd.Series) -> pd.DataFrame:
    """friday_shakeout_z: Thursday->Friday move in ATRs, only when Friday volume is light (< 21-day average)
    or a climax (> 2x average); 0 otherwise. Carried forward to later days of the week.
    weekend_gap_reversion: over the last 52 weeks, average of -sign(Fri move) x (Fri close -> Tue close return).
    Positive = Friday moves tend to reverse by Tuesday. Uses only weeks whose Tuesday is already past."""
    c, v = px["adj_close"], px["volume"].astype(float)
    move = c.diff()
    vavg = v.rolling(21).mean().shift(1)
    vol_ok = (v < vavg) | (v > 2 * vavg)
    is_fri = px.index.dayofweek == 4
    shake = (move / a14).where(is_fri & vol_ok, 0.0).where(is_fri)
    out = pd.DataFrame(index=px.index)
    out["friday_shakeout_z"] = shake.ffill().fillna(0.0)
    out["is_friday"] = is_fri.astype(float)
    # Pair each Friday with the next Tuesday (2 trading days later in a normal week).
    fri_idx = np.flatnonzero(is_fri)
    rows = []
    for i in fri_idx:
        j = i + 2
        if i == 0 or j >= len(c) or px.index[j].dayofweek != 1:
            continue
        r_fri = c.iloc[i] / c.iloc[i - 1] - 1
        r_rev = c.iloc[j] / c.iloc[i] - 1
        rows.append((px.index[j], -np.sign(r_fri) * r_rev))
    if rows:
        s = pd.Series(dict(rows)).sort_index().rolling(52, min_periods=20).mean()
        # Known from the Tuesday close onwards; use strictly earlier Tuesdays.
        out["weekend_gap_reversion"] = s.reindex(px.index.union(s.index)).ffill().shift(1).reindex(px.index)
    else:
        out["weekend_gap_reversion"] = np.nan
    return out


def price_features(px: pd.DataFrame, bench: pd.Series) -> pd.DataFrame:
    c = px["adj_close"]
    r = np.log(c).diff()
    f = pd.DataFrame(index=px.index)
    for n in (5, 21, 63, 126, 252):
        f[f"ret_{n}"] = c.pct_change(n)
    for n in (21, 63):
        f[f"vol_{n}"] = r.rolling(n).std() * np.sqrt(252)
        f[f"rel_{n}"] = f[f"ret_{n}"] - bench.reindex(c.index).pct_change(n)
    f["dist_52w_high"] = c / c.rolling(252).max() - 1
    f["dist_52w_low"] = c / c.rolling(252).min() - 1
    f["rsi_14"] = _rsi(c)
    vol = px["volume"].astype(float)
    obv = (np.sign(c.diff()).fillna(0) * vol).cumsum()
    f["obv_slope_21"] = (obv - obv.shift(21)) / (21 * vol.rolling(63).mean())
    dv = (px["close"] * vol).replace(0, np.nan)
    f["volume_z"] = (np.log(dv) - np.log(dv).rolling(63).mean()) / np.log(dv).rolling(63).std()
    a14 = atr(px)
    f["atr_pct"] = a14 / c
    return f.join(friday_features(px, a14))


def fundamental_features(cik, px: pd.DataFrame, lag: int) -> pd.DataFrame:
    p = RAW / "companyfacts" / f"CIK{int(cik):010d}.json" if pd.notna(cik) else None
    cf = json.loads(p.read_text()) if p is not None and p.exists() else {}
    pit = pit_frame(cf, px.index, lag)
    mcap = px["close"] * pit["shares"]                       # raw close x shares known that day
    f = pd.DataFrame(index=px.index)
    f["ocf_yield"] = pit["ocf"] / mcap
    f["fcf_yield"] = (pit["ocf"] - pit["capex"]) / mcap
    f["earnings_yield"] = pit["net_income"] / mcap
    f["book_to_price"] = pit["equity"] / mcap
    f["liab_to_equity"] = pit["liabilities"] / pit["equity"].where(pit["equity"] > 0)
    f["share_growth_1y"] = pit["shares"] / pit["shares"].shift(252) - 1
    f["days_since_annual"] = pit["days_since_annual"]
    return f.replace([np.inf, -np.inf], np.nan)


def macro_features(index: pd.DatetimeIndex, bench: pd.Series, lag: int) -> pd.DataFrame:
    f = pd.DataFrame(index=index)
    b = bench.reindex(index).ffill()
    f["mkt_ret_21"], f["mkt_ret_63"] = b.pct_change(21), b.pct_change(63)
    f["mkt_vol_21"] = np.log(b).diff().rolling(21).std() * np.sqrt(252)
    fred = {n: RAW / "macro" / f"{n}.csv" for n in MACRO}
    if all(p.exists() for p in fred.values()):
        for n, p in fred.items():
            s = pd.read_csv(p, parse_dates=["date"]).set_index("date")["value"]
            s = s[~s.index.duplicated(keep="last")]
            s = s.reindex(index.union(s.index)).ffill().reindex(index).shift(lag)
            if n in ("vix", "curve_10y2y"):
                f[f"{n}_level"], f[f"{n}_chg_21"] = s, s.diff(21)
            else:
                f[f"{n}_ret_21"] = s.pct_change(21)
        f.attrs["macro_source"] = "VIX, dollar, oil, 10Y-2Y (data/raw/macro)"
    else:
        for n, (_, etf) in MACRO.items():
            px = load_prices(etf) if etf else None
            if px is not None:
                f[f"{n}_proxy_ret_21"] = px["adj_close"].reindex(index).ffill().pct_change(21)
        ief, shy = (load_prices(s) for s in CURVE_PROXY)
        if ief is not None and shy is not None:
            f["curve_proxy_63"] = (ief["adj_close"].reindex(index).ffill().pct_change(63)
                                   - shy["adj_close"].reindex(index).ffill().pct_change(63))
        f.attrs["macro_source"] = "ETF proxies"
    # Scenario stress Z history from Module 0 (lagged one day).
    zp = ROOT / "data" / "regime" / "z_history.csv"
    if zp.exists():
        z = pd.read_csv(zp, parse_dates=["date"]).set_index("date")
        z = z.reindex(index.union(z.index)).ffill().reindex(index).shift(lag)
        for col in z:
            f[f"scen_z_{col}"] = z[col]
    return f


def scenario_tilt_series(panel: pd.DataFrame) -> pd.Series:
    """Per row: sum over scenarios of cluster exposure x scenario stress Z (history, no look-ahead)."""
    sc = scenarios()
    names = list(sc["scenarios"])
    tilt = pd.Series(0.0, index=panel.index)
    for cl, row in sc["exposure"].items():
        m = panel["cluster"] == cl
        for s, e in zip(names, row):
            col = f"scen_z_{s}"
            if col in panel and e:
                tilt[m] += e * panel.loc[m, col].fillna(0) / 2
    return tilt


def build_panel(universe: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """universe: columns ticker, cik, cluster. Returns (panel, feature_cols); labels y_{h} (triple barrier), tbret_{h} (trade return), fwd_{h} (excess vs benchmark)."""
    cfg = settings()["ml"]
    barriers = settings()["ledger"]["barriers"]
    bench_px = load_prices(cfg["benchmark"])
    if bench_px is None:
        raise FileNotFoundError(f"No prices for benchmark {cfg['benchmark']}. Fetch prices first.")
    bench = bench_px["adj_close"]
    start = bench.index.max() - pd.DateOffset(years=cfg["history_years"]) - pd.DateOffset(days=400)  # warm-up
    frames = []
    for t, cik, cl in universe[["ticker", "cik", "cluster"]].itertuples(index=False):
        px = load_prices(t)
        if px is None or len(px) < 300:
            log.warning("%s: no or short price history, skipped", t)
            continue
        px = px[px.index >= start]
        f = price_features(px, bench).join(fundamental_features(cik, px, cfg["fundamentals_lag_days"]))
        c, b = px["adj_close"], bench.reindex(px.index).ffill()
        for h in cfg["horizons"]:
            bar = barriers[str(h)]
            f[f"y_{h}"], f[f"tbret_{h}"] = triple_barrier(px, h, bar["tp_atr"], bar["sl_atr"])
            f[f"fwd_{h}"] = (c.shift(-h) / c - 1) - (b.shift(-h) / b - 1)
        f["ticker"], f["cluster"] = t, cl
        frames.append(f)
    if not frames:
        raise RuntimeError("No tickers with price history. Fetch prices first.")
    panel = pd.concat(frames)
    macro = macro_features(pd.DatetimeIndex(sorted(panel.index.unique())), bench, cfg["macro_lag_days"])
    panel = panel.join(macro, how="left")
    panel.attrs["macro_source"] = macro.attrs.get("macro_source")
    panel = panel[panel.index >= bench.index.max() - pd.DateOffset(years=cfg["history_years"])]
    panel = panel.rename_axis("date").reset_index()
    panel["scenario_tilt"] = scenario_tilt_series(panel)
    # Cross-sectional Z within the candidate group on each date (sector-relative normalisation).
    g = panel.groupby("date")
    for col in XS_FEATURES:
        if col in panel:
            m, s = g[col].transform("mean"), g[col].transform("std")
            panel[f"xs_{col}"] = ((panel[col] - m) / s.replace(0, np.nan)).clip(-4, 4)
    label_cols = {f"{k}_{h}" for k in ("y", "tbret", "fwd") for h in cfg["horizons"]}
    drop = label_cols | {"date", "ticker", "cluster", "is_friday"} | set(XS_FEATURES)
    feats = [c for c in panel if c not in drop]
    return panel, feats


def weeks_gap(h: int) -> int:
    """Purge gap in Friday rows for an h-trading-day label (+1 week for holidays)."""
    return math.ceil(h / 5) + 1

"""Module 0: where is each of the 6 scenarios right now?

For each scenario:
  Z_t      stress level: the scenario's 21-day stress move as a Z-score vs its 3-year baseline
  dZ_t     stress velocity: change in Z over 21 days
  p_high   probability the scenario's price proxy is in the high-volatility regime
           (2-state Markov switching-variance model, statsmodels)
  Z_price  21-day move of the asset the event hurts, as a Z-score
States (soft, sum to 1): LATENT, IMMINENT, ACTIVE_SHOCK, POST_RECOVERY.
The split uses smooth versions of the spec's thresholds, so a Z of 1.99 vs 2.01 does not flip a state.
This is a rule-based classifier with a Markov volatility input, not a fitted 4-state Markov chain.

The same Z series are written as a daily history, so Module 2 can learn from them without look-ahead.
"""
from __future__ import annotations

import json
import warnings
from datetime import date

import numpy as np
import pandas as pd

from common.config import ROOT, scenarios, settings
from common.log import get_logger

log = get_logger("regime")
RAW = ROOT / "data" / "raw"
STATES = ["LATENT", "IMMINENT", "ACTIVE_SHOCK", "POST_RECOVERY"]
OUT = ROOT / "knowledge_base" / "live_regime_weights.json"
HISTORY = ROOT / "data" / "regime" / "z_history.csv"


def _px(sym: str) -> pd.Series:
    p = RAW / "prices" / f"{sym}.csv"
    if not p.exists():
        raise FileNotFoundError(f"No prices for {sym}. Fetch config/scenarios.yaml proxy_symbols with browser_fetch/04_prices.js")
    s = pd.read_csv(p, parse_dates=["date"]).drop_duplicates("date", keep="last").set_index("date")["adj_close"]
    return s.sort_index()


def _basket(syms: list[str], idx: pd.DatetimeIndex) -> pd.Series:
    """Equal-weight log level of a basket (each member rebased to 1)."""
    logs = [np.log(_px(s).reindex(idx).ffill()) for s in syms]
    return sum(l - l.dropna().iloc[0] for l in logs) / len(logs)


def _z(x: pd.Series, n: int) -> pd.Series:
    m, s = x.rolling(n, min_periods=n // 2).mean(), x.rolling(n, min_periods=n // 2).std()
    return (x - m) / s


def stress_series(spec: dict, idx: pd.DatetimeIndex, w: int, base: int) -> pd.Series:
    """Daily Z of the scenario's stress move. Higher = more stress."""
    t = spec["type"]
    if t == "spread":
        return _z(_basket(spec["long"], idx).diff(w) - _basket(spec["short"], idx).diff(w), base)
    if t == "spread_plus_vol":
        spread = _z(_basket(spec["long"], idx).diff(w) - _basket(spec["short"], idx).diff(w), base)
        vol = _z(np.log(_px(spec["vol"]).reindex(idx).ffill()).diff().rolling(w).std(), base)
        return (spread + vol) / 2
    parts = []
    for part in spec["parts"]:
        (kind, arg), = part.items()
        if kind == "spread":
            parts.append(_z(_basket([arg[0]], idx).diff(w) - _basket([arg[1]], idx).diff(w), base))
        elif kind in ("up", "down"):
            m = _basket([arg], idx).diff(w)
            parts.append(_z(m if kind == "up" else -m, base))
        elif kind == "level":
            parts.append(_z(_px(arg).reindex(idx).ffill(), base))
    return sum(parts) / len(parts)


def markov_high_vol_prob(price: pd.Series, n: int) -> float:
    """P(high-variance regime) on the last day, from a 2-state switching-variance model of daily returns."""
    from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

    r = (np.log(price).diff().dropna().tail(n) * 100).to_numpy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            res = MarkovRegression(r, k_regimes=2, switching_variance=True).fit(disp=False)
        except Exception as e:  # noqa: BLE001 - fit can fail on degenerate data
            log.warning("Markov fit failed: %s", e)
            return float("nan")
    params = dict(zip(res.model.param_names, np.asarray(res.params)))
    hi = int(np.argmax([params[f"sigma2[{i}]"] for i in range(2)]))
    return float(np.asarray(res.smoothed_marginal_probabilities)[-1, hi])


def _rsi(close: pd.Series, n: int = 14) -> float:
    d = close.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n).mean()
    return float((100 - 100 / (1 + up / dn)).iloc[-1])


def _sig(x: float) -> float:
    return float(1 / (1 + np.exp(-x)))


def classify(z: float, dz: float, p_high: float, z_price: float, rsi: float, th: dict, soft: float) -> dict:
    """Soft version of the 4 state rules; returns probabilities summing to 1."""
    s = lambda x: _sig(x / soft)  # noqa: E731
    p_high = 0.5 if np.isnan(p_high) else p_high
    active = s(z - th["active"]) * s((p_high - th["markov_high"]) * 4)
    imminent = s(z - th["latent"]) * s(th["active"] - z) * s(dz)
    rsi_ok = _sig((rsi - th["rsi_low"]) / 2) * _sig((th["rsi_high"] - rsi) / 2)
    post = s(th["price_depressed"] - z_price) * s(-dz) * rsi_ok
    latent = s(th["latent"] - abs(z)) * float(np.exp(-(dz / 0.75) ** 2))
    raw = np.array([latent, imminent, active, post]) + 1e-3
    raw[0] += 0.05  # nothing fits well -> lean to LATENT (no action) rather than a shock call
    p = raw / raw.sum()
    return dict(zip(STATES, (round(float(v), 3) for v in p)))


def run() -> dict:
    sc, cfg = scenarios(), settings()["regime"]
    w, base, th = cfg["window"], cfg["baseline_days"], cfg["thresholds"]
    idx = _px("SPY").index
    out, hist = {"as_of": date.today().isoformat(), "price_date": str(idx[-1].date()),
                 "method": "rule-based soft states + 2-state Markov switching-variance probability",
                 "scenarios": {}}, {}
    for name, spec in sc["scenarios"].items():
        z = stress_series(spec["stress"], idx, w, base)
        hist[name] = z
        price = _px(spec["price"]).reindex(idx).ffill()
        zp = _z(np.log(price).diff(w), base)
        zt, dzt = float(z.iloc[-1]), float(z.iloc[-1] - z.iloc[-1 - w])
        ph = markov_high_vol_prob(price, cfg["markov_days"])
        rsi = _rsi(price.dropna())
        probs = classify(zt, dzt, ph, float(zp.iloc[-1]), rsi, th, cfg["softness"])
        state = max(probs, key=probs.get)
        weights = {h: round(sum(probs[s] * cfg["weights"][s][h] for s in STATES), 3) for h in ("5", "21", "63")}
        out["scenarios"][name] = {
            "name": spec["name"], "state": state, "state_probs": probs,
            "z": round(zt, 2), "dz_21": round(dzt, 2), "markov_high_vol": round(ph, 3) if not np.isnan(ph) else None,
            "z_price": round(float(zp.iloc[-1]), 2), "rsi_price": round(rsi, 1), "price_proxy": spec["price"],
            "polarity": -1 if state == "POST_RECOVERY" else 1, "weights": weights,
            "instruction": ("Crash is priced in: favour beaten-down survivors (deep-value accumulation)"
                            if state == "POST_RECOVERY" else
                            "Favour defensive beneficiaries" if state in ("IMMINENT", "ACTIVE_SHOCK") else
                            "Long-term only: counts for quarterly picks"),
        }
        log.info("%-26s %-13s Z %+.2f dZ %+.2f pHigh %.2f Zp %+.2f RSI %.0f  w5/21/63 %s",
                 name, state, zt, dzt, ph, zp.iloc[-1], rsi, list(weights.values()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(hist).rename_axis("date").to_csv(HISTORY)
    return out


def load() -> dict:
    return json.loads(OUT.read_text()) if OUT.exists() else {"scenarios": {}}


def exposure_vector(cluster: str) -> dict[str, int]:
    sc = scenarios()
    row = sc["exposure"].get(cluster) or [0] * len(sc["scenarios"])
    return dict(zip(sc["scenarios"], row))


def scenario_tilt(cluster: str, horizon: int, regime: dict | None = None) -> float:
    """-1..+1: how much the live regime favours this cluster at this horizon."""
    regime = regime or load()
    exp = exposure_vector(cluster)
    t = 0.0
    for name, s in regime.get("scenarios", {}).items():
        t += s["weights"][str(horizon)] * s["polarity"] * exp.get(name, 0) / 2
    return float(np.clip(t, -1, 1))

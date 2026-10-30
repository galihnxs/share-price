"""Module 2: one classifier per horizon, purged walk-forward test on Friday closes, then picks.

Label (triple barrier): from a Friday close, does the price touch close + tp*ATR14 before close - sl*ATR14
within h trading days? Those are exactly the barriers the ledger places, so precision here = win rate.
The test that matters: how often the model's #1 pick each Friday won, vs a random candidate (base rate),
and whether the trades made money (profit factor).
For comparison, the old label (beat RSP over h days) is evaluated on the same rows and features.
"""
from __future__ import annotations

import json
from datetime import date

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from common.config import ROOT, path, settings
from common.log import get_logger
from ml_engine.cv import purged_date_splits
from ml_engine.features import build_panel, weeks_gap

log = get_logger("ml")


def latest_candidates() -> dict:
    files = sorted((ROOT / settings()["paths"]["screener_out"]).glob("candidates_*.json"))
    if not files:
        raise FileNotFoundError("No screener output. Run: python main.py --screen")
    return json.loads(files[-1].read_text())


def _model(cfg: dict) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(**cfg["model"], random_state=7, verbose=-1)


def _pf(r: pd.Series) -> float:
    gain, loss = r[r > 0].sum(), -r[r < 0].sum()
    return float(gain / loss) if loss > 0 else float("inf")


def evaluate(d: pd.DataFrame, feats: list[str], h: int, cfg: dict, label: str, ret: str) -> dict:
    d = d.dropna(subset=[label]).reset_index(drop=True)
    oos = []
    for tr, te in purged_date_splits(d["date"], cfg["n_splits"], weeks_gap(h), cfg["min_train_days"] // 5):
        m = _model(cfg).fit(d.loc[tr, feats], d.loc[tr, label])
        oos.append(pd.DataFrame({"date": d.loc[te, "date"], "ticker": d.loc[te, "ticker"], "y": d.loc[te, label],
                                 "ret": d.loc[te, ret], "p": m.predict_proba(d.loc[te, feats])[:, 1]}))
    o = pd.concat(oos)
    base = float(o["y"].mean())
    k = cfg["top_k"]
    ranked = o.sort_values("p", ascending=False).groupby("date")
    top1, topk = ranked.head(1), ranked.head(k)
    # Friday rows h days apart overlap when h > 5: shrink n by the weeks a label spans.
    weeks = max(np.ceil(h / 5), 1)

    def z_of(prec: float, n: int, per_date: int) -> float:
        # The k picks of one Friday share the same market move, so count each Friday once.
        n_eff = max(n / per_date / weeks, 1.0)
        se = np.sqrt(base * (1 - base) / n_eff)
        return float((prec - base) / se) if se > 0 else 0.0

    prec1, preck = float(top1["y"].mean()), float(topk["y"].mean())
    pf1, pfk = _pf(top1["ret"]), _pf(topk["ret"])
    zk = z_of(preck, len(topk), k)
    r = lambda x: round(x, 3) if np.isfinite(x) else None  # noqa: E731
    return {
        "label": label, "oos_fridays": int(o["date"].nunique()), "oos_rows": len(o),
        "oos_start": str(o["date"].min().date()), "oos_end": str(o["date"].max().date()),
        "base_rate": round(base, 4), "k": k,
        # The traded set: the top-k picks each Friday. Edge is judged on these.
        "topk_precision": round(preck, 4), "topk_picks": len(topk), "lift": round(preck - base, 4),
        "z_effective": round(zk, 2), "profit_factor_topk": r(pfk), "mean_ret_topk": round(float(topk["ret"].mean()), 4),
        # The single best pick, for comparison.
        "top1_precision": round(prec1, 4), "top1_lift": round(prec1 - base, 4),
        "top1_z": round(z_of(prec1, len(top1), 1), 2), "profit_factor_top1": r(pf1),
        "mean_ret_top1": round(float(top1["ret"].mean()), 4), "mean_ret_all": round(float(o["ret"].mean()), 4),
        "auc": round(float(roc_auc_score(o["y"], o["p"])), 4) if o["y"].nunique() > 1 else None,
        "edge": bool(preck >= cfg["min_precision"] and np.isfinite(pfk) and pfk > cfg["min_profit_factor"]
                     and zk >= cfg["min_z"]),
    }


def run(as_of: str | None = None) -> dict:
    from regime_engine.state_tracker import load as load_regime, scenario_tilt

    cfg, all_cfg = settings()["ml"], settings()
    cands = latest_candidates()
    uni = pd.DataFrame(cands["candidates"])
    uni["cluster"] = uni.get("cluster", uni.get("sector"))
    panel, feats = build_panel(uni)
    fri = panel[panel["date"].dt.dayofweek == cfg["decision_weekday"]]
    log.info("panel: %s rows (%s Friday rows), %s tickers, %s features, %s -> %s", len(panel), len(fri),
             panel["ticker"].nunique(), len(feats), panel["date"].min().date(), panel["date"].max().date())
    last_date = panel["date"].max()
    today = panel[panel["date"] == last_date]
    info = uni.set_index("ticker")
    regime = load_regime()
    out = {"as_of": as_of or date.today().isoformat(), "price_date": str(last_date.date()),
           "price_date_weekday": last_date.day_name(), "screener_as_of": cands["as_of"], "benchmark": cfg["benchmark"],
           "macro_source": panel.attrs.get("macro_source"), "features": feats, "label": "triple_barrier",
           "caveat": ("Universe = today's screener candidates, chosen with today's fundamentals; the backtest measures "
                      "ranking skill inside that list, not the screen itself. Research only, not advice."),
           "horizons": {}}
    for h in cfg["horizons"]:
        bar = all_cfg["ledger"]["barriers"][str(h)]
        m_new = evaluate(fri, feats, h, cfg, f"y_{h}", f"tbret_{h}")
        old = fri.assign(**{f"yold_{h}": (fri[f"fwd_{h}"] > cfg["target_min_excess"]).astype(float).where(fri[f"fwd_{h}"].notna())})
        m_old = evaluate(old, feats, h, cfg, f"yold_{h}", f"fwd_{h}")
        train = fri.dropna(subset=[f"y_{h}"])
        m = _model(cfg).fit(train[feats], train[f"y_{h}"])
        imp = pd.Series(m.booster_.feature_importance("gain"), index=feats).sort_values(ascending=False)
        p = pd.Series(m.predict_proba(today[feats])[:, 1], index=today["ticker"])
        rows = []
        for t, prob in p.items():
            cl = info.at[t, "cluster"] if t in info.index else None
            tilt = scenario_tilt(cl, h, regime) if cl else 0.0
            rows.append({"ticker": t, "prob": round(float(prob), 4), "scenario_tilt": round(tilt, 3),
                         "score": round(float(prob) + all_cfg["regime"]["rank_tilt"] * tilt, 4), "cluster": cl,
                         "pass_status": info.at[t, "pass_status"] if t in info.index else None,
                         "flag": (info.at[t, "flag"] if t in info.index else "") or ""})
        ranked = sorted(rows, key=lambda r: -r["score"])
        out["horizons"][str(h)] = {"name": bar["name"], "barriers_atr": {"tp": bar["tp_atr"], "sl": bar["sl_atr"]},
                                   "metrics": m_new, "metrics_old_label": m_old, "picks": ranked[:cfg["top_k"]],
                                   "top_features": {k: round(float(v), 1) for k, v in imp.head(10).items()},
                                   "all": ranked}
        log.info("h=%-3s TRIPLE-BARRIER base %.3f top%d %.3f (z %.2f PF %s) | #1 %.3f (z %.2f PF %s) edge=%s | "
                 "OLD top%d lift %+.3f z %.2f | picks %s", h, m_new["base_rate"], m_new["k"], m_new["topk_precision"],
                 m_new["z_effective"], m_new["profit_factor_topk"], m_new["top1_precision"], m_new["top1_z"],
                 m_new["profit_factor_top1"], m_new["edge"], m_old["k"], m_old["lift"], m_old["z_effective"],
                 [r["ticker"] for r in ranked[:cfg["top_k"]]])
    out["picks_union"] = sorted({x["ticker"] for v in out["horizons"].values() for x in v["picks"]})
    # Names to fetch filings for and audit: top_k plus spares per horizon, so audit skips still leave k picks.
    out["audit_union"] = sorted({x["ticker"] for v in out["horizons"].values()
                                 for x in v["all"][:cfg["top_k"] + cfg["audit_spares"]]})
    out_dir = path("ml_out")
    txt = json.dumps(out, indent=2, default=str)
    (out_dir / "ml_candidates.json").write_text(txt)
    (out_dir / f"ml_candidates_{out['as_of']}.json").write_text(txt)
    log.info("wrote %s", out_dir / "ml_candidates.json")
    return out

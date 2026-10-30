"""Module 5: triple-barrier tickets, position monitor and the Friday Capitulation ticket.

Two kinds of position in portfolio.db:
  PAPER  signal positions logged automatically while a horizon has no proven edge. Simulated:
         they close themselves on a barrier hit, time expiry or thesis break.
  MANUAL real trades the owner reports (python main.py --buy/--sell). The pipeline never assumes a broker
         fill: it gives a verdict each run, and the position closes only when the owner reports the sale.
A horizon's ticket is LIVE (1 real share) once its model shows validated edge, or its paper record does.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime

import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay, USMartinLutherKingJr,
                                    USMemorialDay, USPresidentsDay, USThanksgivingDay, nearest_workday)
from pandas.tseries.offsets import CustomBusinessDay

from common.config import ROOT, path, settings
from common.log import get_logger
from ml_engine.features import load_prices
from portfolio_ledger.db import connect, log_event, now, open_positions

log = get_logger("ledger")
HORIZON_NAMES = {5: "weekly", 21: "monthly", 63: "quarterly"}
NAME_TO_H = {v: k for k, v in HORIZON_NAMES.items()}
STATE_FILE = ROOT / "data" / "ledger" / "ledger_state.json"


class NYSECalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("NewYearsDay", month=1, day=1, observance=nearest_workday), USMartinLutherKingJr, USPresidentsDay,
        GoodFriday, USMemorialDay, Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01",
                                           observance=nearest_workday),
        Holiday("IndependenceDay", month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


TDAY = CustomBusinessDay(calendar=NYSECalendar())


def add_trading_days(d, n: int) -> date:
    return (pd.Timestamp(d) + n * TDAY).date()


def trading_days_between(a, b) -> int:
    """Trading days after a, up to and including b (0 if b <= a)."""
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    return 0 if b <= a else len(pd.date_range(a + TDAY, b, freq=TDAY))


def next_trading_day(d=None) -> date:
    """d itself if it is a trading day, else the next one."""
    return TDAY.rollforward(pd.Timestamp(d or date.today())).date()


def atr14(ticker: str, as_of=None) -> tuple[float, float, str]:
    """(ATR_14 on raw prices, last close, price date) as of a date. Raw prices = the levels a broker shows."""
    px = load_prices(ticker)
    if px is None:
        raise FileNotFoundError(f"No prices for {ticker}: fetch them with browser_fetch/04_prices.js first.")
    if as_of:
        px = px[px.index <= pd.Timestamp(as_of)]
    h, l, c = px["high"], px["low"], px["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(14).mean().iloc[-1]), float(c.iloc[-1]), str(px.index[-1].date())


def barriers(price: float, atr: float, horizon: int, entry_date) -> dict:
    b = settings()["ledger"]["barriers"][str(horizon)]
    return {"entry": round(price, 2), "atr14": round(atr, 4), "tp": round(price + b["tp_atr"] * atr, 2),
            "sl": round(max(price - b["sl_atr"] * atr, 0.01), 2),
            "expiry": add_trading_days(entry_date, horizon).isoformat()}


# ---------------------------------------------------------------- PAPER -> LIVE
def horizon_badges(ml: dict) -> dict:
    """LIVE if the walk-forward test shows edge, or the paper record passes the promotion rule."""
    cfg, mcfg = settings()["ledger"], settings()["ml"]
    with connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT horizon, ret_pct FROM positions WHERE mode='PAPER' AND status!='OPEN'")]
    out = {}
    for h, v in ml["horizons"].items():
        m = v["metrics"]
        closed = [r["ret_pct"] for r in rows if str(r["horizon"]) == h and r["ret_pct"] is not None]
        n, wins = len(closed), sum(1 for r in closed if r > 0)
        wr = wins / n if n else None
        base = m["base_rate"]
        z = (wr - base) / math.sqrt(base * (1 - base) / n) if n and 0 < base < 1 else 0.0
        paper_ok = n >= cfg["promote_min_trades"] and wr >= cfg["promote_min_win_rate"] and \
            (not cfg["promote_require_significance"] or z >= mcfg["min_z"])
        live = m["edge"] or paper_ok
        out[h] = {"badge": "LIVE BUY (1 SHARE)" if live else "PAPER TRADE (CALIBRATING EDGE)",
                  "mode": "LIVE" if live else "PAPER", "model_edge": m["edge"],
                  "paper_closed": n, "paper_win_rate": round(wr, 3) if wr is not None else None,
                  "paper_z": round(z, 2),
                  "reason": ("walk-forward edge" if m["edge"] else "paper record passed" if paper_ok else
                             f"no edge yet: top-{m['k']} win rate {m['topk_precision']:.0%} vs base {base:.0%}, "
                             f"PF {m['profit_factor_topk']}, paper {n}/{cfg['promote_min_trades']} trades")}
    return out


# ---------------------------------------------------------------- monitor
def _bars_since(ticker: str, entry_date: str) -> pd.DataFrame | None:
    px = load_prices(ticker)
    return None if px is None else px[px.index > pd.Timestamp(entry_date)]


def _8k_hits(ticker: str, since: str, filings: dict, key: str = "toxic_8k_items") -> list[dict]:
    items = set(settings()["ledger"][key])
    return [f for f in filings.get(ticker, []) if f["date"] > since and set(f["items"].split(",")) & items]


def _regime_flip(cluster: str | None, horizon: int) -> tuple[bool, float]:
    from regime_engine.state_tracker import scenario_tilt

    if not cluster:
        return False, 0.0
    t = scenario_tilt(cluster, horizon)
    return t <= -0.2, t


def monitor(ml: dict, audit: dict, filings: dict) -> list[dict]:
    """Check every OPEN position. PAPER positions close themselves; MANUAL ones get a verdict."""
    lcfg = settings()["ledger"]
    probs = {h: {r["ticker"]: r for r in v["all"]} for h, v in ml["horizons"].items()}
    top3 = {h: [r["ticker"] for r in v["picks"]] for h, v in ml["horizons"].items()}
    results = []
    with connect() as con:
        for p in open_positions(con):
            h, t = int(p["horizon"]), p["ticker"]
            bars = _bars_since(t, p["entry_date"])
            last = float(bars["close"].iloc[-1]) if bars is not None and len(bars) else p["entry_price"]
            last_date = str(bars.index[-1].date()) if bars is not None and len(bars) else p["entry_date"]
            hit_tp = hit_sl = None
            if bars is not None and len(bars) and p["tp"]:
                for d, row in bars.iterrows():
                    if row["low"] <= p["sl"]:  # same-day touch of both counts as stop (conservative)
                        hit_sl = str(d.date())
                        break
                    if row["high"] >= p["tp"]:
                        hit_tp = str(d.date())
                        break
            expired = p["expiry_date"] and last_date >= p["expiry_date"]
            ml_row = probs.get(str(h), {}).get(t)
            ml_p = ml_row["prob"] if ml_row else None
            toxic = _8k_hits(t, p["entry_date"], filings)
            review = _8k_hits(t, p["entry_date"], filings, "review_8k_items")
            flip, tilt = _regime_flip(p["cluster"], h)
            clean = audit.get(t, {}).get("verdict") not in ("TRAP", "AVOID")
            ret = last / p["entry_price"] - 1
            r = {"id": p["id"], "ticker": t, "horizon": h, "horizon_name": HORIZON_NAMES[h], "mode": p["mode"],
                 "entry_date": p["entry_date"], "entry_price": p["entry_price"], "last": round(last, 2),
                 "last_date": last_date, "pnl_pct": round(ret * 100, 2), "tp": p["tp"], "sl": p["sl"],
                 "expiry": p["expiry_date"], "days_left": trading_days_between(last_date, p["expiry_date"]),
                 "ml_prob": ml_p, "scenario_tilt": round(tilt, 3), "toxic_8k": toxic, "review_8k": review}
            if p["mode"] == "PAPER":
                status, exit_px, reason = None, None, None
                if hit_sl:
                    status, exit_px, reason = "CLOSED_SL", p["sl"], f"Stop-loss hit {hit_sl}"
                elif hit_tp:
                    status, exit_px, reason = "CLOSED_TP", p["tp"], f"Take-profit hit {hit_tp}"
                elif toxic or flip:
                    status, exit_px, reason = "CLOSED_EXIT", last, "EARLY EXIT - THESIS INVALIDATED (" + \
                        ("negative 8-K" if toxic else "regime flip") + ")"
                elif expired:
                    if t in top3.get(str(h), []) and clean:
                        atr, close, d = atr14(t)
                        b = barriers(close, atr, h, d)
                        con.execute("UPDATE positions SET expiry_date=?, tp=?, sl=? WHERE id=?",
                                    (b["expiry"], b["tp"], b["sl"], p["id"]))
                        log_event(con, p["id"], "ROLLOVER", json.dumps(b))
                        reason = "HOLD & ROLLOVER (Extend Time Barrier)"
                    else:
                        status, exit_px, reason = "CLOSED_TIME", last, "SELL AT MARKET OPEN (Time Barrier Expired)"
                if status:
                    con.execute("UPDATE positions SET status=?, exit_date=?, exit_price=?, pnl=?, ret_pct=? WHERE id=?",
                                (status, hit_sl or hit_tp or last_date, exit_px, exit_px - p["entry_price"],
                                 exit_px / p["entry_price"] - 1, p["id"]))
                    log_event(con, p["id"], status, reason)
                r.update(action=reason or "HOLD", closed=bool(status))
            else:
                if last >= p["tp"] or hit_tp:
                    v = "TAKE PROFIT NOW"
                elif last <= p["sl"] or hit_sl or toxic or flip or (ml_p is not None and ml_p < lcfg["ml_broken_max"]):
                    v = "STOP LOSS / THESIS BROKEN"
                elif expired:
                    v = "TIME EXPIRED - SELL OR ROLLOVER" + (" (rollover OK: still top 3, audit clean)"
                                                           if t in top3.get(str(h), []) and clean else "")
                elif ml_p is not None and ml_p > lcfg["ml_hold_min"]:
                    v = "STRONG HOLD"
                else:
                    v = "HOLD"
                why = [w for w, on in [("TP touched", bool(hit_tp)), ("SL touched", bool(hit_sl)),
                                       ("negative 8-K", bool(toxic)), ("regime flip", flip),
                                       ("ML < 35%", ml_p is not None and ml_p < lcfg["ml_broken_max"])] if on]
                r.update(action=v, why=why, closed=False)
                # Opportunity cost: a same-horizon name scoring 20 pts higher while this one drifts.
                alts = [x for x in ml["horizons"].get(str(h), {}).get("all", []) if x["ticker"] != t]
                if ml_p is not None and alts and abs(ret) < 0.02:
                    best = max(alts, key=lambda x: x["prob"])
                    if best["prob"] >= ml_p + lcfg["swap_prob_gap"]:
                        r["swap_candidate"] = best["ticker"]
            results.append(r)
    return results


# ---------------------------------------------------------------- Friday ticket
def new_tickets(ml: dict, badges: dict, audit: dict) -> list[dict]:
    """Top-k picks per horizon (settings ml.top_k), skipping names already OPEN in that horizon and audit traps.
    Re-running on the same price date keeps that day's paper tickets and only fills the remaining slots."""
    k = settings()["ml"]["top_k"]
    opens = open_positions()
    held = {(p["ticker"], int(p["horizon"])) for p in opens}
    out = []
    for h, v in ml["horizons"].items():
        logged_today = {p["ticker"] for p in opens if int(p["horizon"]) == int(h) and p["mode"] == "PAPER"
                        and p["entry_date"] == ml["price_date"]}
        picked = []
        for cand in v["all"]:
            t = cand["ticker"]
            if audit.get(t, {}).get("verdict") in ("TRAP", "AVOID"):
                continue
            if (t, int(h)) in held and t not in logged_today:
                continue
            picked.append(cand)
            if len(picked) == k:
                break
        for rank, cand in enumerate(picked, 1):
            t = cand["ticker"]
            atr, close, d = atr14(t)
            entry_day = next_trading_day(pd.Timestamp(d) + pd.Timedelta(days=1))
            b = barriers(close, atr, int(h), entry_day)
            out.append({"ticker": t, "horizon": int(h), "horizon_name": v["name"], "rank": rank,
                        "cluster": cand["cluster"], "conviction_pct": round(cand["prob"] * 100, 1),
                        "score": cand["score"], "scenario_tilt": cand["scenario_tilt"], "badge": badges[h]["badge"],
                        "mode": badges[h]["mode"], "limit": b["entry"], "tp": b["tp"], "sl": b["sl"],
                        "atr14": b["atr14"], "expiry": b["expiry"], "price_date": d,
                        "entry_day": entry_day.isoformat(), "audit": audit.get(t, {}).get("verdict", "NOT AUDITED")})
    return out


def log_paper(tickets: list[dict]) -> int:
    """PAPER tickets go into the ledger automatically (entry = limit). One per ticker/horizon/day."""
    n = 0
    with connect() as con:
        for tk in tickets:
            if tk["mode"] != "PAPER":
                continue
            dup = con.execute("SELECT 1 FROM positions WHERE ticker=? AND horizon=? AND entry_date=? AND mode='PAPER'",
                              (tk["ticker"], tk["horizon"], tk["price_date"])).fetchone()
            if dup:
                continue
            cur = con.execute(
                "INSERT INTO positions(ticker,horizon,mode,source,entry_date,entry_price,atr14,tp,sl,expiry_date,status,"
                "ml_prob,cluster,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,'OPEN',?,?,?,?)",
                (tk["ticker"], tk["horizon"], "PAPER", "signal", tk["price_date"], tk["limit"], tk["atr14"], tk["tp"],
                 tk["sl"], tk["expiry"], tk["conviction_pct"] / 100, tk["cluster"], "auto-logged paper ticket", now()))
            log_event(con, cur.lastrowid, "OPEN_PAPER", json.dumps(tk))
            n += 1
    return n


def _add_names(rows: list[dict]) -> list[dict]:
    """Company name and exchange next to each ticker (helps find it in a broker app)."""
    from data_fetch.sec import company_names

    names = company_names()
    for r in rows:
        n = names.get(r["ticker"], {})
        r["name"], r["exchange"] = n.get("name", ""), n.get("exchange", "")
    return rows


def run(audit: dict | None = None, filings: dict | None = None) -> dict:
    ml = json.loads((path("ml_out") / "ml_candidates.json").read_text())
    audit = audit if audit is not None else load_audit()
    badges = horizon_badges(ml)
    checked = monitor(ml, audit, filings or {})  # closes/rolls existing positions first
    tickets = new_tickets(ml, badges, audit)
    logged = log_paper(tickets)
    positions = monitor(ml, audit, filings or {})  # every OPEN position now, including new paper ones
    _add_names(checked), _add_names(tickets), _add_names(positions)
    state = {"generated": datetime.now().isoformat(timespec="seconds"), "badges": badges,
             "sell_or_rollover": [p for p in checked if p.get("closed") or p["action"] not in ("HOLD", "STRONG HOLD")],
             "positions": positions, "new_buys": tickets, "paper_logged": logged}
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
    log.info("ledger: %s open checked, %s new tickets (%s paper logged) | badges %s", len(positions), len(tickets),
             logged, {h: b["mode"] for h, b in badges.items()})
    return state


def load_audit() -> dict:
    """Claude's in-session value-trap verdicts (data/evidence/judgments.json): {ticker: {verdict, ...}}."""
    p = ROOT / "data" / "evidence" / "judgments.json"
    return json.loads(p.read_text()).get("tickers", {}) if p.exists() else {}

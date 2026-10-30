"""Module 7: record the owner's real trades (python main.py --buy / --sell)."""
from __future__ import annotations

import json
from datetime import date

from common.config import path
from common.log import get_logger
from portfolio_ledger.db import connect, log_event, now
from portfolio_ledger.execution_manager import HORIZON_NAMES, NAME_TO_H, atr14, barriers

log = get_logger("sync")


def auto_horizon(ticker: str) -> int:
    """Horizon where the ticker scored highest in the latest ml_candidates.json; monthly if unlisted."""
    p = path("ml_out") / "ml_candidates.json"
    if not p.exists():
        return 21
    best, best_p = 21, -1.0
    for h, v in json.loads(p.read_text())["horizons"].items():
        row = next((r for r in v["all"] if r["ticker"] == ticker), None)
        if row and row["prob"] > best_p:
            best, best_p = int(h), row["prob"]
    return best


def _cluster(ticker: str) -> str | None:
    from ml_engine.train import latest_candidates

    try:
        return next((c.get("cluster") for c in latest_candidates()["candidates"] if c["ticker"] == ticker), None)
    except FileNotFoundError:
        return None


def buy(ticker: str, price: float, horizon: str | None = None, on: str | None = None) -> dict:
    ticker = ticker.upper()
    h = NAME_TO_H[horizon] if horizon else auto_horizon(ticker)
    on = on or date.today().isoformat()
    atr, _, price_date = atr14(ticker, as_of=on)
    b = barriers(price, atr, h, on)  # anchored to the owner's actual fill price
    with connect() as con:
        cur = con.execute(
            "INSERT INTO positions(ticker,horizon,mode,source,entry_date,entry_price,atr14,tp,sl,expiry_date,status,"
            "cluster,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,'OPEN',?,?,?)",
            (ticker, h, "MANUAL", "user", on, price, b["atr14"], b["tp"], b["sl"], b["expiry"], _cluster(ticker),
             f"ATR_14 as of {price_date}", now()))
        log_event(con, cur.lastrowid, "BUY", json.dumps({"price": price, **b}))
    out = {"id": cur.lastrowid, "ticker": ticker, "horizon": HORIZON_NAMES[h], **b}
    log.info("BUY %s @ %.2f (%s): TP %.2f  SL %.2f  expires %s", ticker, price, HORIZON_NAMES[h], b["tp"], b["sl"],
             b["expiry"])
    return out


def sell(ticker: str, price: float, on: str | None = None) -> dict:
    """Closes the oldest OPEN real position in the ticker (first in, first out)."""
    ticker, on = ticker.upper(), on or date.today().isoformat()
    with connect() as con:
        row = con.execute("SELECT * FROM positions WHERE ticker=? AND status='OPEN' AND source='user' "
                          "ORDER BY entry_date, id LIMIT 1", (ticker,)).fetchone()
        if not row:
            raise ValueError(f"No OPEN position in {ticker} that you bought. Open positions: see the dashboard.")
        pnl, ret = price - row["entry_price"], price / row["entry_price"] - 1
        con.execute("UPDATE positions SET status='CLOSED_MANUAL', exit_date=?, exit_price=?, pnl=?, ret_pct=? WHERE id=?",
                    (on, price, pnl, ret, row["id"]))
        log_event(con, row["id"], "SELL", json.dumps({"price": price, "pnl": pnl, "ret_pct": ret}))
    log.info("SELL %s @ %.2f: P&L $%.2f (%+.2f%%)", ticker, price, pnl, ret * 100)
    return {"id": row["id"], "ticker": ticker, "entry": row["entry_price"], "exit": price, "pnl": round(pnl, 2),
            "ret_pct": round(ret * 100, 2)}

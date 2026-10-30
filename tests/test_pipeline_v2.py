"""Triple-barrier labels, Track B rules, 8-K window and the trade ledger (offline, temp database)."""
import numpy as np
import pandas as pd
import pytest

from common.config import settings
from data_fetch.sec import friday_after_hours
from ml_engine.features import triple_barrier
from screener.rules import add_metrics, add_track_b_metrics, apply_track_b


def _px(closes, spread=0.5):
    d = pd.bdate_range("2026-01-05", periods=len(closes))
    c = np.asarray(closes, float)
    return pd.DataFrame({"open": c, "high": c + spread, "low": c - spread, "close": c, "adj_close": c,
                         "adj_open": c, "adj_high": c + spread, "adj_low": c - spread, "volume": 1e6}, index=d)


def test_triple_barrier_up_down_and_time():
    flat = [100.0] * 20                       # ATR_14 = 1.0 (high-low spread)
    up = _px(flat + [100, 101, 103, 99, 99])  # touches +2 ATR (high 103.5 >= 102) on day 3
    y, r = triple_barrier(up, 5, 2.0, 2.5)
    i = 19
    assert y.iloc[i] == 1 and r.iloc[i] == pytest.approx(0.02)
    down = _px(flat + [99, 97, 96, 100, 104])  # low 96.5 <= 97.5 before the high reaches 102
    y, r = triple_barrier(down, 5, 2.0, 2.5)
    assert y.iloc[i] == 0 and r.iloc[i] == pytest.approx(-0.025)
    still = _px(flat + [100.5] * 5)            # no barrier: time exit, not a win
    y, r = triple_barrier(still, 5, 2.0, 2.5)
    assert y.iloc[i] == 0 and r.iloc[i] == pytest.approx(0.005)
    assert np.isnan(y.iloc[-1])                # future not known yet


def test_track_b_runway_and_rnd():
    df = pd.DataFrame([
        # cash-rich biotech burning cash: 600 cash / 100 burn = 72 months runway
        {"ticker": "BIO", "mcap": 1500.0, "fcf_ttm": -100.0, "ocf_ttm": -90.0, "cash": 600.0, "total_debt": 0.0,
         "ptb": 2.0, "rev_y4": 0.0, "rnd_y4": 80.0, "currency": "USD", "price": 10.0, "fwd_pe": None, "pe_ttm": None},
        # short runway: 50 / 100 = 6 months
        {"ticker": "BURN", "mcap": 900.0, "fcf_ttm": -100.0, "ocf_ttm": -90.0, "cash": 50.0, "total_debt": 0.0,
         "ptb": 1.0, "rev_y4": 0.0, "rnd_y4": 60.0, "currency": "USD", "price": 5.0, "fwd_pe": None, "pe_ttm": None},
    ])
    out = apply_track_b(add_track_b_metrics(add_metrics(df)), settings()["screener"]["track_b"]["rules"]).set_index("ticker")
    assert out.loc["BIO"].r_ocf_or_runway and out.loc["BIO"].r_rnd_intensity and out.loc["BIO"].hard_pass
    assert not out.loc["BURN"].r_ocf_or_runway and not out.loc["BURN"].safety_pass


def test_friday_after_hours_window_uses_new_york_time():
    f = lambda ts: {"form": "8-K", "date": ts[:10], "accepted": ts, "items": "2.02"}  # noqa: E731
    filings = {"X": [f("2026-10-23T19:59:00.000Z"),   # 3:59 PM ET Friday: before the close
                     f("2026-10-23T20:05:00.000Z"),   # 4:05 PM ET Friday: in
                     f("2026-10-26T13:00:00.000Z"),   # 9:00 AM ET Monday: in
                     f("2026-10-26T14:00:00.000Z")]}  # 10:00 AM ET Monday: out
    hits = friday_after_hours(filings, "2026-10-23")
    assert [h["accepted_et"] for h in hits["X"]] == ["2026-10-23T16:05:00", "2026-10-26T09:00:00"]


def test_buy_sell_round_trip(tmp_path, monkeypatch):
    import portfolio_ledger.db as db
    import portfolio_ledger.execution_manager as em
    import portfolio_ledger.sync as sync

    monkeypatch.setattr(db, "DB", tmp_path / "portfolio.db")
    monkeypatch.setattr(em, "load_prices", lambda t: _px([50.0] * 30, spread=1.0))
    monkeypatch.setattr(sync, "_cluster", lambda t: "defense_materials")
    b = sync.buy("TEST", 50.0, "monthly", "2026-02-13")
    assert b["horizon"] == "monthly" and b["tp"] == pytest.approx(57.0) and b["sl"] == pytest.approx(43.0)
    assert b["expiry"] == em.add_trading_days("2026-02-13", 21).isoformat()   # skips Presidents' Day
    s = sync.sell("TEST", 55.0, "2026-03-01")
    assert s["pnl"] == pytest.approx(5.0) and s["ret_pct"] == pytest.approx(10.0)
    with pytest.raises(ValueError):
        sync.sell("TEST", 55.0)

from pathlib import Path

import pandas as pd

from common.config import settings
from screener.rules import add_metrics, apply_rules, score, select

FIX = Path(__file__).parent / "fixtures" / "fundamentals_sample.csv"


def screened():
    cfg = settings()["screener"]
    df = add_metrics(pd.read_csv(FIX))
    return score(apply_rules(df, cfg["rules"]), cfg["score_weights"]).set_index("ticker")


def test_zim_metrics():
    z = screened().loc["ZIM"]
    assert abs(z.fcf_yield - 991.5 / 3510.7) < 1e-9          # ~28%
    assert abs(z.ptbv - 3510.7 / 3911.5) < 1e-9               # ~0.90x
    assert z.r_fcf_yield and z.r_valuation_ptbv and z.r_valuation_pe
    assert z.r_debt_trend                                      # D/E 1.49 -> 1.42, falling
    assert z.hard_pass


def test_pfe_fails_on_negative_tangible_book():
    p = screened().loc["PFE"]
    assert not p.r_valuation_ptbv and not p.hard_pass
    assert "valuation_ptbv" in p.failed_rules


def test_non_usd_statements_never_selected():
    s = screened()
    assert not s.loc["FOR"].safety_pass
    picked = select(s.reset_index(), 30)
    assert "FOR" not in set(picked.ticker)
    assert picked.iloc[0].ticker == "ZIM" and picked.iloc[0].pass_status == "HARD_PASS"

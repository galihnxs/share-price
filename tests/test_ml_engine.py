"""Leakage guards for Module 2 (offline, synthetic data)."""
import numpy as np
import pandas as pd

from ml_engine.cv import purged_date_splits
from ml_engine.fundamentals import pit_frame


def _fact(start, end, val, filed, form="10-K"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "fp": "FY"}


CF = {"facts": {"us-gaap": {"NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
    _fact("2023-01-01", "2023-12-31", 100, "2024-02-20"),
    _fact("2024-01-01", "2024-12-31", 200, "2025-02-20"),
    # Restatement of 2023 filed later must not replace the newer 2024 value.
    _fact("2023-01-01", "2023-12-31", 999, "2025-06-01", "10-K/A"),
    # Quarterly flow must be ignored.
    _fact("2025-01-01", "2025-03-31", 5, "2025-05-01", "10-Q"),
]}}}}}


def test_fundamentals_use_filing_date_not_period_end():
    d = pd.bdate_range("2025-01-02", "2025-07-01")
    s = pit_frame(CF, d, lag_days=1)["ocf"]
    assert s.loc["2025-02-20"] == 100        # filed that day: not usable until the next day
    assert s.loc["2025-02-21"] == 200
    assert s.loc["2025-01-02"] == 100        # FY2024 ended 31 Dec but was not filed yet
    assert s.loc["2025-06-30"] == 200        # late 2023 restatement does not win
    assert (s != 5).all()                    # quarterly flow ignored


def test_purged_splits_leave_horizon_gap():
    dates = pd.Series(np.repeat(pd.bdate_range("2021-01-01", periods=600), 3))
    h = 21
    for tr, te in purged_date_splits(dates, n_splits=5, horizon=h, min_train_days=100):
        ud = np.sort(dates.unique())
        last_train = np.searchsorted(ud, dates.iloc[tr].max())
        first_test = np.searchsorted(ud, dates.iloc[te].min())
        assert first_test - last_train > h   # labels of the last train day end before the test starts
        assert not set(dates.iloc[tr]) & set(dates.iloc[te])

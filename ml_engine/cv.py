"""Purged walk-forward splits on dates (not rows), so one day's tickers never straddle train and test."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit


def purged_date_splits(dates: pd.Series, n_splits: int, horizon: int, min_train_days: int = 0):
    """Yield (train_rows, test_rows). The gap of `horizon` dates drops training rows whose
    labels (which look `horizon` days ahead) would overlap the test period."""
    udates = np.sort(dates.unique())
    tss = TimeSeriesSplit(n_splits=n_splits, gap=horizon)
    for tr_d, te_d in tss.split(udates):
        if len(tr_d) < min_train_days:
            continue
        tr, te = udates[tr_d], udates[te_d]
        yield np.flatnonzero(dates.isin(tr).to_numpy()), np.flatnonzero(dates.isin(te).to_numpy())

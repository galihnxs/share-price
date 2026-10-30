"""Point-in-time fundamentals from SEC XBRL companyfacts.

Every fact carries a `filed` date. A value is only usable from filed + lag, so a feature on day t
never sees a number the market did not have yet (no look-ahead from fiscal period ends or restatements).
Flows (cash flow, profit) use annual filings only (10-K/20-F/40-F, ~1-year duration): US and
foreign filers then mean the same thing. Balance-sheet items and share counts use any filing.
"""
from __future__ import annotations

import pandas as pd

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}

# metric -> candidate (taxonomy, tag) pairs; the tag with the freshest data wins.
TAGS = {
    "ocf": [("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
            ("ifrs-full", "CashFlowsFromUsedInOperatingActivities")],
    "capex": [("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
              ("ifrs-full", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
              ("ifrs-full", "PurchaseOfPropertyPlantAndEquipment")],
    "net_income": [("us-gaap", "NetIncomeLoss"), ("ifrs-full", "ProfitLossAttributableToOwnersOfParent"),
                   ("ifrs-full", "ProfitLoss")],
    "equity": [("us-gaap", "StockholdersEquity"), ("ifrs-full", "EquityAttributableToOwnersOfParent")],
    "liabilities": [("us-gaap", "Liabilities"), ("ifrs-full", "Liabilities")],
    "shares": [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding"),
               ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding")],
}
FLOWS = {"ocf", "capex", "net_income"}


def _facts(cf: dict, metric: str) -> pd.DataFrame:
    """Rows (end, filed, val) for the freshest candidate tag of a metric, USD (or shares) only."""
    best = pd.DataFrame(columns=["end", "filed", "val"])
    for tax, tag in TAGS[metric]:
        units = ((cf.get("facts") or {}).get(tax) or {}).get(tag, {}).get("units", {})
        rows = units.get("shares" if metric == "shares" else "USD")
        if not rows:
            continue
        df = pd.DataFrame(rows)
        if metric in FLOWS:
            df = df[df["form"].isin(ANNUAL_FORMS) & df["start"].notna()]
            dur = (pd.to_datetime(df["end"]) - pd.to_datetime(df["start"])).dt.days
            df = df[dur.between(330, 400)]
        if metric == "shares":
            df = df[df["val"] > 0]  # some cover pages report 0
        if df.empty:
            continue
        df = df[["end", "filed", "val"]].assign(end=lambda d: pd.to_datetime(d["end"]),
                                                filed=lambda d: pd.to_datetime(d["filed"]))
        if best.empty or df["filed"].max() > best["filed"].max():
            best = df
    return best


def known_as_of(facts: pd.DataFrame, dates: pd.DatetimeIndex, lag_days: int) -> pd.Series:
    """Value of the latest period end that had been filed by each date (filed + lag <= date).

    Walk filings in filed order and keep the newest period seen so far: a late restatement of an
    old year never replaces a newer year, and a new year only appears once it was filed.
    """
    if facts.empty:
        return pd.Series(float("nan"), index=dates)
    f = facts.sort_values(["filed", "end"])
    snap, cur_end, cur_val = [], None, None
    for filed, grp in f.groupby("filed", sort=True):
        top = grp.loc[grp["end"].idxmax()]
        if cur_end is None or top["end"] >= cur_end:
            cur_end, cur_val = top["end"], top["val"]
        snap.append((filed + pd.Timedelta(days=lag_days), cur_val, cur_end))
    s = pd.DataFrame(snap, columns=["avail", "val", "end"]).drop_duplicates("avail", keep="last")
    out = pd.merge_asof(pd.DataFrame({"date": dates}), s.sort_values("avail"),
                        left_on="date", right_on="avail", direction="backward")
    return pd.Series(out["val"].to_numpy(dtype=float), index=dates)


def pit_frame(cf: dict, dates: pd.DatetimeIndex, lag_days: int = 1) -> pd.DataFrame:
    """One row per date with each metric as it was known on that date."""
    df = pd.DataFrame({m: known_as_of(_facts(cf, m), dates, lag_days) for m in TAGS}, index=dates)
    # Staleness: days since the newest annual flow became usable.
    ocf = _facts(cf, "ocf")
    if not ocf.empty:
        avail = pd.Series(sorted(ocf["filed"] + pd.Timedelta(days=lag_days)))
        idx = avail.searchsorted(dates, side="right") - 1
        last = pd.Series([avail.iloc[i] if i >= 0 else pd.NaT for i in idx], index=dates)
        df["days_since_annual"] = (dates.to_series() - last).dt.days
    else:
        df["days_since_annual"] = float("nan")
    return df

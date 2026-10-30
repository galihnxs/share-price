"""CLI runner (run inside the conda env: conda activate shareprice).

Friday workflow (Claude runs the browser steps, Yahoo blocks Python on this Mac):
  0. Browser: browser_fetch/04_prices.js for `python main.py --price-symbols` (proxies, RSP, candidates, held)
     -> python browser_fetch/extract.py <saved result> data/raw
  1. python main.py --run-all
       Module 0 regime -> Module 1 screen -> SEC facts -> Module 2 train -> 8-K watch + filings + embed
       -> Module 4 evidence packs -> Module 5 ledger -> report + dashboard (opens in the browser)
     If the screen added tickers without prices, it lists them: fetch, then run --run-all again.
  2. Claude reads data/evidence/*.md, writes data/evidence/judgments.json, then: --ledger --report --dashboard
Trades (Claude runs these whenever the owner says they bought or sold):
  python main.py --buy ZIM --price 29.10 [--horizon weekly|monthly|quarterly] [--date YYYY-MM-DD]
  python main.py --sell ZIM --price 31.40 [--date YYYY-MM-DD]
Other steps:
  --fetch-universe (SEC universe)  --fundamentals: browser_fetch/02_fundamentals.js
  --screen  --fetch-facts  --train  --fetch-filings [--tickers]  --ingest  --evidence  --regime
  --audit-friday-dumps [--friday YYYY-MM-DD]  --query "debt maturities" --ticker ZIM
"""
import argparse
import json
import sys
from datetime import date, timedelta

from common.log import get_logger

log = get_logger("main")


def held_and_paper() -> dict[str, int]:
    """{ticker: cik} for every OPEN position (real and paper)."""
    from portfolio_ledger.db import open_positions
    from ml_engine.train import latest_candidates

    ciks = {c["ticker"]: c.get("cik") for c in latest_candidates()["candidates"]}
    return {p["ticker"]: ciks.get(p["ticker"]) for p in open_positions() if ciks.get(p["ticker"])}


def price_symbols() -> list[str]:
    from common.config import scenarios, settings
    from ml_engine.train import latest_candidates
    from portfolio_ledger.db import open_positions

    syms = list(scenarios()["proxy_symbols"]) + [settings()["ml"]["benchmark"]]
    try:
        syms += [c["ticker"] for c in latest_candidates()["candidates"]]
    except FileNotFoundError:
        pass
    syms += [p["ticker"] for p in open_positions()]
    return list(dict.fromkeys(syms))


def missing_prices() -> list[str]:
    from common.config import ROOT

    return [s for s in price_symbols() if not (ROOT / "data" / "raw" / "prices" / f"{s}.csv").exists()]


def last_friday(today: date | None = None) -> str:
    today = today or date.today()
    return (today - timedelta(days=(today.weekday() - 4) % 7)).isoformat()


def watch_filings(since_days: int = 120) -> dict:
    """8-K/6-K since each position's window, for open positions and today's picks."""
    from data_fetch.sec import watch_8k
    from ml_engine.train import latest_candidates
    from common.config import path

    ciks = {c["ticker"]: c.get("cik") for c in latest_candidates()["candidates"]}
    picks = json.loads((path("ml_out") / "ml_candidates.json").read_text())["audit_union"]
    want = {t: ciks[t] for t in set(picks) | set(held_and_paper()) if ciks.get(t)}
    return watch_8k(want, (date.today() - timedelta(days=since_days)).isoformat())


def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid Quant-ML + RAG investment engine")
    ap.add_argument("--run-all", action="store_true", help="Friday pipeline: modules 0-6")
    ap.add_argument("--regime", action="store_true", help="Module 0: scenario states -> knowledge_base/live_regime_weights.json")
    ap.add_argument("--fetch-universe", action="store_true", help="SEC: exchange-listed tickers in scenario clusters")
    ap.add_argument("--screen", action="store_true", help="Module 1: two-track screen, top 6 per cluster + held")
    ap.add_argument("--price-symbols", action="store_true", help="Print the symbols the browser price step must fetch")
    ap.add_argument("--fetch-facts", action="store_true", help="SEC XBRL companyfacts for screener candidates")
    ap.add_argument("--fetch-prices", action="store_true", help="Tiingo prices + macro (needs TIINGO_API_KEY)")
    ap.add_argument("--train", action="store_true", help="Module 2: train, walk-forward test, write ml_candidates.json")
    ap.add_argument("--fetch-filings", action="store_true", help="SEC filings for --tickers (default: picks + held)")
    ap.add_argument("--ingest", action="store_true", help="Module 3: chunk + embed filings in data/raw/filings")
    ap.add_argument("--evidence", action="store_true", help="Module 4: value-trap evidence packs")
    ap.add_argument("--ledger", action="store_true", help="Module 5: monitor positions, Friday ticket, log paper trades")
    ap.add_argument("--report", action="store_true", help="Write reports/recommendations_YYYY_MM_DD.md")
    ap.add_argument("--dashboard", action="store_true", help="Module 6: compile dashboard/index.html")
    ap.add_argument("--no-open", action="store_true", help="Do not open the dashboard in the browser")
    ap.add_argument("--buy", metavar="TICKER", help="Record a real 1-share buy (needs --price)")
    ap.add_argument("--sell", metavar="TICKER", help="Record a real sale (needs --price)")
    ap.add_argument("--price", type=float, help="Fill price for --buy/--sell")
    ap.add_argument("--horizon", choices=["weekly", "monthly", "quarterly"], help="Horizon for --buy")
    ap.add_argument("--date", help="Trade date for --buy/--sell (default today)")
    ap.add_argument("--audit-friday-dumps", action="store_true", help="8-Ks filed after Friday 4 PM ET for open positions")
    ap.add_argument("--friday", help="Friday to audit (default: the latest Friday)")
    ap.add_argument("--tickers", help="Comma list to limit --ingest / --fetch-filings")
    ap.add_argument("--notes", action="store_true", help="Module 3: embed knowledge_base/user_notes/")
    ap.add_argument("--watch-notes", action="store_true", help="Keep polling user_notes/ for changes")
    ap.add_argument("--query", help="Search the knowledge base")
    ap.add_argument("--ticker", help="Filter --query to one ticker")
    ap.add_argument("--section", help="Filter --query to one section, e.g. item1a_risk_factors")
    ap.add_argument("-k", type=int, default=6, help="Results for --query")
    ap.add_argument("--as-of", help="Override output date tag (YYYY-MM-DD)")
    a = ap.parse_args()
    if len(sys.argv) == 1:
        ap.print_help()
        return 1

    # ---------------------------------------------------------------- trades
    if a.buy or a.sell:
        if a.price is None:
            ap.error("--buy/--sell need --price")
        from portfolio_ledger.sync import buy, sell

        res = buy(a.buy, a.price, a.horizon, a.date) if a.buy else sell(a.sell, a.price, a.date)
        print(json.dumps(res, indent=2))
        from portfolio_ledger.execution_manager import run as ledger
        from dashboard.generator import build as dash

        try:
            ledger()
        except FileNotFoundError as e:
            log.warning("ledger not refreshed: %s", e)
        dash(open_browser=not a.no_open)
        return 0

    if a.price_symbols:
        print(" ".join(price_symbols()))
        return 0
    if a.fetch_universe:
        from data_fetch.sec import fetch_universe

        fetch_universe(as_of=a.as_of)
    if a.regime or a.run_all:
        from regime_engine.state_tracker import run as regime

        regime()
    if a.screen or a.run_all:
        from screener.run import run as screen

        top = screen(a.as_of)
        print(top[["rank", "ticker", "cluster", "track", "pass_status", "fwd_pe", "fcf_yield", "score"]].to_string(index=False))
    if a.fetch_facts or a.run_all:
        from data_fetch.http import SEC
        from data_fetch.sec import companyfacts
        from ml_engine.train import latest_candidates

        sec = SEC()
        for c in latest_candidates()["candidates"]:
            if c.get("cik"):
                companyfacts(c["cik"], sec)
    if a.fetch_prices:
        from data_fetch.prices import fetch_macro, fetch_prices

        fetch_prices(price_symbols())
        fetch_macro()
    if a.run_all:
        miss = missing_prices()
        if miss:
            log.warning("No prices yet for %s symbols. Fetch them with browser_fetch/04_prices.js, then run "
                        "--run-all again:\n%s", len(miss), " ".join(miss))
            return 2
    if a.train or a.run_all:
        from ml_engine.train import run as train

        train(a.as_of)
    filings = {}
    if a.run_all or a.ledger:
        filings = watch_filings()
    if a.fetch_filings or a.run_all:
        from data_fetch.sec import fetch_filings
        from ml_engine.train import latest_candidates
        from common.config import path

        ciks = {c["ticker"]: c.get("cik") for c in latest_candidates()["candidates"]}
        want = a.tickers.split(",") if a.tickers else \
            json.loads((path("ml_out") / "ml_candidates.json").read_text())["audit_union"] + list(held_and_paper())
        fetch_filings({t: ciks[t] for t in dict.fromkeys(want) if ciks.get(t)})
    if a.ingest or a.run_all:
        from knowledge_base.pipeline import ingest_filings

        ingest_filings(a.tickers.split(",") if a.tickers else None)
    if a.notes or a.run_all:
        from knowledge_base.pipeline import ingest_notes

        ingest_notes()
    if a.evidence or a.run_all:
        from llm_evaluator.evidence import build

        build()
    if a.ledger or a.run_all:
        from portfolio_ledger.execution_manager import run as ledger

        ledger(filings=filings)
    if a.report or a.run_all:
        from llm_evaluator.report import build as report

        print(report(a.as_of))
    if a.dashboard or a.run_all:
        from dashboard.generator import build as dash

        print(dash(open_browser=not a.no_open))
    if a.audit_friday_dumps:
        from data_fetch.sec import friday_after_hours, watch_8k

        fri = a.friday or last_friday()
        hits = friday_after_hours(watch_8k(held_and_paper(), fri), fri)
        if not hits:
            print(f"No 8-K/6-K filed after 4:00 PM ET on {fri} (through Monday open) for open positions.")
        for t, fs in hits.items():
            for f in fs:
                print(f"{t}  {f['form']}  accepted {f['accepted_et']} ET  items {f['items'] or '-'}  {f['url']}")
    if a.query:
        from knowledge_base.pipeline import query

        for h in query(a.query, a.ticker, a.section, a.k):
            m = h["meta"]
            print(f"\n[{h['score']:.3f}] {h['id']}  {m.get('url', m.get('file', ''))}\n{h['text'][:600]}")
    if a.watch_notes:
        from knowledge_base.pipeline import watch_notes

        watch_notes()
    return 0


if __name__ == "__main__":
    sys.exit(main())

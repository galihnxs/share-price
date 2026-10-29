"""CLI runner (run inside the conda env: conda activate shareprice).

Data flow each session:
  1. Browser fetch (Claude runs browser_fetch/*.js in the built-in browser) -> data/raw/
  2. python main.py --screen               Module 1 -> data/screener/candidates_YYYY-MM-DD.{csv,json}
  3. python main.py --ingest [--tickers]   Module 3 -> knowledge_base/chroma (filings in data/raw/filings)
     python main.py --notes                embed knowledge_base/user_notes/ (--watch-notes to keep polling)
     python main.py --query "debt maturities" --ticker ZIM [--section item1a_risk_factors]
  (next phase) --train, --evaluate, --report
"""
import argparse
import json
import sys

from common.log import get_logger

log = get_logger("main")


def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid Quant-ML + RAG investment engine")
    ap.add_argument("--screen", action="store_true", help="Module 1: deep-value screen from data/raw CSVs")
    ap.add_argument("--ingest", action="store_true", help="Module 3: chunk + embed filings in data/raw/filings")
    ap.add_argument("--tickers", help="Comma list to limit --ingest")
    ap.add_argument("--notes", action="store_true", help="Module 3: embed knowledge_base/user_notes/")
    ap.add_argument("--watch-notes", action="store_true", help="Keep polling user_notes/ for changes")
    ap.add_argument("--query", help="Search the knowledge base")
    ap.add_argument("--ticker", help="Filter --query to one ticker")
    ap.add_argument("--section", help="Filter --query to one section, e.g. item1a_risk_factors")
    ap.add_argument("-k", type=int, default=6, help="Results for --query")
    ap.add_argument("--run-all", action="store_true", help="Run every module that is built")
    ap.add_argument("--as-of", help="Override output date tag (YYYY-MM-DD)")
    a = ap.parse_args()

    if not any([a.screen, a.ingest, a.notes, a.watch_notes, a.query, a.run_all]):
        ap.print_help()
        return 1
    if a.screen or a.run_all:
        from screener.run import run

        top = run(a.as_of)
        print(top[["rank", "ticker", "sector", "pass_status", "fwd_pe", "ptbv", "fcf_yield", "score"]].to_string(index=False))
    if a.ingest or a.run_all:
        from knowledge_base.pipeline import ingest_filings

        ingest_filings(a.tickers.split(",") if a.tickers else None)
    if a.notes or a.run_all:
        from knowledge_base.pipeline import ingest_notes

        ingest_notes()
    if a.query:
        from knowledge_base.pipeline import query

        for h in query(a.query, a.ticker, a.section, a.k):
            m = h["meta"]
            print(f"\n[{h['score']:.3f}] {h['id']}  {m.get('url', m.get('file', ''))}\n{h['text'][:600]}")
    if a.watch_notes:
        from knowledge_base.pipeline import watch_notes

        watch_notes()
    if a.run_all:
        log.info("Modules 2 and 4 not built yet (ML engine, evaluator).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

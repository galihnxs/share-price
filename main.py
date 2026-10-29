"""CLI runner.

Data flow each session:
  1. Browser fetch (Claude runs browser_fetch/*.js in the built-in browser) -> data/raw/*.csv
  2. python main.py --screen     -> data/screener/candidates_YYYY-MM-DD.{csv,json}
  3. (next phase) --train, --ingest, --evaluate, --report
"""
import argparse
import sys

from common.log import get_logger

log = get_logger("main")


def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid Quant-ML + RAG investment engine")
    ap.add_argument("--screen", action="store_true", help="Module 1: deep-value screen from data/raw CSVs")
    ap.add_argument("--run-all", action="store_true", help="Run every module that is built")
    ap.add_argument("--as-of", help="Override output date tag (YYYY-MM-DD)")
    a = ap.parse_args()

    if not (a.screen or a.run_all):
        ap.print_help()
        return 1
    if a.screen or a.run_all:
        from screener.run import run

        top = run(a.as_of)
        print(top[["rank", "ticker", "sector", "pass_status", "fwd_pe", "ptbv", "fcf_yield", "score"]].to_string(index=False))
    if a.run_all:
        log.info("Modules 2-4 not built yet (ML engine, knowledge base, evaluator).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

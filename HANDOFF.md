# Handoff — status as of 2026-10-29

Spec: Hybrid Quant-ML + Local RAG engine, 4 modules (screener, ML engine, knowledge base, LLM evaluator).
Data so far was fetched through the Claude app's browser (scripts in `browser_fetch/`), because the
earlier session's sandbox could not reach Yahoo/SEC. In Claude Code on this Mac, Python has normal
internet, so you can replace the browser layer with direct fetchers that write the SAME files into `data/raw/`.

## Done
- Module 1 screener (`screener/`, `python main.py --screen`): SEC SIC universe (2,374 tickers, tech SIC 3559/3570-3579 excluded)
  -> Yahoo fundamentals (570 after pre-filter: mcap>=$300M, OCF>0, FCF yield>3%) -> hard rules + ranked fill to 30.
  Output: `data/screener/candidates_2026-10-29.{csv,json}`. 8 hard passes: GM, ZIM, ESEA, PANL, UVV, GSL, NVGS, SENEB.
  Fixes in: dedupe share classes by CIK, non-USD statements excluded, GM/F flagged (captive finance inflates FCF).
- Module 3 knowledge base code (`knowledge_base/`): section-aware chunker (10-K, 10-Q part-aware, 20-F, 8-K/6-K),
  tables kept separate, deterministic IDs, bge-small on MPS, ChromaDB upsert-only-new, user_notes with edit detection.
  44 filings for the 8 hard passes are in `data/raw/filings/` (2,456 chunks). NOT yet embedded.
- Tests: `pytest tests` -> 8 passed (offline, fake embedder).

## Remaining (in order)
1. Env: run `bash scripts/setup_env.sh` again (fix added: llvm-openmp for xgboost). Expect ">> SETUP OK" in data/setup_log.txt.
2. Embed: `bash scripts/ingest.sh` -> check data/ingest_log.txt: query results should be ZIM debt/refinancing chunks.
3. Data layer for Claude Code: write Python fetchers (SEC submissions/browse-by-SIC with User-Agent from .env,
   Yahoo quoteSummary + fundamentals-timeseries + chart API) producing the same CSV/filing formats. Copy `.env.example` to `.env`.
4. Module 2 ML engine (`ml_engine/`, not started): 5y daily OHLCV for candidates + RSP, ^VIX, DXY (DX-Y.NYB), CL=F, 10Y-2Y;
   3 models (5/21/63-day targets per spec), TimeSeriesSplit with a purge gap = horizon (labels overlap),
   report out-of-sample precision vs. base rate per horizon; write `ml_candidates.json` (top 3 per horizon).
   Fundamental features must be point-in-time (use SEC XBRL companyfacts with filed dates), else leakage.
5. Fetch filings for the 9 ML picks (`browser_fetch/03_filings.js` logic) and ingest.
6. Module 4 evaluator (`llm_evaluator/`): build evidence packs per pick (value-trap queries on risk factors / MD&A / legal /
   debt maturities + macro rotation); the user wants the judgment done by Claude in-session, NOT via an API.
7. Report: `reports/recommendations_YYYY_MM_DD.md` (pyramid summary, quant card, cited RAG audit, hold calendar D+5/21/63).

## Known gaps
- P/E-percentile rule is a proxy (only 4 years of EPS).
- SENEB MD&A is incorporated by reference (Exhibit 13) — fetch that exhibit.
- No git commit made yet.

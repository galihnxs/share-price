# Handoff - status as of 2026-10-29 (late evening)

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

## Done in session 2 (2026-10-29)
- Setup: `scripts/setup_env.sh` now installs conda-forge llvm-openmp -> ">> SETUP OK" (py 3.14.10, MPS).
- Ingest: 2,456 chunks embedded (56 s). ZIM debt query returns liquidity covenant / $5.7B debt chunks.
- `data_fetch/` replaces browser_fetch 01 + 03: SEC universe, filings (+ Ex-99 / Ex-13), XBRL companyfacts.
  Yahoo returns HTTP 429 to all Python requests from this Mac (curl_cffi impersonation was refused by the
  permission check), so prices come from Tiingo (`TIINGO_API_KEY`) and macro from the FRED API
  (`FRED_API_KEY`, optional; ETF proxies otherwise). `data_fetch/yahoo.py` is kept for when Yahoo allows it.
  browser_fetch/02_fundamentals.js is still the way to refresh the screener's Yahoo fundamentals.
- Module 2 `ml_engine/` built: point-in-time fundamentals (filed date + 1 day, annual flows only),
  purged walk-forward CV (gap = horizon), top-3 precision vs base rate with overlap-adjusted z, edge flag.
  `python main.py --fetch-prices --fetch-facts` then `--train` -> data/ml/ml_candidates.json.
  Random-walk sanity run: no edge at any horizon (as it should be). Tests: 10 passed.

## Done in session 3 (2026-10-30)
- Prices + macro via `browser_fetch/04_prices.js` (user chose browser over a Tiingo key; Tiingo/FRED code kept in
  data_fetch/prices.py as an option). 36 symbols, extract.py writes data/raw/prices + data/raw/macro.
- Module 2 trained on real data: NO edge at 5/21/63d (63d lift +4.1 pts, z 0.51). data/ml/ml_candidates.json.
- Filings for GFI, GIII, VHI fetched + embedded (KB total 3,954 chunks).
- Module 4: `llm_evaluator/evidence.py` (`python main.py --evidence`) -> data/evidence/*.md.
- Report: reports/recommendations_2026_10_30.md (GIII = likely value trap, VHI caution).

## Done in session 4 (2026-10-30): v2 pipeline (6 scenarios, Friday cadence)
- Module 0 `regime_engine/` -> knowledge_base/live_regime_weights.json + data/regime/z_history.csv.
  Today: Pandemic 2028 + Asia war IMMINENT, others LATENT.
- Module 1: 6 scenario clusters (config/sectors.yaml, config/scenarios.yaml), Track A/B rules, AI gate,
  top 6 per cluster (36) + held. 2,365 universe -> 689 fundamentals -> 95 hard passes.
- Module 2: triple-barrier labels = ledger barriers, Friday rows only, xs Z-scores, Friday features,
  scenario Z features, depth-3 trees. Result: NO edge (monthly lift +11.5 pts, z 1.43, PF 1.08; driven by atr_pct).
- Module 5/7 `portfolio_ledger/` (portfolio.db): PAPER auto-logged + self-closing; MANUAL via --buy/--sell.
  3 PAPER positions open: VHI 5d, GM 21d, ESEA 63d (entry 29 Oct close).
- Module 6 `dashboard/` (index.html, file://). `--audit-friday-dumps` (8-K after Fri 4 PM ET, UTC-converted).
- judgments.json = Claude's verdicts; ZIM AVOID (pending $35 Hapag-Lloyd deal), APTV AVOID (unadjusted spin).
- Tests: 14 passed. Note: the generated report replaced the hand-written 30 Oct report (same filename).

- 5 picks per horizon (settings ml.top_k: 5, audit_spares: 4): edge judged on the top-5 set; 15 PAPER positions
  open (weekly VHI GFI APA SM CHRD; monthly GM LEA VHI ESEA NEXA; quarterly ESEA LEA VHI GM FSM).

## Next ideas
- Adjust APTV's pre-2026-04-01 prices for the Versigent spin; move autos/auto parts out of defense_materials.
- The edge test is dominated by volatility (atr_pct): try sector-neutral barriers or rank within ATR buckets.
- Log picks monthly and score them at D+5/21/63 to build a live track record.
- The model has no edge: try fewer features, sector-neutral targets, or a longer history before trusting picks.

## Remaining (original list; all steps now done once)
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

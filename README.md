# Share Price — Hybrid Quant-ML + Local RAG Investment Engine

A personal research tool that picks three US stocks to "buy 1 share and hold" for three time frames:
**1 week (5 trading days), 1 month (21 days) and 1 quarter (63 days)**.
The picks should hold up even if the AI/tech bubble deflates, so the search covers old-economy sectors only.

> This is a research tool, not financial advice. Short-horizon predictions are noisy; every model must
> show its out-of-sample edge against a "pick at random" baseline before its picks are trusted.

## Goal

Each run produces `reports/recommendations_YYYY_MM_DD.md` with:
1. **Summary:** the 3 tickers to buy today (weekly, monthly, quarterly) and their price.
2. **Quant card:** model probability, expected return range, P/E, FCF yield, P/TBV.
3. **Filing audit:** quotes from the latest 10-K/10-Q (or 20-F/6-K) showing why the stock is cheap and that it is not a value trap.
4. **Hold calendar:** the review/exit date for each share (day +5, +21, +63).

## How it works (4 modules)

| Module | Folder | What it does | Status |
|---|---|---|---|
| 1. Deep-value screener | `screener/` | SEC industry codes -> ~2,400 tickers in energy, hard assets, industrials, shipping, old economy, mature healthcare. Hard rules: forward P/E < 12 (or bottom 25% of own history), P/TBV < 1.5, FCF yield > 8%, positive operating cash flow, debt/equity not rising, market cap > $300M, share growth < 3%. Fills to 30 names by a value/safety score. | Done |
| 2. ML engine | `ml_engine/` | Three models (5/21/63-day targets: +4% with drawdown better than -3%, +8%, +15%). Time-ordered cross-validation, no data leakage. Outputs top 3 per horizon -> `ml_candidates.json`. | Not started |
| 3. Knowledge base | `knowledge_base/` | SEC filings split by legal section (Business, Risk Factors, MD&A, Legal), tables kept separate, embedded locally (bge-small on Apple GPU) into ChromaDB. Also embeds your own notes from `knowledge_base/user_notes/`. | Built, not yet embedded |
| 4. Evaluator | `llm_evaluator/` | Pulls the most relevant filing passages for each pick and audits value-trap risk (lawsuits, lost customers, debt walls) and fit with a rotation out of tech. Claude does the judgment in-session (no API). | Not started |

## Current approach and key decisions

- **Data in, Python reads files.** All raw data lands in `data/raw/` (universe CSV, fundamentals CSV, filing text files). The modules never fetch from the internet themselves, so runs are repeatable.
- **Fetching.** The first session fetched through the Claude app's browser (`browser_fetch/*.js`) because its sandbox was blocked. On this Mac, Python fetchers can replace that and write the same files.
- **Universe from SEC SIC codes**, not an index, so foreign shippers (20-F filers) are included. Computer, networking and chip-equipment codes are excluded on purpose.
- **Safety gates never relax:** market cap, positive cash flow, no heavy dilution, statements in USD. Only valuation rules relax in the ranked fill.
- **Known distortions are flagged**, e.g. GM/Ford lending arms inflate FCF.
- **No look-ahead:** ML features from fundamentals must use the filing date, not the period end.
- **Local and private:** embeddings run on the Mac (MPS); no paid APIs.

## Setup

```bash
bash scripts/setup_env.sh        # conda env "shareprice", Python 3.14, checks MPS + embedding model
cp .env.example .env             # SEC requires a contact in the User-Agent
conda activate shareprice
```

## Commands

```bash
python main.py --screen                         # Module 1 -> data/screener/candidates_YYYY-MM-DD.csv
bash scripts/ingest.sh                          # Module 3: embed filings + notes, run test searches
python main.py --query "debt maturities" --ticker ZIM
python main.py --watch-notes                    # re-embed notes when you edit them
pytest tests                                    # offline tests
```

## Layout

```
config/          settings.yaml (all thresholds), sectors.yaml (SIC ranges)
browser_fetch/   browser data-fetch scripts used in the first session
screener/        Module 1
ml_engine/       Module 2 (to build)
knowledge_base/  Module 3 (+ user_notes/ for your own research)
llm_evaluator/   Module 4 (to build)
data/            raw inputs and outputs (git-ignored)
reports/         final markdown reports
scripts/         setup_env.sh, ingest.sh
HANDOFF.md       what is done and what is next
```

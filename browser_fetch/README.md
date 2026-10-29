# Browser fetch layer

Python on this Mac cannot always reach Yahoo/SEC from Claude's sandbox, so Claude pulls raw
data through the Claude app's built-in browser, shrinks it to CSV in the page, and writes the
CSV into `data/raw/`. Python modules only ever read `data/raw/` (no network calls).

| Step | Script | Tab origin | Output |
|---|---|---|---|
| 1 | `01_universe.js` | https://www.sec.gov | `data/raw/universe_YYYY-MM-DD.csv` |
| 2 | `02_fundamentals.js` | https://query1.finance.yahoo.com | `data/raw/fundamentals_YYYY-MM-DD.csv` |

Step 2 needs `window.__sp.tickers` set to the universe tickers first.
Pre-filter in step 2: market cap >= $300M, operating cash flow > 0, TTM FCF yield > 3%.

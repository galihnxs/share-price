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

**Status (2026-10-29):** steps 1 and 3 now run in Python (`data_fetch/sec.py`, `python main.py --fetch-universe`,
`--fetch-filings`). Step 2 stays here while Yahoo blocks Python requests from this Mac.
| 4 | `04_prices.js` | https://query1.finance.yahoo.com | `data/raw/prices/*.csv` + `data/raw/macro/*.csv` |

Step 4: set `window.__sp.priceSymbols` (RSP + screener candidates + `^VIX, DX-Y.NYB, CL=F, ^TNX, 2YY=F`), run the
script, then return `window.__sp.px.payload()`; the tool saves the large result to a file. Run
`python browser_fetch/extract.py <that file> data/raw` (also writes the macro series; 10Y-2Y = ^TNX - 2YY=F).

**Status (2026-10-30):** `02_fundamentals.js` now takes `window.__sp.trackA` / `trackB` (tickers by screening track,
from the scenario clusters) and adds cash, total debt, P/B, revenue and R&D columns. `extract.py` also handles the
`<<<CSV>>>` fundamentals payload and drops today's bar until 4:15 PM New York time.

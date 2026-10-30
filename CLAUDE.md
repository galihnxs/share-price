# CLAUDE.md — working rules for this repo

Read `README.md` (goals, design) and `HANDOFF.md` (status, next steps) first.

## Environment
- Always use the conda env `shareprice` (Python 3.14, Apple Silicon M2, 24GB). Prefix commands with
  `conda run -n shareprice` or activate it. Never install into the `ind5003` env (a university course env).
- Torch device: use `common/device.py` (MPS with CPU fallback). Free GPU memory between big batches.

## Architecture rules
- Modules only read from `data/raw/` and write to `data/` or `reports/`. Fetching lives in its own layer.
- All thresholds live in `config/settings.yaml`; do not hard-code them.
- Chunk IDs must stay deterministic (`ticker_form_date_section_n`) so re-runs embed only new filings.
- SEC requests: User-Agent from `.env` (`SEC_USER_AGENT`), max ~8 requests/second.

## Correctness rules (do not break)
- No look-ahead: fundamental features must use the filing date, not the fiscal period end.
- Time-series CV must purge a gap equal to the target horizon (labels overlap).
- Report out-of-sample precision vs the base rate for each horizon; flag horizons with no edge.
- Safety gates (market cap, OCF > 0, dilution, USD statements) are never relaxed in the ranked fill.
  Track B (bio/tech) replaces OCF > 0 with "OCF > 0 or >= 24 months cash runway" (owner's decision, 30 Oct 2026).
- Keep known data distortions flagged (e.g. GM/F captive finance FCF).

## Working style
- The owner prefers: clarifying questions before big or irreversible steps; high-level summary first,
  detail on request; plain English, short sentences.
- Module 4 judgment is done by Claude in the session, not by calling an LLM API.
- Run `pytest tests` after changes. Do not commit to git unless asked.
- This is a research tool, not financial advice; reports must say so.

## Trades (always)
- Whenever the user says they bought or sold a stock, immediately run
  `python main.py --buy <TICKER> --price <PRICE> [--horizon weekly|monthly|quarterly] [--date YYYY-MM-DD]` or
  `python main.py --sell <TICKER> --price <PRICE> [--date YYYY-MM-DD]`. Both refresh the dashboard.
  If the ticker has no price file yet, fetch it first with browser_fetch/04_prices.js (ATR_14 needs it).
- MANUAL positions are real money: never close them on a barrier hit; only the user's --sell closes them.
  PAPER positions are simulated and close themselves.

## Friday workflow
1. Browser: `python main.py --price-symbols`, fetch those with browser_fetch/04_prices.js in the Yahoo tab,
   then `python browser_fetch/extract.py <saved result> data/raw`. Refresh fundamentals (02) about weekly.
2. `python main.py --run-all --no-open` (stops and lists symbols if new candidates have no prices).
3. Read data/evidence/*.md, write the verdicts to data/evidence/judgments.json (cite chunk IDs), then
   `python main.py --ledger --report --dashboard`.
4. After the US close: `python main.py --audit-friday-dumps`.
- Yahoo blocks Python on this Mac. Do not use curl_cffi or any TLS impersonation (bot-check circumvention).
- Browser: run long jobs in the Yahoo tab and always pass its tabId; file previews open new tabs.

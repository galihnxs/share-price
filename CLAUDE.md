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
- Keep known data distortions flagged (e.g. GM/F captive finance FCF).

## Working style
- The owner prefers: clarifying questions before big or irreversible steps; high-level summary first,
  detail on request; plain English, short sentences.
- Module 4 judgment is done by Claude in the session, not by calling an LLM API.
- Run `pytest tests` after changes. Do not commit to git unless asked.
- This is a research tool, not financial advice; reports must say so.

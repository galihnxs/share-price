"""Module 6: compile dashboard/index.html from template.html + the pipeline state.

The state is embedded as <script>window.PIPELINE_DATA = {...}</script>, so the file opens straight
from disk (file://) with no server. Re-run after every pipeline run or trade sync.
"""
from __future__ import annotations

import json
import webbrowser
from datetime import datetime

from common.config import ROOT, path, scenarios
from common.log import get_logger

log = get_logger("dashboard")
DIR = ROOT / "dashboard"


def _chunks(ids: list[str]) -> dict[str, dict]:
    """Verbatim filing excerpts for cited chunk IDs."""
    if not ids:
        return {}
    from knowledge_base import store

    r = store.collection().get(ids=ids, include=["documents", "metadatas"])
    return {i: {"text": d, "url": m.get("url", ""), "section": m.get("section", ""), "form": m.get("form", ""),
                "date": m.get("date", "")} for i, d, m in zip(r["ids"], r["documents"], r["metadatas"])}


def state() -> dict:
    from portfolio_ledger.db import all_positions
    from portfolio_ledger.execution_manager import STATE_FILE, load_audit
    from regime_engine.state_tracker import OUT as REGIME_FILE, exposure_vector

    regime = json.loads(REGIME_FILE.read_text()) if REGIME_FILE.exists() else {"scenarios": {}}
    mlp = path("ml_out") / "ml_candidates.json"
    ml = json.loads(mlp.read_text()) if mlp.exists() else {"horizons": {}}
    led = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"positions": [], "new_buys": [],
                                                                         "sell_or_rollover": [], "badges": {}}
    audit = load_audit()
    jp = ROOT / "data" / "evidence" / "judgments.json"
    judg = json.loads(jp.read_text()).get("tickers", {}) if jp.exists() else {}
    cand_files = sorted((ROOT / "data" / "screener").glob("candidates_*.json"))
    cands = {c["ticker"]: c for c in json.loads(cand_files[-1].read_text())["candidates"]} if cand_files else {}
    names = list(scenarios()["scenarios"])

    # Per horizon: the ticket's top-k names (same audit filter as the ledger), plus names the audit skipped.
    top = {}
    for h, v in ml["horizons"].items():
        tickets = [t for t in led["new_buys"] if str(t["horizon"]) == h]
        rows = {r["ticker"]: r for r in v.get("all", [])}
        picks = []
        for tk in tickets:
            t, p = tk["ticker"], rows.get(tk["ticker"], {})
            j = judg.get(t, {})
            cite_ids = [c for pt in j.get("points", []) for c in pt.get("cite", [])]
            sc = j.get("scenario_scores") or exposure_vector(tk.get("cluster") or "")
            picks.append({"ticker": t, "name": tk.get("name", ""), "exchange": tk.get("exchange", ""), "rank": tk["rank"], "prob": p.get("prob"), "score": p.get("score"),
                          "scenario_tilt": p.get("scenario_tilt"), "cluster": tk.get("cluster"),
                          "ticket": {k: tk[k] for k in ("limit", "tp", "sl", "expiry", "mode", "badge")},
                          "fundamentals": {k: cands.get(t, {}).get(k) for k in
                                           ("fwd_pe", "fcf_yield", "ptbv", "price_to_book", "mcap", "pass_status", "flag")},
                          "scenario_scores": [sc.get(n, 0) for n in names], "audit": j, "excerpts": _chunks(cite_ids)})
        last_rank_prob = picks[-1]["prob"] if picks else 0
        skipped = [{"ticker": r["ticker"], "prob": r["prob"], "verdict": audit.get(r["ticker"], {}).get("verdict")}
                   for r in v.get("all", []) if audit.get(r["ticker"], {}).get("verdict") in ("TRAP", "AVOID")
                   and r["prob"] >= (last_rank_prob or 0)]
        top[h] = {"horizon_name": v["name"], "badge": led["badges"].get(h, {}).get("badge"), "metrics": v["metrics"],
                  "picks": picks, "skipped": skipped}
    closed = [p for p in all_positions() if p["status"] != "OPEN"]
    return {
        "generated": datetime.now().isoformat(timespec="seconds"), "price_date": ml.get("price_date"),
        "scenario_names": names, "macro_regimes": regime.get("scenarios", {}),
        "friday_orders": {"sell_or_rollover": led["sell_or_rollover"], "new_buys": led["new_buys"]},
        "open_positions": led["positions"], "closed_positions": closed[-30:], "badges": led["badges"],
        "top_picks_rag": top,
        "model": {h: {"name": v["name"], "metrics": v["metrics"], "old": v.get("metrics_old_label")}
                  for h, v in ml["horizons"].items()},
    }


def build(open_browser: bool = False) -> str:
    data = json.dumps(state(), default=str).replace("</", "<\\/")  # keep </script> inside strings harmless
    html = (DIR / "template.html").read_text().replace("/*__PIPELINE_DATA__*/null", data)
    out = DIR / "index.html"
    out.write_text(html)
    log.info("dashboard -> %s", out)
    if open_browser:
        webbrowser.open(out.as_uri())
    return str(out)

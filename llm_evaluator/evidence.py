"""Module 4 part 1: evidence packs for the value-trap audit.

No LLM API: this only gathers evidence. The judgment is written by Claude in the session,
reading these packs, and every claim in the report cites a chunk ID from them.

Pack per pick = quant card (screener + ML) + top chunks for each value-trap question
from that company's own filings + the macro backdrop.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd

from common.config import ROOT, path, settings
from common.log import get_logger
from knowledge_base.pipeline import query

log = get_logger("evidence")

# Each question targets one way a cheap stock stays cheap (or gets cheaper).
TRAP_QUERIES = {
    "debt_refinancing": "debt maturities, refinancing risk, covenants, credit facility, liquidity",
    "earnings_decline": "revenue decline, lower prices, margin pressure, weaker demand, guidance cut",
    "customer_concentration": "customer concentration, contract termination, charter expiry, loss of major customer",
    "legal_regulatory": "litigation, legal proceedings, investigation, regulatory fines, sanctions",
    "impairment_writedown": "impairment, write-down, going concern, restructuring charges",
    "capital_allocation": "dividend policy, share repurchase, share issuance, dilution, capital expenditure plans",
    "cycle_outlook": "industry outlook, overcapacity, orderbook, commodity price cycle, freight rates",
}


def _macro_snapshot() -> dict:
    out = {}
    for n in ("vix", "usd", "oil", "curve_10y2y"):
        p = ROOT / "data" / "raw" / "macro" / f"{n}.csv"
        if p.exists():
            s = pd.read_csv(p, index_col="date")["value"].dropna()
            out[n] = {"last": round(float(s.iloc[-1]), 3), "date": s.index[-1],
                      "chg_21d": round(float(s.iloc[-1] - s.iloc[-22]), 3),
                      "pct_rank_5y": round(float((s.tail(1260) <= s.iloc[-1]).mean()), 2)}
    return out


def build(k: int = 3, max_chars: int = 1100) -> list:
    ml = json.loads((path("ml_out") / "ml_candidates.json").read_text())
    scr = {c["ticker"]: c for c in json.loads(sorted((ROOT / settings()["paths"]["screener_out"])
                                                     .glob("candidates_*.json"))[-1].read_text())["candidates"]}
    out_dir = path("data_dir") / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    macro = _macro_snapshot()
    written = []
    from portfolio_ledger.db import open_positions
    from regime_engine.state_tracker import exposure_vector, load as load_regime

    regime = load_regime().get("scenarios", {})
    held = [p["ticker"] for p in open_positions()]
    for t in dict.fromkeys(ml["audit_union"] + held):
        horizons = {}
        for h, v in ml["horizons"].items():
            row = next((r for r in v["all"] if r["ticker"] == t), {})
            horizons[h] = {"prob": row.get("prob"), "is_pick": t in [p["ticker"] for p in v["picks"]],
                           "edge": v["metrics"]["edge"]}
        s = scr.get(t, {})
        exp = exposure_vector(s.get("cluster") or "")
        lines = [f"# Evidence pack: {t}" + ("  (HELD)" if t in held else ""), "",
                 "## Quant card",
                 f"- Screener: {s.get('pass_status')} (rank {s.get('rank')}, {s.get('rules_passed')}/{s.get('rules_total')} rules), "
                 f"cluster {s.get('cluster')} (track {s.get('track')}), flag: {s.get('flag') or 'none'}",
                 f"- Price {s.get('price')}, mcap ${s.get('mcap')}M, fwd P/E {s.get('fwd_pe')}, P/TBV {s.get('ptbv')}, "
                 f"P/B {s.get('price_to_book')}, FCF yield {s.get('fcf_yield')}, D/E {s.get('de_prev')} -> {s.get('de_now')}, "
                 f"share growth {s.get('share_growth')}, cash/debt {s.get('cash_to_debt')}, R&D/revenue {s.get('rnd_intensity')}",
                 "- ML prob (triple-barrier win): " + ", ".join(
                     f"{h}d {v['prob']} ({'PICK' if v['is_pick'] else '-'}; edge={v['edge']})" for h, v in horizons.items()),
                 "- Scenario exposure (cluster default, -2..+2): " + ", ".join(
                     f"{k} {e:+d} [{regime.get(k, {}).get('state', '?')}]" for k, e in exp.items()),
                 f"- Macro: {json.dumps(macro)}", ""]
        seen = set()
        for name, q in TRAP_QUERIES.items():
            lines.append(f"## {name}  (query: {q})")
            n = 0
            for h in query(q, ticker=t, k=k + 3):
                if h["id"] in seen or n >= k:  # skip chunks an earlier question already showed
                    continue
                seen.add(h["id"])
                n += 1
                txt = " ".join(h["text"].split())[:max_chars]
                lines.append(f"- [{h['id']}] (score {h['score']:.2f}) {txt}")
            lines.append("")
        p = out_dir / f"{t}.md"
        p.write_text("\n".join(lines))
        written.append(p)
        log.info("%s: %s chunks -> %s", t, len(seen), p)
    (out_dir / "_index.json").write_text(json.dumps({"as_of": date.today().isoformat(), "ml": ml["as_of"],
                                                     "macro": macro, "packs": [p.name for p in written]}, indent=2))
    return written

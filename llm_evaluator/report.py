"""Writes reports/recommendations_YYYY_MM_DD.md from the pipeline outputs.

The value-trap judgment is Claude's, written in-session to data/evidence/judgments.json:
  {"as_of": "...", "tickers": {"ESEA": {"verdict": "PASS|WATCH|CAUTION|TRAP", "summary": "...",
     "points": [{"text": "...", "cite": ["CHUNK_ID", ...]}], "scenario_scores": {"SCENARIO": -2..2}}}}
Everything else (ticket, regime, model test, positions) is generated from data.
"""
from __future__ import annotations

import json
from datetime import date

from common.config import ROOT, path, scenarios
from common.log import get_logger
from portfolio_ledger.execution_manager import STATE_FILE, load_audit
from regime_engine.state_tracker import OUT as REGIME_FILE, exposure_vector

log = get_logger("report")
SHORT = {"ASIA_US_AI_DIVERGENCE": "AI div.", "HARD_TECH_BIO_AI": "Bio-AI", "PANDEMIC_2028": "Pandemic",
         "FINANCIAL_SYSTEM_SHOCK": "Fin. shock", "STRAIT_CHOKEPOINT_CRISIS": "Strait", "ASIA_KINETIC_WAR": "Asia war"}


def _pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def _co(r: dict) -> str:
    """'Company Name (NYSE)' for a row carrying name/exchange."""
    return f"{r.get('name', '')} ({r.get('exchange', '')})" if r.get("name") else ""


def _num(x, d=2):
    return "n/a" if x is None else f"{x:.{d}f}"


def scenario_scores(ticker: str, cluster: str | None, audit: dict) -> dict:
    """-2..+2 per scenario: Claude's override if given, else the cluster's exposure row."""
    return audit.get(ticker, {}).get("scenario_scores") or exposure_vector(cluster or "")


def build(as_of: str | None = None) -> str:
    as_of = as_of or date.today().isoformat()
    regime = json.loads(REGIME_FILE.read_text())
    ml = json.loads((path("ml_out") / "ml_candidates.json").read_text())
    st = json.loads(STATE_FILE.read_text())
    audit = load_audit()
    judg_path = ROOT / "data" / "evidence" / "judgments.json"
    judg = json.loads(judg_path.read_text()) if judg_path.exists() else {}
    L = [f"# Recommendations, {as_of}", "",
         "Research tool output. Not financial advice. "
         f"Prices: close of {ml['price_date']} ({ml['price_date_weekday']}).", ""]

    # ------------------------------------------------ Friday ticket
    L += ["## Friday Capitulation Execution Ticket", "",
          "Place limit orders during Friday's US session. PAPER rows are logged automatically and need no order.", "",
          "### Table 1: Sell / rollover (existing shares)", ""]
    sells = st["sell_or_rollover"]
    if sells:
        L += ["| Ticker | Company | Horizon | Mode | Entry | Last | P&L | Trigger |", "|---|---|---|---|---|---|---|---|"]
        for p in sells:
            L.append(f"| {p['ticker']} | {_co(p)} | {p['horizon_name']} | {p['mode']} | {p['entry_price']:.2f} | {p['last']:.2f} | "
                     f"{p['pnl_pct']:+.2f}% | {p['action']} |")
    else:
        L.append("No open position needs action.")
    L += ["", "### Table 2: New buy orders (1 share each)", ""]
    for h, v in ml["horizons"].items():
        rows = [t for t in st["new_buys"] if str(t["horizon"]) == h]
        if not rows:
            continue
        L += [f"**{v['name'].capitalize()} ({h} trading days): {st['badges'][h]['badge']}, expires {rows[0]['expiry']}**", "",
              "| # | Ticker | Company | Cluster | Conviction | Limit buy | GTC take-profit | GTC stop-loss | Audit |",
              "|---|---|---|---|---|---|---|---|---|"]
        for t in rows:
            L.append(f"| {t['rank']} | **{t['ticker']}** | {_co(t)} | {t['cluster']} | {t['conviction_pct']:.0f}% | ${t['limit']:.2f} | "
                     f"${t['tp']:.2f} | ${t['sl']:.2f} | {t['audit']} |")
        L.append("")
    L += ["", "Conviction = the model's probability that the take-profit is hit before the stop. "
          "Barriers: weekly +2.0/-2.5 ATR, monthly +/-3.5 ATR, quarterly +6.0/-5.0 ATR (ATR_14 on raw prices).", ""]
    real = [p for p in st["positions"] if p["mode"] == "MANUAL"]
    if real:
        L += ["### My live portfolio and exit radar", "",
              "| Ticker | Company | Horizon | Entry | Last | P&L | TP | SL | Days left | ML | Verdict |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for p in real:
            v = p["action"] + (f" (swap: {p['swap_candidate']})" if p.get("swap_candidate") else "")
            L.append(f"| {p['ticker']} | {_co(p)} | {p['horizon_name']} | {p['entry_price']:.2f} | {p['last']:.2f} | "
                     f"{p['pnl_pct']:+.2f}% | {p['tp']:.2f} | {p['sl']:.2f} | {p['days_left']} | "
                     f"{_pct(p['ml_prob'], 0)} | {v} |")
        L.append("")

    # ------------------------------------------------ bottom line
    if judg.get("bottom_line"):
        L += ["## Bottom line", ""] + [f"{i}. {b}" for i, b in enumerate(judg["bottom_line"], 1)] + [""]

    # ------------------------------------------------ regime
    L += ["## Macro regime (Module 0)", "",
          "| Scenario | State | P(state) | Stress Z | 21d change | High-vol prob | Weight 5d/21d/63d | Mode |",
          "|---|---|---|---|---|---|---|---|"]
    for k, s in regime["scenarios"].items():
        w = s["weights"]
        mode = "INVERTED (post-recovery)" if s["polarity"] < 0 else "normal"
        hv = "n/a" if s["markov_high_vol"] is None else f"{s['markov_high_vol']:.2f}"
        L.append(f"| {s['name']} | **{s['state']}** | {s['state_probs'][s['state']]:.2f} | {s['z']:+.2f} | "
                 f"{s['dz_21']:+.2f} | {hv} | {w['5']:.2f} / {w['21']:.2f} / {w['63']:.2f} | {mode} |")
    L += ["", f"Method: {regime['method']}. States are soft (probabilities), not hard thresholds.", ""]

    # ------------------------------------------------ model test
    L += ["## Is the ML signal real? (walk-forward, Friday closes)", "",
          "| Horizon | Badge | Base rate | Top-5 win rate | Lift | z | Profit factor | #1 only: win (z, PF) | AUC | "
          "Old label: lift (z) | Edge |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for h, v in ml["horizons"].items():
        m, o, b = v["metrics"], v["metrics_old_label"], st["badges"][h]
        L.append(f"| {v['name']} ({h}d) | {b['mode']} | {_pct(m['base_rate'])} | {_pct(m['topk_precision'])} | "
                 f"{m['lift'] * 100:+.1f} pts | {m['z_effective']:.2f} | {m['profit_factor_topk']} | "
                 f"{_pct(m['top1_precision'])} ({m['top1_z']:.2f}, {m['profit_factor_top1']}) | {m['auc']} | "
                 f"{o['lift'] * 100:+.1f} pts ({o['z_effective']:.2f}) | **{'YES' if m['edge'] else 'No'}** |")
    first = next(iter(ml["horizons"].values()))["metrics"]
    L += ["", f"Test window {first['oos_start']} to {first['oos_end']} ({first['oos_fridays']} Fridays). "
          "Edge is judged on the traded set (top 5 each Friday): win rate >= 55%, profit factor > 1.05, and lift "
          "significant (z >= 1.64, each Friday counted once). "
          "Old label = beat RSP over the horizon (previous model), same rows and features.", "",
          f"Caveat: {ml['caveat']}", ""]

    # ------------------------------------------------ picks + audit
    L += ["## Top picks and value-trap audit", ""]
    cands = {c["ticker"]: c for c in json.loads(sorted((ROOT / "data" / "screener").glob("candidates_*.json"))[-1]
                                                  .read_text())["candidates"]}
    names = list(scenarios()["scenarios"])
    from data_fetch.sec import company_names

    cos = company_names()
    L += ["| Horizon | Ticker | Company | Cluster | Prob | Scenario tilt | Fwd P/E | FCF yield | P/TBV | Audit | "
          + " | ".join(SHORT[n] for n in names) + " |", "|" + "---|" * (10 + len(names))]
    for h, v in ml["horizons"].items():
        for r in v["picks"]:
            c = cands.get(r["ticker"], {})
            sc = scenario_scores(r["ticker"], r["cluster"], audit)
            L.append(f"| {v['name']} | {r['ticker']} | {_co({'ticker': r['ticker'], **cos.get(r['ticker'], {})})} | {r['cluster']} | {_pct(r['prob'], 0)} | {r['scenario_tilt']:+.2f} | "
                     f"{_num(c.get('fwd_pe'))} | {_pct(c.get('fcf_yield'))} | {_num(c.get('ptbv'))} | "
                     f"{audit.get(r['ticker'], {}).get('verdict', 'NOT AUDITED')} | "
                     + " | ".join(f"{sc.get(n, 0):+d}" for n in names) + " |")
    L.append("")
    for t, j in judg.get("tickers", {}).items():
        co = cos.get(t, {})
        L += [f"### {t} ({co.get('name', '')}, {co.get('exchange', '')}): {j['verdict']}", "", j.get("summary", ""), ""]
        for pt in j.get("points", []):
            cite = " ".join(f"[{c}]" for c in pt.get("cite", []))
            L.append(f"- {pt['text']} {cite}".rstrip())
        L.append("")

    # ------------------------------------------------ calendar + method
    L += ["## Hold calendar", "", "| Horizon | Names | Entry day | Time barrier |", "|---|---|---|---|"]
    for h, v in ml["horizons"].items():
        rows = [t for t in st["new_buys"] if str(t["horizon"]) == h]
        if rows:
            L.append(f"| {v['name']} | {', '.join(t['ticker'] for t in rows)} | {rows[0]['entry_day']} | {rows[0]['expiry']} |")
    L += ["", "## Method and known gaps", ""] + [f"- {m}" for m in judg.get("method_notes", [])] + [""]
    out = ROOT / "reports" / f"recommendations_{as_of.replace('-', '_')}.md"
    out.write_text("\n".join(L))
    log.info("report -> %s", out)
    return str(out)

// Run in the built-in browser on an https://query1.finance.yahoo.com tab.
// Yahoo answers 429 to plain Python from this Mac, but a real browser works.
// Set window.__sp.priceSymbols = [...] first (screener candidates + RSP + macro symbols).
// Then window.__sp.px.payload(from, to) returns blocks for browser_fetch/extract.py:
//   <<<PRICES {"symbol":"ZIM"}>>>\ndate,open,high,low,close,adj_close,volume\n...\n<<<END>>>
// Macro symbols (see MACRO in data_fetch/prices.py): ^VIX, DX-Y.NYB, CL=F, ^TNX, 2YY=F.
window.__sp = window.__sp || {};
(async () => {
  const job = window.__sp.px = { status: 'running', done: 0, errors: [], data: {} };
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const p2 = Math.floor(Date.now() / 1000), p1 = p2 - 6 * 365 * 86400;
  const R = (v, d = 4) => v == null ? '' : +(+v).toPrecision(7);
  const one = async (s) => {
    const j = await (await fetch(`/v8/finance/chart/${encodeURIComponent(s)}?period1=${p1}&period2=${p2}&interval=1d&events=div,split`)).json();
    const r = j?.chart?.result?.[0]; if (!r?.timestamp) throw new Error(j?.chart?.error?.description || 'no data');
    const q = r.indicators.quote[0], adj = r.indicators.adjclose?.[0]?.adjclose || q.close;
    const off = (r.meta?.gmtoffset || 0);
    const rows = ['date,open,high,low,close,adj_close,volume'];
    r.timestamp.forEach((t, i) => {
      if (q.close[i] == null) return;
      const d = new Date((t + off) * 1000).toISOString().slice(0, 10);  // exchange-local trading date
      rows.push([d, R(q.open[i]), R(q.high[i]), R(q.low[i]), R(q.close[i]), R(adj[i]), q.volume[i] ?? ''].join(','));
    });
    return rows.join('\n');
  };
  for (const s of window.__sp.priceSymbols || []) {
    for (let a = 0; a < 3; a++) {
      try { job.data[s] = await one(s); break; }
      catch (e) { if (a === 2) job.errors.push(s + ':' + String(e).slice(0, 60)); await sleep(1500 * (a + 1)); }
    }
    job.done++; await sleep(300);
  }
  job.payload = (from = 0, to = 1e9) => Object.entries(job.data).slice(from, to)
    .map(([s, csv]) => `<<<PRICES ${JSON.stringify({ symbol: s })}>>>\n${csv}\n<<<END>>>`).join('\n');
  job.status = 'done';
})();
'started';

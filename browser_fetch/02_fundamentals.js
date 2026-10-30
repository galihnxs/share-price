// Run in the built-in browser on an https://query1.finance.yahoo.com tab.
// Set window.__sp.trackA = [...] and window.__sp.trackB = [...] first (tickers by screening track,
// from config/scenarios.yaml clusters). Produces window.__sp.fun.csv (USD millions).
// Pre-filter (documented in the report), market cap >= $300M for both tracks, then:
//   Track A (hard assets): operating cash flow > 0 and TTM FCF yield > 3%
//   Track B (bio/tech):    cash / total debt > 1.5 (or no debt); cash burners allowed, runway checked in Python
window.__sp = window.__sp || {};
(async () => {
  const job = window.__sp.fun = { status: 'starting', done: 0, kept: 0, errors: [], rows: [] };
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const crumb = await (await fetch('/v1/test/getcrumb')).text();
  const KEYS = { fcf: 'annualFreeCashFlow', ocf: 'annualOperatingCashFlow', tbv: 'annualTangibleBookValue',
                 debt: 'annualTotalDebt', eq: 'annualStockholdersEquity', sh: 'annualOrdinarySharesNumber', eps: 'annualDilutedEPS',
                 rev: 'annualTotalRevenue', rnd: 'annualResearchAndDevelopment' };
  const p2 = Math.floor(Date.now() / 1000), p1 = p2 - 6 * 365 * 86400;
  const M = v => v == null ? '' : Math.round(v / 1e5) / 10;          // -> USD millions, 1dp
  const R = (v, d = 3) => v == null ? '' : +(+v).toFixed(d);
  const header = ['ticker', 'track', 'price', 'mcap', 'fwd_pe', 'pe_ttm', 'fcf_ttm', 'ocf_ttm', 'cash', 'total_debt', 'ptb', 'currency', 'fy_end'];
  for (const k of Object.keys(KEYS)) for (let i = 1; i <= 4; i++) header.push(`${k}_y${i}`);
  job.header = header;
  job.status = 'running';
  const one = async (t, track) => {
    const q = await (await fetch(`/v10/finance/quoteSummary/${encodeURIComponent(t)}?modules=summaryDetail,defaultKeyStatistics,financialData,price&crumb=${encodeURIComponent(crumb)}`)).json();
    const r = q?.quoteSummary?.result?.[0]; if (!r) throw new Error('no quote');
    const mcap = r.summaryDetail?.marketCap?.raw ?? r.price?.marketCap?.raw;
    const ocf = r.financialData?.operatingCashflow?.raw, fcf = r.financialData?.freeCashflow?.raw;
    const cash = r.financialData?.totalCash?.raw, tdebt = r.financialData?.totalDebt?.raw;
    if (!(mcap >= 3e8)) return null;
    if (track === 'A' && (!(ocf > 0) || !(fcf / mcap > 0.03))) return null;
    if (track === 'B' && !(cash > 0 && (!tdebt || cash / tdebt > 1.5))) return null;
    const ts = await (await fetch(`/ws/fundamentals-timeseries/v1/finance/timeseries/${encodeURIComponent(t)}?symbol=${encodeURIComponent(t)}&type=${Object.values(KEYS).join(',')}&period1=${p1}&period2=${p2}&crumb=${encodeURIComponent(crumb)}`)).json();
    const by = {}; let fy = '';
    for (const x of ts?.timeseries?.result || []) {
      const k = x.meta.type[0]; const arr = (x[k] || []).filter(Boolean).sort((a, b) => a.asOfDate.localeCompare(b.asOfDate)).slice(-4);
      by[k] = arr; if (arr.length && arr.at(-1).asOfDate > fy) fy = arr.at(-1).asOfDate;
    }
    const row = [t, track, R(r.financialData?.currentPrice?.raw, 2), M(mcap), R(r.summaryDetail?.forwardPE?.raw ?? r.defaultKeyStatistics?.forwardPE?.raw, 2),
                 R(r.summaryDetail?.trailingPE?.raw, 2), M(fcf), M(ocf), M(cash), M(tdebt), R(r.defaultKeyStatistics?.priceToBook?.raw, 3),
                 r.financialData?.financialCurrency || r.price?.currency || '', fy];
    for (const [k, yk] of Object.entries(KEYS)) {
      const arr = by[yk] || []; const pad = Array(4 - arr.length).fill(null).concat(arr.map(a => a.reportedValue?.raw));
      for (const v of pad) row.push(k === 'eps' ? R(v, 2) : M(v));
    }
    return row;
  };
  const queue = [...(window.__sp.trackA || []).map(t => [t, 'A']), ...(window.__sp.trackB || []).map(t => [t, 'B'])];
  job.total = queue.length;
  const N = 3;
  await Promise.all(Array.from({ length: N }, async () => {
    while (queue.length) {
      const [t, track] = queue.shift();
      for (let a = 0; a < 3; a++) {
        try { const row = await one(t, track); if (row) { job.rows.push(row); job.kept++; } break; }
        catch (e) { if (a === 2) job.errors.push(t + ':' + String(e).slice(0, 40)); await sleep(1500 * (a + 1)); }
      }
      job.done++; await sleep(250);
    }
  }));
  job.csv = [job.header.join(',')].concat(job.rows.map(r => r.join(','))).join('\n');
  job.status = 'done';
})();
'started';

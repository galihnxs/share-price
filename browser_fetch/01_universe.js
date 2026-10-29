// Run in the built-in browser on an https://www.sec.gov tab (~20 min, ~1,000 page loads at ~7/s).
// Output: window.__sp.uni.csv  -> data/raw/universe_YYYY-MM-DD.csv
// Logic: exchange-listed tickers (SEC company_tickers_exchange.json) x companies registered
// under each target SIC code (EDGAR browse-by-SIC). SIC ranges mirror config/sectors.yaml.
window.__sp = window.__sp || {};
const SECT = {
 energy:[[1220,1241],[1310,1389],[2910,2999],[4610,4619],[4920,4925]],
 hard_assets:[[1000,1099],[1400,1499],[2400,2499],[2600,2679],[2800,2829],[2860,2899],[3210,3299],[3310,3399]],
 industrials:[[1500,1799],[3400,3558],[3560,3569],[3580,3599],[3600,3629],[3700,3799],[4011,4013],[4210,4231],[4500,4581],[5000,5099]],
 maritime_shipping:[[4400,4499]],
 old_economy:[[2000,2099],[2100,2199],[2200,2399],[2510,2599],[3140,3199],[5140,5199],[5300,5399],[5400,5499],[5500,5599],[7500,7549]],
 mature_healthcare:[[2833,2836],[3841,3851],[5120,5122],[8000,8099]]};
const sectorOf = s => { for (const [k,rs] of Object.entries(SECT)) for (const [a,b] of rs) if (s>=a && s<=b) return k; return null; };
const sleep = ms => new Promise(r=>setTimeout(r,ms));
const job = window.__sp.uni = {status:'starting', log:[], rows:[], done:0, total:0, errors:0};
(async () => {
 try {
  const tj = await (await fetch('/files/company_tickers_exchange.json')).json();
  const EX = new Set(['NYSE','Nasdaq','NYSE American','NYSE Arca','CBOE']);
  const byCik = new Map();
  for (const [cik,name,ticker,ex] of tj.data) { if (!EX.has(ex) || !ticker) continue; if (!byCik.has(cik)) byCik.set(cik, []); byCik.get(cik).push({name,ticker,ex}); }
  const html = await (await fetch('/search-filings/standard-industrial-classification-sic-code-list')).text();
  const doc = new DOMParser().parseFromString(html,'text/html');
  const codes = [...new Set([...doc.querySelectorAll('td')].map(td=>td.textContent.trim()).filter(t=>/^\d{4}$/.test(t)).map(Number))].filter(sectorOf);
  job.total = codes.length; job.status='crawling';
  for (const sic of codes) {
    for (let start=0; start<5000; start+=100) {
      await sleep(130);
      let txt; try { txt = await (await fetch(`/cgi-bin/browse-edgar?action=getcompany&SIC=${sic}&owner=include&match=&start=${start}&count=100&hidefilings=0`)).text(); } catch(e) { job.errors++; break; }
      const d = new DOMParser().parseFromString(txt,'text/html');
      const trs = [...d.querySelectorAll('table.tableFile2 tr')].slice(1);
      for (const tr of trs) { const cik = Number(tr.querySelector('td')?.textContent.trim()); const hit = byCik.get(cik);
        if (hit) for (const h of hit) job.rows.push([cik,h.ticker,h.name.replace(/,/g,' '),h.ex,sic,sectorOf(sic)]); }
      if (trs.length < 100) break;
    }
    job.done++;
  }
  // Clean: drop preferreds/units/warrants (tickers with '-' or 5+ chars ending W/U/R), one row per ticker.
  const seen = new Set();
  job.clean = job.rows.filter(r => { const t=r[1]; if (t.includes('-') || (t.length>=5 && /[WUR]$/.test(t)) || seen.has(t)) return false; seen.add(t); return true; });
  job.csv = ['ticker,cik,sic'].concat(job.clean.map(r=>[r[1],r[0],r[4]].join(','))).join('\n');
  job.status='done';
 } catch(e) { job.status='error: '+e; }
})();

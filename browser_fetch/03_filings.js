// Run in the built-in browser on an https://www.sec.gov tab.
// Defines window.__sp.filings.list(cik) and window.__sp.filings.text(url).
// Claude calls list() per company, then text() per filing; each text result is large,
// so it lands as a file in Claude's workspace and is copied to data/raw/filings/.
//
// Form mapping: US filers use 10-K / 10-Q / 8-K. Foreign private issuers (many shippers)
// file 20-F (annual) and 6-K (current reports) instead, so those are accepted as equivalents.
window.__sp = window.__sp || {};
window.__sp.filings = {
  LIMITS: { annual: 1, quarterly: 2, current: 4 },
  KIND: { '10-K': 'annual', '20-F': 'annual', '40-F': 'annual', '10-Q': 'quarterly', '8-K': 'current', '6-K': 'current' },

  async list(cik) {
    const pad = String(cik).padStart(10, '0');
    const j = await (await fetch(`https://data.sec.gov/submissions/CIK${pad}.json`)).json();
    const r = j.filings.recent, out = [], used = { annual: 0, quarterly: 0, current: 0 };
    const yearAgo = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
    for (let i = 0; i < r.form.length; i++) {
      const kind = this.KIND[r.form[i]]; if (!kind || used[kind] >= this.LIMITS[kind]) continue;
      if (kind === 'current' && r.filingDate[i] < yearAgo) continue;   // stale current reports add noise
      // 8-K/6-K: keep earnings (2.02), material agreements (1.01/1.02), debt (2.03/2.04), impairments (2.06).
      if (kind === 'current' && r.form[i] === '8-K' && r.items[i] && !/1\.01|1\.02|2\.02|2\.03|2\.04|2\.06/.test(r.items[i])) continue;
      used[kind]++;
      const acc = r.accessionNumber[i];
      out.push({ form: r.form[i], date: r.filingDate[i], period: r.reportDate[i], accession: acc, items: r.items[i] || '',
        url: `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${acc.replace(/-/g, '')}/${r.primaryDocument[i]}` });
    }
    return { name: j.name, sic: j.sic, tickers: j.tickers, filings: out };
  },

  // 8-K/6-K primary documents are often just a cover page; the substance is in Exhibit 99.x.
  async withExhibits(url) {
    const dir = url.slice(0, url.lastIndexOf('/') + 1);
    let text = await this.text(url);
    try {
      const idx = await (await fetch(dir + 'index.json')).json();
      const ex = idx.directory.item.map(x => x.name).filter(n => /ex(hibit)?[-_ ]?99/i.test(n) && /\.html?$/i.test(n)).slice(0, 3);
      for (const n of ex) { await new Promise(r => setTimeout(r, 150)); text += `\n\n[EXHIBIT ${n}]\n` + await this.text(dir + n); }
    } catch (e) { /* index missing: keep primary doc only */ }
    return text;
  },

  async text(url) {
    const html = await (await fetch(url)).text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    doc.querySelectorAll('script,style,head').forEach(e => e.remove());
    doc.querySelectorAll('[style*="display:none"],[style*="display: none"]').forEach(e => e.remove()); // iXBRL hidden facts
    for (const t of [...doc.querySelectorAll('table')].reverse()) {
      const rows = [...t.querySelectorAll('tr')].map(tr => [...tr.querySelectorAll('td,th')].map(c => c.textContent.replace(/\s+/g, ' ').trim()).filter(Boolean)).filter(r => r.length);
      const cells = rows.flat(); const numeric = cells.filter(c => /\d/.test(c)).length;
      const isData = rows.length >= 2 && cells.length >= 4 && numeric / cells.length >= 0.3;
      const rep = doc.createElement('div');
      // Layout tables (headings laid out as tables) become plain text; data tables are fenced.
      rep.textContent = isData ? `\n[TABLE]\n${rows.map(r => r.join(' | ')).join('\n')}\n[/TABLE]\n` : '\n' + rows.map(r => r.join(' ')).join('\n') + '\n';
      t.replaceWith(rep);
    }
    doc.querySelectorAll('p,div,br,li,h1,h2,h3,h4,h5,h6,tr').forEach(e => e.append('\n'));
    return doc.body.textContent.replace(/ /g, ' ').replace(/[ \t]+/g, ' ').replace(/\n\s*\n\s*\n+/g, '\n\n').trim();
  },
};
'filings helper ready';

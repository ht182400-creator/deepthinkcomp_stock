const { JSDOM } = require('jsdom');
const fs = require('fs');
const INDEX = fs.readFileSync('static/index.html', 'utf8');
const dom = new JSDOM(INDEX, { url: 'http://localhost:8899/', runScripts: 'outside-only', pretendToBeVisual: true });
const { window } = dom;
globalThis.window = window;
globalThis.document = window.document;
globalThis.echarts = { init: () => ({ setOption() {}, dispose() {}, isDisposed() { return false; } }) };
const full = {
  quote: { name: '呈和科技', code: 'sh688025', price: 58.47, change: 2.57, change_pct: 4.60, pre_close: 55.90, open: 56.16, high: 58.58, low: 56.01, volume: 5310000, amount: 3.06e8, turnover_pct: 4.60, volume_ratio: 0.80, outer: 3150000, inner: 2160000, total_mv: 151.8, float_mv: 151.8, pe_dyn: 51.55, pb: 10.20, eps: 1.05, source: 'tencent',
    order_book: { bids: [{price:58.46,vol:50}], asks: [{price:58.48,vol:50}] },
    minute: [{t:'0930',price:55.0,vol:10000}]
  },
  fund: { series: [] }, stats: {pct_60d:-41.81}, finance: {revenue:2.49e8,eps:0.49,report_type:'2026一季报'},
  profit_trend: [], holders: [], company: {}, forecast: {org_num:7}, margin: [], lhb: [], announcements: [], day5_funds: [], sentiment: {}, north: {}
};
globalThis.fetch = async (url) => {
  if (url.includes('/api/stock/full')) return { ok: true, status: 200, json: async () => full };
  if (url.includes('/api/stock/announcement')) return { ok: true, status: 200, json: async () => ({ title: 't', content: 'c' }) };
  throw new Error('fail: ' + url);
};
(async () => {
  const stock = await import('file:///E:/AI_Studio/deepthinkcomp_stock/static/js/modules/stock.js');
  stock.render('sh688025');
  await new Promise(r => setTimeout(r, 200));
  const mid = document.querySelector('.minute-mid-bottom');
  const mbl = document.querySelector('#midBottomLeft');
  const mbr = document.querySelector('#midBottomRight');
  console.log('mid exists:', !!mid);
  if (mid) {
    console.log('mid children count:', mid.children.length);
    console.log('mid children ids:', Array.from(mid.children).map(c => c.id));
    console.log('mid children classes:', Array.from(mid.children).map(c => c.className));
    console.log('mid innerHTML length:', mid.innerHTML.length);
    console.log('mid innerHTML first 500 chars:');
    console.log(mid.innerHTML.substring(0, 500));
  }
  console.log('mbl exists:', !!mbl, 'class:', mbl?.className);
  console.log('mbr exists:', !!mbr, 'class:', mbr?.className);
})();
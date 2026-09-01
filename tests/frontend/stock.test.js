// -*- coding: utf-8 -*-
// DeepThinkCompStock · 个股详情页（stock.js）DOM 级测试（T-S 系列 v3）
// stock.js 是 ES Module，渲染 deepthinkSingle 完整 DOM 并由 single-app.js 驱动。
// 数据源: /api/quote（聚合形状 {quote, minute, fund, ...}，与 deepthinkSingle 契约一致）
// 运行: node --test --test-force-exit tests/frontend/stock.test.js
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..', '..');
const INDEX = fs.readFileSync(path.join(ROOT, 'static', 'index.html'), 'utf8');
const STOCK_JS = path.join(ROOT, 'static', 'js', 'modules', 'stock.js');
const SINGLE_APP_JS = path.join(ROOT, 'static', 'js', 'modules', 'single-app.js');
const SINGLE_INDICATORS_JS = path.join(ROOT, 'static', 'js', 'modules', 'single-indicators.js');
const STOCK_JS_ABS = 'file://' + STOCK_JS.replace(/\\/g, '/');

// ---------------- /api/quote mock（deepthinkSingle 兼容聚合形状） ----------------
function makeFull(overrides = {}) {
  const base = {
    quote: {
      name: '贵州茅台', code: '600519', price: 1341.99, change: 13.3, change_pct: 1.2,
      pre_close: 1328.69, open: 1355.0, high: 1356.0, low: 1338.14,
      volume: 3500000, amount: 4.69e9, turnover_pct: 0.24, volume_ratio: 0.82,
      outer: 1800000, inner: 1700000, total_mv: 16860, float_mv: 16860,
      pe_dyn: 20.6, pb: 8.1, eps: 65.15, bvps: 200.9, net_asset: 200.9,
      source: 'tencent', total_shares: '12.5亿', float_shares: '12.5亿',
      time: '18:00:00',
      order_book: {
        bids: [{price: 1341.98, vol: 100}, {price: 1341.97, vol: 200}, {price: 1341.96, vol: 300}, {price: 1341.95, vol: 400}, {price: 1341.94, vol: 500}],
        asks: [{price: 1342.00, vol: 100}, {price: 1342.01, vol: 200}, {price: 1342.02, vol: 300}, {price: 1342.03, vol: 400}, {price: 1342.04, vol: 500}],
      },
    },
    minute: [
      { t: '0930', price: 1355.0, avg: 1355.0, open: 1355.0, vol: 22700, amount: 3.07e6 },
      { t: '0931', price: 1353.5, avg: 1354.25, open: 1355.0, vol: 41000, amount: 5.5e6 },
      { t: '0932', price: 1356.2, avg: 1354.9, open: 1353.5, vol: 66000, amount: 8.9e6 },
    ],
    fund: { series: [
      { t: '0930', super_big: 500, big: 300, mid: -100, small: -200 },
      { t: '0931', super_big: -200, big: 150, mid: 80, small: -50 },
    ]},
    stats: { pct_60d: 4.01, pct_360d: -6.01, pct_ytd: -5.89, hi_1y: 1568.0, lo_1y: 1151.01 },
    finance: { revenue: 9.2278e10, yoy_revenue: 1.30, net_profit: 4.4517e10, yoy_profit: -1.95, eps: 35.57, roe: 16.75, report_type: '2026中报' },
    profit_trend: [
      { year: '2025', net_profit: 8.232e10, yoy: -4.53 },
      { year: '2024', net_profit: 8.6228e10, yoy: 15.38 },
    ],
    holders: [{ date: '2026-06-30', total: 296404, change_pct: 21.90 }],
    company: { org_name: '贵州茅台酒股份有限公司', industry: '食品饮料', market: '上交所' },
    forecast: { org_num: 44, buy_num: 37, add_num: 7, eps_years: [{ year: 2026, mark: 'E', eps: 68.72 }] },
    margin: [{ date: '2026-08-14', rzye: 1.77e10, rqye: 1.23e8, rzrqye: 1.78e10, rzyezb: 1.05 }],
    lhb: [{ date: '2026-05-13', amount: 4.36e8, change_pct: 19.99 }],
    announcements: [{ date: '2026-08-15', title: '贵州茅台:半年度业绩说明会公告', code: 'AN202608141827994407' }],
    day5_funds: [{ date: '2026-08-14', main_net: 3.5e8 }, { date: '2026-08-13', main_net: -1.2e8 }],
    sentiment: { days: 240, bull_pct: 42.92, bear_pct: 57.08 },
    north: { latest_date: '2026-08-15', holdings: 8500.55, hold_value: 1.14e11, ratio: 6.76, change_pct: -0.23, rows: [] },
    errors: [],
    ...overrides,
  };
  return base;
}

// ---------------- setup：jsdom + echarts mock + fetch mock + 加载 single-app ----------------
let dom;
let stockMod;

function makeFetch(overrides = {}) {
  const full = makeFull(overrides);
  const kline = { kline: [{ t: '2026-08-14', open: 1328.0, close: 1341.99, high: 1356.0, low: 1325.0, vol: 30000 }] };
  return async (url) => {
    if (typeof url === 'string' && url.includes('/api/quote')) {
      return { ok: true, status: 200, json: async () => full };
    }
    if (typeof url === 'string' && url.includes('/api/kline')) {
      return { ok: true, status: 200, json: async () => kline };
    }
    if (typeof url === 'string' && url.includes('/api/minute')) {
      return { ok: true, status: 200, json: async () => ({ code: '600519', date: '2026-08-14', minute: full.minute }) };
    }
    if (typeof url === 'string' && url.includes('/api/watchlist')) {
      return { ok: true, status: 200, json: async () => [
        { code: 'sh600519', name: '贵州茅台', in_watchlist: true },
        { code: 'sh688025', name: '呈和科技', in_watchlist: true },
      ] };
    }
    if (typeof url === 'string' && url.includes('/api/many')) {
      return { ok: true, status: 200, json: async () => ({ items: [full.quote] }) };
    }
    if (typeof url === 'string' && url.includes('/api/search')) {
      return { ok: true, status: 200, json: async () => [{ code: '600519', name: '贵州茅台' }] };
    }
    if (typeof url === 'string' && url.includes('/api/announcement')) {
      return { ok: true, status: 200, json: async () => ({ title: 't', content: 'c', date: '2026-08-15' }) };
    }
    if (typeof url === 'string' && url.includes('/api/analysis')) {
      return { ok: true, status: 200, json: async () => [] };
    }
    throw new Error('TEST fetch 未 mock: ' + url);
  };
}

function setup() {
  dom = new JSDOM(INDEX, { url: 'http://localhost:8899/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  globalThis.window = window;
  globalThis.document = window.document;
  globalThis.location = window.location;
  // echarts mock（single-app 需要 resize/clear）—— 必须挂 window，因为 single-app 是 window.eval 执行
  const echartsMock = {
    init: () => ({ setOption() {}, dispose() {}, isDisposed() { return false; }, resize() {}, clear() {} }),
  };
  window.echarts = echartsMock;
  globalThis.echarts = echartsMock;
  globalThis.fetch = makeFetch();
  window.fetch = globalThis.fetch;   // single-app 用裸 fetch()，需挂 window
  globalThis.setInterval = () => 0;
  globalThis.clearInterval = () => {};
  // 加载 single-indicators.js（window.DTIndicators）+ single-app.js（window.__SINGLE_APP__）
  try {
    const indSrc = fs.readFileSync(SINGLE_INDICATORS_JS, 'utf8');
    window.eval(indSrc);
    const appSrc = fs.readFileSync(SINGLE_APP_JS, 'utf8');
    window.eval(appSrc);
  } catch (e) {
    console.warn('[setup] single-app 加载失败:', e.message);
  }
  return window;
}

async function getStock() {
  if (!stockMod) stockMod = await import(STOCK_JS_ABS);
  return stockMod;
}

const pane = () => document.querySelector('#pane-stock');

// ============ T-S 系列 ============
test('T-S1: render 生成 deepthinkSingle 完整 DOM（顶部栏/分钟视图/K线视图/modal/右键菜单）', async () => {
  setup();
  const m = await getStock();
  await m.loadAll('sh600519');
  await new Promise(r => setTimeout(r, 50));
  const p = pane();
  assert.ok(p, '#pane-stock 存在');
  assert.ok(p.querySelector('.topbar'), '顶部状态栏');
  assert.ok(p.querySelector('#stName'), '股票名');
  assert.ok(p.querySelector('#minuteView'), '分钟视图');
  assert.ok(p.querySelector('#klineView'), 'K线视图');
  assert.ok(p.querySelector('.minute-row'), '三列布局');
  assert.ok(p.querySelector('.minute-left'), '左列');
  assert.ok(p.querySelector('.minute-mid'), '中列');
  assert.ok(p.querySelector('.minute-right'), '右列');
  assert.ok(p.querySelector('#orderBook'), '盘口');
  assert.ok(p.querySelector('#minuteDetail'), '逐笔成交');
  assert.ok(p.querySelector('#marketPanel'), '市场综合（中列/右列）');
  assert.ok(p.querySelector('#marketPanelRight'), '市场综合右列');
  dom.window.close();
});

test('T-S2: loadAll → 头部填充 + 盘口 ob-stats 8 行 + 市场综合 section', async () => {
  const w = setup();
  const m = await getStock();
  await m.loadAll('sh600519');
  await new Promise(r => setTimeout(r, 80));
  // 头部
  assert.equal(document.querySelector('#stName')?.textContent, '贵州茅台');
  assert.equal(document.querySelector('#stPrice')?.textContent, '1341.99');
  assert.ok(document.querySelector('#stChg')?.classList.contains('up'), '涨 → up 类');
  // 盘口大字现价 + 8 行 ob-stats
  const ob = document.querySelector('#orderBook');
  assert.ok(ob && ob.textContent.includes('卖5'), '盘口卖5档');
  assert.ok(ob && ob.textContent.includes('买1'), '盘口买1档');
  const obStats = document.querySelectorAll('#orderBook .ob-stat');
  assert.ok(obStats.length >= 8, `盘口 .ob-stats ≥ 8 行，实际 ${obStats.length}`);
  const obText = ob?.textContent || '';
  ['现价', '今开', '涨跌', '最高', '涨幅', '最低', '总手', '量比', '外盘', '内盘', '换手', '股本', '净资', '流通', '收益', 'PE'].forEach(lbl => {
    assert.ok(obText.includes(lbl), `盘口含「${lbl}」`);
  });
  // 逐笔成交
  assert.ok(document.querySelector('#minuteDetail')?.textContent.includes('时间'), '逐笔表头');
  dom.window.close();
});

test('T-S3: 完整功能 DOM — 搜索/自选/复盘/资金流/副图配置/历史分时 modal', async () => {
  const w = setup();
  const m = await getStock();
  await m.loadAll('sh600519');
  await new Promise(r => setTimeout(r, 50));
  const p = pane();
  // 顶部控件
  assert.ok(p.querySelector('#watchInput'), '自选/搜索输入');
  assert.ok(p.querySelector('#searchInput'), '搜索框');
  assert.ok(p.querySelector('#addBtn'), '自选加');
  assert.ok(p.querySelector('#delBtn'), '自选减');
  assert.ok(p.querySelector('#refreshBtn'), '刷新');
  assert.ok(p.querySelector('#klineBtn'), 'K线按钮');
  assert.ok(p.querySelector('#watchlistBtn'), '自选按钮');
  assert.ok(p.querySelector('#analysisBtn'), '复盘按钮');
  // 全部 modal
  ['histModal', 'annModal', 'fundFlowModal', 'klineSubConfigModal', 'subConfigModal', 'analysisModal'].forEach(id => {
    assert.ok(p.querySelector('#' + id), `modal #${id} 存在`);
  });
  // 右键菜单
  assert.ok(p.querySelector('#contextMenu'), '右键菜单');
  assert.ok(p.querySelector('#ctxConfigSub'), '右键-副图配置');
  assert.ok(p.querySelector('#ctxExportCsv'), '右键-导出CSV');
  dom.window.close();
});

test('T-S4: K线视图 — 7 周期按钮 + 返回分时 + 历史分时 modal', async () => {
  const w = setup();
  const m = await getStock();
  await m.loadAll('sh600519');
  await new Promise(r => setTimeout(r, 50));
  const p = pane();
  // 7 周期按钮
  const periods = p.querySelectorAll('.kperiod');
  assert.ok(periods.length >= 7, `K线周期按钮 ≥ 7，实际 ${periods.length}`);
  // 默认日K active
  const dayBtn = [...periods].find(b => b.dataset.p === 'day');
  assert.ok(dayBtn?.classList.contains('active'), '日K默认 active');
  // 返回分时按钮
  assert.ok(p.querySelector('#backBtn'), '返回分时按钮');
  // 市场综合（K线视图）
  assert.ok(p.querySelector('#klineMarketPanel'), 'K线市场综合面板');
  // K线主图容器
  assert.ok(p.querySelector('#ch4'), 'K线主图容器');
  dom.window.close();
});

test('T-DIAG-1: 市场综合 section 完整性（中列+右列 13 个）', async () => {
  const w = setup();
  const m = await getStock();
  await m.loadAll('sh600519');
  await new Promise(r => setTimeout(r, 60));
  const mp = document.querySelector('#marketPanel');
  const mpr = document.querySelector('#marketPanelRight');
  const mpText = (mp?.textContent || '') + (mpr?.textContent || '');
  ['行情', '估值', '财务', '净利', '多空', '融资融券', '股东户数', '龙虎榜', '公司', '盈利预测', '公告', '北向'].forEach(k => {
    assert.ok(mpText.includes(k), `市场综合含「${k}」`);
  });
  dom.window.close();
});

test('T-DIAG-2: 头部涨跌颜色（A股红涨绿跌）', async () => {
  setup();
  const m = await getStock();
  await m.loadAll('sh600519');
  await new Promise(r => setTimeout(r, 60));
  assert.ok(document.querySelector('#stChg').classList.contains('up'), '涨红 up');
  // 盘口卖档红色 ask、买档绿色 bid
  assert.ok(document.querySelector('.ob-price.ask'), '卖价 ask 类');
  assert.ok(document.querySelector('.ob-price.bid'), '买价 bid 类');
  dom.window.close();
});

test('语法: node --check stock.js / single-app.js / single-template.js', () => {
  const { execSync } = require('child_process');
  ['stock.js', 'single-app.js', 'single-template.js'].forEach(f => {
    assert.doesNotThrow(() => execSync(`node --check "${path.join(ROOT, 'static', 'js', 'modules', f)}"`, { stdio: 'pipe' }));
  });
});

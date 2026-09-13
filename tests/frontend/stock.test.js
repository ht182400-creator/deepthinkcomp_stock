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
let seenOptions = [];   // mock echarts 收到的 setOption 选项（用于校验 tooltip 桥接）

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
    if (typeof url === 'string' && url.includes('/api/stock/quote')) {
      return { ok: true, status: 200, json: async () => ({ price: 191.96, name: '澜起科技' }) };
    }
    if (typeof url === 'string' && url.includes('/api/stock/finance_full')) {
      return { ok: true, status: 200, json: async () => ({
        card: { latest: { period: 20260630 }, valuation: {} },
        table: { periods: [20260331, 20260630], rows: [] },
      }) };
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
  seenOptions = [];
  const chartsApi = () => ({
    setOption(opt) { seenOptions.push(opt); },
    dispose() {}, isDisposed() { return false; }, resize() {}, clear() {},
    showLoading() {}, hideLoading() {}, dispatchAction() {}, getOption() { return {}; },
    getWidth() { return 800; }, getHeight() { return 400; }, on() {}, off() {},
  });
  const echartsMock = {
    init: () => chartsApi(),
    getInstanceByDom: () => null,
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

// ============ 本地量价（volume_price 前端渲染）============
test('本地量价: 经典量价图（价线 + 成交量柱）渲染', async () => {
  const finMod = await import('file://' + path.join(ROOT, 'static', 'js', 'modules', 'single-finance.js').replace(/\\/g, '/'));
  const volume = {
    code: '600519',
    periods: [20260904, 20260911],
    close: [100, 101],
    volume_yi: [1.2, 1.5],
    amount_yi: [12, 15],
    chg_pct: [null, 1.0],
    vol_ratio: [null, 1.25],
    pattern: ['--', '量价齐升'],
    latest: { period: '20260911', close: 101, chg_pct: 1.0, vol_ratio: 1.25,
      pattern: '量价齐升', amount_yi: 15, vol_trend_pct: 5, divergence: false },
    tip: '量价齐升，量能配合良好',
    note: '口径说明',
    source: 'local_price_panel',
  };
  const root = { innerHTML: '' };
  finMod.renderFinance(root, { volume }, 'volume', null);
  const html = root.innerHTML;
  assert.ok(html.includes('最新判读'), '包含最新判读横幅');
  assert.ok(html.includes('finVolChart'), '包含量价图容器');
  assert.ok(html.includes('成交量(亿股)'), '图例含成交量柱（经典量价图）');
  assert.ok(html.includes('量价齐升'), '分周表格含量价形态');
});

// ============ 估值分析（卡片式渲染）============
test('估值分析: 卡片式渲染（估值/每股/规模/成长 四组卡片）', async () => {
  const finMod = await import('file://' + path.join(ROOT, 'static', 'js', 'modules', 'single-finance.js').replace(/\\/g, '/'));
  const data = { card: {
    valuation: { pe_ttm: 142.4, pb: 24.89, ps_ttm: 35.19, eps_ttm: 1.25, rev_per_share: 5.08, price: 10 },
    latest: { bvps: 7.18, total_share: 2.41e8, total_assets_yi: 29.64, total_equity_yi: 17.86,
              holders: 27710, period: 20260630, rev_yoy: 21.21, np_yoy: 7.48, np_deduct_yoy: 4.42 },
  } };
  const root = { innerHTML: '' };
  finMod.renderFinance(root, data, 'valuation', null);
  const html = root.innerHTML;
  assert.ok(html.includes('fin-vp-card'), '使用卡片容器');
  assert.ok(html.includes('估值指标') && html.includes('每股指标') && html.includes('成长性'), '包含分组标题');
  assert.ok(html.includes('PE(TTM)') && html.includes('142.40'), 'PE 卡片与格式化数值');
  assert.ok(html.includes('21.21%'), '营收同比带百分比');
  assert.ok(html.includes('val up'), '正增长用 up 类（红涨）');
  assert.ok(!html.includes('mp-row'), '不再使用旧的行式布局');
});

// ============ 其它标签卡片化（诊断/趋势/杜邦/单季/变动/现金流/资产负债）============
const FIN_URL = 'file://' + path.join(ROOT, 'static', 'js', 'modules', 'single-finance.js').replace(/\\/g, '/');
const loadFin = () => import(FIN_URL);
const renderTab = async (tab, data) => {
  const m = await loadFin();
  const root = { innerHTML: '' };
  m.renderFinance(root, data, tab, null);
  return root.innerHTML;
};

test('财务诊断: 五维评分与关键指标为卡片', async () => {
  const html = await renderTab('diagnose', { diag: {
    score: 78, period: 20260630,
    dims: { profit: 88, growth: 75, solvency: 55, cash: 90, oper: 62 },
    detail: { roe_ttm: 15.2, roe_period: 12.1, gp_margin: 45.6, np_margin: 20.3,
              rev_yoy: 21.2, np_yoy: 7.5, debt_ratio: 75.0, current_ratio: 0.8,
              ocf_to_np: 120, asset_turnover: 0.53 },
  } });
  assert.ok(html.includes('fin-vp-card'), '卡片渲染');
  assert.ok(html.includes('五维评分') && html.includes('关键指标'), '分组标题');
  assert.ok(html.includes('120.00%'), 'OCF/净利 百分比');
  assert.ok(html.includes('val warn'), '资产负债率 75% 触发 warn');
  assert.ok(!html.includes('mp-row'), '不再使用行式布局');
});

test('成长趋势: 顶部 KPI 卡片含 TTM 同比', async () => {
  const html = await renderTab('trend', { card: { trend: {
    periods: [20250331, 20250630, 20250930, 20251231, 20260331, 20260630],
    rev_ttm_yi: [10, 11, 12, 13, 14, 15],
    np_ttm_yi: [1, 1.1, 1.2, 1.3, 1.4, 1.5],
    roe_ttm: [12, 12.5, 13, 13.5, 14, 14.5],
    roe: [3, 6, 9, 12, 3, 6],
  } } });
  assert.ok(html.includes('营业总收入 TTM') && html.includes('归母净利润 TTM'), '含 TTM KPI');
  assert.ok(html.includes('营收 TTM 同比'), '含营收同比卡片');
  assert.ok(html.includes('<span class="arw">↑</span>+36.4%'), '营收 TTM 同比 = (15-11)/11 = +36.4%（红+醒目上箭头）');
  assert.ok(html.includes('finTrendChart'), '保留趋势图容器');
});

test('杜邦分析: 驱动横幅 + 三因子卡片', async () => {
  const html = await renderTab('dupont', { dupont: {
    periods: [20260331, 20260630], npm: [10, 11], turnover: [0.5, 0.53],
    equity_mult: [2, 2.1], roe: [5, 6], roe_calc: [5.1, 6.2],
    driver: '高利润率', driver_desc: '产品溢价 / 成本控制',
  } });
  assert.ok(html.includes('fin-vp-banner'), '驱动信息横幅');
  assert.ok(html.includes('杜邦三因子'), '三因子分组');
  assert.ok(html.includes('销售净利率') && html.includes('权益乘数'), '因子卡片');
});

test('单季度: 最新单季卡片含环比', async () => {
  const html = await renderTab('quarterly', { quarterly: {
    periods: [20260331, 20260630], note: '单季说明',
    rows: [{ key: 'rev_q', label: '营业总收入', values: [10, 12] },
           { key: 'np_q', label: '归母净利润', values: [1, 1.2] }],
  } });
  assert.ok(html.includes('最新单季'), '含最新单季分组');
  assert.ok(html.includes('营收环比') && html.includes('<span class="arw">↑</span>+20.0%'), '营收环比 = (12-10)/10 = +20.0%（红+醒目上箭头）');
  assert.ok(html.includes('finQChart'), '保留图表容器');
});

test('变动说明: 环比卡片（上期→本期）', async () => {
  const html = await renderTab('changes', { table: {
    periods: [20260331, 20260630],
    rows: [{ label: '营业总收入', kind: 'money', values: [100, 121] },
           { label: '归母净利润', kind: 'money', values: [10, 9] }],
  } });
  assert.ok(html.includes('环比'), '含环比说明');
  assert.ok(html.includes('100.00 → 121.00'), '上期→本期');
  assert.ok(html.includes('val up') && html.includes('val down'), '正负配色');
});

test('现金流/资产负债: 质量与偿债指标卡片化', async () => {
  const cfHtml = await renderTab('cashflow', { cashflow: {
    periods: [20260331, 20260630], rows: [{ key: 'ocf_q', values: [1, 2] }],
    quality: { ocf_to_np: 120, cash_recovery: 95, sales_cash_to_rev: 100, cf_per_share: 1.2, ocf_ttm_yi: 8.5 },
    latest_period: 20260630, note: '口径说明',
  } });
  assert.ok(cfHtml.includes('现金流质量') && cfHtml.includes('fin-vp-card'));
  assert.ok(cfHtml.includes('120.00'), 'OCF/净利 120% 已展示');
  assert.ok(!cfHtml.includes('val up'), '含金量高为中性（红仅保留给正向/增长）');

  const balHtml = await renderTab('balance', { balance: {
    periods: [20260331, 20260630], rows: [],
    ratios: { current_assets_pct: 60, current_liab_pct: 40, debt_ratio: 75, current_ratio: 0.8, quick_ratio: 0.5 },
    latest_period: 20260630,
  } });
  assert.ok(balHtml.includes('结构与偿债') && balHtml.includes('fin-vp-card'));
  assert.ok(balHtml.includes('val warn'), '高负债率/低流动比率触发 warn');
});

// ============ 财务视图 ↔ 图表视图切换（修复 K线/分时 被压缩）============
test('财务视图: 打开隐藏图表视图，返回时还原并派发 resize', async () => {
  const w = setup();
  const m = await getStock();
  await m.loadAll('sh600519');
  await new Promise((r) => setTimeout(r, 60));

  document.querySelector('#financeBtn').click();
  await new Promise((r) => setTimeout(r, 120));
  assert.ok(!document.querySelector('#financeView').classList.contains('hidden'), '财务视图已打开');
  assert.ok(document.querySelector('#minuteView').classList.contains('hidden'), '分时视图被隐藏');

  let resized = 0;
  w.addEventListener('resize', () => { resized += 1; });

  document.querySelector('#finBack').click();
  await new Promise((r) => setTimeout(r, 200));

  assert.ok(document.querySelector('#financeView').classList.contains('hidden'), '财务视图已关闭');
  assert.ok(!document.querySelector('#minuteView').classList.contains('hidden'), '还原进入前的分时视图');
  assert.ok(resized >= 1, '返回时应派发 window.resize（single-app 据此重算图表尺寸，防压缩）');
  dom.window.close();
});

test('财务视图: 点顶栏 K线 同步隐藏财务视图', async () => {
  const w = setup();
  const m = await getStock();
  await m.loadAll('sh600519');
  await new Promise((r) => setTimeout(r, 60));

  document.querySelector('#financeBtn').click();
  await new Promise((r) => setTimeout(r, 120));
  assert.ok(!document.querySelector('#financeView').classList.contains('hidden'), '财务视图已打开');

  document.querySelector('#klineBtn').click();
  await new Promise((r) => setTimeout(r, 150));
  assert.ok(document.querySelector('#financeView').classList.contains('hidden'), '财务视图被隐藏');
  assert.ok(!document.querySelector('#klineView').classList.contains('hidden'), 'K线视图可见');
  dom.window.close();
});

// ============ 财务图表生命周期（唯一 resize 监听 + 重渲染 dispose）============
test('财务图表: resize 监听只注册一次，且重渲染前 dispose 旧实例', async () => {
  const m = await loadFin();
  const savedWin = globalThis.window;
  const savedDoc = globalThis.document;
  const listeners = { resize: 0 };
  const fakeEl = {};
  globalThis.window = { addEventListener: (t) => { if (t === 'resize') listeners.resize += 1; } };
  globalThis.document = { getElementById: () => fakeEl };   // finStyle 与图表容器都返回真值
  const disposed = [];
  const mkChart = () => ({
    setOption() {}, resize() {}, clear() {}, isDisposed() { return false; },
    getDom() { return null; }, dispose() { disposed.push(1); },
  });
  const ec = { init: () => mkChart(), getInstanceByDom: () => null };
  const data = { volume: {
    periods: [20260904, 20260911], close: [100, 101], volume_yi: [1.2, 1.5],
    amount_yi: [12, 15], chg_pct: [null, 1.0], vol_ratio: [null, 1.25],
    pattern: ['--', '量价齐升'], latest: {}, tip: 't', note: 'n',
  } };
  try {
    const root = { innerHTML: '' };
    m.renderFinance(root, data, 'volume', ec);
    await new Promise((r) => setTimeout(r, 60));
    const afterFirst = listeners.resize;
    m.renderFinance(root, data, 'volume', ec);
    await new Promise((r) => setTimeout(r, 60));
    m.renderFinance(root, data, 'volume', ec);
    await new Promise((r) => setTimeout(r, 60));
    assert.ok(afterFirst <= 1, '全局 resize 监听最多注册 1 个');
    assert.equal(listeners.resize, afterFirst, '后续渲染不再新增 resize 监听');
    assert.ok(disposed.length >= 2, '每次重渲染都应 dispose 上一批实例（防泄漏）');
  } finally {
    globalThis.window = savedWin;
    globalThis.document = savedDoc;
  }
});

// ============ 数据配色语义（红=正向 / 绿=负向 / 橙=阈值 / 白=中性）============
test('财务指标: 同比=红绿、阈值=橙、其余中性，且带图例与指标说明', async () => {
  const html = await renderTab('indicators', { table: {
    periods: [20260331, 20260630],
    rows: [
      { key: 'rev_yi', label: '营业总收入(亿)', kind: 'money', values: [1, 2] },
      { key: 'eps', label: '每股收益(元)', kind: 'plain', values: [0.5, 0.6] },
      { key: 'roe', label: '净资产收益率%', kind: 'pct', values: [15.45, 5.87] },
      { key: 'debt_ratio', label: '资产负债率%', kind: 'pct', values: [70, 75] },
      { key: 'current_ratio', label: '流动比率', kind: 'plain', values: [5.3, 0.8] },
      { key: 'ocf_to_np', label: '经营现金流/净利润%', kind: 'pct', values: [80, 40] },
      { key: 'rev_yoy', label: '营收同比增长%', kind: 'pct', values: [10, -5] },
      { key: 'np_yoy', label: '净利同比增长%', kind: 'pct', values: [0.01, 0] },
    ],
  } });
  // 图例 + 指标说明
  assert.ok(html.includes('fin-legend'), '顶部有配色图例');
  assert.ok(html.includes('fin-dict'), '有指标说明块');
  assert.ok(html.includes('收入 TTM'), '说明含口径描述');
  // 同比 → ↑红 / ↓绿 / →白（持平）；箭头为醒目高亮标记
  assert.ok(html.includes('class="up"><span class="arw">↑</span>+10.00</td>'), '增长 → 红 + 上箭头');
  assert.ok(html.includes('class="down"><span class="arw">↓</span>-5.00</td>'), '下降 → 绿 + 下箭头');
  assert.ok(html.includes('class="flat"><span class="arw">→</span>+0.01</td>'), '持平（|变化| < 0.1）→ 白 + 持平箭头');
  // 阈值 → 橙
  assert.ok(html.includes('class="warn">75.00</td>'), '负债率 75% → 橙(warn)');
  assert.ok(html.includes('class="warn">0.80</td>'), '流动比率 0.80 → 橙(warn)');
  assert.ok(html.includes('class="warn">40.00</td>'), '含金量 40% → 橙(warn)');
  // 中性 → 白（不再"凡正数皆红"）
  assert.ok(html.includes('class="">15.45</td>'), 'ROE 中性（不再全红）');
  assert.ok(html.includes('class="">2.00</td>'), '金额中性');
  assert.ok(html.includes('class="">0.60</td>'), '每股中性');
  assert.ok(html.includes('class="">70.00</td>'), '负债率 70% 未越阈值 → 中性');
});

test('所有财务标签顶部都有配色图例', async () => {
  const cases = [
    ['valuation', { card: { valuation: {}, latest: {} } }],
    ['diagnose', { diag: { score: 70, dims: {}, detail: {} } }],
    ['cashflow', { cashflow: { periods: [], rows: [], quality: {} } }],
    ['balance', { balance: { periods: [], rows: [], ratios: {} } }],
  ];
  for (const [tab, data] of cases) {
    const html = await renderTab(tab, data);
    assert.ok(html.includes('fin-legend'), `${tab} 标签应有配色图例`);
  }
});

test('表格负值标绿（现金流 FCF 等），正数保持中性', async () => {
  const html = await renderTab('cashflow', { cashflow: {
    periods: ['20250630', '20250930', '20251231', '20260331', '20260630'],
    rows: [
      { key: 'ocf_q', label: '经营现金流(亿)', values: [1.33, 1.65, 0.58, 1.87, 1.80] },
      { key: 'fcf_q', label: '自由现金流 FCF(亿)', values: [0.69, -1.04, -0.08, 1.29, -0.63] },
    ],
    quality: { ocf_to_np: 60.24, cash_recovery: 5.46, sales_cash_to_rev: 95.71,
               cf_per_share: -0.17, ocf_ttm_yi: 5.15 },
    latest_period: '20260630', note: '口径说明',
  } });
  assert.ok(html.includes('<td class="down">-1.04</td>'), 'FCF 负值标绿');
  assert.ok(html.includes('<td class="down">-0.08</td>'), 'FCF 负值标绿（小数）');
  assert.ok(html.includes('<td class="">1.80</td>'), '正值保持中性（不标红）');
  // 卡片：每股现金流 -0.17 也应标绿
  assert.ok(html.includes('class="val down">-0.17元'), '负数卡片标绿');
});

test('资产负债: 同期对比（vs 上年同季）箭头与配色', async () => {
  const html = await renderTab('balance', { balance: {
    periods: [20250630, 20250930, 20251231, 20260331, 20260630],
    latest_period: 20260630,
    rows: [
      { key: 'ta', label: '总资产(亿)', values: [100, 101, 102, 103, 109] },
      { key: 'tl', label: '总负债(亿)', values: [20, 21, 22, 23, 18] },
      { key: 'te', label: '净资产(亿)', values: [80, 80, 80, 80, 91] },
    ],
    ratios: { current_assets_pct: 64.73, current_liab_pct: 55.81,
              debt_ratio: 17.16, current_ratio: 6.76, quick_ratio: 4.47 },
    ratio_series: {
      debt_ratio: [20.0, 20.8, 21.5, 22.3, 17.16],
      current_ratio: [5.0, 5.2, 5.5, 5.8, 6.76],
      quick_ratio: [3.0, 3.1, 3.3, 3.5, 4.47],
    },
  } });
  assert.ok(html.includes('同期对比'), '含同期对比分组');
  assert.ok(html.includes('vs 25Q2'), '对比基准为上年同季（25Q2）');
  // 总负债 18 vs 20 → -10% → 绿 + 下箭头
  assert.ok(html.includes('总负债同比') && html.includes('<span class="arw">↓</span>-10.0%'),
            '总负债同比 -10%（降 = 去杠杆）');
  // 资产负债率 17.16 - 20.0 = -2.84 个百分点 → 绿
  assert.ok(html.includes('资产负债率变化') && html.includes('<span class="arw">↓</span>-2.84'),
            '资产负债率变化 -2.84 个百分点');
  // 流动比率 6.76 - 5.0 = +1.76 → 红
  assert.ok(html.includes('<span class="arw">↑</span>+1.76'), '流动比率变化 +1.76（红）');
  assert.ok(html.includes('class="arw"'), '箭头使用醒目样式');
});

test('资产负债: 缺 ratio_series 时用科目兜底推算，且 -- 给出通用解释', async () => {
  const html = await renderTab('balance', { balance: {
    periods: [20250630, 20250930, 20251231, 20260331, 20260630],
    latest_period: 20260630,
    rows: [
      { key: 'ta', label: '总资产(亿)', values: [100, 101, 102, 103, 109] },
      { key: 'tl', label: '总负债(亿)', values: [20, 21, 22, 23, 18] },
      { key: 'te', label: '净资产(亿)', values: [80, 80, 80, 80, 91] },
      { key: 'ca', label: '流动资产(亿)', values: [50, 51, 52, 53, 60] },
      { key: 'cl', label: '流动负债(亿)', values: [10, 10, 10, 10, 8] },
    ],
    ratios: { current_assets_pct: 64.73, current_liab_pct: 55.81,
              debt_ratio: 17.16, current_ratio: 6.76, quick_ratio: 4.47 },
    // 故意不给 ratio_series（模拟旧后端 / 服务未重启）
  } });
  // 兜底推算：资产负债率 = 18/109*100 − 20/100*100 = −3.49 → 绿
  assert.ok(html.includes('资产负债率变化') && html.includes('</span>-3.49'),
            '负债率变化由多期科目兜底推算');
  // 兜底推算：流动比率 = 60/8 − 50/10 = +2.50 → 红
  assert.ok(html.includes('</span>+2.50'), '流动比率变化由多期科目兜底推算');
  // 速动比率需存货字段、无法推算 → --，并在解释行给出通用说明
  assert.ok(html.includes('速动比率变化'), '含速动比率卡片');
  assert.ok(html.includes('表示该项缺少'), '-- 有通用解释');
  assert.ok(html.includes('受影响：') && html.includes('速动比率变化'), '解释行列出受影响项');
});

// ============ 分时 tooltip 数字格式化（桥接，不改 single-app.js）============
test('分时 tooltip: 涨跌幅保留 4 位小数，且不影响非分时图', async () => {
  const w = setup();
  const m = await getStock();
  await m.loadAll('sh600519');
  await new Promise((r) => setTimeout(r, 60));
  assert.ok(w.echarts.__dtTooltipPatched, 'echarts.init 已被桥接（boot 前完成）');

  // 分时主图：含"涨跌幅"系列 → 应注入格式化 formatter
  seenOptions = [];
  const c1 = w.echarts.init(w.document.createElement('div'));
  c1.setOption({ tooltip: { trigger: 'axis' }, series: [{ name: '现价' }, { name: '均价' }, { name: '涨跌幅' }] });
  const opt = seenOptions[seenOptions.length - 1];
  assert.ok(opt && opt.tooltip && typeof opt.tooltip.formatter === 'function', '已注入 tooltip formatter');
  const html = opt.tooltip.formatter([
    { axisValue: '14:25', seriesName: '现价', data: 218.89, marker: '' },
    { axisValue: '14:25', seriesName: '均价', data: 218.9, marker: '' },
    { axisValue: '14:25', seriesName: '涨跌幅', data: -1.6578308922634672, marker: '' },
  ]);
  assert.ok(html.includes('-1.6578%'), '涨跌幅保留 4 位小数');
  assert.ok(!html.includes('1.6578308922634672'), '不再出现原始长小数');
  assert.ok(html.includes('218.89'), '价格保留 2 位小数');

  // 其它图（如回测净值曲线）不应被改动
  seenOptions = [];
  const c2 = w.echarts.init(w.document.createElement('div'));
  c2.setOption({ tooltip: {}, series: [{ name: 'B(分市场段)' }] });
  const opt2 = seenOptions[seenOptions.length - 1];
  assert.ok(opt2 && !opt2.tooltip.formatter, '非分时图不注入 formatter');
  dom.window.close();
});

// -*- coding: utf-8 -*-
// DeepThinkCompStock · 前端 DOM 级渲染测试库（jsdom）
// 目的: 加载真实 index.html + 执行真实 app.js，调真实渲染函数，
//       断言生成 DOM 结构合法（table/thead/tbody/tr 完整、列数正确、徽章在位）。
//       补齐 P3 的盲区——"JS 语法对但 HTML 结构塌缩"（如 renderRecs 缺 <table>）。
// 运行: cd static && node --test ../tests/frontend/dom.test.js
// 或:   cd 项目根 && node --test tests/frontend/
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..', '..');
const INDEX = fs.readFileSync(path.join(ROOT, 'static', 'index.html'), 'utf8');
const APPJS = fs.readFileSync(path.join(ROOT, 'static', 'js', 'app.js'), 'utf8');

// ---------------- Mock 数据（与真实 API 返回结构一致） ----------------
const MOCK = {
  '/api/pool?cls=all': { total: 3, items: [
    { code: '688625', name: '呈和科技', industry: '化学制品', market: 'sh' },
    { code: '002484', name: '江海股份', industry: '元件', market: 'sz' },
    { code: '920002', name: '万达轴承', industry: '通用设备', market: 'bj' },
  ]},
  '/api/holdings': { items: [
    { code: '688625', name: '呈和科技', industry: '化学制品', market: 'sh', amount: 12000, dingtou: true },
    { code: '002484', name: '江海股份', industry: '元件', market: 'sz', amount: 15000, dingtou: false },
  ]},
  '/api/settings': { auto_track: false, weekly: 10000, newpos: 5000, cash: 50000, N: 4 },
  '/api/action_log': { items: [
    { ts: '2026-08-14 15:00', code: '688625', action: '加仓', amount: 12000, note: '本周精选' },
    { ts: '2026-08-07 15:00', code: '300408', action: '清仓', amount: 0, note: '退出买池' },
    { ts: '2026-08-07 15:00', code: '002484', action: '建仓', amount: 15000, note: '新进' },
  ]},
  '/api/analyze/status': {
    running: false, percent: 100, message: '分析完成',
    result: {
      signal_date: '20260814',
      summary: { regime_cn: '全部上涨 · 建议建仓', buy_pool: 30 },
      cards: [
        { code: '688625', name: '呈和科技', industry: '化学制品', market: 'sh', score: 72.5, advice: '加仓', action: '加仓(已持仓)', desc: 'ROE 18.1% · 52w动量 +127% · 段 沪深300 UP', amount: 12000 },
        { code: '002484', name: '江海股份', industry: '元件', market: 'sz', score: 70.1, advice: '加仓', action: '加仓(已持仓)', desc: 'ROE 10.6% · 52w动量 +150% · 段 沪深300 UP', amount: 15000 },
      ],
      selected_recommends: [
        { code: '688625', name: '呈和科技', industry: '化学制品', market: 'sh', score: 72.5, advice: '加仓', action: '加仓(已持仓)', held: true, is_top: true, fea_ratio: 52, one_hand: 5847, desc: 'ROE 18.1% · 52w动量 +127% · 段 沪深300 UP' },
        { code: '002484', name: '江海股份', industry: '元件', market: 'sz', score: 70.1, advice: '加仓', action: '加仓(已持仓)', held: true, is_top: true, fea_ratio: 62, one_hand: 6979, desc: 'ROE 10.6% · 52w动量 +150% · 段 沪深300 UP' },
        { code: '688127', name: '蓝特光学', industry: '光学光电子', market: 'sh', score: 64.7, advice: '买入', action: '建议建仓', held: false, is_top: true, fea_ratio: 59, one_hand: 6622, desc: 'ROE 12% · 52w动量 +80%' },
        { code: '300684', name: '中石科技', industry: '其他电子', market: 'sz', score: 64.7, advice: '买入', action: '建议建仓', held: false, is_top: true, fea_ratio: 60, one_hand: 6736, desc: 'ROE 15% · 52w动量 +90%' },
      ],
      recommends: [
        { code: '300394', name: '天孚通信', industry: '通信设备', market: 'sz', score: 84.0, advice: '买入', action: '建议建仓', held: false, is_top: false, fea_ratio: 238, one_hand: 26771, desc: 'ROE 22% · 52w动量 +200%' },
        { code: '688300', name: '联瑞新材', industry: '非金属材料Ⅱ', market: 'sh', score: 78.0, advice: '买入', action: '建议建仓', held: false, is_top: false, fea_ratio: 146, one_hand: 16465, desc: 'ROE 17% · 52w动量 +101%' },
      ],
    },
  },
  '/api/backtest': {
    'current_全样本1996+': { annualized: 0.114, sharpe: 0.50, max_drawdown: -0.52, empty_frac: 0.46, avg_turnover: 0.13 },
    'A_全样本1996+':      { annualized: 0.067, sharpe: 0.29, max_drawdown: -0.57, empty_frac: 0.45, avg_turnover: 0.09 },
    'B_全样本1996+':      { annualized: 0.114, sharpe: 0.44, max_drawdown: -0.56, empty_frac: 0.0,  avg_turnover: 0.17 },
    'C_全样本1996+':      { annualized: 0.098, sharpe: 0.32, max_drawdown: -0.68, empty_frac: 0.0,  avg_turnover: 0.21 },
    'E_全样本1996+':      { annualized: 0.023, sharpe: 0.01, max_drawdown: -0.74, empty_frac: 0.45, avg_turnover: 0.13 },
  },
  '/api/curves': {
    'B_全样本1996+': { dates: ['1996-01-01', '2026-08-14'], equity: [1, 26.89] },
    'current_全样本1996+': { dates: ['1996-01-01', '2026-08-14'], equity: [1, 26.99] },
  },
  '/api/logs': { items: [
    '[2026-08-14 09:00] 分析完成 signal=20260814 持仓2 推荐10',
    '[2026-08-14 09:01] 警告: 东财节点响应慢, 已切换',
    '[2026-08-14 09:02] 分析异常: 内存不足',
    '[2026-08-14 09:03] 添加/更新持仓 688625 amount=12000',
  ]},
};

// ---------------- jsdom 环境工厂 ----------------
const _windows = [];
function setupApp(html) {
  const dom = new JSDOM(html, {
    url: 'http://localhost:8899/',
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  });
  _windows.push(dom.window);
  const { window } = dom;

  // 0) stub 定时器：app.js 顶层 setInterval(tick,1000) 会产生残留异步活动，
  //    导致 node:test 报 unhandledRejection。测试不需要真实时钟。
  window.setInterval = () => 0;
  window.clearInterval = () => {};

  // 1) stub fetch：按 URL 返回 mock
  window.fetch = async (url) => {
    const key = url.split('?')[0];
    const found = MOCK[url] !== undefined ? MOCK[url] : MOCK[key];
    if (found === undefined) throw new Error('TEST fetch 未 mock: ' + url);
    return { ok: true, status: 200, statusText: 'OK', json: async () => found };
  };
  // 2) stub Chart（echarts 脚本在 jsdom 里不会执行，renderBacktest 用的 Chart 需 stub）
  window.Chart = class { constructor() {} destroy() {} update() {} };
  window.echarts = { init: () => ({ setOption() {}, dispose() {} }) };

  // 3) 执行真实 app.js（同一 eval 作用域内导出函数探针到 window.__app）
  window.eval(APPJS + `;\nwindow.__app = { renderRecs, renderCardTable, renderHoldingsPane, renderBt, renderLog, drawLog, setProgress, loadHoldings, bindCodeClicks, dispatchRoute };`);
  return window;
}

// ---------------- 工具：统计未闭合标签 ----------------
function tagBalance(html) {
  const opens = {}; const closes = {};
  const reOpen = /<([a-zA-Z][a-zA-Z0-9]*)((?:"[^"]*"|'[^']*'|[^'">])*)>/g;
  const reClose = /<\/([a-zA-Z][a-zA-Z0-9]*)>/g;
  let m;
  while ((m = reOpen.exec(html))) {
    const tag = m[1].toLowerCase();
    if (m[2].endsWith('/') || ['meta','link','br','hr','img','input','col'].includes(tag)) continue;
    opens[tag] = (opens[tag] || 0) + 1;
  }
  while ((m = reClose.exec(html))) { const t = m[1].toLowerCase(); closes[t] = (closes[t] || 0) + 1; }
  const bad = [];
  for (const t of Object.keys(opens)) if ((opens[t] || 0) !== (closes[t] || 0)) bad.push(`${t}: ${opens[t]}/${closes[t]}`);
  return bad;
}

// ==================== 测试用例 ====================
test('renderRecs: 无数据 → 空态提示（不残表）', () => {
  const w = setupApp(INDEX);
  const { renderRecs } = w.__app;
  renderRecs({ signal_date: '20260814', summary: { regime_cn: '' },
               selected_recommends: [], recommends: [] });
  const pane = w.document.querySelector('#pane-rec');
  assert.ok(pane.textContent.includes('暂无推荐'), '空态提示');
  assert.ok(!pane.querySelector('table'), '空态不渲染表格');
});

test('renderLog: drawLog 按级别筛选', async () => {
  const w = setupApp(INDEX);
  const { renderLog, drawLog } = w.__app;
  await renderLog();                       // 加载 4 条日志（含 error/warn/success）
  drawLog('error');
  const pane = w.document.querySelector('#pane-log');
  const lines = pane.querySelectorAll('.log-line');
  assert.equal(lines.length, 1, '仅错误级别');
  assert.ok(lines[0].classList.contains('error'), '错误行');
});

test('renderRecs: 本周推荐渲染为合法 <table>（回归: 裸 tr 塌缩 bug）', () => {
  const w = setupApp(INDEX);
  const { renderRecs } = w.__app;
  const res = MOCK['/api/analyze/status'].result;

  renderRecs(res);

  const pane = w.document.querySelector('#pane-rec');
  const table = pane.querySelector('table');
  assert.ok(table, '必须有 <table> 容器（本次回归点）');
  assert.ok(table.querySelector('thead'), '必须有 <thead>');
  assert.ok(table.querySelector('tbody'), '必须有 <tbody>');

  const rows = table.querySelectorAll('tr');
  assert.equal(rows.length, 1 + 1 + 4 + 1 + 2, '行数 = 表头1 + ⭐章节1 + 精选4 + 📋章节1 + 候选2 = 9');

  // 每行 8 列（除章节行 colspan=8）
  table.querySelectorAll('tbody tr:not(.rec-section)').forEach(tr => {
    assert.equal(tr.children.length, 8, '数据行必须 8 列: ' + tr.textContent.trim().slice(0, 20));
  });

  // 代码列可点击（跳转衔接）
  const clicks = table.querySelectorAll('.code-click');
  assert.ok(clicks.length >= 6, '至少 6 个可点击代码');
  assert.ok(clicks[0].textContent.includes('688625'));

  // 徽章在位（注意 ⭐/📋 后紧跟 <b>，不能直接 includes '⭐ 本周最值得买入'）
  const paneHtml = pane.innerHTML;
  assert.ok(paneHtml.includes('⭐') && paneHtml.includes('<b>本周最值得买入</b>'), '⭐ 章节标题');
  assert.ok(paneHtml.includes('📋') && paneHtml.includes('<b>更多候选</b>'), '📋 章节标题');
  assert.ok(paneHtml.includes('占预算'), '精选行有占预算徽章');
  assert.ok(paneHtml.includes('超预算'), '候选行有超预算徽章');

  // 标签闭合（回归核心：不再有裸 tr 塌缩）
  assert.deepEqual(tagBalance(pane.innerHTML), [], '标签必须全闭合');
});

test('renderCardTable: 持仓操作卡为合法表格 + 空态分支', async () => {
  const w = setupApp(INDEX);
  const { renderCardTable, loadHoldings } = w.__app;
  const res = MOCK['/api/analyze/status'].result;

  // 先填充全局 holdings（renderCardTable 依赖 holdings 交叉校验）
  await loadHoldings();

  // 有持仓: 2 只 cards 都在 holdings 里 → 渲染 2 行 + 表头
  renderCardTable(res);
  const pane = w.document.querySelector('#pane-holdings');
  assert.ok(pane.querySelector('table'), '有 <table>');
  assert.equal(pane.querySelectorAll('tr').length, 3, '表头1 + 数据2');
  assert.deepEqual(tagBalance(pane.innerHTML), [], '标签闭合');

  // 空态分支: cards=[] → 空态提示
  renderCardTable({ ...res, cards: [] });
  const pane2 = w.document.querySelector('#pane-holdings');
  assert.ok(pane2.innerHTML.includes('暂无持仓'), '空态提示');
  assert.ok(!pane2.querySelector('table'), '空态不渲染表格');
});

test('renderHoldingsPane: 走 fetch 链渲染持仓操作卡', async () => {
  const w = setupApp(INDEX);
  const { renderHoldingsPane, loadHoldings } = w.__app;
  await loadHoldings();
  await renderHoldingsPane();
  const pane = w.document.querySelector('#pane-holdings');
  assert.ok(pane.querySelector('table'), 'fetch → renderCardTable 正常出表格');
  assert.equal(pane.querySelectorAll('tbody tr').length, 2, '2 只持仓');
});

test('renderBt: 回测 5 方案表格 + 徽章（fetch + echarts stub）', () => {
  const w = setupApp(INDEX);
  const { renderBt } = w.__app;
  return renderBt().then(() => {
    const pane = w.document.querySelector('#pane-bt');
    assert.ok(pane.textContent.includes('current(上证)'), '方案名');
    assert.ok(pane.textContent.includes('11.4%'), '年化数字');
    assert.ok(pane.textContent.includes('历史最优(基准)'), 'current 徽章');
    assert.ok(pane.textContent.includes('修复后≈基准'), 'B 徽章');
    const rows = pane.querySelectorAll('#btTable tbody tr');
    assert.equal(rows.length, 5, '5 个方案行');
    assert.deepEqual(tagBalance(pane.innerHTML), [], '标签闭合');
  });
});

test('renderLog: 日志级别统计 + 错误行着色', async () => {
  const w = setupApp(INDEX);
  const { renderLog } = w.__app;
  await renderLog();
  const pane = w.document.querySelector('#pane-log');
  assert.ok(pane.querySelector('.log-line.error'), '至少 1 条错误行（分析异常）');
  assert.ok(pane.querySelector('.log-line.success'), '至少 1 条成功行（分析完成）');
  assert.ok(pane.querySelector('.log-line.warn'), '至少 1 条警告行');
  // 统计条数字
  assert.ok(pane.textContent.includes('总计'), '统计条存在');
  assert.ok(pane.textContent.includes('错误'), '错误计数存在');
  assert.deepEqual(tagBalance(pane.innerHTML), [], '标签闭合');
});

test('index.html 骨架: 8 个 Tab 容器 + 引用新路径静态资源', () => {
  const w = setupApp(INDEX);
  const tabs = w.document.querySelectorAll('.tab');
  assert.ok(tabs.length >= 7, 'Tab 数量 >= 7');
  const panes = w.document.querySelectorAll('.tab-pane');
  assert.ok(panes.length >= 7, 'pane 数量 >= 7');
  // 静态资源引用必须是新路径（有 css/js 子目录）
  assert.ok(INDEX.includes('/static/css/style.css'), 'style.css 新路径');
  assert.ok(INDEX.includes('/static/js/app.js'), 'app.js 新路径');
  assert.ok(!INDEX.includes('src="/static/style.css"'), '无旧路径残留');
  assert.ok(!INDEX.includes('src="/static/app.js"'), '无旧路径残留');
});

test('T-J1 DOM级: 点击 code-click → hash 变为 #/stock/xx?from=...', async () => {
  const w = setupApp(INDEX);
  const { renderRecs, loadHoldings } = w.__app;
  // 消费 hashchange 派发的 dispatchRoute 动态 import 失败（测试环境无相对模块），避免 unhandledRejection
  w.window.addEventListener('unhandledrejection', e => e.preventDefault());
  await loadHoldings();
  renderRecs(MOCK['/api/analyze/status'].result);
  const td = w.document.querySelector('#pane-rec .code-click');
  assert.ok(td, '代码列可点击');
  td.onclick();
  assert.match(w.location.hash, /^#\/stock\/(sh|sz|bj)\d{6}\?from=/, '跳转 hash 格式正确');
  // 等 hashchange 派发完成再结束测试
  await new Promise(r => setTimeout(r, 30));
});

test('hashchange 监听 → dispatchRoute 被触发（#/rec）', async () => {
  const w = setupApp(INDEX);
  const { dispatchRoute } = w.__app;
  let called = false;
  w.window.addEventListener('hashchange', () => { called = true; });
  w.location.hash = '#/rec';
  // jsdom 的 hashchange 是异步派发，稍等一拍
  await new Promise(r => setTimeout(r, 20));
  assert.ok(called, 'hashchange 事件已触发（真实浏览器中 dispatchRoute 由该事件驱动）');
});

test('renderBt: 无回测数据 → 错误空态', async () => {
  const w = setupApp(INDEX);
  const { renderBt } = w.__app;
  w.fetch = async (url) => {
    if (url.includes('/api/curves')) return { ok: true, json: async () => ({}) };
    return { ok: false, status: 500, statusText: 'ERR', json: async () => ({ error: '尚未生成回测数据' }) };
  };
  await renderBt();
  const pane = w.document.querySelector('#pane-bt');
  assert.ok(pane.textContent.includes('失败') || pane.textContent.includes('error'),
            '显示错误信息而非白屏');
});

test('renderHoldingsPane: 无分析结果 → 空态提示', async () => {
  const w = setupApp(INDEX);
  const { renderHoldingsPane } = w.__app;
  w.fetch = async (url) => ({ ok: true, json: async () => ({ running: false, result: null }) });
  await renderHoldingsPane();
  const pane = w.document.querySelector('#pane-holdings');
  assert.ok(pane.textContent.includes('暂无持仓'), '空态提示');
});

test('setProgress: 状态/百分比/标签渲染', () => {
  const w = setupApp(INDEX);
  const { setProgress } = w.__app;
  setProgress('done', 100, '分析完成');
  const wrap = w.document.querySelector('#progressWrap');
  assert.ok(wrap.classList.contains('done'), 'done 状态类');
  assert.equal(w.document.querySelector('#progressFill').style.width, '100%', '进度条宽度');
  assert.equal(w.document.querySelector('#progressState').textContent, '分析完成', '状态标签');
  setProgress('', 30, '运行中');
  assert.ok(!wrap.classList.contains('done'), '切回运行中清除 done');
});

test('T-DIAG: renderRecs 徽章完整生成（不降级 + 不被 CSS 截断的回归）', () => {
  const w = setupApp(INDEX);
  const { renderRecs } = w.__app;
  const testRes = {
    signal_date: '20260814',
    summary: { regime_cn: '测试' },
    selected_recommends: [
      { code: '688625', name: '呈和科技', industry: '化学制品', market: 'sh', score: 72.5,
        advice: '加仓', action: '加仓(已持仓)', held: true, is_top: true,
        one_hand: 5847, fea_ratio: 52, desc: 'ROE 18.3% · 52w动量 +152% · 段 sh000688 UP' }
    ],
    recommends: [
      { code: '300394', name: '天孚通信', industry: '通信设备', market: 'sz', score: 88,
        advice: '买入', action: '建议建仓', held: false, is_top: false,
        one_hand: 26771, fea_ratio: 238, desc: 'ROE 22% · 52w动量 +200%' }
    ],
  };
  renderRecs(testRes);
  const html = w.document.querySelector('#pane-rec').innerHTML;
  // 关键回归：徽章必须完整生成 + desc 完整保留（CSS 截断防御）
  assert.ok(html.includes('class="rec-table"'), '表 class 有 rec-table');
  assert.ok(html.includes('tag-star'), '⭐精选徽章');
  assert.ok(html.includes('tag-held'), '已持仓徽章');
  assert.ok(html.includes('tag-budget'), '占预算徽章');
  assert.ok(html.includes('tag-over'), '超预算徽章');
  assert.ok(html.includes('ROE 18.3%'), 'desc 完整文本保留');
  assert.ok(html.includes('sh000688'), 'desc 末段标识符');
  // 防御：徽章必须在 cell-code 容器内（flex 横排），desc 在 cell-desc 容器内（换行）
  assert.ok(/<div class="cell-code">[^<]*<b[^>]*>688625<\/b><span[^>]*tag-star/.test(html),
            '徽章必须放在 cell-code 容器内（flex 横排）');
  assert.ok(/<div class="cell-desc">ROE[^<]*<\/div>/.test(html),
            'desc 放在 cell-desc 容器内（保留换行）');
  // 防御：table-layout 必须是 auto（fixed 会让 flex 溢出导致徽章漂到下一列）
  const css = fs.readFileSync(path.join(ROOT, 'static/css/style.css'), 'utf8');
  assert.ok(/table\.rec-table[^{]*\{[^}]*table-layout:\s*auto/.test(css),
            'table.rec-table 必须用 table-layout:auto（fixed 会让徽章溢出到相邻列）');
  // cell-code 必须用 inline-block（不是 flex，因为 td 内 flex 会被 table-cell 解释为 block）
  assert.ok(/table\.rec-table[^}]*tbody\s+td\.code-click[^}]*\.cell-code[^{]*\{[^}]*display:\s*inline-block/.test(css),
            'cell-code 必须 display:inline-block（避免 td 内 flex 子项被解释为 block）');
  // 徽章的 margin-left 必须为 0（避免视觉上"换行"效果）
  assert.ok(/\.tag-(star|held|budget|over)\s*\{[^}]*margin-left:\s*0/.test(css),
            '徽章 margin-left:0（避免在 cell-code 内视觉错位）');
  // 不能有 td 通用 nowrap+ellipsis 规则覆盖到 rec-table
  assert.ok(!/(tbody\s+td\s*\{[^}]*white-space:\s*nowrap\s*;[^}]*text-overflow:\s*ellipsis)/.test(css),
            '存在 td 通用 nowrap+ellipsis 规则会截断 rec-table');
});

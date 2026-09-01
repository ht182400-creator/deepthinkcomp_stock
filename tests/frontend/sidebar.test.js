// -*- coding: utf-8 -*-
// DeepThinkCompStock · 侧栏交互（持仓录入/删除/设置/分析）DOM 级测试
// 加载真实 index.html + eval 真实 app.js，mock fetch/alert/confirm，测表单校验与交互链路。
// 运行: node --test --test-force-exit tests/frontend/sidebar.test.js
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..', '..');
const INDEX = fs.readFileSync(path.join(ROOT, 'static', 'index.html'), 'utf8');
const APPJS = fs.readFileSync(path.join(ROOT, 'static', 'js', 'app.js'), 'utf8');

let dom;
let calls = [];        // fetch 调用记录
let alerts = [];
let confirms = [];

function makeFetch(state) {
  // state: { holdings: [], pool: [...], settings: {...} }
  return async (url, opts) => {
    calls.push({ url, opts });
    const method = (opts && opts.method) || 'GET';
    const u = url.split('?')[0];
    let body = { items: state.holdings };
    if (u === '/api/pool') body = { total: state.pool.length, items: state.pool };
    else if (u === '/api/settings') body = state.settings;
    else if (u === '/api/analyze') body = { message: '分析已提交', running: true };
    else if (u === '/api/analyze/status') body = { running: false, message: '分析完成', percent: 100, result: null };
    else if (u === '/api/holdings' && method === 'POST') {
      const arg = JSON.parse(opts.body);
      state.holdings = state.holdings.filter(h => h.code !== arg.code);
      state.holdings.push({ code: arg.code, name: '呈和科技', amount: arg.amount, dingtou: arg.dingtou, date: '2026-08-14' });
      body = { items: state.holdings };
    } else if (u === '/api/holdings/delete') {
      const arg = JSON.parse(opts.body);
      state.holdings = state.holdings.filter(h => !arg.codes.includes(h.code));
      body = { items: state.holdings };
    }
    return { ok: true, status: 200, statusText: 'OK', json: async () => body };
  };
}

function setup(state = {}) {
  dom = new JSDOM(INDEX, { url: 'http://localhost:8899/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  calls = []; alerts = []; confirms = [];
  window.fetch = makeFetch({
    holdings: state.holdings || [],
    pool: state.pool || [{ code: '688625', name: '呈和科技', industry: '化学制品', market: 'sh' }],
    settings: state.settings || { auto_track: false, weekly: 10000, newpos: 5000, cash: 50000, N: 4 },
  });
  window.setInterval = () => 0;
  window.clearInterval = () => {};
  window.alert = msg => alerts.push(msg);
  window.confirm = msg => { confirms.push(msg); return state.confirmOk !== false; };
  window.eval(APPJS + `;\nwindow.__app = { renderHoldings, addHolding, delHoldings, loadHoldings, loadPool, loadSettings, saveSettings, doAnalyze, pollAnalyze, setProgress, renderHoldingsPane };`);
  return window;
}

test('侧栏: 持仓为空 → 显示空态', async () => {
  const w = setup();
  const { loadHoldings } = w.__app;
  await loadHoldings();
  assert.ok(w.document.querySelector('#holdTable').textContent.includes('暂无持仓'));
  assert.equal(w.document.querySelector('#holdCount').textContent, '0');
  dom.window.close();
});

test('侧栏: 有持仓 → 行渲染 + 定投徽章 + 金额格式化', async () => {
  const w = setup({ holdings: [
    { code: '688625', name: '呈和科技', amount: 12000, dingtou: true, date: '2026-08-14' },
    { code: '002484', name: '江海股份', amount: 15000, dingtou: false, date: '' },
  ]});
  const { loadHoldings } = w.__app;
  await loadHoldings();
  const rows = w.document.querySelectorAll('#holdTable tr[data-code]');
  assert.equal(rows.length, 2);
  assert.ok(rows[0].textContent.includes('呈和科技'));
  assert.ok(rows[0].textContent.includes('12,000'), '金额千分位');
  assert.ok(rows[0].querySelector('.tag-up'), '定投徽章');
  dom.window.close();
});

test('侧栏: addHolding 空输入 → alert 不发请求', async () => {
  const w = setup();
  const { addHolding } = w.__app;
  w.document.querySelector('#poolInput').value = '';
  await addHolding();
  assert.ok(alerts.length >= 1, '提示输入标的');
  assert.ok(!calls.some(c => c.url.includes('/api/holdings') && (c.opts || {}).method === 'POST'),
            '不应发 POST');
  dom.window.close();
});

test('侧栏: addHolding 代码不在池 → alert 不发请求', async () => {
  const w = setup();
  const { addHolding, loadPool } = w.__app;
  await loadPool();
  w.document.querySelector('#poolInput').value = '999999 不存在';
  await addHolding();
  assert.ok(alerts.some(a => a.includes('不在池中')), '提示不在池');
  assert.ok(!calls.some(c => c.url.includes('/api/holdings') && (c.opts || {}).method === 'POST'));
  dom.window.close();
});

test('侧栏: addHolding 成功 → POST + 刷新列表 + 清空输入', async () => {
  const w = setup();
  const { addHolding, loadPool } = w.__app;
  await loadPool();
  w.document.querySelector('#poolInput').value = '688625 呈和科技';
  w.document.querySelector('#holdAmount').value = '12000';
  w.document.querySelector('#holdDingtou').checked = true;
  await addHolding();
  const post = calls.filter(c => c.url.includes('/api/holdings') && (c.opts || {}).method === 'POST');
  assert.equal(post.length, 1, '发 1 次 POST');
  const arg = JSON.parse(post[0].opts.body);
  assert.equal(arg.code, '688625');
  assert.equal(arg.amount, 12000);
  assert.equal(arg.dingtou, true);
  assert.equal(w.document.querySelector('#poolInput').value, '', '输入已清空');
  assert.equal(w.document.querySelector('#holdCount').textContent, '1', '列表已刷新');
  dom.window.close();
});

test('侧栏: delHoldings 未选中 → alert 不发请求', async () => {
  const w = setup({ holdings: [{ code: '688625', name: '呈和科技', amount: 100, dingtou: false, date: '' }] });
  const { delHoldings, loadHoldings } = w.__app;
  await loadHoldings();
  await delHoldings();
  assert.ok(alerts.some(a => a.includes('勾选')), '提示先勾选');
  assert.ok(!calls.some(c => c.url.includes('/delete')));
  dom.window.close();
});

test('侧栏: delHoldings 选中 → DELETE + 列表刷新', async () => {
  const w = setup({ holdings: [{ code: '688625', name: '呈和科技', amount: 100, dingtou: false, date: '' }] });
  const { delHoldings, loadHoldings } = w.__app;
  await loadHoldings();
  const tr = w.document.querySelector('#holdTable tr[data-code="688625"]');
  tr.classList.add('selected');
  await delHoldings();
  assert.equal(confirms.length, 1, '确认框弹出');
  assert.ok(calls.some(c => c.url.includes('/delete')));
  assert.equal(w.document.querySelector('#holdCount').textContent, '0', '删除后刷新');
  dom.window.close();
});

test('侧栏: saveSettings → POST /api/settings', async () => {
  const w = setup();
  const { saveSettings, loadSettings } = w.__app;
  await loadSettings();
  w.document.querySelector('#setWeekly').value = '8000';
  await saveSettings();
  const post = calls.filter(c => c.url.includes('/api/settings') && (c.opts || {}).method === 'POST');
  assert.equal(post.length, 1);
  const arg = JSON.parse(post[0].opts.body);
  assert.equal(arg.weekly, 8000);
  dom.window.close();
});

test('侧栏: doAnalyze → POST /api/analyze', async () => {
  const w = setup();
  const { doAnalyze } = w.__app;
  await doAnalyze();
  assert.ok(calls.some(c => c.url.includes('/api/analyze') && (c.opts || {}).method === 'POST'),
            '提交分析');
  dom.window.close();
});

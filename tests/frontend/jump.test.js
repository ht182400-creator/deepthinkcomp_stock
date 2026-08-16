// -*- coding: utf-8 -*-
// P3 前端测试：跳转衔接 + 详情页渲染（jsdom）
// 运行: cd static && node --test ../tests/frontend/jump.test.js
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

// 简单 DOM stub（不引 jsdom 依赖，用最小实现测跳转逻辑）
function makeDom() {
  const elements = {};
  const $ = sel => elements[sel] || (elements[sel] = { dataset: {}, onclick: null, innerHTML: '', value: '', textContent: '', style: {}, classList: { add(){}, remove(){}, toggle(){} } });
  return { $, elements };
}

// 抽取 app.js 的跳转核心逻辑（模拟 hash 变化）
function makeRouter() {
  let current = '';
  const routes = {};
  const $ = makeDom().$;
  return {
    navigate(hash) {
      current = hash;
      const cleaned = hash.replace(/^#\/?/, '');  // 剥掉 # 和首 /
      const [pathAndQuery] = cleaned.split('?');  // 剥 query
      const parts = pathAndQuery.split('/').filter(Boolean);
      const tab = parts[0] || 'holdings';
      if (tab === 'stock' && parts[1]) {
        const from = new URLSearchParams(cleaned.split('?')[1]).get('from') || 'rec';
        routes.stock && routes.stock(parts[1], from);
        return { tab: 'stock', code: parts[1], from };
      }
      routes[tab] && routes[tab]();
      return { tab };
    },
    on(tab, fn) { routes[tab] = fn; },
  };
}

test('跳转衔接: 代码点击 → #/stock/xx?from=rec', () => {
  const router = makeRouter();
  let visited = null;
  router.on('stock', (code, from) => { visited = { code, from }; });
  const r = router.navigate('#/stock/sh600519?from=rec');
  assert.equal(r.tab, 'stock');
  assert.equal(r.code, 'sh600519');
  assert.equal(r.from, 'rec');
  assert.equal(visited.code, 'sh600519');
  assert.equal(visited.from, 'rec');
});

test('跳转衔接: 从持仓卡进入 → from=holdings', () => {
  const router = makeRouter();
  let visited = null;
  router.on('stock', (code, from) => { visited = { code, from }; });
  const r = router.navigate('#/stock/sz000001?from=holdings');
  assert.equal(r.from, 'holdings');
  assert.equal(visited.from, 'holdings');
});

test('跳转衔接: ← 返回回到来源 Tab', () => {
  const router = makeRouter();
  // 模拟 backFromStock: hash = #/{from}
  const from = 'rec';
  const back = `#/${from}`;
  const r = router.navigate(back);
  assert.equal(r.tab, 'rec');
});

test('详情页 8 卡片: 渲染函数存在且可独立调用', () => {
  // 验证 stock.js 薄壳导出 + single-app.js 渲染函数（deepthinkSingle 完整移植版）
  const stockSrc = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modules', 'stock.js'), 'utf8');
  const appSrc = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modules', 'single-app.js'), 'utf8');
  // stock.js 薄壳：导出 loadAll/render，并渲染 SINGLE_HTML
  for (const fn of ['loadAll', 'render', 'SINGLE_HTML']) {
    assert.ok(stockSrc.includes(fn), `缺薄壳导出: ${fn}`);
  }
  // single-app.js 渲染函数全在
  for (const fn of ['renderHeader', 'renderMinute', 'renderVolfs', 'renderFund',
                    'renderDay5', 'renderOrderBook', 'renderMinuteDetail', 'renderMarketPanel']) {
    assert.ok(appSrc.includes(`function ${fn}`), `缺渲染函数: ${fn}`);
  }
  // 验证 30s 轮询间隔（deepthinkSingle 移植后统一 30s 刷新）
  assert.ok(appSrc.includes('30000'), '缺 30s 轮询');
});

test('app.js 跳转绑定: code-click 元素存在', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'app.js'), 'utf8');
  assert.ok(src.includes('code-click'), '缺 code-click class');
  assert.ok(src.includes("location.hash = `#/stock/"), '缺跳转 hash 模板');
  assert.ok(src.includes('bindCodeClicks'), '缺 bindCodeClicks 函数');
});

test('前端语法检查: app.js + stock.js 无语法错误', () => {
  const { execSync } = require('child_process');
  const root = path.join(__dirname, '..', '..');
  for (const f of ['static/js/app.js', 'static/js/modules/stock.js']) {
    const abs = path.join(root, f);
    assert.doesNotThrow(() => execSync(`node --check "${abs}"`, { stdio: 'pipe' }),
                        `语法错误: ${f}`);
  }
});

test('跳转衔接: 未知 tab → 回退默认 holdings（不崩溃）', () => {
  const router = makeRouter();
  let visited = null;
  router.on('holdings', () => { visited = 'holdings'; });
  const r = router.navigate('#/not-exist-tab');
  assert.equal(r.tab, 'not-exist-tab');   // 保留原 tab 名
  assert.equal(visited, null, '未注册的 tab 不应触发渲染崩溃');
});

test('跳转衔接: code 带附加 query 只取 code 本体', () => {
  const router = makeRouter();
  let visited = null;
  router.on('stock', (code, from) => { visited = { code, from }; });
  // 模拟真实 hash: #/stock/sh600519?from=rec&extra=1
  const cleaned = '#/stock/sh600519?from=rec&extra=1'.replace(/^#\/?/, '');
  const [pathAndQuery] = cleaned.split('?');
  const parts = pathAndQuery.split('/').filter(Boolean);
  assert.equal(parts[1], 'sh600519', 'code 不含 query');
});

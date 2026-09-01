// 前端功能测试（US-071，评审 §5-2）—— 真·页面冒烟，不是静态文本检查
// ---------------------------------------------------------------
// 上半部：源码级回归守护（无依赖、恒跑，守护 D2/D3/M1 修复不被回退）
// 下半部：jsdom 加载真实 index.html + mock echarts/fetch，触发 init()，
//         断言页面启动、复盘 modal、搜索下拉/键盘导航、自选删除等真实交互。
//         若 jsdom 仍未安装，该段自动 skip 并提示 `npm i -D jsdom`。
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "../..");
const APP_SRC = fs.readFileSync(path.join(ROOT, "static/js/app.js"), "utf8");
const IND_SRC = fs.readFileSync(path.join(ROOT, "static/js/indicators.js"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "templates/index.html"), "utf8");

// ---------- 源码级回归守护（恒跑，无依赖） ----------
test("D2 回归守护：不再 resize 未 init 的 p2/p3/p5（仅 charts.p1 + charts.sub[] / p4 + klineSub[]）", () => {
  assert.ok(!/charts\.p2\.resize\(\)/.test(APP_SRC), "不应存在 charts.p2.resize()");
  assert.ok(!/charts\.p3\.resize\(\)/.test(APP_SRC), "不应存在 charts.p3.resize()");
  assert.ok(!/charts\.p5\.resize\(\)/.test(APP_SRC), "不应存在 charts.p5.resize()");
  assert.ok(/charts\.p1\.resize\(\)/.test(APP_SRC), "应保留 charts.p1.resize()");
  assert.ok(/charts\.p4\.resize\(\)/.test(APP_SRC), "应保留 charts.p4.resize()");
  assert.ok(/\(charts\.sub \|\| \[\]\)\.forEach/.test(APP_SRC), "分钟视图应遍历 charts.sub[] resize");
  assert.ok(/\(charts\.klineSub \|\| \[\]\)\.forEach/.test(APP_SRC), "K线视图应遍历 charts.klineSub[] resize");
});

test("D3 回归守护：K线 zoom handler 为模块级稳定函数（非每次渲染新闭包）", () => {
  assert.ok(/function _onKlineDataZoom\(/.test(APP_SRC), "应存在模块级 _onKlineDataZoom 定义");
  assert.ok(/_bindKlineZoomSync/.test(APP_SRC), "应存在 _bindKlineZoomSync 绑定入口");
});

test("M1/US-069 守护：分时与 K线副图均已收敛到数据驱动骨架", () => {
  assert.ok(/function buildSubOption\(/.test(APP_SRC), "分时副图骨架 buildSubOption 应存在");
  assert.ok(/function buildKlineSubOption\(/.test(APP_SRC), "K线指标副图骨架 buildKlineSubOption 应存在");
  for (const fn of ["renderMacd", "renderKdj", "renderBoll", "renderRsi"]) {
    const re = new RegExp("function " + fn + "\\([^)]*\\)\\s*\\{[^]*?buildKlineSubOption\\(");
    assert.ok(re.test(APP_SRC), `${fn} 应调用 buildKlineSubOption`);
  }
});

// ---------- 前端功能测试（需 jsdom） ----------
let jsdomMod = null;
try { jsdomMod = require("jsdom"); } catch (e) { jsdomMod = null; }

// 用真实静态资源 mock 后端：按 URL 前缀返回最小可解析响应
let MINUTE_EMPTY = false; // 测试开关：设为 true 时 /api/minute 返回空数组（模拟免费源无历史分时）
function mockResponse(url) {
  const u = String(url);
  if (u.includes("/api/search"))
    return { ok: true, json: async () => [{ code: "sh600519", name: "贵州茅台", cat: "沪A" }, { code: "sz000858", name: "五粮液", cat: "深A" }] };
  if (u.includes("/api/analysis"))
    return { ok: true, json: async () => [] };
  if (u.includes("/api/quote"))
    return { ok: true, json: async () => ({ code: "sh600519", name: "贵州茅台", price: 1680, minute: [] }) };
  if (u.includes("/api/watchlist"))
    return { ok: true, json: async () => [] };
  if (u.includes("/api/many"))
    return { ok: true, json: async () => ({}) };
  if (u.includes("/api/kline")) {
    if (u.includes("period=m60"))
      return { ok: true, json: async () => [
        { date: "2026-08-14 10:30:00", open: 1348, close: 1341, high: 1350, low: 1338, vol: 1000 },
        { date: "2026-08-14 11:30:00", open: 1341, close: 1340, high: 1342, low: 1339, vol: 2000 },
        { date: "2026-08-14 14:00:00", open: 1340, close: 1348, high: 1350, low: 1338, vol: 3000 },
        { date: "2026-08-14 15:00:00", open: 1348, close: 1341, high: 1344, low: 1339, vol: 4000 },
      ] };
    return { ok: true, json: async () => Array.from({ length: 20 }, (_, i) => ({
      date: `2026-08-${String(i + 1).padStart(2, "0")}`,
      open: 1300 + i, close: 1301 + i, high: 1302 + i, low: 1299 + i, vol: 1000,
    })) };
  }
  if (u.includes("/api/minute")) {
    if (MINUTE_EMPTY)
      return { ok: true, json: async () => [] };
    return { ok: true, json: async () => Array.from({ length: 48 }, (_, i) => ({
      t: `09:${String(30 + i).padStart(2, "0")}`, price: 100 + i, avg: 100 + i / 2, vol: 1000 + i,
    })) };
  }
  return { ok: true, json: async () => ({}) };
}

// 启动一个完整的页面实例（init 已跑），返回测试探针
async function boot() {
  const { JSDOM } = jsdomMod;
  const dom = new JSDOM(HTML, { runScripts: "outside-only", pretendToBeVisual: true, url: "http://localhost/" });
  const { window } = dom;

  // 阻止后台自动刷新（setInterval）让测试进程挂起；ResizeObserver jsdom 无，置空
  window.ResizeObserver = undefined;
  window.setInterval = () => 0;

  let inited = 0;
  const instances = [];
  window.echarts = {
    init(el) {
      inited += 1;
      const inst = {
        id: el && el.id,
        handlers: {},
        _last: null,
        _cleared: 0,
        setOption(opt) { this._last = opt; },
        resize() {},
        dispose() { this.disposed = true; },
        clear() { this._cleared += 1; },
        getOption() { return {}; },
        showLoading() {},
        hideLoading() {},
        on(ev, fn) { this.handlers[ev] = fn; },
        off() {},
      };
      instances.push(inst);
      return inst;
    },
  };

  const fetchCalls = [];
  const fetchFn = async (url, opts) => {
    fetchCalls.push({ url: String(url), opts: opts || null });
    return mockResponse(url);
  };
  window.fetch = fetchFn;
  global.window = window;
  global.document = window.document;
  global.fetch = fetchFn;
  global.Event = window.Event;
  global.KeyboardEvent = window.KeyboardEvent;
  global.ResizeObserver = undefined;

  window.eval(IND_SRC);
  window.eval(APP_SRC);
  // jsdom 在构造后会异步 fire 一次 DOMContentLoaded（app.js 已注册 init 监听）；
  // 若当前环境未自动触发则手动补一次，但绝不重复派发，否则 init 双触发会让
  // keydown 等监听器绑两次，键盘导航等交互断言失真。
  await new Promise(r => setTimeout(r, 50));
  if (inited === 0) {
    window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
    await new Promise(r => setTimeout(r, 10));
  }
  return { window, document: window.document, fetchCalls, inited, instances };
}

test("启动：init() 不抛异常，DTIndicators 挂载且 p1 图表已 init", async (t) => {
  if (!jsdomMod) { t.skip("jsdom 未安装（npm i -D jsdom）"); return; }
  const { window, inited } = await boot();
  assert.ok(window.DTIndicators && typeof window.DTIndicators.macd === "function", "DTIndicators 应挂载到 window");
  assert.ok(inited >= 1, "initCharts 应至少 init 一个图表实例（p1）");
});

test("复盘 modal：点击「复盘」打开，点击「关闭」隐藏", async (t) => {
  if (!jsdomMod) { t.skip("jsdom 未安装（npm i -D jsdom）"); return; }
  const { window, document } = await boot();
  document.getElementById("analysisBtn").dispatchEvent(new window.Event("click"));
  assert.ok(!document.getElementById("analysisModal").classList.contains("hidden"), "复盘 modal 应显示");
  document.getElementById("analysisClose").dispatchEvent(new window.Event("click"));
  assert.ok(document.getElementById("analysisModal").classList.contains("hidden"), "复盘 modal 应隐藏");
});

test("搜索：输入触发 /api/search 请求并渲染下拉项", async (t) => {
  if (!jsdomMod) { t.skip("jsdom 未安装（npm i -D jsdom）"); return; }
  const { window, document, fetchCalls } = await boot();
  const input = document.getElementById("searchInput");
  input.value = "茅台";
  input.dispatchEvent(new window.Event("input"));
  await new Promise(r => setTimeout(r, 300)); // 等 doSearch 的 200ms 防抖定时器
  assert.ok(fetchCalls.some(c => c.url.includes("/api/search")), "应发起 /api/search 请求");
  const items = document.querySelectorAll("#searchResults .item");
  assert.strictEqual(items.length, 2, "应渲染 2 个搜索结果项");
});

test("搜索键盘导航：ArrowDown 高亮首项，Enter 触发切换并请求 quote", async (t) => {
  if (!jsdomMod) { t.skip("jsdom 未安装（npm i -D jsdom）"); return; }
  const { window, document, fetchCalls } = await boot();
  const input = document.getElementById("searchInput");
  input.value = "茅台";
  input.dispatchEvent(new window.Event("input"));
  await new Promise(r => setTimeout(r, 300));

  const items = document.querySelectorAll("#searchResults .item");
  input.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowDown" }));
  assert.ok(items[0].classList.contains("active"), "ArrowDown 应高亮第一个搜索项");

  const before = fetchCalls.filter(c => c.url.includes("/api/quote")).length;
  input.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter" }));
  await new Promise(r => setTimeout(r, 50));
  const after = fetchCalls.filter(c => c.url.includes("/api/quote")).length;
  assert.ok(after > before, "Enter 应选定标的并触发 /api/quote 切换");
});

test("自选删除：点击「−」触发 /api/watchlist remove 请求", async (t) => {
  if (!jsdomMod) { t.skip("jsdom 未安装（npm i -D jsdom）"); return; }
  const { window, document, fetchCalls } = await boot();
  document.getElementById("delBtn").dispatchEvent(new window.Event("click"));
  await new Promise(r => setTimeout(r, 50));
  const called = fetchCalls.some(c =>
    c.url.includes("/api/watchlist") && c.opts && JSON.parse(c.opts.body).action === "remove");
  assert.ok(called, "应发起 /api/watchlist {action:'remove'} 请求");
});

test("空数据占位（US-030）：quote 返回空分钟数据时应显示「暂无分时数据」", async (t) => {
  if (!jsdomMod) { t.skip("jsdom 未安装（npm i -D jsdom）"); return; }
  const { window, document, fetchCalls } = await boot();
  // 等待 init 内的 loadQuote 完成
  await new Promise(r => setTimeout(r, 50));
  assert.ok(fetchCalls.some(c => c.url.includes("/api/quote")), "init 应请求 /api/quote");
  const overlay = document.getElementById("p1Empty");
  assert.ok(overlay && !overlay.classList.contains("hidden"), "空分钟数据时应显示 p1Empty 占位层");
});

test("K线 60分（US-071 功能回归）：m60 只返回 4 根（<10）仍应直接渲染并显示 60分K 标题", async (t) => {
  if (!jsdomMod) { t.skip("jsdom 未安装（npm i -D jsdom）"); return; }
  const { window, document, fetchCalls } = await boot();
  // 进入 K线视图（默认请求 day）
  document.getElementById("klineBtn").dispatchEvent(new window.Event("click"));
  await new Promise(r => setTimeout(r, 50));
  // 切换到 60 分
  const m60Btn = document.querySelector('.kperiod[data-p="m60"]');
  assert.ok(m60Btn, "页面应存在 60分 周期按钮");
  m60Btn.dispatchEvent(new window.Event("click"));
  await new Promise(r => setTimeout(r, 80));
  assert.ok(fetchCalls.some(c => c.url.includes("/api/kline") && c.url.includes("period=m60")),
    "应发起 /api/kline?period=m60 请求");
  const title = document.getElementById("klineTitle").textContent;
  assert.ok(title.includes("60分K") && title.includes("4 根"),
    `m60 只有 4 根时不应 fallback 成其他周期或卡在 loading；当前标题：${title}`);
});

test("历史分时弹窗（缺陷#14 回归）：双击 K 线打开 modal 取数，renderHistChart 正确 setOption（非白图）", async (t) => {
  if (!jsdomMod) { t.skip("jsdom 未安装（npm i -D jsdom）"); return; }
  MINUTE_EMPTY = false;
  const { window, document, fetchCalls, instances } = await boot();
  // 进入 K线视图，等 day 加载把 _lastKlineList 填满
  document.getElementById("klineBtn").dispatchEvent(new window.Event("click"));
  await new Promise(r => setTimeout(r, 90));
  const p4 = instances.find(i => i.id === "ch4");
  assert.ok(p4, "p4 图表实例应存在（id=ch4）");
  assert.ok(typeof p4.handlers.click === "function", "p4 应注册 click 事件（用于选中日期）");
  // 模拟点击第 3 根 K 线，设置 _lastKlineIdx
  p4.handlers.click({ dataIndex: 3 });
  assert.ok(typeof p4.handlers.dblclick === "function", "p4 应注册 dblclick（历史分时）事件");
  // 双击触发 showHistMinute
  p4.handlers.dblclick();
  // showHistMinute 先显示 modal 再 fetch /api/minute
  assert.ok(!document.getElementById("histModal").classList.contains("hidden"), "双击后应弹出历史分时 modal");
  await new Promise(r => setTimeout(r, 90));
  assert.ok(fetchCalls.some(c => c.url.includes("/api/minute")), "showHistMinute 应请求 /api/minute");
  // renderHistChart 在 fetch 后 setOption —— 这正是「白图」修复的验证点
  const histChart = instances.find(i => i.id === "histChart");
  assert.ok(histChart, "应创建 histChart 实例（id=histChart）");
  assert.ok(histChart._last, "renderHistChart 应调用 setOption 渲染（修复白图）");
  assert.strictEqual(histChart._last.series[0].data.length, 48, "历史分时应渲染全部分钟数据点");
  const msg = document.getElementById("histMsg").textContent;
  const htitle = document.getElementById("histTitle").textContent;
  assert.ok(htitle.includes("历史分时"), `histTitle 应标注「历史分时」；当前：${htitle}`);
  assert.ok(msg.includes("48 点"), `histMsg 应显示数据点数；当前：${msg}`);
});

test("历史分时边界（免费源无数据）：modal 仍显示并提示「暂无历史分时」，不抛错不崩溃", async (t) => {
  if (!jsdomMod) { t.skip("jsdom 未安装（npm i -D jsdom）"); return; }
  MINUTE_EMPTY = true;
  try {
    const { window, document, fetchCalls, instances } = await boot();
    document.getElementById("klineBtn").dispatchEvent(new window.Event("click"));
    await new Promise(r => setTimeout(r, 90));
    const p4 = instances.find(i => i.id === "ch4");
    p4.handlers.click({ dataIndex: 3 });
    p4.handlers.dblclick();
    assert.ok(!document.getElementById("histModal").classList.contains("hidden"), "空数据时 modal 也应弹出");
    await new Promise(r => setTimeout(r, 90));
    assert.ok(fetchCalls.some(c => c.url.includes("/api/minute")), "仍应请求 /api/minute");
    const msg = document.getElementById("histMsg").textContent;
    assert.ok(msg.includes("暂无历史分时"), `空数据应提示暂无历史分时；当前：${msg}`);
  } finally {
    MINUTE_EMPTY = false;
  }
});

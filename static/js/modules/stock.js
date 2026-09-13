// -*- coding: utf-8 -*-
// DeepThinkCompStock · 个股详情 —— 100% 移植 deepthinkSingle 完整前端
// 策略：渲染 deepthinkSingle 完整 DOM（顶部栏/自选管理/搜索/K线7周期/副图配置/
//       资金流明细/复盘记录/右键菜单/历史分时/公告/导出CSV + 全部 modal），
//       由 single-app.js（挂 window.__SINGLE_APP__）驱动全部交互逻辑。
// 数据源：与 deepthinkSingle 完全一致的 /api/* 端点（server.py 已全部实现）。
//
// 【本仓新增】「财务分析」视图（本文件桥接，**不改 single-app.js**）：
//   - 入口：#financeBtn（模板 single-template.js 中已加）
//   - 视图：#financeView（四个标签：财务指标 / 财务诊断 / 成长趋势 / 估值分析）
//   - 数据：GET /api/stock/finance_full（panels/fund_local.py，本地财务面板 65 列）
//   - 渲染：./single-finance.js
//   之所以放在薄壳而不是 single-app.js：后者是 deepthinkSingle 的原样移植（92KB），
//   上游升级时会被覆盖（见 docs/02-架构设计.md §5）。
'use strict';

import { SINGLE_HTML } from './single-template.js';
import { fetchFinance, renderFinance, disposeFinance } from './single-finance.js';

let _booted = false;

// 财务视图状态（跨 tab 切换保留）
let _finCode = null;
let _finData = null;
let _finTab = 'indicators';
let _prevViewId = 'minuteView';   // 进入财务前的视图（分时/K线/自选），返回时精确还原

async function ensureApp() {
  if (window.__SINGLE_APP__ && !_booted) return;
  if (window.__SINGLE_APP__) { _booted = true; return; }
  // single-app.js 是 IIFE（无 export），side-effect import 会执行并挂 window.__SINGLE_APP__
  await import('./single-app.js');
  if (!window.__SINGLE_APP__) {
    console.error('[stock] single-app.js 未定义 window.__SINGLE_APP__');
  }
  _booted = true;
}

// ============== 财务分析视图 ==============
/** 宽容地从行情返回里取现价（不同接口字段名不一）。 */
function pickPrice(d) {
  const tryObj = (o) => {
    if (!o || typeof o !== 'object') return null;
    for (const k of ['price', 'last', 'now', 'current', 'close', 'latest', 'zxj']) {
      const v = o[k];
      if (typeof v === 'number' && v > 0) return v;
      if (typeof v === 'string' && parseFloat(v) > 0) return parseFloat(v);
    }
    return null;
  };
  return tryObj(d) || tryObj(d && (d.quote || d.data || d.stock));
}

async function getPrice(code) {
  try {
    const r = await fetch(`/api/stock/quote?code=${encodeURIComponent(code)}`);
    return pickPrice(await r.json());
  } catch (e) {
    return null;
  }
}

function hideOtherViews() {
  ['minuteView', 'klineView', 'watchlistView'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  });
}

/**
 * 通知 single-app 重算图表尺寸。
 *
 * 背景：财务视图打开时会把 minuteView/klineView 置为 display:none。ECharts 在隐藏容器上
 * resize/setOption 只能拿到 0×0，导致切回 K线/分时 时图像被压成一条。single-app 内部注册了
 * window.resize 处理器（按当前 _view resize 对应图表 + 同步右侧高度），因此这里主动派发一次
 * resize 事件即可修复——无需改动 single-app.js。
 * 下一帧 + 100ms 双保险：容器 display 切换后布局需要一帧才生效。
 */
function notifyViewResize() {
  // 用 window 自身的 Event 构造器（jsdom 下 Node 的 Event 无法被 window.dispatchEvent 接受）
  const fire = () => window.dispatchEvent(new window.Event('resize'));
  if (window.requestAnimationFrame) window.requestAnimationFrame(fire);
  setTimeout(fire, 100);
}

/** 仅隐藏财务视图（视图切换交由 single-app），用于点顶栏 K线/自选/返回。 */
function hideFinanceView() {
  document.getElementById('financeView')?.classList.add('hidden');
}

// ============== 分时 tooltip 数字格式化（桥接，不改 single-app.js） ==============
/**
 * single-app.js 的分时 tooltip 用默认格式，会把原始浮点全部打印
 * （如 涨跌幅 -1.6578308922634672）。这里统一：涨跌幅保留 4 位小数、价格保留 2 位。
 */
function fmtMinuteTooltip(params) {
  const arr = Array.isArray(params) ? params : [params];
  if (!arr.length) return '';
  const head = arr[0] && arr[0].axisValue != null ? String(arr[0].axisValue) : '';
  const rows = arr.map((p) => {
    const raw = Array.isArray(p.data) ? p.data[p.data.length - 1] : p.data;
    const v = Number(raw);
    if (!isFinite(v)) return '';
    const txt = p.seriesName === '涨跌幅' ? `${v.toFixed(4)}%` : v.toFixed(2);
    return `${p.marker || ''}${p.seriesName}  <b>${txt}</b>`;
  }).filter(Boolean);
  return `${head}<br>${rows.join('<br>')}`;
}

/**
 * 桥接 echarts.init → setOption：仅当图表含「涨跌幅」系列（即分时主图）时注入数字格式化
 * tooltip。刻意不改 single-app.js（架构铁律：上游升级会覆盖）。
 */
function patchEchartsTooltip() {
  const ec = window.echarts;
  if (!ec || typeof ec.init !== 'function' || ec.__dtTooltipPatched) return;
  const origInit = ec.init.bind(ec);
  ec.init = function (...args) {
    const inst = origInit(...args);
    if (!inst || typeof inst.setOption !== 'function') return inst;
    const origSet = inst.setOption.bind(inst);
    inst.setOption = function (opt, ...rest) {
      try {
        if (opt && opt.tooltip && Array.isArray(opt.series)
            && opt.series.some((s) => s && s.name === '涨跌幅')) {
          opt = Object.assign({}, opt, {
            tooltip: Object.assign({}, opt.tooltip, { formatter: fmtMinuteTooltip }),
          });
        }
      } catch (_) { /* 保底：按原样设置 */ }
      return origSet(opt, ...rest);
    };
    return inst;
  };
  ec.__dtTooltipPatched = true;
}

/** 当前可见的图表视图 id（进入财务前记录用）。 */
function currentVisibleViewId() {
  for (const id of ['minuteView', 'klineView', 'watchlistView']) {
    const el = document.getElementById(id);
    if (el && !el.classList.contains('hidden')) return id;
  }
  return 'minuteView';
}

/** 打开（并渲染）财务分析视图。 */
async function openFinance(code) {
  const view = document.getElementById('financeView');
  const body = document.getElementById('finBody');
  const meta = document.getElementById('finMeta');
  if (!view || !body) return;
  _prevViewId = currentVisibleViewId();   // 记录进入前的视图（分时/K线/自选）
  hideOtherViews();
  view.classList.remove('hidden');

  if (_finCode !== code || !_finData) {
    body.innerHTML = '<div class="muted" style="padding:12px">财务数据加载中…</div>';
    const price = await getPrice(code);
    _finData = await fetchFinance(code, price);
    _finCode = code;
    _finTab = 'indicators';
    document.querySelectorAll('#finTabs .fin-tab').forEach((x) =>
      x.classList.toggle('active', x.dataset.t === 'indicators'));
  }
  renderFinance(body, _finData, _finTab, window.echarts);
  if (meta) {
    const lat = (_finData && _finData.card && _finData.card.latest) || {};
    meta.textContent = `${code} · 本地面板 · 报告期 ${lat.period || '--'} · 共 ${
      (_finData && _finData.card && _finData.card.n_periods_total) || 0
    } 期`;
  }
}

function closeFinance() {
  document.getElementById('financeView')?.classList.add('hidden');
  // 精确还原进入财务前的视图（分时/K线/自选）；single-app 的 _view 状态未变，可正确 resize
  document.getElementById(_prevViewId)?.classList.remove('hidden');
  notifyViewResize();   // 关键：重算被隐藏过的图表尺寸，否则会压缩
}

/** 绑定财务视图的交互（SINGLE_HTML 每次重建，故每次重新绑定）。 */
function bindFinance(code) {
  const btn = document.getElementById('financeBtn');
  if (btn) {
    btn.addEventListener('click', () => {
      const v = document.getElementById('financeView');
      if (v && !v.classList.contains('hidden')) closeFinance();
      else openFinance(code);
    });
  }
  const back = document.getElementById('finBack');
  if (back) back.addEventListener('click', closeFinance);
  // 顶栏「K线 / 自选 / 返回」由 single-app 切换视图：同步隐藏财务视图 + 重算图表尺寸（防压缩）
  ['klineBtn', 'watchlistBtn', 'backBtn'].forEach((id) => {
    const b = document.getElementById(id);
    if (b) b.addEventListener('click', () => { hideFinanceView(); notifyViewResize(); });
  });
  document.querySelectorAll('#finTabs .fin-tab').forEach((t) => {
    t.addEventListener('click', () => {
      document.querySelectorAll('#finTabs .fin-tab').forEach((x) =>
        x.classList.toggle('active', x === t));
      _finTab = t.dataset.t || 'indicators';
      renderFinance(document.getElementById('finBody'), _finData, _finTab, window.echarts);
    });
  });
}

// ============== 加载个股详情（完整 deepthinkSingle 界面） ==============
export async function loadAll(full) {
  console.log('[stock/loadAll] START code=', full);
  const pane = document.getElementById('pane-stock');
  if (!pane) { console.error('[stock/loadAll] 找不到 #pane-stock'); return; }
  disposeFinance();          // 重建 DOM 前释放上一次个股页的财务图表实例（防内存泄漏）
  pane.innerHTML = SINGLE_HTML;
  await ensureApp();
  if (window.__SINGLE_APP__) {
    patchEchartsTooltip();             // 【新增】分时 tooltip 数字格式化（须在 boot 前）
    window.__SINGLE_APP__.boot(full);
    bindFinance(full);                 // 【新增】绑定财务分析入口
  } else {
    pane.innerHTML = '<div class="empty-hint">单股详情应用加载失败（single-app.js 未就绪）</div>';
  }
}

export function render(code, from) {
  loadAll(code);
}

export function cleanTimers() {
  if (window.__SINGLE_APP__ && window.__SINGLE_APP__.cleanup) window.__SINGLE_APP__.cleanup();
  disposeFinance();
}

export function resetView() {
  if (window.__SINGLE_APP__ && window.__SINGLE_APP__.reset) window.__SINGLE_APP__.reset();
}

export function switchToKline() {
  if (window.__SINGLE_APP__ && window.__SINGLE_APP__.switchToKline) window.__SINGLE_APP__.switchToKline();
}

export function switchToMinute() {
  if (window.__SINGLE_APP__ && window.__SINGLE_APP__.switchToMinute) window.__SINGLE_APP__.switchToMinute();
}

export { SINGLE_HTML };

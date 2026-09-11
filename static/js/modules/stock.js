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
import { fetchFinance, renderFinance } from './single-finance.js';

let _booted = false;

// 财务视图状态（跨 tab 切换保留）
let _finCode = null;
let _finData = null;
let _finTab = 'indicators';

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

/** 打开（并渲染）财务分析视图。 */
async function openFinance(code) {
  const view = document.getElementById('financeView');
  const body = document.getElementById('finBody');
  const meta = document.getElementById('finMeta');
  if (!view || !body) return;
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
  // 回到分时视图（single-app 的 _view 状态会在点 K线/自选时自行同步）
  document.getElementById('minuteView')?.classList.remove('hidden');
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
  pane.innerHTML = SINGLE_HTML;
  await ensureApp();
  if (window.__SINGLE_APP__) {
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

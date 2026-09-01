// -*- coding: utf-8 -*-
// DeepThinkCompStock · 个股详情 —— 100% 移植 deepthinkSingle 完整前端
// 策略：渲染 deepthinkSingle 完整 DOM（顶部栏/自选管理/搜索/K线7周期/副图配置/
//       资金流明细/复盘记录/右键菜单/历史分时/公告/导出CSV + 全部 modal），
//       由 single-app.js（挂 window.__SINGLE_APP__）驱动全部交互逻辑。
// 数据源：与 deepthinkSingle 完全一致的 /api/* 端点（server.py 已全部实现）。
'use strict';

import { SINGLE_HTML } from './single-template.js';

let _booted = false;

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

// ============== 加载个股详情（完整 deepthinkSingle 界面） ==============
export async function loadAll(full) {
  console.log('[stock/loadAll] START code=', full);
  const pane = document.getElementById('pane-stock');
  if (!pane) { console.error('[stock/loadAll] 找不到 #pane-stock'); return; }
  pane.innerHTML = SINGLE_HTML;
  await ensureApp();
  if (window.__SINGLE_APP__) {
    window.__SINGLE_APP__.boot(full);
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

/** -*- coding: utf-8 -*- */
/** DeepThinkCompStock · 前端主入口（P3）
 * 职责: 侧栏(持仓录入/当前/预算) + Tab 路由 + 策略 Tab 渲染 + 跳转衔接
 * 模块: holdings(操作卡) / rec(本周推荐) / stock(个股详情) / bt / html / md / log
 */
'use strict';

// 版本签名 — 刷新页面后请打开浏览器控制台（DevTools → Console）确认这行日志
// 若没有这行日志，说明加载到的还是老版本 app.js（被 dropbook/浏览器缓存了）
console.log('%c[DeepThinkCompStock] 主入口 app.js v20260816p loaded — Tab路由(8) + 推荐行点击跳转个股详情', 'color:#5eead4;font-weight:bold');

const API = '';
const MKT_CN = { sh: '沪市', sz: '深市', bj: '北交所' };
const MKT_COLOR = { sh: '#3b82f6', sz: '#10b981', bj: '#f59e0b' };
let pool = [];
let poolMap = {};
let holdings = [];

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

async function fetchJSON(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { const e = await r.json(); msg = e.error || msg; } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function mktOf(code) {
  if (code.startsWith('920') || code.startsWith('8') || code.startsWith('4')) return 'bj';
  if (code.startsWith('60') || code.startsWith('68') || code.startsWith('90')) return 'sh';
  return 'sz';
}

function mktTag(code) {
  const m = mktOf(code);
  return `<span class="mkt" style="background:${MKT_COLOR[m]}">${MKT_CN[m]}</span>`;
}

function adviceTag(a) {
  const map = { '加仓': 'advice-buy', '买入': 'advice-buy', '持有': 'advice-hold',
                '减仓': 'advice-cut', '清仓': 'advice-cut', '观望': 'advice-watch' };
  return `<span class="tag ${map[a] || 'advice-watch'}">${a}</span>`;
}

// ==================== 时钟 ====================
function tick() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  $('#clock').textContent =
    `${now.getFullYear()}/${now.getMonth()+1}/${now.getDate()} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
setInterval(tick, 1000);

// ==================== 标的池 ====================
async function loadPool() {
  const cls = $('#poolCls').value;
  const d = await fetchJSON(`${API}/api/pool?cls=${cls}`);
  pool = d.items;
  poolMap = {};
  for (const p of pool) poolMap[p.code] = p;
  $('#poolCount').textContent = pool.length;
  const dl = $('#poolList');
  dl.innerHTML = '';
  for (const p of pool) {
    const opt = document.createElement('option');
    opt.value = `${p.code} ${p.name}`;
    dl.appendChild(opt);
  }
}

// ==================== 持仓 ====================
async function loadHoldings() {
  const d = await fetchJSON(`${API}/api/holdings`);
  holdings = d.items;
  renderHoldings();
}

function renderHoldings() {
  $('#holdCount').textContent = holdings.length;
  $('#holdTable').innerHTML = holdings.length ? holdings.map(h => {
    const mk = mktOf(h.code);
    return `<tr data-code="${h.code}">
      <td><b>${h.code}</b> ${escapeHtml(h.name || '')}</td>
      <td class="num">${(+h.amount || 0).toLocaleString()}</td>
      <td>${h.dingtou ? '<span class="tag tag-up">定投</span>' : '—'}</td>
      <td>${h.date || '—'}</td></tr>`;
  }).join('') : '<tr><td colspan="4" class="empty" style="padding:14px">暂无持仓</td></tr>';
}

// ==================== 添加/删除持仓 ====================
async function addHolding() {
  const raw = $('#poolInput').value.trim();
  if (!raw) { alert('请先输入/选择标的'); return; }
  const code = (raw.match(/\d{6}/) || [raw.split(' ')[0]])[0];
  if (!poolMap[code]) { alert(`标的 ${code} 不在池中`); return; }
  const amount = parseFloat($('#holdAmount').value) || 0;
  const dingtou = $('#holdDingtou').checked;
  try {
    await fetchJSON(`${API}/api/holdings`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ code, amount, dingtou })
    });
    $('#poolInput').value = '';
    await loadHoldings();
    await renderHoldingsPane();
  } catch (e) { alert(e.message); }
}

async function delHoldings() {
  const codes = [...$$('#holdTable tr[data-code].selected')].map(tr => tr.dataset.code);
  if (!codes.length) { alert('请先勾选要删除的持仓（点击表格行选中）'); return; }
  if (!confirm(`删除 ${codes.length} 条持仓？`)) return;
  await fetchJSON(`${API}/api/holdings/delete`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ codes })
  });
  await loadHoldings();
  await renderHoldingsPane();
}

// ==================== 设置 ====================
async function loadSettings() {
  const s = await fetchJSON(`${API}/api/settings`);
  $('#setWeekly').value = s.weekly;
  $('#setNewpos').value = s.newpos;
  $('#setAutoTrack').checked = !!s.auto_track;
  $('#autoTrack').checked = !!s.auto_track;
}

async function saveSettings() {
  await fetchJSON(`${API}/api/settings`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      weekly: parseFloat($('#setWeekly').value) || 0,
      newpos: parseFloat($('#setNewpos').value) || 0,
      auto_track: $('#setAutoTrack').checked
    })
  });
}

// ==================== 保存并分析 ====================
let pollTimer = null;

async function doAnalyze() {
  await saveSettings();
  const forceRefresh = $('#forceRefresh').checked;
  const autoTrack = $('#autoTrack').checked;
  $('#btnAnalyze').disabled = true;
  setProgress('running', 2, '提交分析...');
  try {
    await fetchJSON(`${API}/api/analyze`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ force_refresh: forceRefresh, auto_track: autoTrack })
    });
    // P4: 优先 SSE 实时进度；EventSource 不支持/失败时回退轮询
    if (typeof EventSource !== 'undefined') {
      const es = new EventSource(`${API}/api/analyze/events`);
      let done = false;
      es.addEventListener('progress', e => {
        try {
          const d = JSON.parse(e.data);
          $('#statusText').textContent = d.message || '';
          setProgress(d.running ? 'running' : (d.percent >= 100 ? 'done' : ''),
                      d.percent || 0, d.message || '');
        } catch (_) {}
      });
      es.addEventListener('done', async e => {
        try { const res = JSON.parse(e.data); if (res && res.signal_date) await renderAll(res); } catch (_) {}
        done = true; es.close();
        $('#btnAnalyze').disabled = false;
        setProgress('done', 100, '分析完成');
      });
      es.addEventListener('close', () => {
        if (!done) {
          // 未收到 done（可能异常结束）→ 兜底查询一次状态
          es.close(); pollAnalyze();
        }
      });
      es.onerror = () => {
        if (!done) { es.close(); pollAnalyze(); }   // SSE 断开 → 回退轮询
      };
      // 兜底：SSE 10s 内无任何事件则回退轮询（某些代理会吞 SSE）
      const sseTimer = setTimeout(() => {
        if (!done) { es.close(); pollAnalyze(); }
      }, 10000);
      es.addEventListener('progress', () => clearTimeout(sseTimer), { once: true });
      return;
    }
    pollTimer = setInterval(pollAnalyze, 1500);
    pollAnalyze();
  } catch (e) {
    alert(e.message); setProgress('', 0, '等待');
    $('#btnAnalyze').disabled = false;
  }
}

async function pollAnalyze() {
  try {
    const s = await fetchJSON(`${API}/api/analyze/status`);
    $('#statusText').textContent = s.running ? s.message : (s.result ? '分析完成' : '就绪');
    setProgress(s.running ? 'running' : (s.percent >= 100 ? 'done' : ''),
                s.percent || 0, s.running ? s.message : (s.percent >= 100 ? '完成' : '等待'));
    if (!s.running) {
      clearInterval(pollTimer); pollTimer = null;
      $('#btnAnalyze').disabled = false;
      if (s.result) { await renderAll(s.result); }
    }
  } catch (e) {
    clearInterval(pollTimer); pollTimer = null;
    $('#btnAnalyze').disabled = false;
  }
}

function setProgress(state, pct, label) {
  const w = $('#progressWrap');
  w.classList.remove('done', 'error');
  if (state) w.classList.add(state);
  $('#progressFill').style.width = (pct || 0) + '%';
  $('#progressState').textContent = label || '';
}

// ==================== Tab 渲染: 持仓操作卡 ====================
async function renderHoldingsPane() {
  try {
    const s = await fetchJSON(`${API}/api/analyze/status`);
    if (s.result) renderCardTable(s.result);
    else showCardEmpty('暂无持仓，请先在左侧录入或直接 [保存并分析]');
  } catch (e) { showCardEmpty('加载失败: ' + (e.message || e)); }
}

function showCardEmpty(msg) {
  $('#pane-holdings').innerHTML = `<div class="pane-head"><span>持仓分析</span><span class="signal"></span></div><div class="empty">${escapeHtml(msg)}</div>`;
}

function codeLink(code) {
  return `<td data-code="${code}" class="code-click" title="点击查看个股行情"><b>${code}</b></td>`;
}

function renderCardTable(res) {
  const heldCodes = new Set(holdings.map(h => h.code));
  const cards = (res.cards || []).filter(c => heldCodes.has(c.code));
  let head = `<div class="pane-head"><span>持仓分析（点击代码查看行情）</span>
    <span class="signal">${cards.length ? `信号日 ${res.signal_date} · ${res.summary.regime_cn}` : ''}</span></div>`;
  if (!cards.length) {
    $('#pane-holdings').innerHTML = head + '<div class="empty">暂无持仓，请先在左侧录入或直接 [保存并分析]</div>';
    return;
  }
  const rows = cards.map(c => `<tr>
    ${codeLink(c.code)}
    <td>${escapeHtml(c.name)}</td><td>${escapeHtml(c.industry || '—')}</td><td>${mktTag(c.code)}</td>
    <td class="num"><b>${c.score.toFixed(0)}</b></td>
    <td>${adviceTag(c.advice)}</td><td>${c.action || '—'}</td>
    <td style="color:#6b7280">${escapeHtml(c.desc)}</td></tr>`).join('');
  $('#pane-holdings').innerHTML = head + `<table>
    <thead><tr><th>代码</th><th>名称</th><th>行业</th><th>市场</th><th class="num">评分</th><th>建议</th><th>本周操作</th><th>说明</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <div class="note">点击代码可查看该股实时行情详情。</div>`;
  bindCodeClicks();
}

// ==================== Tab 渲染: 本周推荐 ====================
function renderRecs(res) {
  // [DEBUG] 记录渲染输入数据
  console.log('[renderRecs] 信号日:', res.signal_date, '| regime:', res.summary?.regime_cn);
  console.log('[renderRecs] selected_recommends count:', (res.selected_recommends || []).length);
  console.log('[renderRecs] recommends count:', (res.recommends || []).length);
  if ((res.selected_recommends || []).length) {
    const c = res.selected_recommends[0];
    console.log('[renderRecs] 首个 selected sample:', JSON.stringify({
      code: c.code, name: c.name, is_top: c.is_top, held: c.held,
      fea_ratio: c.fea_ratio, one_hand: c.one_hand,
      desc_len: (c.desc || '').length, desc_sample: (c.desc || '').slice(0, 60),
    }));
  }
  if ((res.recommends || []).length) {
    const c = res.recommends[0];
    console.log('[renderRecs] 首个 recommends sample:', JSON.stringify({
      code: c.code, name: c.name, is_top: c.is_top, held: c.held,
      fea_ratio: c.fea_ratio, desc_len: (c.desc || '').length, desc_sample: (c.desc || '').slice(0, 60),
    }));
  }
  const selected = res.selected_recommends || [];
  const others = res.recommends || [];
  const sortFn = (a, b) => (a.held ? 0 : 1) - (b.held ? 0 : 1) || b.score - a.score;
  selected.sort(sortFn);
  others.sort(sortFn);

  const head = `<div class="pane-head"><span>本周推荐（点击代码查看行情）</span>
    <span class="signal">信号日 ${res.signal_date} · ${res.summary.regime_cn}</span></div>`;

  if (!selected.length && !others.length) {
    $('#pane-rec').innerHTML = head + '<div class="empty">暂无推荐，请先 [保存并分析]</div>';
    return;
  }

  const thead = `<thead><tr>
    <th style="width:14%">代码</th><th>名称</th><th>行业</th><th>市场</th>
    <th class="num" style="width:6%">评分</th><th>建议</th><th>本周操作</th><th>说明</th>
  </tr></thead>`;

  const row = c => {
    const star = c.is_top ? '<span class="tag tag-star">⭐精选</span>' : '';
    const heldTag = c.held ? '<span class="tag tag-held">已持仓</span>' : '';
    let budget = '';
    if (c.is_top && c.fea_ratio != null)
      budget = `<span class="tag tag-budget" title="一手 ${c.one_hand.toFixed(0)}元 ÷ 单仓预算">占预算 ${c.fea_ratio.toFixed(0)}%</span>`;
    else if (!c.is_top && c.fea_ratio > 100)
      budget = `<span class="tag tag-over">超预算 ${(c.fea_ratio - 100).toFixed(0)}%</span>`;
    // 第一列：代码 + 徽章 用 <div class="cell-code"> 包裹（flex 横排）；desc 列用 <div class="cell-desc"> 包裹（保留换行）
    return `<tr class="${c.is_top ? 'rec-top' : 'rec-buy'}">
      <td data-code="${c.code}" class="code-click" title="点击查看个股行情">
        <div class="cell-code"><b class="code-text">${c.code}</b>${star}${heldTag}${budget}</div>
      </td>
      <td>${escapeHtml(c.name)}</td><td>${escapeHtml(c.industry || '—')}</td><td>${mktTag(c.code)}</td>
      <td class="num score-buy"><b>${c.score.toFixed(0)}</b></td>
      <td>${adviceTag(c.advice)}</td><td>${c.action || '—'}</td>
      <td style="color:#6b7280;font-size:12px" title="${escapeHtml(c.desc || '')}"><div class="cell-desc">${escapeHtml(c.desc)}</div></td></tr>`;
  };

  const sectionRow = (icon, title, tip) =>
    `<tr class="rec-section"><td colspan="8">${icon} <b>${title}</b>（${tip}）</td></tr>`;

  let body = '';
  if (selected.length) {
    body += sectionRow('⭐', '本周最值得买入', '已通过<b>资金可行性筛选</b>+模型评分，整行标红，点击代码看行情');
    body += selected.map(row).join('');
  }
  if (others.length) {
    body += sectionRow('📋', '更多候选', '评分高但<b>价格超出单仓预算</b>暂未入精选，可作替补观察');
    body += others.map(row).join('');
  }

  $('#pane-rec').innerHTML = head + `<table class="rec-table">${thead}<tbody>${body}</tbody></table>`;
  // [DEBUG] 渲染后报告行列数 + 徽章是否真实存在
  const renderedTable = $('#pane-rec table');
  console.log('[renderRecs] 渲染完 table 行数:', renderedTable?.rows.length, '| HTML 长度:', body.length);
  console.log('[renderRecs] ⭐精选数:', (body.match(/rec-top/g) || []).length,
              '| 📋更多候选数:', (body.match(/rec-buy/g) || []).length);
  console.log('[renderRecs] 徽章星星数:', (body.match(/tag-star/g) || []).length,
              '| 已持仓数:', (body.match(/tag-held/g) || []).length,
              '| 占预算数:', (body.match(/tag-budget/g) || []).length,
              '| 超预算数:', (body.match(/tag-over/g) || []).length);
  bindCodeClicks();
  // 推荐表行点击：单只高亮 + 进入详情（点击行内"代码"列直接触发 stock 跳转）
  $$('#pane-rec tbody tr').forEach(tr => {
    tr.addEventListener('click', e => {
      $$('#pane-rec tbody tr.selected').forEach(t => t.classList.remove('selected'));
      tr.classList.add('selected');
    });
  });
}

// ==================== 跳转衔接（核心） ====================
function bindCodeClicks() {
  $$('.code-click').forEach(td => {
    td.onclick = () => {
      const code = td.dataset.code;
      // 补市场前缀
      const m = mktOf(code);
      const full = m + code;
      location.hash = `#/stock/${full}?from=${getActiveTab()}`;
      window.scrollTo(0, 0);
    };
  });
}

function getActiveTab() {
  const t = $$('.tab.active')[0];
  return t ? t.dataset.tab : 'rec';
}

// ==================== 历史回测 ====================
async function renderBt() {
  try {
    const bt = await fetchJSON(`${API}/api/backtest`);
    const schemes = [
      { label: 'current(上证)', key: 'current_全样本1996+' },
      { label: 'A(全指)', key: 'A_全样本1996+' },
      { label: 'B(分市场段)', key: 'B_全样本1996+' },
      { label: 'C(内生)', key: 'C_全样本1996+' },
      { label: 'E(尾部)', key: 'E_全样本1996+' },
    ];
    const labels = schemes.map(s => s.label);
    const ann = schemes.map(s => (bt[s.key]?.annualized || 0) * 100);
    const shp = schemes.map(s => bt[s.key]?.sharpe || 0);

    $('#pane-bt').innerHTML = `
      <div class="grid2">
        <div class="chart-box"><div class="chart-label">年化收益率（全样本 1996+）</div><div id="annChart" class="echart"></div></div>
        <div class="chart-box"><div class="chart-label">夏普比率</div><div id="shpChart" class="echart"></div></div>
      </div>
      <div id="btTable"></div>
      <div class="chart-box tall"><div class="chart-label">策略长期净值曲线（B vs current，对数轴）</div><div id="curveChart" class="echart"></div></div>
      <div class="note">
        <p><b>结论</b>：年化排序 current(上证)≈11.4% ≈ B(分市场段, 修复后)≈11.0% &gt; C(内生)9.8% &gt; A(全指)6.7% &gt; E(尾部)2.3%。修复段指数缺失/未成熟时退化为"无脑放行"的缺陷后，B 回撤收敛到 -56%、2014+ 年化从 0.6% 回升到 7.2%，长期表现已与上证单指数门控基本持平。E（尾部降仓）经多参数验证仍被否定（全样本 2.3%、2014+ -3.1%）。</p>
        <p><b>风控规则</b>：</p>
        <ul style="margin:6px 0 0 18px;line-height:1.7">
          <li><b>仓位规则</b>：单只上限 = 单仓预算 = (现金 × 暴露 0.9) / N；价格 × 100 &gt; 单仓预算则整手不可买（退到 ⭐精选 4 只的"价格×100≤单仓预算"严格筛选）。</li>
          <li><b>空仓规则</b>：任一关键段指数（上证/创业板/科创/北证）跌破 56 周均线即该段清仓；全盘普跌时整体空仓（回测空仓占比见上表）。</li>
          <li><b>退出规则</b>：估值泡沫（PE/PB &gt; 行业中位数 × 2）或基本面恶化（ROE 持续下行 + 负 FCF）→ 估值/基本面双退出（非价格止损）。</li>
        </ul>
      </div>`;

    const mkBar = (elId, data, fmt) => {
      const el = document.getElementById(elId);
      if (!el || typeof echarts === 'undefined') return;
      const chart = echarts.init(el);
      chart.setOption({
        tooltip: { trigger: 'item', formatter: p => `${p.name}: ${fmt(p.value)}` },
        grid: { left: 50, right: 16, top: 20, bottom: 30 },
        xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 11, color: '#6b7280' } },
        yAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#6b7280', formatter: v => fmt(v) } },
        series: [{ type: 'bar', data, barWidth: '55%',
          itemStyle: { color: p => p.value >= 0 ? '#10b981' : '#ef4444', borderRadius: [4, 4, 0, 0] } }],
      });
    };
    mkBar('annChart', ann, v => v.toFixed(1) + '%');
    mkBar('shpChart', shp, v => v.toFixed(2));

    let rows = '';
    for (const s of schemes) {
      const r = bt[s.key];
      if (!r) continue;
      const tag = s.key === 'current_全样本1996+' ? ' <span class="tag tag-mid">历史最优(基准)</span>'
                : (s.key === 'B_全样本1996+' ? ' <span class="tag tag-up">修复后≈基准</span>' : '');
      rows += `<tr><td>${s.label}${tag}</td><td class="num">${(r.annualized*100).toFixed(1)}%</td>
        <td class="num">${r.sharpe.toFixed(2)}</td>
        <td class="num" style="color:#dc2626">${(r.max_drawdown*100).toFixed(0)}%</td>
        <td class="num">${(r.empty_frac*100).toFixed(0)}%</td>
        <td class="num">${(r.avg_turnover*100).toFixed(0)}%</td></tr>`;
    }
    $('#btTable').innerHTML = `<table><thead><tr><th>方案</th><th class="num">年化</th><th class="num">夏普</th><th class="num">最大回撤</th><th class="num">空仓占比</th><th class="num">换手</th></tr></thead><tbody>${rows}</tbody></table>`;

    // 净值曲线（P5-修复：去掉静默 catch，确保曲线画出来；echarts 未加载时给明确提示）
    const curveEl = document.getElementById('curveChart');
    if (!curveEl) {
      const div = document.createElement('div');
      div.className = 'warn';
      div.textContent = '净值曲线容器未初始化（请重新切换 Tab 或刷新页面）';
      document.querySelector('#pane-bt').appendChild(div);
    } else if (typeof echarts === 'undefined') {
      curveEl.innerHTML = '<div class="empty">ECharts 未加载，请检查 /static/js/echarts.min.js 是否可达</div>';
    } else {
      fetchJSON(`${API}/api/curves`)
        .then(curves => {
          const bk = curves['B_全样本1996+'];
          const ck = curves['current_全样本1996+'];
          if (!bk) { curveEl.innerHTML = '<div class="empty">曲线数据缺失</div>'; return; }
          const dates = bk.dates.map(d => String(d));
          const minEq = Math.max(0.1, Math.min(...bk.equity.filter(v => v > 0), ...(ck?.equity || []).filter(v => v > 0)));
          const chart = echarts.init(curveEl);
          chart.setOption({
            tooltip: { trigger: 'axis' },
            legend: { data: ['B(分市场段)', 'current(上证)'], textStyle: { fontSize: 11 } },
            grid: { left: 55, right: 16, top: 30, bottom: 30 },
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10, color: '#6b7280', formatter: v => String(v).slice(0, 4) } },
            yAxis: { type: 'log', min: minEq, max: Math.max(...bk.equity), axisLabel: { fontSize: 10, color: '#6b7280' } },
            series: [
              { name: 'B(分市场段)', type: 'line', data: bk.equity, showSymbol: false, lineStyle: { width: 2, color: '#2ecc71' } },
              ...(ck ? [{ name: 'current(上证)', type: 'line', data: ck.equity, showSymbol: false, lineStyle: { width: 1.5, color: '#4aa3ff' } }] : []),
            ],
          });
        })
        .catch(e => { curveEl.innerHTML = '<div class="empty">净值曲线加载失败: ' + escapeHtml(e.message || e) + '</div>'; });
    }
  } catch (e) {
    $('#pane-bt').innerHTML = `<div class="empty">回测数据加载失败: ${escapeHtml(e.message || e)}</div>`;
  }
}

// ==================== 报告 / 日志 ====================
function renderHtmlReport() {
  $('#pane-html').innerHTML = `
    <div class="report-actions">
      <button class="btn primary" id="btnOpenHtml">打开最新 HTML 报告</button>
      <span class="hint">报告由 [保存并分析] 时生成</span>
    </div>
    <iframe id="htmlFrame" class="report-frame" src="/report/latest"></iframe>`;
  $('#btnOpenHtml').onclick = () => window.open('/report/latest', '_blank');
}

async function mdPreview() {
  try {
    const r = await fetch(`${API}/api/report/md`);
    if (!r.ok) { const e = await r.json(); alert(e.error || '请先保存并分析'); return; }
    $('#pane-md').innerHTML = `
      <div class="report-actions">
        <button class="btn primary" id="btnMdDownload">生成并下载 MD 报告</button>
        <button class="btn" id="btnMdPreview">刷新预览</button>
      </div>
      <pre class="md-box">${escapeHtml(await r.text())}</pre>`;
    $('#btnMdDownload').onclick = () => triggerDownload(`${API}/api/report/md?download=1`, 'report.md');
    $('#btnMdPreview').onclick = mdPreview;
  } catch (e) {
    $('#pane-md').innerHTML = `<div class="report-actions"><button class="btn primary" id="btnMdPreview">预览</button></div><pre class="md-box">加载失败: ${escapeHtml(e.message || e)}</pre>`;
    $('#btnMdPreview').onclick = mdPreview;
  }
}

let logCache = [];
async function renderLog() {
  try {
    const d = await fetchJSON(`${API}/api/logs`);
    logCache = d.items || [];
    drawLog('all');
  } catch (e) {
    $('#pane-log').innerHTML = `<div class="empty">日志加载失败: ${escapeHtml(e.message || e)}</div>`;
  }
}

function parseLogLevel(msg) {
  if (/异常|失败|错误|Error|fail|traceback/i.test(msg)) return 'error';
  if (/警告|Warn|warning/i.test(msg)) return 'warn';
  if (/完成|成功|已写|加载|缓存|Done|OK/i.test(msg)) return 'success';
  return 'info';
}

function drawLog(filter) {
  const counts = { info: 0, success: 0, warn: 0, error: 0 };
  const parsed = logCache.map(line => {
    const m = line.match(/^\[([^\]]+)\]\s*(.*)$/);
    const ts = m ? m[1] : '';
    const msg = m ? m[2] : line;
    const level = parseLogLevel(msg);
    counts[level]++;
    return { ts, level, msg };
  });
  const visible = filter === 'all' ? parsed : parsed.filter(l => l.level === filter);
  $('#pane-log').innerHTML = `
    <div class="log-stats">
      <span>总计 <b>${parsed.length}</b> 条</span>
      <span class="success">成功 <b>${counts.success}</b></span>
      <span class="warn">警告 <b>${counts.warn}</b></span>
      <span class="err">错误 <b>${counts.error}</b></span>
    </div>
    <div class="report-actions">
      <button class="btn primary" id="btnLogDownload">下载日志文件</button>
      <button class="btn" id="btnLogRefresh">刷新</button>
      <select id="logFilter" class="filter-sel">
        <option value="all">全部级别</option><option value="success">仅成功</option>
        <option value="warn">仅警告</option><option value="error">仅错误</option><option value="info">仅信息</option>
      </select>
    </div>
    <div class="md-box log-list">${visible.length ? visible.slice().reverse().map(l =>
      `<div class="log-line ${l.level}"><span class="ts">${escapeHtml(l.ts)}</span><span class="lvl">${l.level.toUpperCase()}</span><span class="msg">${escapeHtml(l.msg)}</span></div>`
    ).join('') : '<div class="empty">无匹配日志</div>'}</div>`;
  $('#btnLogDownload').onclick = () => triggerDownload(`${API}/api/logs/download`, 'analyze.log');
  $('#btnLogRefresh').onclick = renderLog;
  $('#logFilter').onchange = e => drawLog(e.target.value);
}

// ==================== 下载工具 ====================
function triggerDownload(url, filename) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || '';
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => a.remove(), 100);
}

// ==================== 路由 ====================
async function dispatchRoute() {
  const hash = location.hash.slice(1) || '/holdings';
  const [pathAndQuery] = hash.split('?');
  const parts = pathAndQuery.split('/').filter(Boolean);   // ['stock','sh600519']
  const tab = parts[0] || 'holdings';

  // 个股详情（承接跳转）
  if (tab === 'stock' && parts[1]) {
    setActiveTab('stock', false);
    const full = parts[1];
    const from = new URLSearchParams(hash.split('?')[1]).get('from') || 'rec';
    await import('./modules/stock.js').then(m => m.render(full, from));
    return;
  }

  setActiveTab(tab);
  switch (tab) {
    case 'holdings': await renderHoldingsPane(); break;
    case 'rec': {
      try {
        const s = await fetchJSON(`${API}/api/analyze/status`);
        if (s.result) renderRecs(s.result);
        else $('#pane-rec').innerHTML = '<div class="empty">暂无推荐，请先 [保存并分析]</div>';
      } catch (e) { $('#pane-rec').innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`; }
      break;
    }
    case 'bt': await renderBt(); break;
    case 'html': renderHtmlReport(); break;
    case 'md': await mdPreview(); break;
    case 'log': await renderLog(); break;
  }
}

function setActiveTab(tab, scroll = true) {
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  $$('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `pane-${tab}`));
}

// ==================== 全量渲染 ====================
async function renderAll(res) {
  await loadHoldings();
  const active = getActiveTab();
  if (active === 'holdings') await renderHoldingsPane();
  else if (active === 'rec') renderRecs(res);
}

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', async () => {
  tick();
  try {
    await loadPool();
    await loadHoldings();
    await loadSettings();
    await dispatchRoute();
  } catch (e) {
    $('#statusText').textContent = '初始化失败: ' + e.message;
  }

  $('#btnAdd').addEventListener('click', addHolding);
  $('#btnDel').addEventListener('click', delHoldings);
  $('#btnAnalyze').addEventListener('click', doAnalyze);
  $('#btnLog').addEventListener('click', () => { location.hash = '#/log'; });
  $('#poolCls').addEventListener('change', loadPool);
  $('#holdTable').addEventListener('click', e => {
    const tr = e.target.closest('tr[data-code]');
    if (tr) tr.classList.toggle('selected');
  });
  $('#autoTrack').addEventListener('change', () => $('#setAutoTrack').checked = $('#autoTrack').checked);
  $('#setAutoTrack').addEventListener('change', () => $('#autoTrack').checked = $('#setAutoTrack').checked);
  $$('.tab').forEach(t => t.addEventListener('click', () => {
    location.hash = `#/${t.dataset.tab}`;
  }));
  window.addEventListener('hashchange', dispatchRoute);
});

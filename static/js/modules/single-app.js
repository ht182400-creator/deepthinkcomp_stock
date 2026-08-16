/* 个股主力追踪 - 前端逻辑（搜索 + 三面板 + K线面板 + 视图切换） */
(function () {
  "use strict";

  const REFRESH_MS = 30000;
  const DARK = {
    bg: "#0d1117", axis: "#30363d", label: "#8b949e",
    up: "#f85149", down: "#3fb950", gray: "#6e7681",
    price: "#f0f6fc", avg: "#e3b341", purple: "#8957e5",
  };

  let charts = { p1: null, p2: null, p3: null, p4: null, p5: null };
  let _minuteList = [];              // 最近一次分时图渲染的数据（用于键盘切换分钟）
  let _minuteQuote = null;           // 最近一次报价（用于渲染分钟详情）
  let _selectedMinuteIdx = -1;       // 用户方向键选中的分钟索引，-1 = 不选中
  let current = "sh600519";
  let timer = null;
  let latestData = null;
  let _view = "minute";       // minute | kline

  const $ = (id) => document.getElementById(id);

  function baseGrid(extra) {
    return Object.assign({ left: 56, right: 56, top: 20, bottom: 30 }, extra || {});
  }
  function normT(t) {
    if (/^\d{4}$/.test(t)) return t.slice(0, 2) + ":" + t.slice(2);
    return t;
  }

  // ---------- ECharts 初始化 ----------
  function initCharts() {
    charts.p1 = echarts.init($("ch1"));
    charts.p4 = echarts.init($("ch4"));
    // 副图实例按 charts.sub[i] 动态生成（init 之后由 _buildSubcharts 填充）
    charts.sub = [];
  }

  // ---------- 副图类型 + 配置 ----------
  const SUBCHART_TYPES = [
    // 5 个默认
    { id: "volfs",    name: "VOLFS 成交量（每分钟手数，红涨绿跌）" },
    { id: "mainflow", name: "主力追踪（主力净流入折线/面积）" },
    { id: "game",     name: "资金博弈（主力柱 + 散户黄线）" },
    { id: "smallnet", name: "散户净额（每分钟散户累计差分）" },
    { id: "bignet",   name: "大单净额（每分钟大单累计差分）" },
    // 7 个扩展
    { id: "superbig", name: "超大单净额（每分钟超大单累计差分）" },
    { id: "middlenet", name: "中单净额（每分钟中单累计差分）" },
    { id: "power",    name: "买卖力道（主力 - 散户 = 净额折线）" },
    { id: "turnover", name: "换手率（每分钟换手率折线，需流通股本）" },
    { id: "outerbuy", name: "外盘内盘差（外盘 - 内盘）" },
    { id: "amtdiff",  name: "每分钟成交额差分（万元）" },
    { id: "mainratio", name: "主力占比（主力净流入/总成交额 %）" },
    { id: "day5",    name: "近5日主力净流入（柱，东财 f178）" },
  ];
  const SUB_DEFAULT = ["volfs", "mainflow", "game"];   // 默认 3 个副图
  let _subConfig = [];                                   // 运行时配置
  function _loadSubConfig() {
    try {
      const raw = localStorage.getItem("subChartConfig");
      const arr = raw ? JSON.parse(raw) : null;
      if (Array.isArray(arr) && arr.length && arr.length <= 5
          && arr.every(t => SUBCHART_TYPES.some(x => x.id === t))) {
        return arr;
      }
    } catch (e) {}
    return SUB_DEFAULT.slice();
  }
  function _saveSubConfig() {
    try { localStorage.setItem("subChartConfig", JSON.stringify(_subConfig)); } catch (e) {}
  }
  // 动态生成 #subCharts 容器内的 panel（按 _subConfig 顺序）
  function _buildSubcharts() {
    _subConfig = _loadSubConfig();
    const box = $("subCharts"); if (!box) return;
    box.innerHTML = "";
    // 销毁旧实例
    charts.sub.forEach(c => { try { c.dispose(); } catch (e) {} });
    charts.sub = [];
    _subConfig.forEach((tid, idx) => {
      const t = SUBCHART_TYPES.find(x => x.id === tid) || SUBCHART_TYPES[0];
      const panel = document.createElement("section");
      panel.className = "panel";
      panel.innerHTML = `<div class="phead">${t.name}</div><div class="chart" id="subc_${idx}"></div>`;
      box.appendChild(panel);
      const c = echarts.init(panel.querySelector(".chart"));
      charts.sub[idx] = c;
    });
  }
  // 按 _subConfig 顺序渲染每个副图
  function _renderSubcharts(d) {
    _subConfig.forEach((tid, idx) => {
      const c = charts.sub[idx]; if (!c) return;
      const map = {
        volfs: renderVolfs, mainflow: renderFund, game: renderFundGame,
        smallnet: renderSmallNet, bignet: renderBigNet,
        superbig: renderSuperBig, middlenet: renderMiddleNet,
        power: renderPower, turnover: renderTurnover,
        outerbuy: renderOuterBuy, amtdiff: renderAmtDiff,
        mainratio: renderMainRatio, day5: renderDay5,
      };
      const fn = map[tid]; if (fn) fn(d, idx);
    });
  }

  // ---------- K线副图配置（技术指标：MACD/KDJ/BOLL） ----------
  const KLINE_SUB_TYPES = [
    { id: "macd", name: "MACD 指标（DIF/DEA/MACD 柱）" },
    { id: "kdj",  name: "KDJ 随机指标（K/D/J 三线）" },
    { id: "boll", name: "BOLL 布林带（中轨 MA20 + ±2σ）" },
    { id: "rsi",  name: "RSI 相对强弱（6/12/24 三周期）" },
  ];
  const KLINE_SUB_DEFAULT = ["macd", "kdj", "boll"];
  let _klineSubConfig = [];
  function _loadKlineSubConfig() {
    try {
      const raw = localStorage.getItem("klineSubConfig");
      const arr = raw ? JSON.parse(raw) : null;
      if (Array.isArray(arr) && arr.every(t => KLINE_SUB_TYPES.some(x => x.id === t))) return arr;
    } catch (e) {}
    return KLINE_SUB_DEFAULT.slice();
  }
  function _saveKlineSubConfig() {
    try { localStorage.setItem("klineSubConfig", JSON.stringify(_klineSubConfig)); } catch (e) {}
  }
  function _buildKlineSubs() {
    _klineSubConfig = _loadKlineSubConfig();
    const box = $("klineSubs"); if (!box) return;
    box.innerHTML = "";
    charts.klineSub = charts.klineSub || [];
    charts.klineSub.forEach(c => { try { c.dispose(); } catch (e) {} });
    charts.klineSub = [];
    _klineSubConfig.forEach((tid, idx) => {
      const t = KLINE_SUB_TYPES.find(x => x.id === tid) || KLINE_SUB_TYPES[0];
      const panel = document.createElement("section");
      panel.className = "panel";
      panel.style.height = "150px";
      panel.innerHTML = `<div class="phead">${t.name}</div><div class="chart" id="ksub_${idx}" style="height:calc(100% - 28px)"></div>`;
      box.appendChild(panel);
      const c = echarts.init(panel.querySelector(".chart"));
      charts.klineSub[idx] = c;
    });
  }
  function _renderKlineSubs(list) {
    if (!charts.klineSub) return;
    _klineSubConfig.forEach((tid, idx) => {
      const c = charts.klineSub[idx]; if (!c) return;
      if (tid === "macd") renderMacd(list, idx);
      else if (tid === "kdj") renderKdj(list, idx);
      else if (tid === "boll") renderBoll(list, idx);
      else if (tid === "rsi") renderRsi(list, idx);
    });
  }

  // ---------- 技术指标算法（标准实现） ----------
  // 算法抽出为独立可测试模块 static/js/indicators.js（在 app.js 之前加载），
  // 此处仅引用，保证前端与测试共用同一份口径，避免口径漂移（原 D1 bug 即源于无测试）。
  const { ema: _ema, macd: _macd, kdj: _kdj, boll: _boll, rsi: _rsi } = (window.DTIndicators || {});

  // ---------- 技术指标渲染器 ----------
  function renderMacd(list, idx) {
    const c = charts.klineSub[idx]; if (!c) return;
    const dates = list.map(x => x.date);
    const closes = list.map(x => x.close);
    const { dif, dea, macd } = _macd(closes);
    c.setOption(buildKlineSubOption({
      dates,
      yAxis: { splitNumber: 2 },
      series: [
        { name: "DIF", type: "line", data: dif, showSymbol: false, lineStyle: { width: 1, color: "#ffd700" }, itemStyle: { color: "#ffd700" } },
        { name: "DEA", type: "line", data: dea, showSymbol: false, lineStyle: { width: 1, color: "#a371f7" }, itemStyle: { color: "#a371f7" } },
        { name: "MACD", type: "bar", data: macd, barWidth: "60%",
          itemStyle: { color: (p) => p.data >= 0 ? DARK.up : DARK.down } },
      ],
    }));
    c.resize();
  }
  function renderKdj(list, idx) {
    const c = charts.klineSub[idx]; if (!c) return;
    const dates = list.map(x => x.date);
    const highs = list.map(x => x.high), lows = list.map(x => x.low), closes = list.map(x => x.close);
    const { k, d, j } = _kdj(highs, lows, closes);
    c.setOption(buildKlineSubOption({
      dates,
      // J = 3K - 2D 可超出 0~100，用 scale 自适应；保留 20/50/80 三条参考线（超买超卖区）
      yAxis: { splitNumber: 4, minInterval: 10 },
      series: [
        { name: "_ref20", type: "line", data: dates.map(() => 20), showSymbol: false,
          lineStyle: { width: 0.5, color: "#6e7681", type: "dashed" }, itemStyle: { color: "#6e7681" },
          tooltip: { show: false } },
        { name: "_ref80", type: "line", data: dates.map(() => 80), showSymbol: false,
          lineStyle: { width: 0.5, color: "#6e7681", type: "dashed" }, itemStyle: { color: "#6e7681" },
          tooltip: { show: false } },
        { name: "K", type: "line", data: k, showSymbol: false, lineStyle: { width: 1, color: "#ffd700" }, itemStyle: { color: "#ffd700" } },
        { name: "D", type: "line", data: d, showSymbol: false, lineStyle: { width: 1, color: "#a371f7" }, itemStyle: { color: "#a371f7" } },
        { name: "J", type: "line", data: j, showSymbol: false, lineStyle: { width: 1, color: "#58a6ff" }, itemStyle: { color: "#58a6ff" } },
      ],
    }));
    c.resize();
  }
  function renderBoll(list, idx) {
    const c = charts.klineSub[idx]; if (!c) return;
    const dates = list.map(x => x.date);
    const closes = list.map(x => x.close);
    const { mid, upper, lower } = _boll(closes);
    c.setOption(buildKlineSubOption({
      dates,
      series: [
        { name: "中轨", type: "line", data: mid, showSymbol: false, lineStyle: { width: 1, color: "#ffd700" }, itemStyle: { color: "#ffd700" } },
        { name: "上轨", type: "line", data: upper, showSymbol: false, lineStyle: { width: 1, color: "#58a6ff" }, itemStyle: { color: "#58a6ff" } },
        { name: "下轨", type: "line", data: lower, showSymbol: false, lineStyle: { width: 1, color: "#f85149" }, itemStyle: { color: "#f85149" } },
      ],
    }));
    c.resize();
  }
  function renderRsi(list, idx) {
    const c = charts.klineSub[idx]; if (!c) return;
    const dates = list.map(x => x.date);
    const closes = list.map(x => x.close);
    const r6 = _rsi(closes, 6);
    const r12 = _rsi(closes, 12);
    const r24 = _rsi(closes, 24);
    c.setOption(buildKlineSubOption({
      dates,
      yAxis: { min: 0, max: 100, splitNumber: 3 },
      series: [
        { name: "RSI6",  type: "line", data: r6,  showSymbol: false, lineStyle: { width: 1, color: "#ffd700" }, itemStyle: { color: "#ffd700" } },
        { name: "RSI12", type: "line", data: r12, showSymbol: false, lineStyle: { width: 1, color: "#a371f7" }, itemStyle: { color: "#a371f7" } },
        { name: "RSI24", type: "line", data: r24, showSymbol: false, lineStyle: { width: 1, color: "#58a6ff" }, itemStyle: { color: "#58a6ff" } },
      ],
    }));
    c.resize();
  }

  // ---------- 数据拉取（带竞态保护 + 超时/取消防护） ----------
  // 同类型（key）上一次未完成的请求会被自动 abort，避免快速切换标的时请求堆积/连接耗尽；
  // 另设安全超时，防止后端/网络挂起导致界面一直 showLoading。
  const _abortCtrls = {};
  function _fetchAbortable(key, url, timeoutMs) {
    if (_abortCtrls[key]) { try { _abortCtrls[key].abort(); } catch (e) {} }
    const ctrl = new AbortController();
    _abortCtrls[key] = ctrl;
    let timer = null;
    if (timeoutMs && timeoutMs > 0) timer = setTimeout(() => ctrl.abort(), timeoutMs);
    return fetch(url, { signal: ctrl.signal })
      .finally(() => { if (timer) clearTimeout(timer); if (_abortCtrls[key] === ctrl) delete _abortCtrls[key]; });
  }

  let _quoteSeq = 0;
  async function loadQuote(code) {
    const seq = ++_quoteSeq;
    try {
      const r = await _fetchAbortable("quote", "/api/quote?code=" + encodeURIComponent(code), 30000);
      const d = await r.json();
      if (seq !== _quoteSeq) return;               // 过期响应丢弃
      if (d.error && !d.quote) throw new Error(d.error);
      latestData = d;
      renderHeader(d, code);
      renderMinute(d);
      renderMarketPanel(d);
      _renderSubcharts(d);
      $("updateTime").textContent = "更新 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
    } catch (e) {
      if (seq !== _quoteSeq) return;               // 被新请求取消 → 静默
      if (e && e.name === "AbortError") { $("updateTime").textContent = "加载超时，重试中…"; return; }
      $("updateTime").textContent = "加载失败: " + e.message;
      console.error(e);
    }
  }

  // ---------- 顶部 ----------
  function renderHeader(d, fullCode) {
    const q = d.quote;
    if (!q) return;
    $("stName").textContent = q.name;
    $("stCode").textContent = (fullCode || q.code).toUpperCase();
    $("stPrice").textContent = q.price.toFixed(2);
    const chg = q.change_pct;
    const el = $("stChg");
    el.textContent = (chg >= 0 ? "+" : "") + chg.toFixed(2) + "%";
    el.className = "chg " + (chg >= 0 ? "up" : "down");
    $("stSource").textContent = q.source === "tencent" ? "腾讯" : "东财";
    renderOrderBook(q);   // 五档盘口信息卡
  }

    // ---------- 时间格式化（腾讯快照 20260813161452 → 16:14:52） ----------
  function fmtSnapshotTime(s) {
    if (!s) return "";
    // 末尾 6 位数字：HHMMSS
    const m = String(s).match(/(\d{2})(\d{2})(\d{2})\s*$/);
    if (m) return m[1] + ":" + m[2] + ":" + m[3];
    // 已经是 HHMMSS
    if (/^\d{6}$/.test(s)) return s.slice(0, 2) + ":" + s.slice(2, 4) + ":" + s.slice(4);
    return s;
  }

  // ---------- 市场综合（三列布局：中列核心 + 右列明细，分组渲染） ----------
  function renderMarketPanel(d) {
    const coreEl = document.getElementById("marketPanel");
    const rightEl = document.getElementById("marketPanelRight");
    if (!coreEl && !rightEl) return;
    const stats = d.stats || {}, quote = d.quote || {}, finance = d.finance || {};
    const holders = d.holders || [], announcements = d.announcements || [];
    const margin = d.margin || [], lhb = d.lhb || [], company = d.company || {};
    const forecast = d.forecast || {}, profitTrend = d.profit_trend || [], sentiment = d.sentiment || {};
    if (!Object.keys(stats).length && !Object.keys(quote).length && !Object.keys(finance).length
      && !holders.length && !announcements.length && !margin.length && !lhb.length
      && !Object.keys(company).length && !Object.keys(forecast).length
      && !profitTrend.length && !Object.keys(sentiment).length) {
      if (coreEl) coreEl.innerHTML = "";
      if (rightEl) rightEl.innerHTML = "";
      return;
    }
    const pctCls = v => v == null || v === "" ? "" : (v >= 0 ? "up" : "down");
    const sgn = v => (v >= 0 ? "+" : "") + v.toFixed(2);
    const yi = v => v >= 1e8 ? (v / 1e8).toFixed(2) + "亿" : (v >= 1e4 ? (v / 1e4).toFixed(0) + "万" : v.toFixed(0));
    const core = [], right = [];

    // ===== 中列（#marketPanel）：行情 / 估值 / 财务 / 净利柱 / 多空 / 两融 =====

    // 行情
    if (Object.keys(stats).length) {
      core.push(`<div class="mp-section"><div class="mp-h">行情（日K）</div>`);
      if (stats.pct_60d != null) core.push(`<div class="mp-row"><span class="lbl">60日</span><span class="${pctCls(stats.pct_60d)}">${sgn(stats.pct_60d)}%</span></div>`);
      if (stats.pct_360d != null) core.push(`<div class="mp-row"><span class="lbl">360日</span><span class="${pctCls(stats.pct_360d)}">${sgn(stats.pct_360d)}%</span></div>`);
      if (stats.pct_ytd != null) core.push(`<div class="mp-row"><span class="lbl">今年</span><span class="${pctCls(stats.pct_ytd)}">${sgn(stats.pct_ytd)}%</span></div>`);
      if (stats.hi_1y != null) core.push(`<div class="mp-row"><span class="lbl">一年高</span><span class="up">${stats.hi_1y}</span></div>`);
      if (stats.lo_1y != null) core.push(`<div class="mp-row"><span class="lbl">一年低</span><span class="down">${stats.lo_1y}</span></div>`);
      core.push(`</div>`);
    }

    // 估值/市值
    if (quote && (quote.total_mv || quote.float_mv || quote.pe_dyn || quote.pb)) {
      core.push(`<div class="mp-section"><div class="mp-h">估值/市值</div>`);
      if (quote.total_mv) core.push(`<div class="mp-row"><span class="lbl">总市值</span><span>${quote.total_mv.toFixed(1)}亿</span></div>`);
      if (quote.float_mv) core.push(`<div class="mp-row"><span class="lbl">流通市值</span><span>${quote.float_mv.toFixed(1)}亿</span></div>`);
      if (quote.pe_dyn) core.push(`<div class="mp-row"><span class="lbl">PE(动)</span><span>${quote.pe_dyn.toFixed(2)}</span></div>`);
      if (quote.pb) core.push(`<div class="mp-row"><span class="lbl">PB</span><span>${quote.pb.toFixed(2)}</span></div>`);
      if (quote.volume_ratio) core.push(`<div class="mp-row"><span class="lbl">量比</span><span>${quote.volume_ratio.toFixed(2)}</span></div>`);
      if (quote.turnover_pct != null) core.push(`<div class="mp-row"><span class="lbl">换手</span><span>${quote.turnover_pct}%</span></div>`);
      core.push(`</div>`);
    }

    // 财务摘要
    if (finance && finance.revenue != null) {
      core.push(`<div class="mp-section"><div class="mp-h">财务（${finance.report_type || ""}）</div>`);
      if (finance.revenue != null) core.push(`<div class="mp-row"><span class="lbl">总营收</span><span>${yi(finance.revenue)}</span></div>`);
      if (finance.yoy_revenue != null) core.push(`<div class="mp-row"><span class="lbl">营收同比</span><span class="${pctCls(finance.yoy_revenue)}">${sgn(finance.yoy_revenue)}%</span></div>`);
      if (finance.net_profit != null) core.push(`<div class="mp-row"><span class="lbl">归母净利</span><span>${yi(finance.net_profit)}</span></div>`);
      if (finance.yoy_profit != null) core.push(`<div class="mp-row"><span class="lbl">净利同比</span><span class="${pctCls(finance.yoy_profit)}">${sgn(finance.yoy_profit)}%</span></div>`);
      if (finance.eps != null) core.push(`<div class="mp-row"><span class="lbl">EPS</span><span>${finance.eps.toFixed(2)}</span></div>`);
      if (finance.roe != null) core.push(`<div class="mp-row"><span class="lbl">ROE</span><span>${finance.roe.toFixed(2)}%</span></div>`);
      core.push(`</div>`);
    }

    // 净利同比柱状图（历史年度）
    if (profitTrend.length) {
      const bars = profitTrend.map(t => {
        const v = +(t.net_profit / 1e8).toFixed(0);
        const yoy = t.yoy != null ? sgn(t.yoy) + "%" : "";
        return `<div class="mp-bar-col" title="${t.year} 净利${v}亿 同比${yoy}">`
          + `<div class="mp-bar-value ${t.yoy >= 0 ? "up" : "down"}">${v}</div>`
          + `<div class="mp-bar ${t.yoy >= 0 ? "up" : "down"}" style="height:${Math.max(4, Math.abs(v) / 15)}px"></div>`
          + `<div class="mp-bar-label">${t.year}</div></div>`;
      }).join("");
      core.push(`<div class="mp-section mp-wide"><div class="mp-h">年度净利（亿）</div>`
        + `<div class="mp-bars">${bars}</div></div>`);
    }

    // 多空情绪（主力资金占比）
    if (sentiment && sentiment.bull_pct != null) {
      core.push(`<div class="mp-section"><div class="mp-h">主力多空（${sentiment.days}分钟）</div>`);
      core.push(`<div class="mp-row"><span class="lbl">多头</span><span class="up">${sentiment.bull_pct}%</span></div>`);
      core.push(`<div class="mp-row"><span class="lbl">空头</span><span class="down">${sentiment.bear_pct}%</span></div>`);
      core.push(`</div>`);
    }

    // 融资融券
    if (margin.length) {
      const m0 = margin[0];
      core.push(`<div class="mp-section"><div class="mp-h">融资融券（${m0.date}）</div>`);
      if (m0.rzye != null) core.push(`<div class="mp-row"><span class="lbl">融资余额</span><span>${yi(m0.rzye)}</span></div>`);
      if (m0.rqye != null) core.push(`<div class="mp-row"><span class="lbl">融券余额</span><span>${yi(m0.rqye)}</span></div>`);
      if (m0.rzrqye != null) core.push(`<div class="mp-row"><span class="lbl">两融合计</span><span>${yi(m0.rzrqye)}</span></div>`);
      if (m0.rzyezb != null) core.push(`<div class="mp-row"><span class="lbl">融资占比</span><span>${m0.rzyezb.toFixed(2)}%</span></div>`);
      core.push(`</div>`);
    }

    // ===== 右列（#marketPanelRight）：股东 / 龙虎榜 / 公司 / 预测 / 公告 =====

    // 股东户数
    if (holders.length) {
      right.push(`<div class="mp-section"><div class="mp-h">股东户数</div>`);
      holders.slice(0, 3).forEach(h => {
        if (!h.date) return;
        const cp = h.change_pct != null ? `${h.change_pct >= 0 ? "+" : ""}${h.change_pct.toFixed(2)}%` : "";
        right.push(`<div class="mp-row"><span class="lbl">${h.date.slice(5)}</span><span>${(h.total || 0).toLocaleString()} <span class="${pctCls(h.change_pct)}">${cp}</span></span></div>`);
      });
      right.push(`</div>`);
    }

    // 龙虎榜
    if (lhb.length) {
      right.push(`<div class="mp-section"><div class="mp-h">龙虎榜</div>`);
      lhb.slice(0, 2).forEach(x => {
        const amt = x.amount != null ? yi(x.amount) : "";
        right.push(`<div class="mp-ann-row" title="${x.explain || ""}"><span class="ann-date">${x.date.slice(5)}</span><span class="ann-title">${amt} ${x.change_pct != null ? sgn(x.change_pct) + "%" : ""}</span></div>`);
      });
      right.push(`</div>`);
    }

    // 公司信息
    if (company && company.org_name) {
      right.push(`<div class="mp-section"><div class="mp-h">公司</div>`);
      right.push(`<div class="mp-row"><span class="lbl">全称</span><span>${company.org_name}</span></div>`);
      if (company.industry) right.push(`<div class="mp-row"><span class="lbl">行业</span><span>${company.industry}</span></div>`);
      if (company.market) right.push(`<div class="mp-row"><span class="lbl">市场</span><span>${company.market}</span></div>`);
      right.push(`</div>`);
    }

    // 北向资金（沪股通+深股通合计；deepthinkcomp_stock 扩展，数据来自 /api/stock/full north 字段）
    if (d.north && !d.north.error && (d.north.holdings != null || d.north.change_pct != null || d.north.latest_date)) {
      const north = d.north;
      right.push(`<div class="mp-section"><div class="mp-h">北向资金（沪股通+深股通）</div>`);
      if (north.latest_date) right.push(`<div class="mp-row"><span class="lbl">最新</span><span>${north.latest_date}</span></div>`);
      if (north.holdings != null) right.push(`<div class="mp-row"><span class="lbl">持股(万股)</span><span>${Number(north.holdings).toFixed(2)}</span></div>`);
      if (north.change_pct != null) right.push(`<div class="mp-row"><span class="lbl">变化率</span><span class="${pctCls(north.change_pct)}">${sgn(north.change_pct)}%</span></div>`);
      if (north.hold_value != null) right.push(`<div class="mp-row"><span class="lbl">持股市值</span><span>${yi(north.hold_value)}</span></div>`);
      if (north.ratio != null) right.push(`<div class="mp-row"><span class="lbl">占总股本%</span><span>${Number(north.ratio).toFixed(2)}%</span></div>`);
      right.push(`</div>`);
    } else if (d.north && d.north.error) {
      right.push(`<div class="mp-section"><div class="mp-h">北向资金</div><div class="mp-empty">暂不可用：${d.north.error}</div></div>`);
    }

    // 盈利预测
    if (forecast && forecast.org_num) {
      const epsRows = (forecast.eps_years || []).filter(e => e.year).map(e =>
        `<div class="mp-row"><span class="lbl">${e.year}${e.mark === "E" ? "E" : ""}</span><span>EPS ${e.eps != null ? e.eps.toFixed(2) : "--"}</span></div>`).join("");
      right.push(`<div class="mp-section"><div class="mp-h">盈利预测（${forecast.org_num}家）</div>`);
      right.push(`<div class="mp-row"><span class="lbl">评级</span><span>买入${forecast.buy_num || 0} 增持${forecast.add_num || 0}</span></div>`);
      right.push(epsRows);
      right.push(`</div>`);
    }

    // 公告（全部 10 条）—— 点击查看
    if (announcements.length) {
      right.push(`<div class="mp-section"><div class="mp-h">最新公告（${announcements.length}）</div>`);
      announcements.forEach(a => {
        const title = (a.title || "").replace(/^[^:]+:/, "");
        right.push(`<div class="mp-ann-row" title="点击查看：${a.title}" data-art="${a.code || ""}"><span class="ann-date">${a.date.slice(5)}</span><span class="ann-title">${title}</span></div>`);
      });
      right.push(`</div>`);
    }

    if (coreEl) coreEl.innerHTML = core.join("");
    if (rightEl) rightEl.innerHTML = right.join("");
    // K 线视图：合并到 #klineMarketPanel，4 列网格展示所有 11 组
    const klineEl = document.getElementById("klineMarketPanel");
    if (klineEl) {
      const all = [...core, ...right];
      klineEl.innerHTML = all.join("");
    }
    // 公告点击查看：fetch 正文 → modal 展示
    [coreEl, rightEl, klineEl].forEach(el => {
      if (!el) return;
      el.querySelectorAll(".mp-ann-row").forEach(row => {
        row.onclick = () => showAnnouncement(row.getAttribute("data-art") || "");
      });
    });
  }

  // ---------- 公告正文 modal ----------
  async function showAnnouncement(artCode) {
    if (!artCode) return;
    const modal = $("annModal");
    const titleEl = $("annTitle"), contentEl = $("annContent"), msgEl = $("annMsg");
    const pdfBtn = $("annPdf");
    pdfBtn.classList.add("hidden");
    titleEl.textContent = "加载中…";
    contentEl.textContent = "";
    msgEl.textContent = "";
    modal.classList.remove("hidden");
    try {
      const r = await fetch("/api/announcement?code=" + encodeURIComponent(artCode));
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      titleEl.textContent = (d.date ? d.date + "  " : "") + d.title;
      contentEl.textContent = d.content || "（无正文内容）";
      if (d.pdf_url) {
        pdfBtn.onclick = () => window.open(d.pdf_url, "_blank");
        pdfBtn.classList.remove("hidden");
      }
    } catch (e) {
      msgEl.textContent = "公告加载失败：" + e.message;
    }
  }

  // ---------- 五档盘口（分时图右上角，右侧栏上半） ----------
  function renderOrderBook(q) {
    const ob = document.getElementById("orderBook");
    if (!ob) return;
    if (!q) { ob.innerHTML = ""; return; }
    const book = q.order_book || { bids: [], asks: [] };
    const changeCls = q.change >= 0 ? "up" : "down";
    const rows = [];
    // 标题（标的 + 现价 + 涨跌色块）
    rows.push(`<div class="ob-head">`
      + `<span class="ob-name">${q.name || q.code || ""}</span>`
      + `<span class="ob-change ${changeCls}">${(q.change >= 0 ? "+" : "")}${q.change.toFixed(2)} (${(q.change_pct >= 0 ? "+" : "")}${q.change_pct.toFixed(2)}%)</span>`
      + `</div>`);
    // 卖 5→1（倒序显示）
    rows.push(`<div class="ob-section ob-asks">`);
    for (let i = 4; i >= 0; i--) {
      const a = book.asks && book.asks[i];
      if (a && a.price > 0) {
        rows.push(`<div class="ob-row"><span class="ob-label ask">卖${5 - i}</span><span class="ob-price ask">${a.price.toFixed(2)}</span><span class="ob-vol">${Math.round(a.vol)}</span></div>`);
      } else {
        rows.push(`<div class="ob-row"><span class="ob-label ask">卖${5 - i}</span><span class="ob-price muted">--</span><span class="ob-vol muted">--</span></div>`);
      }
    }
    rows.push(`</div>`);
    // 现价
    rows.push(`<div class="ob-now ${changeCls}">${q.price.toFixed(2)}</div>`);
    // 买 1→5
    rows.push(`<div class="ob-section ob-bids">`);
    for (let i = 0; i < 5; i++) {
      const b = book.bids && book.bids[i];
      if (b && b.price > 0) {
        rows.push(`<div class="ob-row"><span class="ob-label bid">买${i + 1}</span><span class="ob-price bid">${b.price.toFixed(2)}</span><span class="ob-vol">${Math.round(b.vol)}</span></div>`);
      } else {
        rows.push(`<div class="ob-row"><span class="ob-label bid">买${i + 1}</span><span class="ob-price muted">--</span><span class="ob-vol muted">--</span></div>`);
      }
    }
    rows.push(`</div>`);
    // 关键指标（2 组 key-value / 行，8 行对齐示例图：现价/今开/涨跌/最高/涨幅/最低/总手/量比/外盘/内盘/换手/股本/净资/流通/收益/PE）
    const mv2cap = mv => mv ? (mv / (q.price || 1)).toFixed(1) + "亿" : "--";
    const v2 = v => v ? v.toFixed(2) : "--";
    const sgn = v => (v >= 0 ? "+" : "") + v.toFixed(2);
    const sgnPct = v => (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
    const capFmt = v => v ? v.toFixed(1) + "亿" : "--";
    const bigNum = v => {
      if (!v) return "--";
      if (v >= 1e4) return (v / 1e4).toFixed(1) + "万";
      return v.toFixed(0);
    };
    const eps = (q.price && q.pe_dyn) ? (q.price / q.pe_dyn).toFixed(2) : "--";
    const nav = (q.price && q.pb) ? (q.price / q.pb).toFixed(2) : "--";
    rows.push(`<div class="ob-stats">`);
    rows.push(`<div class="ob-stat"><span class="lbl">现价</span><span class="${changeCls}">${v2(q.price)}</span><span class="lbl">今开</span><span>${v2(q.open)}</span></div>`);
    rows.push(`<div class="ob-stat"><span class="lbl">涨跌</span><span class="${changeCls}">${sgn(q.change)}</span><span class="lbl">最高</span><span class="up">${v2(q.high)}</span></div>`);
    rows.push(`<div class="ob-stat"><span class="lbl">涨幅</span><span class="${changeCls}">${sgnPct(q.change_pct)}</span><span class="lbl">最低</span><span class="down">${v2(q.low)}</span></div>`);
    rows.push(`<div class="ob-stat"><span class="lbl">总手</span><span>${bigNum(q.volume)}</span><span class="lbl">量比</span><span>${q.volume_ratio ? q.volume_ratio.toFixed(2) : "--"}</span></div>`);
    rows.push(`<div class="ob-stat"><span class="lbl">外盘</span><span>${bigNum(q.outer)}</span><span class="lbl">内盘</span><span>${bigNum(q.inner)}</span></div>`);
    rows.push(`<div class="ob-stat"><span class="lbl">换手</span><span>${q.turnover_pct}%</span><span class="lbl">股本</span><span>${mv2cap(q.total_mv)}</span></div>`);
    rows.push(`<div class="ob-stat"><span class="lbl">净资</span><span>${nav}</span><span class="lbl">流通</span><span>${mv2cap(q.float_mv)}</span></div>`);
    rows.push(`<div class="ob-stat"><span class="lbl">收益</span><span>${eps}</span><span class="lbl">PE(动)</span><span>${q.pe_dyn ? q.pe_dyn.toFixed(2) : "--"}</span></div>`);
    rows.push(`</div>`);
    // 时间戳
    if (q.time) rows.push(`<div class="ob-time">⏱ ${fmtSnapshotTime(q.time)}</div>`);
    ob.innerHTML = rows.join("");
  }

  // ---------- 分钟详情（分时图右侧栏下半，240 条滚动列表 + ↑/↓ 切换选中行） ----------
  function renderMinuteDetail(minuteList, selIdx) {
    const el = document.getElementById("minuteDetail");
    if (!el) return;
    if (!minuteList || !minuteList.length) { el.innerHTML = ""; return; }
    if (selIdx < 0 || selIdx >= minuteList.length) selIdx = minuteList.length - 1;
    const preClose = _minuteQuote && _minuteQuote.pre_close ? _minuteQuote.pre_close : 0;
    const rows = [];
    rows.push(`<div class="header">选中分钟 ${selIdx + 1}/${minuteList.length}（↑↓ 切换）</div>`);
    rows.push(`<div class="list-head"><span>时间</span><span style="text-align:right">价格</span><span style="text-align:right">量(手)</span><span style="text-align:right">额(万)</span></div>`);
    rows.push(`<div class="list" id="minuteDetailList">`);
    minuteList.forEach((m, i) => {
      const prev = i > 0 ? minuteList[i - 1] : null;
      const vol = prev ? Math.max(0, m.vol - prev.vol) : m.vol;
      const amt = prev ? Math.max(0, m.amount - prev.amount) : m.amount;
      const change = prev ? (m.price - prev.price) : 0;
      const cls = change > 0 ? "up" : (change < 0 ? "dn" : "eq");
      const arrow = prev ? (change > 0 ? "↑" : (change < 0 ? "↓" : "=")) : "";
      const active = (i === selIdx) ? " active" : "";
      rows.push(`<div class="list-row${active}" data-idx="${i}">`
        + `<span>${normT(m.t)}</span>`
        + `<span style="text-align:right" class="${cls}">${m.price.toFixed(2)}${arrow}</span>`
        + `<span style="text-align:right">${vol}</span>`
        + `<span style="text-align:right">${(amt / 1e4).toFixed(1)}</span>`
        + `</div>`);
    });
    rows.push(`</div>`);
    el.innerHTML = rows.join("");
    // 点击行直接切换
    const listEl = el.querySelector("#minuteDetailList");
    if (listEl) {
      listEl.addEventListener("click", e => {
        const row = e.target.closest(".list-row");
        if (!row) return;
        const idx = parseInt(row.dataset.idx, 10);
        if (!isNaN(idx)) {
          _selectedMinuteIdx = idx;
          renderMinuteDetail(_minuteList, _selectedMinuteIdx);
        }
      });
    }
    // 滚动到选中行
    const activeRow = el.querySelector(".list-row.active");
    if (activeRow && listEl) {
      const lr = activeRow.offsetTop - listEl.offsetTop - listEl.clientHeight / 2 + activeRow.clientHeight / 2;
      listEl.scrollTop = Math.max(0, lr);
    }
  }

  // ---------- ① 分时（左轴价格 + 右轴涨跌幅%，对齐同花顺/东财通用样式） ----------
  function renderMinute(d) {
    const m = d.minute || [];
    const empty = $("p1Empty");
    if (!m.length) { if (empty) empty.classList.remove("hidden"); return; }
    if (empty) empty.classList.add("hidden");
    const times = m.map(x => normT(x.t));
    const prices = m.map(x => x.price);
    const avgs = m.map(x => x.avg);
    const pre = d.quote && d.quote.pre_close ? d.quote.pre_close : prices[0];
    const maxAbs = Math.max(1, ...prices.map(p => Math.abs((p - pre) / pre * 100)));
    // 价格 Y 轴：按当日实际最高最低 ±0.5% 范围（让分时线波动更醒目，避免被大范围压平）
    const priceMin = Math.min(...prices), priceMax = Math.max(...prices);
    const pricePad = (priceMax - priceMin) * 0.1 || priceMin * 0.005;
    charts.p1.setOption({
      backgroundColor: DARK.bg,
      grid: baseGrid(),
      tooltip: { trigger: "axis", confine: true },
      xAxis: { type: "category", data: times, axisLabel: { fontSize: 10, interval: 55 } },
      yAxis: [
        { type: "value", min: priceMin - pricePad, max: priceMax + pricePad, scale: false,
          axisLabel: { color: DARK.label, fontSize: 10, formatter: v => v.toFixed(2) },
          splitLine: { lineStyle: { color: "#1b222c" } } },
        { type: "value", min: -maxAbs * 1.2, max: maxAbs * 1.2, splitNumber: 4,
          axisLabel: { color: DARK.label, fontSize: 10, formatter: v => v.toFixed(2) + "%" },
          splitLine: { show: false } },
      ],
      series: [
        { name: "现价", type: "line", data: prices, showSymbol: false,
          yAxisIndex: 0,
          lineStyle: { width: 1.8, color: DARK.price }, itemStyle: { color: DARK.price } },
        { name: "均价", type: "line", data: avgs, showSymbol: false,
          yAxisIndex: 0,
          lineStyle: { width: 2, color: "#ffd700", type: "dashed", opacity: 0.9 },
          itemStyle: { color: "#ffd700" } },
        { name: "涨跌幅", type: "line", data: prices.map(p => (p - pre) / pre * 100),
          showSymbol: false, yAxisIndex: 1,
          lineStyle: { width: 0.8, color: "#388bfd", type: "dashed", opacity: 0.6 },
          itemStyle: { color: "#388bfd" } },
      ],
    });
    charts.p1.resize();
    window._minuteTimes = times;
    // 保存数据供键盘切换分钟使用
    _minuteList = m;
    _minuteQuote = (d.quote || null);
    if (_selectedMinuteIdx < 0 || _selectedMinuteIdx >= m.length) {
      _selectedMinuteIdx = m.length - 1;  // 默认选中最后一根（最新分钟）
    }
    renderMinuteDetail(_minuteList, _selectedMinuteIdx);
  }

  // ---------- 副图通用骨架：消除 12 个渲染函数重复的 backgroundColor/grid/tooltip/xAxis/yAxis 样板 ----------
  function _zeroLine(times, name) {
    return { name: name || "零轴", type: "line", data: times.map(() => 0), showSymbol: false,
      lineStyle: { width: 1, color: DARK.gray, type: "dashed" } };
  }
  // 每分钟累计值 → 差分（首根为 0）
  function _deltaByKey(f, key) { return f.map((x, i) => i === 0 ? 0 : (x[key] - f[i - 1][key])); }
  function _deltaByFn(f, fn) { return f.map((x, i) => i === 0 ? 0 : fn(x, f[i - 1])); }
  function _toWan(arr) { return arr.map(v => +(v / 1e4).toFixed(1)); }   // 元 → 万元
  function _subAxis(times) { return { type: "category", data: times, axisLabel: { fontSize: 10, interval: 55 } }; }
  // 组装副图通用 ECharts option；times/yFmt/tip/series 各函数按需提供，xAxis/grid/legend 可覆盖
  function buildSubOption(cfg) {
    const opt = {
      backgroundColor: DARK.bg,
      grid: cfg.grid || baseGrid(),
      tooltip: { trigger: "axis", confine: true, formatter: cfg.tip },
      xAxis: cfg.xAxis || _subAxis(cfg.times),
      yAxis: { type: "value", splitNumber: cfg.splitNumber || 3,
        axisLabel: { color: DARK.label, fontSize: 10, formatter: cfg.yFmt },
        splitLine: { lineStyle: { color: "#1b222c" } } },
      series: cfg.series,
    };
    if (cfg.legend) opt.legend = cfg.legend;
    return opt;
  }
  // K线技术指标副图通用骨架（US-069：消除 MACD/KDJ/BOLL/RSI 重复的
  // backgroundColor/grid/tooltip/dataZoom/xAxis/yAxis 样板）。cfg: { dates, yAxis, series }
  function buildKlineSubOption(cfg) {
    return {
      backgroundColor: DARK.bg,
      tooltip: { trigger: "axis", confine: true },
      grid: { left: 56, right: 20, top: 8, bottom: 18 },
      dataZoom: [{ type: "inside", xAxisIndex: 0, zoomLock: true }],
      xAxis: { type: "category", data: cfg.dates, axisLabel: { show: false }, splitLine: { show: false } },
      yAxis: Object.assign({
        scale: true, splitNumber: 3,
        axisLabel: { color: DARK.label, fontSize: 10 }, splitLine: { lineStyle: { color: "#1b222c" } },
      }, cfg.yAxis || {}),
      series: cfg.series,
    };
  }

  // ---------- ② VOLFS（每分钟成交量，按价格涨跌方向染色：红涨绿跌对齐通达信/A 股惯例） ----------
  function renderVolfs(d, idx = 0) {
    const c = charts.sub[idx];
    if (!c) return;
    const m = d.minute || [];
    if (!m.length) return;
    const rawT = m.map(x => x.t);
    // 后端统一返回每分钟成交量（手）；VOLFS 直接显示为"手"
    const vols = m.map(x => x.vol);
    // 染色：price 上涨 → 红（A 股惯例），price 下跌 → 绿，首根灰色
    let colors = [];
    for (let i = 0; i < vols.length; i++) {
      if (i === 0 || m[i].price > m[i - 1].price) {
        colors.push(DARK.up);   // 红
      } else if (m[i].price < m[i - 1].price) {
        colors.push(DARK.down); // 绿
      } else {
        colors.push(DARK.gray); // 平
      }
    }
    c.setOption(buildSubOption({
      times: rawT.map(normT),
      yFmt: v => (v >= 10000 ? (v / 10000).toFixed(0) + "万手" : v + "手"),
      tip: ps => ps[0].name + "<br/>" + ps[0].seriesName + ": " + ps[0].value + " 手",
      series: [{ name: "每分钟成交量", type: "bar", data: vols, barWidth: "60%",
        itemStyle: { color: (p) => colors[p.dataIndex] } }],
    }));
    c.resize();
  }

  // ---------- ③ 主力追踪 ----------
  function renderFund(d, idx = 1) {
    const c = charts.sub[idx];
    if (!c) return;
    const f = d.fund || [];
    if (!f.length) return;
    const times = f.map(x => normT(x.t));
    const main = f.map(x => x.main);
    c.setOption(buildSubOption({
      times,
      splitNumber: 4,
      yFmt: v => (v / 1e8).toFixed(1) + "亿",
      tip: ps => { const p = ps[0]; return p.name + "<br/>主力净流入: " + (p.value / 1e8).toFixed(2) + " 亿"; },
      series: [{ name: "主力净流入", type: "line", data: main, showSymbol: false,
        lineStyle: { width: 1.6, color: DARK.purple },
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: "rgba(137,87,229,.45)" }, { offset: 1, color: "rgba(137,87,229,.02)" }] } },
        itemStyle: { color: DARK.purple } }],
    }));
    c.resize();
  }

  // ---------- ③.5 资金博弈副图（通达信「分时资金博弈 - Level2精简版」适配） ----------
  // 通达信公式：主力净额=(超B+大B)-(超S+大S)；散户净额=小B-小S
  // 数据源为东财分钟资金（main/small 为累计值），此处取每分钟增量并换算万元。
    // ---------- US-009 近5日主力净流入（柱状） ----------
  function renderDay5(d, idx) {
    const c = charts.sub[idx]; if (!c) return;
    const rows = d.day_fund_5d || [];
    if (!rows.length) return;
    const dates = rows.map(x => x.date.slice(5));
    const mains = rows.map(x => +(x.main / 1e8).toFixed(2));   // 亿元
    c.setOption(buildSubOption({
      grid: { left: 56, right: 20, top: 12, bottom: 18 },
      xAxis: { type: "category", data: dates, axisLabel: { fontSize: 10, color: DARK.label } },
      yFmt: v => v.toFixed(1) + "亿",
      tip: ps => ps[0].name + "<br/>主力净流入: " + ps[0].value.toFixed(2) + " 亿",
      series: [{ name: "主力净流入", type: "bar", data: mains, barWidth: "55%",
        itemStyle: { color: (p) => p.data >= 0 ? DARK.up : DARK.down },
        label: { show: true, position: "top", fontSize: 9, color: DARK.label, formatter: p => p.value.toFixed(2) } }],
    }));
    c.resize();
  }

  // ---------- US-010 主力异动告警（资金博弈副图内） ----------
  function _renderAlertsInto(gameChart, mainDelta) {
    // 阈值：|delta| > 当日中位数 × 3（自适应）→ 柱体橙色高亮
    const abs = mainDelta.map(Math.abs).filter(v => v > 0);
    if (!abs.length) return;
    abs.sort((a, b) => a - b);
    const median = abs[Math.floor(abs.length / 2)] || 1;
    const threshold = median * 3;
    return { threshold, alerts: mainDelta.map(v => Math.abs(v) > threshold && v !== 0) };
  }

  // ---------- 资金博弈副图（同花顺配色：主力紫色柱 + 散户黄色线） ----------
  function renderFundGame(d, idx = 2) {
    const c = charts.sub[idx];
    if (!c) return;
    const f = d.fund || [];
    if (!f.length) return;
    const times = f.map(x => normT(x.t));
    const mainDelta = f.map((x, i) => i === 0 ? 0 : x.main - f[i - 1].main);
    const smallDelta = f.map((x, i) => i === 0 ? 0 : x.small - f[i - 1].small);
    const mainW = mainDelta.map(v => +(v / 1e4).toFixed(1));    // 万元
    const smallW = smallDelta.map(v => +(v / 1e4).toFixed(1));
    // 主力净额柱（紫色，正负双向）；散户净额（黄色线）
    const mainBar = mainW.map(v => +v.toFixed(1));
    // US-010 异动告警：|主力净额差分| > 中位数×3 → 橙色高亮
    const { alerts } = _renderAlertsInto(c, mainDelta);
    c.setOption(buildSubOption({
      times,
      yFmt: v => v.toFixed(0) + "万",
      tip: ps => {
        let s = ps[0].name;
        ps.forEach(p => { s += "<br/>" + p.seriesName + ": " + p.value.toFixed(1) + " 万"; });
        return s;
      },
      legend: { data: ["主力净额", "散户净额"], textStyle: { color: DARK.label, fontSize: 10 }, top: 4 },
      series: [
        { name: "主力净额", type: "bar", data: mainBar, barWidth: "50%",
          itemStyle: { color: (p) => alerts[p.dataIndex] ? "#ff8c00" : DARK.purple } },
        { name: "散户净额", type: "line", data: smallW, showSymbol: false, yAxisIndex: 0,
          lineStyle: { width: 1.5, color: "#ffd700", opacity: 0.75, type: "solid" }, itemStyle: { color: "#ffd700" } },
        _zeroLine(times),
      ],
    }));
    c.resize();
  }

  // ---------- 散户净额（独立副图：东财每分钟 small 累计差分 → 折线） ----------
  function renderSmallNet(d, idx = 3) {
    const c = charts.sub[idx];
    if (!c) return;
    const f = d.fund || [];
    if (!f.length) return;
    const times = f.map(x => normT(x.t));
    const smallDelta = f.map((x, i) => i === 0 ? 0 : x.small - f[i - 1].small);
    const smallW = smallDelta.map(v => +(v / 1e4).toFixed(1));
    c.setOption(buildSubOption({
      times,
      yFmt: v => v.toFixed(0) + "万",
      tip: ps => ps[0].name + "<br/>散户净额: " + ps[0].value.toFixed(1) + " 万",
      series: [
        { name: "散户净额", type: "line", data: smallW, showSymbol: false,
          lineStyle: { width: 1.6, color: "#ffd700" },
          areaStyle: { color: "rgba(255,215,0,0.15)" },
          itemStyle: { color: "#ffd700" } },
        _zeroLine(times),
      ],
    }));
    c.resize();
  }

  // ---------- 大单净额（东财 big 字段累计差分 → 折线） ----------
  function renderBigNet(d, idx = 4) {
    const c = charts.sub[idx];
    if (!c) return;
    const f = d.fund || [];
    if (!f.length) return;
    const times = f.map(x => normT(x.t));
    const bigW = _toWan(_deltaByKey(f, "big"));
    c.setOption(buildSubOption({
      times,
      yFmt: v => v.toFixed(0) + "万",
      tip: ps => ps[0].name + "<br/>大单净额: " + ps[0].value.toFixed(1) + " 万",
      series: [
        { name: "大单净额", type: "line", data: bigW, showSymbol: false,
          lineStyle: { width: 1.6, color: DARK.up },
          areaStyle: { color: "rgba(248,81,73,0.15)" },
          itemStyle: { color: DARK.up } },
        _zeroLine(times),
      ],
    }));
    c.resize();
  }

  // ---------- 通用差分折线（万元）渲染器（用于超大单/中单/买卖力道/成交额差分） ----------
  function _renderDeltaLine(c, d, key, color, name, idx, isRatio) {
    const f = d.fund || [];
    if (!f.length) return;
    const times = f.map(x => normT(x.t));
    const delta = _deltaByKey(f, key);
    const vals = isRatio
      ? delta.map(v => +(v * 100).toFixed(2))  // 比率转 %
      : _toWan(delta);                          // 元转万元
    const yFmt = isRatio ? "{value}%" : "{value}万";
    c.setOption(buildSubOption({
      times,
      yFmt,
      tip: ps => ps[0].name + "<br/>" + name + ": " + ps[0].value.toFixed(2) + (isRatio ? "%" : " 万"),
      series: [
        { name, type: "line", data: vals, showSymbol: false,
          lineStyle: { width: 1.6, color },
          areaStyle: { color: color + "26" },
          itemStyle: { color } },
        _zeroLine(times),
      ],
    }));
    c.resize();
  }
  function renderSuperBig(d, idx) { _renderDeltaLine(charts.sub[idx], d, "super_big", "#a371f7", "超大单净额", idx); }
  function renderMiddleNet(d, idx) { _renderDeltaLine(charts.sub[idx], d, "mid", "#56b8ff", "中单净额", idx); }
  function renderPower(d, idx) {
    // 买卖力道 = 主力 - 散户（每分钟）
    const c = charts.sub[idx]; if (!c) return;
    const f = d.fund || [];
    if (!f.length) return;
    const times = f.map(x => normT(x.t));
    const delta = _deltaByFn(f, (x, prev) => (x.main - x.small) - (prev.main - prev.small));
    const data = _toWan(delta);
    c.setOption(buildSubOption({
      times,
      yFmt: v => v.toFixed(0) + "万",
      tip: ps => ps[0].name + "<br/>买卖力道: " + ps[0].value.toFixed(1) + " 万",
      series: [
        { name: "买卖力道", type: "line", data, showSymbol: false,
          lineStyle: { width: 1.6, color: DARK.up },
          areaStyle: { color: "rgba(248,81,73,0.15)" }, itemStyle: { color: DARK.up } },
        _zeroLine(times),
      ],
    }));
    c.resize();
  }
  function renderTurnover(d, idx) {
    // 换手率：每分钟成交量 / 流通股本（%）—— 需 quote 提供 float_share
    const c = charts.sub[idx]; if (!c) return;
    const f = d.fund || [];
    if (!f.length) return;
    const times = f.map(x => normT(x.t));
    // 注：东财免费源不直接给逐分钟换手率，这里是"当日累计换手率 ÷ 240 分钟"的线性估算，
    // 仅用于观察盘中换手节奏，非真实逐分钟换手。已在名称/提示中标注"估算"。
    const cumTurnover = (d.quote && d.quote.turnover_pct) || 0;
    const perMin = cumTurnover / 240;  // 估算每分钟
    const series = times.map((_, i) => +(perMin * (i + 1)).toFixed(3));
    c.setOption(buildSubOption({
      times,
      yFmt: v => v.toFixed(2) + "%",
      tip: ps => ps[0].name + "<br/>累计换手(估算): " + ps[0].value.toFixed(2) + "%",
      series: [{ name: "累计换手率(估算)", type: "line", data: series, showSymbol: false,
        lineStyle: { width: 1.6, color: "#58a6ff" }, areaStyle: { color: "rgba(88,166,255,0.15)" },
        itemStyle: { color: "#58a6ff" } }],
    }));
    c.resize();
  }
  function renderOuterBuy(d, idx) {
    // 外盘内盘差：quote.outer - quote.inner（单值，是日级快照，无法分钟级）
    const c = charts.sub[idx]; if (!c) return;
    const f = d.minute || [];
    if (!f.length) return;
    const times = f.map(x => normT(x.t));
    const q = d.quote || {};
    const diff = (q.outer || 0) - (q.inner || 0);
    // 外盘/内盘是当日累计快照，逐分钟无意义：整段画同一条水平线，并明确标注为"日级快照"
    const series = times.map(() => diff);
    c.setOption(buildSubOption({
      times,
      yFmt: v => v.toLocaleString() + "手",
      tip: ps => "外盘-内盘(日级快照): " + ps[0].value.toLocaleString() + " 手",
      series: [{ name: "外内盘差(日级快照)", type: "line", data: series, showSymbol: false,
        lineStyle: { width: 1.6, type: "dashed", color: diff >= 0 ? DARK.up : DARK.down },
        areaStyle: { color: (diff >= 0 ? "248,81,73" : "63,185,80") + ",0.15" },
        itemStyle: { color: diff >= 0 ? DARK.up : DARK.down } }],
    }));
    c.resize();
  }
  function renderAmtDiff(d, idx) {
    // 每分钟成交额差分（万元）
    const c = charts.sub[idx]; if (!c) return;
    const m = d.minute || [];
    if (!m.length) return;
    const times = m.map(x => normT(x.t));
    const data = _toWan(_deltaByKey(m, "amount"));
    c.setOption(buildSubOption({
      times,
      yFmt: v => v.toFixed(0) + "万",
      tip: ps => ps[0].name + "<br/>成交额: " + ps[0].value.toFixed(1) + " 万",
      series: [{ name: "成交额差分", type: "bar", data, barWidth: "60%",
        itemStyle: { color: (p) => p.data >= 0 ? DARK.up : DARK.down } }],
    }));
    c.resize();
  }
  function renderMainRatio(d, idx) {
    // 主力占比：主力净流入 / 总成交额 × 100%
    const c = charts.sub[idx]; if (!c) return;
    const m = d.minute || [];
    if (!m.length) return;
    const times = m.map(x => normT(x.t));
    const f = d.fund || [];
    // 用 main 累计 + amount 累计 → 比率
    const series = [];
    for (let i = 0; i < m.length; i++) {
      const totalAmt = m[i].amount || 0;
      const mainNet = f[i] ? f[i].main : 0;
      if (totalAmt > 0) {
        series.push(+(mainNet / totalAmt * 100).toFixed(2));
      } else {
        series.push(0);
      }
    }
    c.setOption(buildSubOption({
      times,
      yFmt: v => v + "%",
      tip: ps => ps[0].name + "<br/>主力占比: " + ps[0].value.toFixed(2) + "%",
      series: [{ name: "主力占比", type: "line", data: series, showSymbol: false,
        lineStyle: { width: 1.6, color: DARK.purple },
        areaStyle: { color: "rgba(137,87,229,0.15)" }, itemStyle: { color: DARK.purple } },
        _zeroLine(times)],
    }));
    c.resize();
  }
  let _klineSeq = 0;
  let _lastKlineList = [];     // 最近一次成功加载的 K 线（用于双击取日期）
  let _lastKlineIdx = -1;       // 用户当前 hover 的 K 线索引（用于双击确定日期）
  async function loadKline(period) {
    const seq = ++_klineSeq;
    $("klineTitle").textContent = "加载中…";
    charts.p4.showLoading();
    try {
      // 现在分钟 K 优先走通达信本地 .lc1（全量历史，跨交易日完整序列），
      // 各周期(m5/m15/m30/m60)由 1 分钟线聚合，数据量充足，非空即有效。
      // 仅当某周期完全无数据时在分钟内逐级降级；不回退到日线（避免把日线当日当成分时）。
      const fallbackChain = { m60: "m30", m30: "m15", m15: "m5", m5: null };
      let p = period, list = null, lastErr = null;
      while (p) {
        const all = (p === "day" || p === "week" || p === "month");
        const limit = 0;  // 日线/分钟 K 均拉全量历史（通达信本地有多少取多少）
        let data;
        try {
          const r = await _fetchAbortable("kline", "/api/kline?code=" + encodeURIComponent(current) + "&period=" + p + "&limit=" + limit, 60000);
          data = await r.json();
        } catch (err) {
          lastErr = err;
          data = null;
        }
        if (seq !== _klineSeq) return;
        // 后端异常时返回 {error: ...}（HTTP 500），不能当成空数组；把错误记下来继续 fallback
        if (data && data.error) {
          lastErr = new Error(data.error);
          data = null;
        }
        if (Array.isArray(data) && data.length) { list = data; break; }
        // 日/周/月数据量天然充足（≥几百），失败也停止 fallback，避免把日线当日数据错当成分钟数据
        if (p === "day" || p === "week" || p === "month") { list = (Array.isArray(data) ? data : []); break; }
        p = fallbackChain[p];
      }
      if (!Array.isArray(list) || !list.length) {
        const msg = lastErr ? lastErr.message : "K线数据为空";
        throw new Error(msg);
      }
      renderKline(list, p);
      _lastKlineList = list;
      // 高亮实际使用周期按钮（fallback 后可能与用户点击不同）
      document.querySelectorAll(".kperiod").forEach(b => b.classList.toggle("active", b.dataset.p === p));
      const klineName = current.toUpperCase();
      const lastDate = (list.length && list[list.length - 1].date) || "";
      let staleNote = "";
      if (p === "day" && lastDate) {
        const days = Math.max(0, Math.round((Date.now() - new Date(lastDate).getTime()) / 86400000));
        if (days >= 3) staleNote = " · ⚠ 数据滞后 " + days + " 天（本地未更新）";
      }
      const intraNote = (p === "m60" || p === "m30" || p === "m15" || p === "m5") ? " · 本地" : "";
      $("klineTitle").textContent = klineName + " · " + periodLabel(p) + " · " + list.length + " 根"
        + (lastDate ? " · 截至 " + lastDate.slice(5) : "") + intraNote + staleNote;
    } catch (e) {
      if (seq !== _klineSeq) return;               // 被新请求取消 → 静默
      if (e && e.name === "AbortError") { $("klineTitle").textContent = "K线加载超时"; return; }
      $("klineTitle").textContent = "K线加载失败: " + e.message;
      // 失败时必须清掉旧图表，防止上一只股票的数据残留误导
      try {
        charts.p4.clear();
        charts.p4.setOption({ xAxis: [{ data: [] }, { data: [] }, { data: [] }], series: [] }, true);
      } catch (cle) { /* ignore */ }
      console.error(e);
    } finally {
      charts.p4.hideLoading();
    }
  }

  function periodLabel(p) {
    return { day: "日K", week: "周K", month: "月K", m60: "60分K", m30: "30分K", m15: "15分K", m5: "5分K" }[p] || p;
  }

  function renderKline(list, period) {
    const dates = list.map(x => x.date);
    // ECharts candlestick 需要 [open, close, low, high]
    const kd = list.map(x => [x.open, x.close, x.low, x.high]);
    const vols = list.map((x, i) => [i, x.vol, x.close >= x.open ? 1 : -1]);  // 用于 VOL 副图

    // MA5/10/20
    const closes = list.map(x => x.close);
    const ma = (n) => closes.map((_, i) => {
      if (i < n - 1) return null;
      let s = 0; for (let j = i - n + 1; j <= i; j++) s += closes[j];
      return +(s / n).toFixed(2);
    });
    const ma5 = ma(5), ma10 = ma(10), ma20 = ma(20);

    charts.p4.setOption({
      backgroundColor: DARK.bg,
      animation: false,
      tooltip: { trigger: "axis", confine: true, axisPointer: { type: "cross" },
        formatter: function(params) {
          if (!params || !params.length) return "";
          const N = { K线: "K线", VOL: "成交量", MA5: "MA5", MA10: "MA10", MA20: "MA20" };
          let html = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`;
          // 找到 K线 + VOL 的 dataIndex，用于反查 list 算昨收/振幅/成交额
          const kp = params.find(p => p.seriesName === "K线");
          const vp = params.find(p => p.seriesName === "VOL");
          const i = (kp || vp || {}).dataIndex || 0;
          const today = list[i];
          const prev = i > 0 ? list[i - 1] : null;
          const prevClose = prev ? prev.close : (today ? today.open : 0);
          params.forEach(p => {
            const lbl = N[p.seriesName] || p.seriesName;
            const dot = `<span style="display:inline-block;width:8px;height:8px;background:${p.color};border-radius:50%;margin-right:6px"></span>`;
            if (p.seriesName === "K线") {
              // 不依赖 ECharts 传入的 p.data 顺序，直接用 list[i] 的 OHLC，避免 dataIndex 被误当开盘价
              const o = today.open, c = today.close, l = today.low, h = today.high;
              const chg = prevClose ? (c - prevClose) / prevClose * 100 : 0;
              const amp = prevClose ? (h - l) / prevClose * 100 : 0;
              const cSign = chg >= 0 ? DARK.up : DARK.down;
              const amt = today.amount != null ? today.amount / 1e8 : c * today.vol * 100 / 1e8;
              html += `<div style="margin:4px 0">${dot}<b>${lbl}</b></div>`
                    + `<div style="padding-left:14px;line-height:1.6">`
                    + `开盘 <b>${o}</b> · 收盘 <b>${c}</b>　<span style="color:${cSign}">${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%</span><br/>`
                    + `最低 <b>${l}</b> · 最高 <b>${h}</b>　振幅 ${amp.toFixed(2)}%<br/>`
                    + `<span style="color:${DARK.label}">昨收 ${prevClose} · 成交额 ≈${amt.toFixed(2)} 亿</span>`
                    + `</div>`;
            } else if (p.seriesName === "VOL") {
              html += `<div style="margin:2px 0">${dot}${lbl}：${p.data[1].toLocaleString()} 手</div>`;
            } else {
              html += `<div style="margin:2px 0">${dot}${lbl}：${(+p.value).toFixed(2)}</div>`;
            }
          });
          return html;
        } },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: [
        { left: 56, right: 20, top: 30, height: "65%" },
        { left: 56, right: 20, top: "75%", height: "18%" },
      ],
      xAxis: [
        { type: "category", data: dates, scale: true, boundaryGap: false,
          axisLine: { lineStyle: { color: DARK.axis } },
          axisLabel: { color: DARK.label, fontSize: 10 },
          splitLine: { show: false },
          axisPointer: { z: 100 } },
        { type: "category", gridIndex: 1, data: dates, scale: true, boundaryGap: false,
          axisLine: { lineStyle: { color: DARK.axis } },
          axisTick: { show: false },
          axisLabel: { show: false },
          splitLine: { show: false } },
      ],
      yAxis: [
        { scale: true, splitNumber: 4,
          axisLine: { lineStyle: { color: DARK.axis } },
          axisLabel: { color: DARK.label, fontSize: 10, formatter: v => v.toFixed(2) },
          splitLine: { lineStyle: { color: "#1b222c" } } },
        { scale: true, gridIndex: 1, splitNumber: 2,
          axisLine: { lineStyle: { color: DARK.axis } },
          axisLabel: { color: DARK.label, fontSize: 10, formatter: v => (v >= 1e6 ? (v/1e6).toFixed(0) + "M" : v >= 1e3 ? (v/1e3).toFixed(0) + "K" : v) },
          splitLine: { show: false } },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1], start: 60, end: 100 },
        { type: "slider", xAxisIndex: [0, 1], height: 18, bottom: 4 },
      ],
      series: [
        { name: "K线", type: "candlestick", data: kd, xAxisIndex: 0, yAxisIndex: 0,
          itemStyle: { color: DARK.up, color0: DARK.down, borderColor: DARK.up, borderColor0: DARK.down } },
        { name: "MA5",  type: "line", data: ma5,  xAxisIndex: 0, yAxisIndex: 0, showSymbol: false,
          lineStyle: { width: 1, color: "#f0e68c" } },
        { name: "MA10", type: "line", data: ma10, xAxisIndex: 0, yAxisIndex: 0, showSymbol: false,
          lineStyle: { width: 1, color: "#9acd32" } },
        { name: "MA20", type: "line", data: ma20, xAxisIndex: 0, yAxisIndex: 0, showSymbol: false,
          lineStyle: { width: 1, color: "#daa520" } },
        { name: "VOL", type: "bar", data: vols, xAxisIndex: 1, yAxisIndex: 1,
          itemStyle: { color: (p) => p.data[2] > 0 ? DARK.up : DARK.down } },
      ],
    }, true);
    charts.p4.resize();
    _renderKlineSubs(list);
    // K线主图 dataZoom 同步到下方技术指标副图（缩放/拖动/平移都联动）
    _bindKlineZoomSync();
    bindKlineEvents();   // 首次渲染后绑定双击事件（仅一次）
  }

  // ---------- K线主图 → 副图 dataZoom 同步 ----------
  // 使用模块级稳定引用，避免每次 renderKline 生成新闭包导致 off() 无法移除旧监听、监听只增不减
  function _onKlineDataZoom() {
    if (!charts.klineSub || !charts.klineSub.length) return;
    const dz = (charts.p4.getOption().dataZoom || [])[0];
    if (!dz) return;
    const action = { type: "dataZoom" };
    if (dz.start != null) { action.start = dz.start; action.end = dz.end; }
    if (dz.startValue != null) { action.startValue = dz.startValue; action.endValue = dz.endValue; }
    charts.klineSub.forEach(c => { try { c.dispatchAction(action); } catch (e) {} });
  }
  function _bindKlineZoomSync() {
    charts.p4.off("dataZoom", _onKlineDataZoom);   // 稳定引用 → 旧监听可被正确移除
    charts.p4.on("dataZoom", _onKlineDataZoom);
  }

  // K 线面板交互：双击 / 回车 → 弹历史分时小图
  let _eventsBound = false;
  function bindKlineEvents() {
    if (_eventsBound) return;
    _eventsBound = true;
    charts.p4.on("click", params => {
      if (params && typeof params.dataIndex === "number") _lastKlineIdx = params.dataIndex;
    });
    // 双击直接取事件参数 dataIndex（不依赖先点击；先点击时也兼容旧逻辑）
    charts.p4.on("dblclick", params => {
      const idx = params && typeof params.dataIndex === "number" ? params.dataIndex : -1;
      showHistMinute(idx);
    });
  }
  function showHistMinute(forceIdx) {
    const idx = (typeof forceIdx === "number" && forceIdx >= 0) ? forceIdx : _lastKlineIdx;
    if (idx < 0 || !_lastKlineList[idx]) {
      $("histMsg").textContent = "请先点击某根 K 线选中日期";
      $("histModal").classList.remove("hidden");
      return;
    }
    const dateRaw = _lastKlineList[idx].date || "";
    const date = dateRaw.split(" ")[0] || dateRaw;  // 取日期部分，兼容 "2026-08-03 10:30"
    const dateCompact = date.replace(/-/g, "");
    const code = current;
    $("histTitle").textContent = code.toUpperCase() + " · " + date + " 历史分时";
    $("histMsg").textContent = "加载中…";
    $("histModal").classList.remove("hidden");
    // 每次打开都销毁旧实例，确保在 visible 容器上重新 init，根治 0x0 尺寸/缓存导致的白图
    if (window._histChart) {
      try { window._histChart.dispose(); } catch (e) {}
      window._histChart = null;
    }
    // 让浏览器先完成 modal 布局，避免 echarts.init 读到 0x0
    void $("histChart").offsetWidth;
    fetch("/api/minute?code=" + encodeURIComponent(code) + "&date=" + dateCompact)
      .then(r => r.json())
      .then(res => {
        // 历史某日：后端返回 {data, meta} 信封；兼容旧版纯数组
        const meta = res && res.meta ? res.meta : null;
        const data = res && res.data ? res.data : (Array.isArray(res) ? res : []);
        if (!Array.isArray(data) || !data.length) {
          let msg = date + " 暂无历史分时";
          if (meta && meta.mismatch) {
            msg += "：本地未下载该日分钟数据，免费在线源返回的不是该日真实走势";
          } else {
            msg += "（免费源仅保留最近约 30 天）";
          }
          $("histMsg").textContent = msg;
          renderHistChart([], date);
        } else {
          let srcNote = "";
          if (meta) {
            const srcName = { tdx: "本地通达信", tencent: "腾讯", eastmoney: "东财" }[meta.source] || meta.source;
            if (meta.source === "tdx") {
              srcNote = " · 来源 " + srcName;
            } else if (meta.local_last_date) {
              srcNote = " · 本地数据止于 " + meta.local_last_date.slice(5) + "，" + date.slice(5) + " 来自 " + srcName;
            } else {
              srcNote = " · 来自 " + srcName;
            }
          }
          $("histMsg").textContent = date + " · " + data.length + " 点" + srcNote;
          renderHistChart(data, date);
        }
      })
      .catch(e => {
        $("histMsg").textContent = "拉取失败: " + e.message;
        renderHistChart([], date);
      });
  }
  function renderHistChart(minute, date) {
    try {
      const el = $("histChart");
      // 强制浏览器完成 modal 布局后再取尺寸，避免 echarts 读到 0x0
      void el.offsetWidth; void el.offsetHeight;
      if (!window._histChart) window._histChart = echarts.init(el);
      window._histChart.clear();
      if (!minute || !minute.length) { return; }
      const times = minute.map(x => normT(x.t));
      const prices = minute.map(x => x.price);
      const avgs = minute.map(x => x.avg);
      const vols = minute.map(x => x.vol);
      window._histChart.setOption({
        backgroundColor: DARK.bg,
        legend: { data: ["价格", "均价"], textStyle: { color: DARK.label }, top: 4 },
        grid: { left: 50, right: 60, top: 36, bottom: 30 },
        tooltip: { trigger: "axis", confine: true },
        xAxis: { type: "category", data: times, axisLabel: { fontSize: 10, interval: 29 } },
        yAxis: [
          { type: "value", scale: true, axisLabel: { color: DARK.label, fontSize: 10 } },
          { type: "value", splitNumber: 3, axisLabel: { color: DARK.label, fontSize: 10, formatter: v => v >= 1e4 ? (v/1e4).toFixed(0) + "万手" : v + "手" } }
        ],
        series: [
          { name: "价格", type: "line", data: prices, showSymbol: false,
            lineStyle: { width: 1.5, color: DARK.price }, itemStyle: { color: DARK.price } },
          { name: "均价", type: "line", data: avgs, showSymbol: false,
            lineStyle: { width: 1.5, color: "#ffd700", type: "dashed" }, itemStyle: { color: "#ffd700" } },
          { name: "成交量", type: "bar", data: vols, yAxisIndex: 1,
            itemStyle: { color: DARK.gray, opacity: 0.5 } }
        ]
      });
      // modal 显示后 DOM 尺寸可能仍在过渡，setTimeout 0 在 layout 之后 resize 确保图能真正画出
      setTimeout(() => {
        if (window._histChart) window._histChart.resize();
      }, 0);
    } catch (e) {
      $("histMsg").textContent = "图表渲染失败: " + e.message;
      console.error("renderHistChart error", e);
    }
  }

  // ---------- 视图切换 ----------
  function switchView(v) {
    _view = v;
    $("minuteView").classList.toggle("hidden", v !== "minute");
    $("klineView").classList.toggle("hidden", v !== "kline");
    $("watchlistView").classList.toggle("hidden", v !== "watchlist");
    if (v === "kline") {
      loadKline(_klinePeriod || "day");
      setTimeout(() => charts.p4.resize(), 50);
    } else if (v === "watchlist") {
      loadWatchlistTable();
    } else {
      charts.p4.clear();
      setTimeout(() => {
        charts.p1.resize();
        charts.sub.forEach(c => { try { c.resize(); } catch (e) {} });
      }, 50);
    }
  }

  // ---------- US-006 自选批量表格（Sprint 3） ----------
  async function loadWatchlistTable() {
    const tb = document.querySelector("#watchlistTable tbody");
    if (!tb) return;
    try {
      const r = await fetch("/api/watchlist");
      const items = await r.json();
      const wl = items.filter(x => x.in_watchlist);
      if (!wl.length) {
        tb.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#8b949e">暂无自选标的，点击顶部「+」加入</td></tr>`;
        return;
      }
      const codes = wl.map(x => x.code);
      const many = await (await fetch("/api/many?codes=" + codes.join(","))).json();
      const rows = [];
      for (const item of wl) {
        const code = item.code;
        const d = many[code] || {};
        const q = d.quote;
        if (!q) continue;
        const cls = q.change_pct >= 0 ? "up" : "down";
        rows.push(`<tr data-code="${code}">`
          + `<td>${code.toUpperCase()}</td>`
          + `<td>${q.name || code}</td>`
          + `<td>${q.price.toFixed(2)}</td>`
          + `<td class="${cls}">${(q.change_pct >= 0 ? "+" : "")}${q.change_pct.toFixed(2)}%</td>`
          + `<td class="${cls}">${(q.change >= 0 ? "+" : "")}${q.change.toFixed(2)}</td>`
          + `<td>${q.amount >= 1e8 ? (q.amount / 1e8).toFixed(2) + "亿" : (q.amount / 1e4).toFixed(0) + "万"}</td>`
          + `<td>${q.turnover_pct != null ? q.turnover_pct + "%" : "--"}</td>`
          + `</tr>`);
      }
      tb.innerHTML = rows.join("");
      tb.querySelectorAll("tr").forEach(tr => {
        tr.addEventListener("click", () => switchTo(tr.dataset.code));
      });
    } catch (e) {
      tb.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#f85149">批量加载失败: ${e.message}</td></tr>`;
    }
  }

  // ---------- 自选列表（datalist 输入式下拉：watchlist + 全部预置池） ----------
  async function loadWatchlist() {
    const r = await fetch("/api/watchlist");
    const items = await r.json();
    const dl = $("watchOptions");
    const inp = $("watchInput");
    // 按 watchlist 在前 / 池在后分组；option value=code（与显示代码完全一致，避免用户输入与 code 冲突）
    const opts = items.map(x => {
      const code = x.code;
      const name = x.name && x.name !== code ? x.name : code.toUpperCase();
      const display = `${name} (${code.toUpperCase()})`;
      return `<option value="${code}" label="${display}">${display}${x.in_watchlist ? " ★" : ""}</option>`;
    });
    dl.innerHTML = opts.join("");
    if (items.some(x => x.code === current)) inp.value = current;
  }
  // 「+」= 把当前正在看的标的加入自选（盯盘场景最常用）
  async function addWatch() {
    const code = current;
    await fetch("/api/watchlist", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "add", code }) });
    await loadWatchlist();
    $("stSource").textContent = "已加自选";
  }
  // 「−」= 把当前正在看的标的移出自选（US-032，与「+」对称）
  async function removeWatch() {
    const code = current;
    await fetch("/api/watchlist", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "remove", code }) });
    await loadWatchlist();
    $("stSource").textContent = "已移出自选";
  }
  // ---------- 复盘/分析记录（US-017） ----------
  function _esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  async function openAnalysis() {
    $("analysisTitle").textContent = "复盘记录 · " + current.toUpperCase();
    $("analysisInput").value = "";
    $("analysisModal").classList.remove("hidden");
    await loadAnalysis();
  }
  async function loadAnalysis() {
    const list = $("analysisList");
    try {
      const r = await fetch("/api/analysis?code=" + encodeURIComponent(current));
      const rows = await r.json();
      if (!rows.length) { list.innerHTML = `<div class="a-empty">暂无记录，写下第一条分析</div>`; return; }
      list.innerHTML = rows.map(x => {
        const t = new Date((x.ts || 0) * 1000);
        const ts = isNaN(t) ? "" : t.toLocaleString("zh-CN", { hour12: false });
        const note = (x.data && x.data.note) || "";
        return `<div class="a-item"><div class="a-meta"><span>${ts}</span><span>${x.code.toUpperCase()}</span></div><div class="a-note">${_esc(note)}</div></div>`;
      }).join("");
    } catch (e) { list.innerHTML = `<div class="a-empty">加载失败</div>`; }
  }
  async function saveAnalysis() {
    const note = $("analysisInput").value.trim();
    if (!note) return;
    await fetch("/api/analysis", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: current, note }) });
    $("analysisInput").value = "";
    await loadAnalysis();
  }

  function switchTo(code) {
    current = code;
    latestData = null;                // 清空旧 quote，防止 K 线标题使用陈旧 name 错配
    _selectedMinuteIdx = -1;          // 重置分钟选中索引
    _minuteList = [];
    $("watchInput").value = code;
    $("searchResults").classList.remove("show");
    $("searchInput").value = "";
    if (_view === "kline") loadKline(_klinePeriod || "day");
    loadQuote(code);
  }

  // ---------- 搜索 ----------
  let _searchTimer = null;
  let _searchActive = -1;   // 当前高亮的搜索项（US-029 键盘导航）
  function _searchHighlight(box, idx) {
    const items = box.querySelectorAll(".item");
    items.forEach((el, i) => el.classList.toggle("active", i === idx));
    const el = items[idx];
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }
  function setupSearch() {
    const input = $("searchInput");
    const box = $("searchResults");
    input.addEventListener("input", () => {
      clearTimeout(_searchTimer);
      _searchTimer = setTimeout(() => doSearch(input.value.trim()), 200);
    });
    input.addEventListener("focus", () => {
      if (box.children.length) box.classList.add("show");
    });
    document.addEventListener("click", e => {
      if (!e.target.closest(".search-wrap")) box.classList.remove("show");
    });
    input.addEventListener("keydown", e => {
      const items = box.querySelectorAll(".item");
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!items.length) return;
        _searchActive = (_searchActive + 1) % items.length;
        _searchHighlight(box, _searchActive);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (!items.length) return;
        _searchActive = (_searchActive - 1 + items.length) % items.length;
        _searchHighlight(box, _searchActive);
      } else if (e.key === "Enter") {
        const el = _searchActive >= 0 ? items[_searchActive] : box.querySelector(".item");
        if (el) el.click();
      }
    });
  }
  async function doSearch(q) {
    const box = $("searchResults");
    const r = await fetch("/api/search?q=" + encodeURIComponent(q));
    const list = await r.json();
    _searchActive = -1;
    box.innerHTML = list.length === 0
      ? `<div class="empty-hint">无匹配结果</div>`
      : list.map(x => `<div class="item" data-code="${x.code}"><span class="code">${x.code.toUpperCase()}</span>${x.name}<span class="cat">${x.cat}</span></div>`).join("");
    box.classList.add("show");
    box.querySelectorAll(".item").forEach(el => {
      el.addEventListener("click", () => switchTo(el.dataset.code));
    });
  }

  // ---------- 启动 ----------
  let _klinePeriod = "day";
  function init() {
    initCharts();
    _buildSubcharts();
    _buildKlineSubs();
    setupSearch();
    loadWatchlist();
    loadQuote(current);
    setupContextMenu();
    setupSubConfigModal();
    setupKlineSubConfigModal();

    function on(id, ev, fn) {
      const el = $(id);
      if (!el) { console.warn("[init] 未找到 #" + id + "，跳过事件绑定（可能缓存了旧页面）"); return; }
      el.addEventListener(ev, fn);
    }
    on("watchInput", "change", e => {
      const v = e.target.value.trim();
      // 从 datalist 选中时 value=code；用户输入中文时不匹配，跳过
      if (v && v !== current) switchTo(v);
    });
    on("addBtn", "click", addWatch);
    on("delBtn", "click", removeWatch);
    on("refreshBtn", "click", () => loadQuote(current));
    on("klineBtn", "click", () => switchView(_view === "kline" ? "minute" : "kline"));
    on("backBtn", "click", () => switchView("minute"));
    // US-006 自选批量表格
    on("watchlistBtn", "click", () => switchView(_view === "watchlist" ? "minute" : "watchlist"));
    on("analysisBtn", "click", openAnalysis);
    on("analysisClose", "click", () => $("analysisModal")?.classList.add("hidden"));
    on("analysisSave", "click", saveAnalysis);
    on("analysisModal", "click", e => { if (e.target.id === "analysisModal") $("analysisModal")?.classList.add("hidden"); });
    $("wlRefreshBtn").addEventListener("click", () => loadWatchlistTable());
    document.querySelectorAll(".kperiod").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".kperiod").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        _klinePeriod = btn.dataset.p;
        loadKline(_klinePeriod);
      });
    });

    // 分时面板双击/回车 → 切到 K线
    const p1 = $("p1");
    p1.addEventListener("dblclick", () => switchView("kline"));
    p1.tabIndex = 0;
    // 全局键盘监听：分时视图下 ↑/↓ 切换分钟详情（焦点不在输入元素时）
    document.addEventListener("keydown", e => {
      if (_view !== "minute") return;
      if (!_minuteList.length) return;
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        if (_selectedMinuteIdx < 0) _selectedMinuteIdx = _minuteList.length - 1;
        _selectedMinuteIdx = e.key === "ArrowUp"
          ? Math.min(_minuteList.length - 1, _selectedMinuteIdx + 1)
          : Math.max(0, _selectedMinuteIdx - 1);
        renderMinuteDetail(_minuteList, _selectedMinuteIdx);
      } else if (e.key === "Enter") {
        switchView("kline");
      }
    });
    p1.addEventListener("click", () => p1.focus());

    timer = setInterval(() => {
      if (_view === "minute") loadQuote(current);
    }, REFRESH_MS);

    // 同步左右两侧高度：列表底边对齐"资金博弈"图底框
    function syncMinuteRightHeight() {
      const left = document.querySelector(".minute-left");
      const right = document.querySelector(".minute-right");
      if (!left || !right) return;
      const h = left.offsetHeight;
      if (h > 0) right.style.height = h + "px";
    }
    syncMinuteRightHeight();
    // ECharts 首次渲染后再同步一次（chart 容器可能延迟撑开）
    setTimeout(syncMinuteRightHeight, 100);
    setTimeout(syncMinuteRightHeight, 500);
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(() => syncMinuteRightHeight());
      const leftEl = document.querySelector(".minute-left");
      if (leftEl) ro.observe(leftEl);
    }

    window.addEventListener("resize", () => {
      syncMinuteRightHeight();
      if (_view === "minute") {
        if (charts.p1) charts.p1.resize();
        (charts.sub || []).forEach(c => c && c.resize());   // p2/p3/p5 从未 init，改用实际的副图数组
      } else {
        if (charts.p4) charts.p4.resize();
        (charts.klineSub || []).forEach(c => c && c.resize());
      }
    });

    // 历史分时模态关闭
    function closeHistModal() {
      $("histModal").classList.add("hidden");
      if (window._histChart) window._histChart.clear();
    }
    $("histClose").addEventListener("click", closeHistModal);
    $("histModal").addEventListener("click", e => { if (e.target.id === "histModal") closeHistModal(); });
    // 公告模态关闭
    $("annClose").addEventListener("click", () => $("annModal").classList.add("hidden"));
    $("annModal").addEventListener("click", e => { if (e.target.id === "annModal") $("annModal").classList.add("hidden"); });
    // K 线视图下按 Enter → 弹当前 hover 日期的历史分时；←/→ 方向键平移 K 线
    document.addEventListener("keydown", e => {
      if (_view !== "kline") return;
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "Enter" && $("histModal").classList.contains("hidden")) {
        showHistMinute();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        _klinePan(e.key === "ArrowLeft" ? 1 : -1);   // 左=往后，右=往前
      }
    });
  }

  // K 线图左右平移（与鼠标滚轮 move 一致：左键=往后看历史，右键=往前看最新）
  function _klinePan(dir) {
    if (!charts.p4) return;
    const opt = charts.p4.getOption();
    const dz = (opt.dataZoom || [])[0];
    if (!dz) return;
    // 计算平移量：当前可视范围的 5%
    let start = parseFloat(dz.start), end = parseFloat(dz.end);
    if (isNaN(start) || isNaN(end)) {
      // startValue/endValue 模式（xAxis 是 category）
      const startValue = dz.startValue, endValue = dz.endValue;
      if (startValue == null || endValue == null) return;
      const span = endValue - startValue;
      const step = Math.max(1, Math.round(span * 0.05 * dir));
      charts.p4.dispatchAction({ type: "dataZoom", startValue: startValue + step, endValue: endValue + step });
    } else {
      const range = end - start;
      const step = range * 0.05 * dir;
      charts.p4.dispatchAction({ type: "dataZoom", start: start - step, end: end - step });
    }
  }

  // ---------- 右键菜单（point-left 空白区） ----------
  function setupContextMenu() {
    const menu = $("contextMenu");
    const show = (x, y) => {
      menu.style.left = x + "px";
      menu.style.top = y + "px";
      menu.classList.remove("hidden");
    };
    const hide = () => menu.classList.add("hidden");
    // 在 .minute-left 上右键触发（在 chart 区域会带 eCharts 默认菜单，需要 preventDefault）
    document.addEventListener("contextmenu", e => {
      const ml = e.target.closest(".minute-left, .minute-mid, .minute-right, #klineView");
      if (!ml) { hide(); return; }
      e.preventDefault();
      show(e.clientX, e.clientY);
      // K线视图下额外显示"K线副图配置"
      const isKline = e.target.closest("#klineView");
      $("ctxConfigKlineSub").style.display = isKline ? "block" : "none";
    });
    document.addEventListener("click", e => {
      if (!e.target.closest("#contextMenu")) hide();
    });
    $("ctxConfigSub").addEventListener("click", () => { hide(); openSubConfig(); });
    $("ctxConfigKlineSub").addEventListener("click", () => { hide(); openKlineSubConfig(); });
    $("ctxFundFlow").addEventListener("click", () => { hide(); showFundFlow(); });
    $("ctxExportCsv").addEventListener("click", () => { hide(); exportCsv(); });
    $("ctxRefresh").addEventListener("click", () => { hide(); loadQuote(current); });
  }

  // ---------- K线副图配置 modal ----------
  function setupKlineSubConfigModal() {
    $("klineSubConfigClose").addEventListener("click", () => $("klineSubConfigModal").classList.add("hidden"));
    $("klineSubConfigModal").addEventListener("click", e => {
      if (e.target.id === "klineSubConfigModal") $("klineSubConfigModal").classList.add("hidden");
    });
    $("klineSubConfigReset").addEventListener("click", () => {
      _klineSubConfig = KLINE_SUB_DEFAULT.slice();
      openKlineSubConfig();
    });
    $("klineSubConfigSave").addEventListener("click", () => {
      const newConfig = [];
      document.querySelectorAll("#klineSubConfigRows select").forEach(sel => newConfig.push(sel.value));
      _klineSubConfig = newConfig;
      _saveKlineSubConfig();
      _buildKlineSubs();
      _renderKlineSubs(_lastKlineList || []);
      $("klineSubConfigModal").classList.add("hidden");
    });
  }

  function openKlineSubConfig() {
    const box = $("klineSubConfigRows"); box.innerHTML = "";
    _klineSubConfig.forEach((tid, i) => {
      const row = document.createElement("div");
      row.className = "sub-row";
      row.innerHTML = `<span class="lbl">副图 ${i + 1}</span><select></select>`;
      const sel = row.querySelector("select");
      KLINE_SUB_TYPES.forEach(t => {
        const o = document.createElement("option");
        o.value = t.id; o.textContent = t.name;
        if (t.id === tid) o.selected = true;
        sel.appendChild(o);
      });
      box.appendChild(row);
    });
    $("klineSubConfigModal").classList.remove("hidden");
  }

  // ---------- US-015 分钟资金流明细 modal ----------
  function showFundFlow() {
    const d = latestData || {};
    const f = d.fund || [];
    if (!f.length) { alert("暂无资金流数据"); return; }
    const tb = $("fundFlowBody");
    const rows = [];
    f.forEach((x, i) => {
      const prev = i > 0 ? f[i - 1] : null;
      const delta = (key) => prev ? (x[key] - prev[key]) / 1e4 : 0;
      const w = (v) => { const r = v.toFixed(0); return r >= 0 ? "+" + r : r; };
      rows.push(`<tr><td>${normT(x.t)}</td>`
        + `<td class="${delta("main") >= 0 ? "up" : "down"}">${w(delta("main"))}</td>`
        + `<td class="${delta("super_big") >= 0 ? "up" : "down"}">${w(delta("super_big"))}</td>`
        + `<td class="${delta("big") >= 0 ? "up" : "down"}">${w(delta("big"))}</td>`
        + `<td class="${delta("mid") >= 0 ? "up" : "down"}">${w(delta("mid"))}</td>`
        + `<td class="${delta("small") >= 0 ? "up" : "down"}">${w(delta("small"))}</td></tr>`);
    });
    tb.innerHTML = rows.join("");
    $("fundFlowTitle").textContent = `分钟资金流明细 · ${current.toUpperCase()} · ${f.length} 分钟（万元，红进绿出）`;
    $("fundFlowModal").classList.remove("hidden");
  }

  // ---------- US-012 导出 CSV（Sprint 4） ----------
  function exportCsv() {
    const d = latestData || {};
    let csv = "";
    // 分时
    const m = d.minute || [];
    if (m.length) {
      csv += "=== 分时 ===\n时间,价格,均价,量(手),额(万元)\n";
      m.forEach((x, i) => {
        const prev = i > 0 ? m[i - 1] : null;
        const vol = prev ? Math.max(0, x.vol - prev.vol) : x.vol;
        const amt = prev ? Math.max(0, x.amount - prev.amount) : x.amount;
        csv += `${x.t},${x.price},${x.avg},${vol},${(amt / 1e4).toFixed(1)}\n`;
      });
    }
    // 资金流
    const f = d.fund || [];
    if (f.length) {
      csv += "\n=== 资金流（元） ===\n时间,主力,超大单,大单,中单,小单\n";
      f.forEach(x => {
        csv += `${x.t},${x.main},${x.super_big},${x.big},${x.mid},${x.small}\n`;
      });
    }
    if (!csv) { alert("暂无数据可导出"); return; }
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${current}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ---------- 副图配置 modal ----------
  function setupSubConfigModal() {
    $("subConfigClose").addEventListener("click", () => $("subConfigModal").classList.add("hidden"));
    $("subConfigModal").addEventListener("click", e => {
      if (e.target.id === "subConfigModal") $("subConfigModal").classList.add("hidden");
    });
    // 资金流明细 modal 关闭
    $("fundFlowClose").addEventListener("click", () => $("fundFlowModal").classList.add("hidden"));
    $("fundFlowModal").addEventListener("click", e => {
      if (e.target.id === "fundFlowModal") $("fundFlowModal").classList.add("hidden");
    });
    // 副图个数下拉（1~5）
    const countSel = $("subConfigCount");
    countSel.innerHTML = "";
    for (let i = 1; i <= 5; i++) {
      const o = document.createElement("option");
      o.value = i; o.textContent = i + " 个";
      countSel.appendChild(o);
    }
    countSel.addEventListener("change", () => _renderSubConfigRows(parseInt(countSel.value)));
    $("subConfigReset").addEventListener("click", () => {
      _subConfig = SUB_DEFAULT.slice();
      openSubConfig();
    });
    $("subConfigSave").addEventListener("click", () => {
      const count = parseInt(countSel.value);
      // 读取每行 select
      const newConfig = [];
      for (let i = 0; i < count; i++) {
        const sel = $(`subConfigRow_${i}`);
        newConfig.push(sel ? sel.value : SUB_DEFAULT[Math.min(i, SUB_DEFAULT.length - 1)]);
      }
      _subConfig = newConfig;
      _saveSubConfig();
      _buildSubcharts();
      _renderSubcharts(latestData || {});
      $("subConfigModal").classList.add("hidden");
    });
  }

  function openSubConfig() {
    $("subConfigCount").value = _subConfig.length;
    _renderSubConfigRows(_subConfig.length);
    $("subConfigModal").classList.remove("hidden");
  }

  function _renderSubConfigRows(count) {
    const box = $("subConfigRows"); box.innerHTML = "";
    for (let i = 0; i < count; i++) {
      const current = _subConfig[i] || SUB_DEFAULT[Math.min(i, SUB_DEFAULT.length - 1)];
      const row = document.createElement("div");
      row.className = "sub-row";
      row.innerHTML = `<span class="lbl">副图 ${i + 1}</span><select id="subConfigRow_${i}"></select>`;
      const sel = row.querySelector("select");
      SUBCHART_TYPES.forEach(t => {
        const o = document.createElement("option");
        o.value = t.id; o.textContent = t.name;
        if (t.id === current) o.selected = true;
        sel.appendChild(o);
      });
      box.appendChild(row);
    }
  }

  // 由宿主（deepthinkcomp_stock stock.js）控制初始化时机：
  // 渲染完整 DOM 后调用 window.__SINGLE_APP__.boot(code)
  window.__SINGLE_APP__ = {
    boot: function (code) { current = code; init(); },
    setCode: function (code) { current = code; },
    getView: function () { return _view; },
    switchToKline: function () { if (_view !== "kline") switchView("kline"); },
    switchToMinute: function () { if (_view !== "minute") switchView("minute"); },
    cleanup: function () { if (timer) { clearInterval(timer); timer = null; } },
    reset: function () { current = ""; latestData = null; _minuteList = []; _selectedMinuteIdx = -1; },
  };

})();
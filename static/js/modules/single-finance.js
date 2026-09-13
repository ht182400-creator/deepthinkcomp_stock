// 财务分析视图（数据源：/api/stock/finance_full → panels/fund_local.py 本地财务面板）
//
// 四个标签页：
//   indicators 财务指标  —— 多期科目表（27 项 × N 期）+ 每股收益柱状图
//   diagnose   财务诊断  —— 综合评分环形 + 五维雷达（盈利/成长/偿债/现金流/运营）
//   trend      成长趋势  —— 营收 / 净利 / ROE / 毛利率 折线
//   valuation  估值分析  —— PE(TTM) / PB / PS / 每股指标
//
// 用法（single-app.js）：
//   import { fetchFinance, renderFinance } from "./single-finance.js";
//   const d = await fetchFinance("sh600519");
//   renderFinance(document.getElementById("finBody"), d, "indicators", echarts);

const API = (code, price) =>
  `/api/stock/finance_full?code=${encodeURIComponent(code)}${price ? `&price=${price}` : ""}`;

/** 拉取财务分析数据。 */
export async function fetchFinance(code, price) {
  const r = await fetch(API(code, price));
  return await r.json();
}

const esc = (s) =>
  String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const num = (v, digits = 2) =>
  v == null || v === "" ? "--" : Number(v).toFixed(digits);

const cls = (v) => (v == null ? "" : v >= 0 ? "up" : "down");

/** 取数组末值（最新期），空数组返回 null。 */
const lastOf = (arr) => (Array.isArray(arr) && arr.length ? arr[arr.length - 1] : null);

/** 卡片配色阈值（仅用于提示"偏离常态"，非投资建议） */
const TH = {
  DEBT_HIGH: 70,        // 资产负债率 > 70% 提示偏高
  CURRENT_LOW: 1.0,     // 流动比率 < 1 提示短期偿债压力
  OCF_NP_GOOD: 100,     // 经营现金流/净利 ≥ 100% 利润含金量高
  OCF_NP_LOW: 60,       // < 60% 提示利润含金量偏低
  DIM_GOOD: 80,         // 五维评分 ≥ 80 良好
  DIM_WEAK: 60,         // 五维评分 < 60 偏弱
};

/** 单张 KPI 卡片：label 标签 / value 数值（null→"--"）/ color 配色类 / hint 小字说明。 */
const kpiCard = (label, value, color = "", hint = "") =>
  `<div class="fin-vp-card">
     <div class="lbl">${esc(label)}</div>
     <div class="val ${color}">${value == null || value === "" ? "--" : esc(value)}</div>
     ${hint ? `<div class="hint">${esc(hint)}</div>` : ""}
   </div>`;

/** 一组 KPI 卡片（自动网格换行）。 */
const kpiGrid = (cards) => `<div class="fin-vp-grid">${cards.join("")}</div>`;

/** 分组：小标题 + 卡片网格。 */
const kpiSection = (title, cards) =>
  `<div class="mp-section fin-val-sec"><div class="mp-h">${esc(title)}</div>${kpiGrid(cards)}</div>`;

/** [标签, 数值数组/数值, 单位, 配色类, 小字说明] → 卡片（数值数组取末值；负值自动标绿）。 */
const valCard = ([label, value, unit = "", color = "", hint = ""]) => {
  const v = Array.isArray(value) ? lastOf(value) : value;
  return kpiCard(label, v == null || v === "" ? null : `${num(v, 2)}${unit}`,
                 color || valCls(v), hint);
};

/* ---------- 变化值渲染（同比 / 环比）----------
 * 约定（A 股习惯）：↑ 红 = 增长、↓ 绿 = 下降、→ 白 = 持平。
 * 持平容差 FLAT_EPS：|变化| < 0.05（个百分点）视为持平，避免浮点噪声与"永远不为 0"的问题。
 */
const FLAT_EPS = 0.1;

/** 醒目标记：箭头单独放大 + 浅色底（底色随父级 up/down/flat 变化）。 */
const ARROW = (a) => `<span class="arw">${a}</span>`;

/** 变化值 → { cls, html }：html 含醒目箭头与带符号数值（如 "↑ +21.2%"）。 */
function chg(v, { pct = true, digits = 2 } = {}) {
  if (v == null || v === "") return { cls: "", html: "--" };
  const tail = pct ? "%" : "";
  const body = `${v > 0 ? "+" : ""}${Number(v).toFixed(digits)}${tail}`;
  if (Math.abs(v) < FLAT_EPS) return { cls: "flat", html: `${ARROW("→")}${body}` };
  return v > 0
    ? { cls: "up", html: `${ARROW("↑")}${body}` }
    : { cls: "down", html: `${ARROW("↓")}${body}` };
}

/** 变化卡片：值 = 醒目箭头 + 带符号数值（自带红/绿/白配色；直接拼 HTML，避免箭头被转义）。 */
const chgCard = (label, v, { pct = true, digits = 1, hint = "" } = {}) => {
  const c = chg(v, { pct, digits });
  return `<div class="fin-vp-card">
     <div class="lbl">${esc(label)}</div>
     <div class="val ${c.cls}">${c.html}</div>
     ${hint ? `<div class="hint">${esc(hint)}</div>` : ""}
   </div>`;
};

/* ---------- 指标字典：口径说明 + 配色语义 ----------
 * 配色语义（全模块统一，每个标签顶部都有图例）：
 *   sign  → 红(≥0) / 绿(<0)：**仅**用于"同比增速"这类有涨跌方向的指标（A股红涨绿跌）
 *   warn  → 橙：触发阈值时提示"偏离常态"（负债率过高、流动比率过低等）
 *   plain → 中性白：金额 / 每股 / 倍数 / 比率，本身无正负好坏之分
 * 说明：此前"所有百分数按正负着色"会让 ROE、毛利率等常年为正的指标全变红，容易被误读。
 */
const COLOR_SIGN = "sign";
const COLOR_WARN = "warn";
const COLOR_PLAIN = "plain";

const IND_META = {
  eps:            { desc: "每股收益（基本），单位：元", color: COLOR_PLAIN },
  eps_deduct:     { desc: "扣非每股收益：剔除一次性损益后的每股盈利，单位：元", color: COLOR_PLAIN },
  bvps:           { desc: "每股净资产 = 净资产 / 总股本，单位：元", color: COLOR_PLAIN },
  ocf_ps:         { desc: "每股经营现金流 = 经营现金流 / 总股本，单位：元", color: COLOR_PLAIN },
  rev_yi:         { desc: "营业总收入 TTM（近 12 个月滚动），单位：亿元", color: COLOR_PLAIN },
  np_yi:          { desc: "归母净利润 TTM（近 12 个月滚动），单位：亿元", color: COLOR_PLAIN },
  npd_yi:         { desc: "扣非归母净利润 TTM（剔除一次性损益），单位：亿元", color: COLOR_PLAIN },
  ocf_yi:         { desc: "经营活动现金流 TTM，单位：亿元", color: COLOR_PLAIN },
  ta_yi:          { desc: "总资产，单位：亿元", color: COLOR_PLAIN },
  te_yi:          { desc: "净资产（归母权益），单位：亿元", color: COLOR_PLAIN },
  roe:            { desc: "净资产收益率（报告期累计口径：Q1≈全年 1/4、Q4=全年，规则锯齿属正常）", color: COLOR_PLAIN },
  roe_w:          { desc: "加权平均净资产收益率（考虑期间权益变动，累计口径）", color: COLOR_PLAIN },
  gp_margin:      { desc: "销售毛利率 =（营业总收入 − 营业成本）/ 营业总收入", color: COLOR_PLAIN },
  np_margin:      { desc: "销售净利率 = 净利润 / 营业总收入", color: COLOR_PLAIN },
  op_margin:      { desc: "营业利润率 = 营业利润 / 营业总收入", color: COLOR_PLAIN },
  debt_ratio:     { desc: `资产负债率 = 总负债 / 总资产；> ${TH.DEBT_HIGH}% 提示偏高`, color: COLOR_WARN, warn: (v) => v > TH.DEBT_HIGH },
  current_ratio:  { desc: `流动比率 = 流动资产 / 流动负债；< ${TH.CURRENT_LOW} 提示短期偿债压力`, color: COLOR_WARN, warn: (v) => v < TH.CURRENT_LOW },
  quick_ratio:    { desc: `速动比率 =（流动资产 − 存货）/ 流动负债；< ${TH.CURRENT_LOW} 提示偿债压力`, color: COLOR_WARN, warn: (v) => v < TH.CURRENT_LOW },
  ocf_to_np:      { desc: `经营现金流 / 净利润；≥ ${TH.OCF_NP_GOOD}% 含金量高，< ${TH.OCF_NP_LOW}% 偏低`, color: COLOR_WARN, warn: (v) => v < TH.OCF_NP_LOW },
  rev_yoy:        { desc: "营业总收入同比增速（红 = 增长，绿 = 下降）", color: COLOR_SIGN },
  np_yoy:         { desc: "归母净利润同比增速（红 = 增长，绿 = 下降）", color: COLOR_SIGN },
  npd_yoy:        { desc: "扣非净利润同比增速（红 = 增长，绿 = 下降）", color: COLOR_SIGN },
  ar_turnover:    { desc: "应收账款周转率（次/年，越高回款越快）", color: COLOR_PLAIN },
  inv_turnover:   { desc: "存货周转率（次/年，越高去化越快）", color: COLOR_PLAIN },
  asset_turnover: { desc: "总资产周转率 = 营业总收入 / 总资产（次）", color: COLOR_PLAIN },
  equity_turnover:{ desc: "净资产周转率 = 营业总收入 / 净资产（次）", color: COLOR_PLAIN },
  holders:        { desc: "股东户数（户）；户数下降通常意味着筹码趋于集中", color: COLOR_PLAIN },
};

/** 取某指标某期的配色类（'' = 中性白）。 */
function indClass(key, v) {
  if (v == null) return "";
  const meta = IND_META[key];
  if (!meta) return "";
  if (meta.color === COLOR_SIGN) return cls(v);
  if (meta.color === COLOR_WARN) return meta.warn && meta.warn(v) ? "warn" : "";
  return "";
}

/** 负值标绿（数值为负 = 负向）；正数/零保持中性白 —— 不"见正即红"。 */
const valCls = (v) => (typeof v === "number" && v < 0 ? "down" : "");

/** 指标配色：先按 IND_META 规则（同比箭头 / 阈值橙），否则负值标绿。 */
function finCls(key, v) {
  return indClass(key, v) || valCls(v);
}

/** 统一配色图例（每个标签顶部展示，解释"数据颜色"的含义）。 */
const finLegend = () =>
  `<div class="fin-legend">
     <span class="lg sw-up"><i></i>↑ 红 = 增长（同比 / 环比为正）</span>
     <span class="lg sw-down"><i></i>↓ 绿 = 负向（下降 / 数值为负）</span>
     <span class="lg sw-flat"><i></i>→ 白 = 持平（|变化| &lt; 0.1）</span>
     <span class="lg sw-warn"><i></i>橙 = 偏离常态警示（触发阈值）</span>
     <span class="lg sw-plain"><i></i>白 = 中性（金额 / 每股 / 倍数 / 比率）</span>
   </div>`;

/** 20260630 → 26-06-30 */
const fmtPeriod = (p) => {
  const s = String(p || "");
  return s.length === 8 ? `${s.slice(2, 4)}-${s.slice(4, 6)}-${s.slice(6)}` : s;
};

/** 20260630 → 26Q2 */
const fmtQuarter = (p) => {
  const s = String(p || "");
  const q = { "03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4" }[s.slice(4, 6)] || "";
  return s.length === 8 ? `${s.slice(2, 4)}${q}` : s;
};

/** 20260904 → 09-04（周线专用，避免 X 轴全显示成 26Q3） */
const fmtWeek = (p) => {
  const s = String(p || "");
  return s.length === 8 ? `${s.slice(4, 6)}-${s.slice(6, 8)}` : s;
};

/* ---------------- 标签 1：财务指标 ---------------- */
function tabIndicators(data, echarts) {
  const t = data.table || {};
  const rows = t.rows || [];
  const pers = t.periods || [];
  if (!rows.length) return `<div class="muted">无财务数据</div>`;

  // 顶部柱状图：每股收益
  const eps = rows.find((r) => r.key === "eps");
  let chart = "";
  if (eps) {
    chart = `<div class="fin-chart" id="finChartEps"></div>`;
  }

  const head = `<tr><th class="fin-th-lbl">科目 \\ 日期</th>${pers
    .map((p) => `<th>${fmtQuarter(p)}</th>`)
    .join("")}</tr>`;

  // 每行数值按其“配色语义”着色：同比=红/绿、风险阈值=橙、其余=中性白（见 IND_META / 顶部图例）
  const body = rows
    .map((r) => {
      const meta = IND_META[r.key] || {};
      const tds = (r.values || [])
        .map((v) => {
          // 同比类 → 箭头 + 红/绿/白（chg）；其余 → 阈值橙 / 中性白（indClass）
          if (meta.color === COLOR_SIGN) {
            const c = chg(v, { pct: false, digits: 2 });
            return `<td class="${c.cls}">${c.html}</td>`;
          }
          return `<td class="${finCls(r.key, v)}">${num(v, 2)}</td>`;
        })
        .join("");
      const tip = meta.desc ? ` title="${esc(meta.desc)}"` : "";
      return `<tr><td class="fin-th-lbl"${tip}>${esc(r.label)}</td>${tds}</tr>`;
    })
    .join("");

  // 指标说明：逐项口径 + 该行配色含义（默认折叠，点开可见）
  const colorTag = {
    [COLOR_SIGN]: '<span class="up">红/绿（按正负）</span>',
    [COLOR_WARN]: '<span class="warn">橙（阈值警示）</span>',
    [COLOR_PLAIN]: "中性（白）",
  };
  const dictBody = rows
    .map((r) => {
      const meta = IND_META[r.key] || {};
      return `<tr><td class="fin-th-lbl" style="text-align:left">${esc(r.label)}</td>`
        + `<td style="text-align:left">${colorTag[meta.color] || colorTag[COLOR_PLAIN]}</td>`
        + `<td style="text-align:left;white-space:normal">${esc(meta.desc || "")}</td></tr>`;
    })
    .join("");
  const dict = `<details class="fin-dict">
      <summary>指标说明与配色（共 ${rows.length} 项，点击展开）</summary>
      <div class="fin-table-wrap" style="max-height:none;margin-top:8px">
        <table class="fin-table"><thead><tr>
          <th class="fin-th-lbl">指标</th><th>配色</th><th style="text-align:left">口径说明</th>
        </tr></thead><tbody>${dictBody}</tbody></table>
      </div></details>`;

  setTimeout(() => {
    if (!echarts || !eps) return;
    const el = document.getElementById("finChartEps");
    if (!el) return;
    const ch = trackChart(echarts.init(el));
    ch.setOption({
      grid: { left: 48, right: 16, top: 28, bottom: 28 },
      title: { text: "每股收益（元）", textStyle: { fontSize: 12, color: "#8aa" } },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: pers.map(fmtQuarter), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", axisLabel: { fontSize: 10 } },
      series: [
        {
          type: "bar",
          data: (eps.values || []).map((v) => (v == null ? 0 : v)),
          itemStyle: { color: "#e8a33d" },
          barMaxWidth: 26,
        },
      ],
    });
  }, 30);

  return `${chart}<div class="fin-table-wrap"><table class="fin-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>${dict}`;
}

/* ---------------- 标签 2：财务诊断 ---------------- */
function tabDiagnose(data, echarts) {
  const d = data.diag || {};
  if (d.error) return `<div class="muted">${esc(d.error)}</div>`;
  const dims = d.dims || {};
  const detail = d.detail || {};
  const nameMap = {
    profit: "盈利能力",
    growth: "成长能力",
    solvency: "偿债能力",
    cash: "现金流",
    oper: "运营效率",
  };
  setTimeout(() => {
    if (!echarts) return;
    const g1 = document.getElementById("finScoreRing");
    if (g1) {
      const c1 = trackChart(echarts.init(g1));
      c1.setOption({
        series: [
          {
            type: "gauge",
            startAngle: 90,
            endAngle: -270,
            radius: "78%",
            pointer: { show: false },
            progress: { show: true, roundCap: true, width: 12, itemStyle: { color: "#e8a33d" } },
            axisLine: { lineStyle: { width: 12, color: [[1, "#2a3140"]] } },
            detail: {
              valueAnimation: true,
              formatter: (v) => `{v|${v}}\n{s|综合评分}`,
              rich: {
                v: { fontSize: 26, color: "#e8a33d", fontWeight: "bold" },
                s: { fontSize: 11, color: "#8aa", padding: [4, 0, 0, 0] },
              },
              offsetCenter: [0, 0],
            },
            data: [{ value: d.score == null ? 0 : d.score }],
          },
        ],
      });
    }
    const g2 = document.getElementById("finRadar");
    if (g2) {
      const c2 = trackChart(echarts.init(g2));
      const keys = ["profit", "growth", "solvency", "cash", "oper"];
      c2.setOption({
        tooltip: {},
        radar: {
          indicator: keys.map((k) => ({ name: nameMap[k], max: 100 })),
          radius: "62%",
          axisName: { fontSize: 11, color: "#9ab" },
          splitLine: { lineStyle: { color: "#2a3140" } },
          axisLine: { lineStyle: { color: "#2a3140" } },
        },
        series: [
          {
            type: "radar",
            data: [{ value: keys.map((k) => dims[k] || 0), name: "财务维度" }],
            areaStyle: { color: "rgba(232,163,61,.28)" },
            lineStyle: { color: "#e8a33d" },
            itemStyle: { color: "#e8a33d" },
          },
        ],
      });
    }
  }, 30);

  // 五维评分卡片（≥80 良好 / <60 偏弱）
  const dimCards = Object.keys(nameMap).map((k) => {
    const v = dims[k];
    const color = v == null ? "" : (v >= TH.DIM_GOOD ? "up" : (v < TH.DIM_WEAK ? "warn" : ""));
    return kpiCard(nameMap[k], v == null ? null : String(v), color, "/100");
  });

  // 关键指标卡片：配色与「财务指标」表一致（同比=红/绿、风险阈值=橙、其余中性白）
  const detailCards = [
    ["ROE(TTM)", detail.roe_ttm, "%", "roe", ""],
    ["ROE(报告期)", detail.roe_period, "%", "roe", "累计口径"],
    ["销售毛利率", detail.gp_margin, "%", "gp_margin", ""],
    ["销售净利率", detail.np_margin, "%", "np_margin", ""],
    ["营收同比", detail.rev_yoy, "%", "rev_yoy", ""],
    ["净利同比", detail.np_yoy, "%", "np_yoy", ""],
    ["资产负债率", detail.debt_ratio, "%", "debt_ratio", `> ${TH.DEBT_HIGH}% 偏高`],
    ["流动比率", detail.current_ratio, "", "current_ratio", `< ${TH.CURRENT_LOW} 偿债压力`],
    ["经营现金流/净利", detail.ocf_to_np, "%", "ocf_to_np", `< ${TH.OCF_NP_LOW}% 含金量偏低`],
    ["总资产周转率", detail.asset_turnover, "次", "asset_turnover", ""],
  ].map(([label, v, unit, key, hint]) => {
    // 同比类 → 箭头 + 红/绿/白；其余 → 阈值橙 / 中性白
    if ((IND_META[key] || {}).color === COLOR_SIGN) {
      return chgCard(label, v, { pct: true, digits: 2, hint });
    }
    return kpiCard(label, v == null || v === "" ? null : `${num(v, 2)}${unit}`, finCls(key, v), hint);
  });

  return `
    <div class="fin-diag">
      <div class="fin-diag-charts">
        <div class="fin-gauge" id="finScoreRing"></div>
        <div class="fin-gauge" id="finRadar"></div>
      </div>
      <div class="fin-diag-detail">
        ${kpiSection("五维评分", dimCards)}
        ${kpiSection(`关键指标（${d.period || ""}）`, detailCards)}
      </div>
    </div>`;
}

/* ---------------- 标签 3：成长趋势 ---------------- */
function tabTrend(data, echarts) {
  const c = data.card || {};
  const tr = c.trend || {};
  const pers = tr.periods || [];
  if (!pers.length) return `<div class="muted">无趋势数据</div>`;
  setTimeout(() => {
    if (!echarts) return;
    const el = document.getElementById("finTrendChart");
    if (!el) return;
    const ch = trackChart(echarts.init(el));
    ch.setOption({
      grid: { left: 56, right: 56, top: 40, bottom: 40 },
      legend: {
        data: ["营业总收入 TTM(亿)", "归母净利润 TTM(亿)", "ROE(TTM)%", "ROE(报告期累计)%"],
        textStyle: { fontSize: 11 },
      },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: pers.map(fmtQuarter), axisLabel: { fontSize: 10 } },
      yAxis: [
        { type: "value", name: "亿元", axisLabel: { fontSize: 10 } },
        { type: "value", name: "%", axisLabel: { fontSize: 10 } },
      ],
      series: [
        {
          name: "营业总收入 TTM(亿)",
          type: "bar",
          data: tr.rev_ttm_yi || [],
          itemStyle: { color: "#4a9eff" },
          barMaxWidth: 22,
        },
        {
          name: "归母净利润 TTM(亿)",
          type: "bar",
          data: tr.np_ttm_yi || [],
          itemStyle: { color: "#e8a33d" },
          barMaxWidth: 22,
        },
        {
          // 绿线：TTM 口径，与柱状图同口径，可直接对比
          name: "ROE(TTM)%",
          type: "line",
          yAxisIndex: 1,
          smooth: true,
          data: tr.roe_ttm || [],
          lineStyle: { color: "#38d39f", width: 2 },
          itemStyle: { color: "#38d39f" },
        },
        {
          // 灰虚线：通达信原始"报告期累计"ROE，每年前低后高的锯齿即由此而来
          name: "ROE(报告期累计)%",
          type: "line",
          yAxisIndex: 1,
          smooth: false,
          data: tr.roe || [],
          lineStyle: { color: "#8aa", width: 1.5, type: "dashed" },
          itemStyle: { color: "#8aa" },
        },
      ],
    });
  }, 30);
  // 最新期 KPI + 同比（TTM 口径：本期 vs 去年同季 last-4）
  const li = pers.length - 1;
  const yoy = (arr) => {
    if (!Array.isArray(arr) || pers.length < 5) return null;
    const a = arr[li], b = arr[li - 4];
    if (a == null || b == null || b === 0) return null;
    return ((a - b) / Math.abs(b)) * 100;
  };
  const yi = (v) => (v == null ? null : `${num(v, 2)} 亿`);
  const pctv = (v) => (v == null ? null : `${num(v, 2)}%`);
  const trendCards = [
    kpiCard("营业总收入 TTM", yi(lastOf(tr.rev_ttm_yi)), "", "近 12 个月滚动"),
    kpiCard("归母净利润 TTM", yi(lastOf(tr.np_ttm_yi)), "", "近 12 个月滚动"),
    chgCard("营收 TTM 同比", yoy(tr.rev_ttm_yi), { pct: true, digits: 1, hint: "较去年同期" }),
    chgCard("净利 TTM 同比", yoy(tr.np_ttm_yi), { pct: true, digits: 1, hint: "较去年同期" }),
    kpiCard("ROE(TTM)", pctv(lastOf(tr.roe_ttm)), "", "TTM 口径（可比）"),
    kpiCard("ROE(报告期累计)", pctv(lastOf(tr.roe)), "", "累计口径（锯齿）"),
  ];

  return `${kpiSection(`最新趋势（${fmtQuarter(lastOf(pers))}）`, trendCards)}
    <div class="fin-chart tall" id="finTrendChart"></div>
    <div class="muted small" style="margin:-4px 0 8px">
      口径说明：柱状图为 <b>TTM（近 12 个月滚动）</b>；绿线 <b>ROE(TTM)</b> 同为 TTM 口径（可比、平滑）。
      灰虚线为通达信原始 <b>报告期累计 ROE</b> —— 该值是"年初至今"累计：Q1≈全年 1/4、Q2≈1/2、Q3≈3/4、Q4=全年，
      年报后归零重来，所以每年前低后高的"锯齿"是<b>累计口径</b>的必然结果，<b>与经营波动无关</b>，
      不宜与 TTM 柱状图直接对比。
    </div>`;
}

/* ---------------- 标签 4：估值分析（卡片式） ---------------- */
function tabValuation(data) {
  const c = data.card || {};
  const v = c.valuation || {};
  const lat = c.latest || {};

  const mktCap = (v.price && lat.total_share)
    ? ((v.price * lat.total_share) / 1e8).toFixed(1) : null;

  const valuation = [
    kpiCard("PE(TTM)", num(v.pe_ttm)),
    kpiCard("PB(市净率)", num(v.pb)),
    kpiCard("PS(市销率)", num(v.ps_ttm)),
  ];
  const perShare = [
    kpiCard("每股收益 TTM", num(v.eps_ttm), "", "元"),
    kpiCard("每股净资产", num(lat.bvps), "", "元"),
    kpiCard("每股营收", num(v.rev_per_share), "", "元"),
  ];
  const scale = [
    kpiCard("总市值", mktCap, "", "亿元"),
    kpiCard("总资产", num(lat.total_assets_yi), "", "亿元"),
    kpiCard("净资产", num(lat.total_equity_yi), "", "亿元"),
    kpiCard("总股本", lat.total_share ? (lat.total_share / 1e8).toFixed(2) : null, "", "亿股"),
    kpiCard("股东户数", num(lat.holders, 0), "", "户"),
    kpiCard("报告期", lat.period || null),
  ];
  const growth = [
    ["营收同比", lat.rev_yoy],
    ["净利同比", lat.np_yoy],
    ["扣非净利同比", lat.np_deduct_yoy],
  ].map(([k, val]) => chgCard(k, val, { pct: true, digits: 2, hint: "较去年同期" }));

  return `<div class="fin-val">
      ${kpiSection("估值指标", valuation)}
      ${kpiSection("每股指标", perShare)}
      ${kpiSection("规模 / 股东", scale)}
      ${kpiSection("成长性", growth)}
    </div>`;
}

/* ---------------- 标签 5：杜邦分析 ---------------- */
function tabDupont(data, echarts) {
  const d = data.dupont || {};
  if (d.error) return `<div class="muted">${esc(d.error)}</div>`;
  const pers = d.periods || [];
  if (!pers.length) return `<div class="muted">无杜邦分析数据</div>`;

  setTimeout(() => {
    if (!echarts) return;
    const el = document.getElementById("finDupontChart");
    if (!el) return;
    const ch = trackChart(echarts.init(el));
    ch.setOption({
      grid: { left: 52, right: 20, top: 40, bottom: 36 },
      legend: { data: ["ROE(面板)", "ROE(杜邦计算)"], textStyle: { fontSize: 11 } },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: pers.map(fmtQuarter), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", name: "%", axisLabel: { fontSize: 10 } },
      series: [
        {
          name: "ROE(面板)",
          type: "bar",
          data: d.roe || [],
          itemStyle: { color: "#4a9eff" },
          barMaxWidth: 24,
        },
        {
          name: "ROE(杜邦计算)",
          type: "line",
          smooth: true,
          data: d.roe_calc || [],
          lineStyle: { color: "#e8a33d", width: 2 },
          itemStyle: { color: "#e8a33d" },
        },
      ],
    });
  }, 30);

  const rows = [
    ["销售净利率 %", d.npm],
    ["总资产周转率(次)", d.turnover],
    ["权益乘数(倍)", d.equity_mult],
    ["ROE 面板 %", d.roe],
    ["ROE 杜邦校验 %", d.roe_calc],
  ]
    .map(([k, arr]) => {
      const tds = (arr || []).map((v) => `<td class="${valCls(v)}">${num(v, 3)}</td>`).join("");
      return `<tr><td class="fin-th-lbl">${k}</td>${tds}</tr>`;
    })
    .join("");

  const head = `<tr><th class="fin-th-lbl">科目 \\ 日期</th>${pers
    .map((p) => `<th>${fmtQuarter(p)}</th>`)
    .join("")}</tr>`;

  const drvCards = [
    ["销售净利率", d.npm, "%", "", ""],
    ["总资产周转率", d.turnover, "次", "", ""],
    ["权益乘数", d.equity_mult, "倍", "", ""],
    ["ROE(面板)", d.roe, "%", "", ""],
    ["ROE(杜邦校验)", d.roe_calc, "%", "", ""],
  ].map(valCard);

  return `
    <div class="fin-vp-banner">驱动类型：<b>${esc(d.driver || "")}</b> —— ${esc(d.driver_desc || "")}
      <span class="muted small">（恒等式：ROE = 销售净利率 × 总资产周转率 × 权益乘数）</span></div>
    ${kpiSection(`杜邦三因子（${fmtQuarter(lastOf(pers))}）`, drvCards)}
    <div class="fin-chart" id="finDupontChart"></div>
    <div class="fin-table-wrap"><table class="fin-table"><thead>${head}</thead><tbody>${rows}</tbody></table></div>
    <div class="muted small" style="margin-top:6px">
      三种盈利模式：净利率高＝产品溢价 / 成本控制（白酒、医药）；周转率高＝运营效率（零售、快消）；
      权益乘数高＝财务杠杆（银行、地产）。因年化/平均口径差异，校验值与面板 ROE 通常相差 &lt;2%。
    </div>`;
}

/* ---------- 通用：多期科目表（不含图表） ---------- */
function periodTable(periods, rows, digits = 2) {
  const head = `<tr><th class="fin-th-lbl">科目 \\ 日期</th>${periods
    .map((p) => `<th>${fmtQuarter(p)}</th>`)
    .join("")}</tr>`;
  const body = rows
    .filter((r) => r.values && r.values.length)
    .map(
      (r) =>
        `<tr><td class="fin-th-lbl">${esc(r.label)}</td>${(r.values || [])
          .map((v) => `<td class="${valCls(v)}">${num(v, digits)}</td>`)
          .join("")}</tr>`
    )
    .join("");
  return `<div class="fin-table-wrap"><table class="fin-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}

/* ---------------- 标签 6：单季度 ---------------- */
function tabQuarterly(data, echarts) {
  const q = data.quarterly || {};
  if (q.error) return `<div class="muted">${esc(q.error)}</div>`;
  const pers = q.periods || [];
  if (!pers.length) return `<div class="muted">无单季度数据</div>`;

  const qrows = q.rows || [];
  const get = (k) => (qrows.find((r) => r.key === k) || {}).values || [];

  setTimeout(() => {
    if (!echarts) return;
    const el = document.getElementById("finQChart");
    if (!el) return;
    const ch = trackChart(echarts.init(el));
    ch.setOption({
      grid: { left: 52, right: 20, top: 40, bottom: 36 },
      legend: { data: ["营业总收入(亿)", "归母净利润(亿)"], textStyle: { fontSize: 11 } },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: pers.map(fmtQuarter), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", name: "亿元", axisLabel: { fontSize: 10 } },
      series: [
        { name: "营业总收入(亿)", type: "bar", data: get("rev_q"),
          itemStyle: { color: "#4a9eff" }, barMaxWidth: 22 },
        { name: "归母净利润(亿)", type: "bar", data: get("np_q"),
          itemStyle: { color: "#e8a33d" }, barMaxWidth: 22 },
      ],
    });
  }, 30);

  // 最新单季 KPI + 环比（环比用箭头 + 红/绿/白）
  const qi = pers.length - 1;
  const qoq = (arr) => {
    if (!Array.isArray(arr) || arr.length < 2) return null;
    const a = arr[qi], b = arr[qi - 1];
    if (a == null || b == null || b === 0) return null;
    return ((a - b) / Math.abs(b)) * 100;
  };
  const revQ = get("rev_q"), npQ = get("np_q");
  const yi = (v) => (v == null ? null : `${num(v, 2)} 亿`);
  const qCards = [
    kpiCard("营业总收入", yi(lastOf(revQ)), "", "单季"),
    chgCard("营收环比", qoq(revQ), { pct: true, digits: 1, hint: "较上季" }),
    kpiCard("归母净利润", yi(lastOf(npQ)), "", "单季"),
    chgCard("净利环比", qoq(npQ), { pct: true, digits: 1, hint: "较上季" }),
  ];

  return `${kpiSection(`最新单季（${fmtQuarter(lastOf(pers))}）`, qCards)}
    <div class="muted small" style="margin-bottom:6px">${esc(q.note || "")}
      —— 单季数据可暴露被累计值平滑掉的<b>业绩拐点</b>（如中报增长但 Q2 实际下滑）。</div>
    <div class="fin-chart" id="finQChart"></div>
    ${periodTable(pers, qrows)}`;
}

/* ---------------- 标签 7：变动说明（环比，前端计算） ---------------- */
function tabChanges(data) {
  const t = data.table || {};
  const pers = t.periods || [];
  const rows = t.rows || [];
  if (pers.length < 2) return `<div class="muted">数据不足（需至少 2 期）</div>`;
  const i = pers.length - 1, j = pers.length - 2;
  const out = [];
  for (const r of rows) {
    const v = r.values || [];
    const a = v[i], b = v[j];
    if (a == null || b == null || b === 0) continue;
    out.push({ label: r.label, prev: b, cur: a, chg: ((a - b) / Math.abs(b)) * 100 });
  }
  out.sort((x, y) => Math.abs(y.chg) - Math.abs(x.chg));
  const cards = out.map((r) =>
    chgCard(r.label, r.chg, { pct: true, digits: 1, hint: `${num(r.prev, 2)} → ${num(r.cur, 2)}` }));

  return `<div class="muted small" style="margin-bottom:8px">
      ${esc(fmtPeriod(pers[j]))} → ${esc(fmtPeriod(pers[i]))} 各指标<b>环比</b>变动，
      按变动幅度降序（仅显示两期均有值且上期非零的科目）。</div>
    ${cards.length ? kpiGrid(cards) : '<div class="muted">无可比科目</div>'}`;
}

/* ---------------- 标签 8：现金流 ---------------- */
function tabCashflow(data, echarts) {
  const c = data.cashflow || {};
  if (c.error) return `<div class="muted">${esc(c.error)}</div>`;
  const pers = c.periods || [];
  if (!pers.length) return `<div class="muted">无现金流数据</div>`;

  setTimeout(() => {
    if (!echarts) return;
    const el = document.getElementById("finCfChart");
    if (!el) return;
    const ch = trackChart(echarts.init(el));
    const rows = c.rows || [];
    const get = (k) => (rows.find((r) => r.key === k) || {}).values || [];
    ch.setOption({
      grid: { left: 52, right: 20, top: 40, bottom: 36 },
      legend: { data: ["经营现金流(亿)", "资本开支(亿)", "自由现金流 FCF(亿)"],
        textStyle: { fontSize: 11 } },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: pers.map(fmtQuarter), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", name: "亿元", axisLabel: { fontSize: 10 } },
      series: [
        { name: "经营现金流(亿)", type: "bar", data: get("ocf_q"),
          itemStyle: { color: "#38d39f" }, barMaxWidth: 18 },
        { name: "资本开支(亿)", type: "bar", data: get("capex_q"),
          itemStyle: { color: "#ff6b6b" }, barMaxWidth: 18 },
        { name: "自由现金流 FCF(亿)", type: "line", smooth: true, data: get("fcf_q"),
          lineStyle: { color: "#e8a33d", width: 2 }, itemStyle: { color: "#e8a33d" } },
      ],
    });
  }, 30);

  const q0 = c.quality || {};
  const qualCards = [
    ["经营现金流/净利润", q0.ocf_to_np, "%",
      indClass("ocf_to_np", q0.ocf_to_np), `< ${TH.OCF_NP_LOW}% 含金量偏低`],
    ["销售现金比率", q0.cash_recovery, "%", "", ""],
    ["销售商品收现/营收", q0.sales_cash_to_rev, "%", "", ""],
    ["每股现金流", q0.cf_per_share, "元", "", ""],
    ["经营现金流 TTM", q0.ocf_ttm_yi, "亿", "", ""],
  ].map(valCard);

  return `<div class="muted small" style="margin-bottom:6px">${esc(c.note || "")}</div>
    <div class="fin-chart" id="finCfChart"></div>
    ${kpiSection(`现金流质量（${c.latest_period || ""}）`, qualCards)}
    ${periodTable(pers, c.rows || [])}`;
}

/* ---------------- 标签 9：资产负债 ---------------- */
function tabBalance(data, echarts) {
  const b = data.balance || {};
  if (b.error) return `<div class="muted">${esc(b.error)}</div>`;
  const pers = b.periods || [];
  if (!pers.length) return `<div class="muted">无资产负债数据</div>`;

  setTimeout(() => {
    if (!echarts) return;
    const la = b.latest || {};
    const g1 = document.getElementById("finAssetPie");
    if (g1 && la.total_assets_yi) {
      const c1 = trackChart(echarts.init(g1));
      c1.setOption({
        tooltip: { trigger: "item" },
        title: { text: "资产结构", textStyle: { fontSize: 12, color: "#8aa" } },
        series: [{
          type: "pie", radius: "62%",
          data: [
            { name: "流动资产", value: la.current_assets_yi || 0 },
            { name: "非流动资产", value: la.noncurrent_assets_yi || 0 },
          ],
          label: { fontSize: 10, formatter: "{b}\n{d}%" },
          itemStyle: { borderColor: "#161b22", borderWidth: 2 },
        }],
      });
    }
    const g2 = document.getElementById("finLiabPie");
    if (g2 && la.total_liab_yi) {
      const c2 = trackChart(echarts.init(g2));
      c2.setOption({
        tooltip: { trigger: "item" },
        title: { text: "负债结构", textStyle: { fontSize: 12, color: "#8aa" } },
        series: [{
          type: "pie", radius: "62%",
          data: [
            { name: "流动负债", value: la.current_liab_yi || 0 },
            { name: "非流动负债", value: la.noncurrent_liab_yi || 0 },
          ],
          label: { fontSize: 10, formatter: "{b}\n{d}%" },
          itemStyle: { borderColor: "#161b22", borderWidth: 2 },
        }],
      });
    }
  }, 30);

  const r0 = b.ratios || {};
  const ratioCards = [
    ["流动资产占比", r0.current_assets_pct, "%", "", ""],
    ["流动负债占比", r0.current_liab_pct, "%", "", ""],
    ["资产负债率", r0.debt_ratio, "%",
      r0.debt_ratio != null && r0.debt_ratio > TH.DEBT_HIGH ? "warn" : "", `> ${TH.DEBT_HIGH}% 偏高`],
    ["流动比率", r0.current_ratio, "",
      r0.current_ratio != null && r0.current_ratio < TH.CURRENT_LOW ? "warn" : "", `> ${TH.CURRENT_LOW} 较安全`],
    ["速动比率", r0.quick_ratio, "", "", "剔除存货后的短期偿债能力"],
  ].map(valCard);

  // ---- 同期对比（最新期 vs 上年同季）：看负债变化与偿债恢复能力 ----
  const rs = b.ratio_series || {};
  const rowVals = (k) => ((b.rows || []).find((r) => r.key === k) || {}).values || [];
  // 精确定位"上年同季"：报告期 − 10000（如 20260630 → 20250630）
  const prevIdx = (() => {
    const p = String(b.latest_period || "");
    if (p.length !== 8) return -1;
    const target = String(Number(p) - 10000);              // 上年同季（如 20260630 → 20250630）
    return (b.periods || []).findIndex((x) => String(x) === target);
  })();
  const prevLabel = prevIdx >= 0 ? fmtQuarter(b.periods[prevIdx]) : "上年同季";
  const at = (arr, i) => (Array.isArray(arr) && i >= 0 && arr[i] != null ? arr[i] : null);
  const yoyPct = (arr) => {                    // 相对变化（%）
    const a = lastOf(arr), p = at(arr, prevIdx);
    if (a == null || p == null || p === 0) return null;
    return ((a - p) / Math.abs(p)) * 100;
  };
  const deltaNum = (arr) => {                  // 绝对变化（个百分点 / 倍数）
    const a = lastOf(arr), p = at(arr, prevIdx);
    if (a == null || p == null) return null;
    return a - p;
  };
  // 各期比率：优先用后端 ratio_series；缺失时由多期科目现场推算（兼容未重启的旧后端）
  const ratioFromRows = (nKey, dKey, scale) => {
    const nArr = rowVals(nKey), dArr = rowVals(dKey);
    if (!nArr.length || !dArr.length) return [];
    return nArr.map((v, i) => {
      const d = dArr[i];
      if (v == null || d == null || d === 0) return null;
      return (v / d) * scale;
    });
  };
  const pickSeries = (key, nKey, dKey, scale) =>
    (Array.isArray(rs[key]) && rs[key].length) ? rs[key] : ratioFromRows(nKey, dKey, scale);
  const S = {
    debt_ratio: pickSeries("debt_ratio", "tl", "ta", 100),
    current_ratio: pickSeries("current_ratio", "ca", "cl", 1),
    current_assets_pct: pickSeries("current_assets_pct", "ca", "ta", 100),
    current_liab_pct: pickSeries("current_liab_pct", "cl", "tl", 100),
    quick_ratio: Array.isArray(rs.quick_ratio) ? rs.quick_ratio : [],   // 需存货字段，无法由科目推算
  };
  const yoyHint = `较 ${prevLabel}`;
  const yoyCards = [
    chgCard("总资产同比", yoyPct(rowVals("ta")), { pct: true, digits: 1, hint: yoyHint }),
    chgCard("总负债同比", yoyPct(rowVals("tl")), { pct: true, digits: 1, hint: `${yoyHint}（降 = 去杠杆）` }),
    chgCard("净资产同比", yoyPct(rowVals("te")), { pct: true, digits: 1, hint: yoyHint }),
    chgCard("资产负债率变化", deltaNum(S.debt_ratio), { pct: false, digits: 2, hint: `${yoyHint}（百分点）` }),
    chgCard("流动比率变化", deltaNum(S.current_ratio), { pct: false, digits: 2, hint: yoyHint }),
    chgCard("速动比率变化", deltaNum(S.quick_ratio), { pct: false, digits: 2, hint: yoyHint }),
  ];

  // 出现 "--" 时在解释行补一句通用说明（区分"没数据"与"服务未重启"）
  const naKeys = [
    ["总资产同比", yoyPct(rowVals("ta"))],
    ["总负债同比", yoyPct(rowVals("tl"))],
    ["净资产同比", yoyPct(rowVals("te"))],
    ["资产负债率变化", deltaNum(S.debt_ratio)],
    ["流动比率变化", deltaNum(S.current_ratio)],
    ["速动比率变化", deltaNum(S.quick_ratio)],
  ].filter(([, v]) => v == null).map(([k]) => k);
  const naNote = naKeys.length
    ? `<br><span style="color:#e8a33d">说明：<b>--</b> 表示该项缺少"上年同季"可比数据 —— 常见原因是`
      + `本地面板没有上年同季这一期、缺少对应字段（如速动比率需存货），`
      + `或服务未重启导致 ratio_series 尚未生效。受影响：${esc(naKeys.join("、"))}。</span>`
    : "";

  return `<div class="fin-diag-charts" style="margin-bottom:10px">
      <div class="fin-gauge" id="finAssetPie"></div>
      <div class="fin-gauge" id="finLiabPie"></div>
    </div>
   ${kpiSection(`结构与偿债（${b.latest_period || ""}）`, ratioCards)}
   ${kpiSection(`同期对比（${b.latest_period || ""} vs ${prevLabel}）`, yoyCards)}
   <div class="muted small" style="margin:-2px 0 8px">
     同期对比 = 最新报告期与<b>上年同季</b>（同期）比较：总负债同比<b>降</b>说明在去杠杆，
     流动/速动比率同比<b>升</b>说明短期偿债能力在恢复；资产负债率变化为<b>百分点</b>。${naNote}
   </div>
   ${periodTable(pers, b.rows || [])}`;
}

/* ---------------- 标签 10：本地量价指标（永不失败，替代东财资金流） ---------------- */
function tabVolume(data, echarts) {
  const v = data.volume || {};
  if (v.error) return `<div class="muted">${esc(v.error)}</div>`;
  const pers = v.periods || [];
  if (!pers.length) return `<div class="muted">无量价数据</div>`;

  setTimeout(() => {
    if (!echarts) return;
    const el = document.getElementById("finVolChart");
    if (!el) return;
    const ch = trackChart(echarts.init(el));
    ch.setOption({
      grid: [
        { left: 52, right: 56, top: 40, height: "52%" },
        { left: 52, right: 56, top: "66%", height: "22%" },
      ],
      legend: { data: ["收盘价", "成交量(亿股)"], textStyle: { fontSize: 11 } },
      tooltip: { trigger: "axis" },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      xAxis: [
        { type: "category", data: pers.map(fmtWeek), gridIndex: 0,
          axisLabel: { show: false }, axisLine: { lineStyle: { color: "#3a4250" } } },
        { type: "category", data: pers.map(fmtWeek), gridIndex: 1,
          axisLabel: { fontSize: 10, rotate: 38, color: "#9ab" },
          axisLine: { lineStyle: { color: "#3a4250" } } },
      ],
      yAxis: [
        { type: "value", name: "价(元)", scale: true, gridIndex: 0,
          nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10 },
          splitLine: { lineStyle: { color: "#222a36" } } },
        { type: "value", name: "亿股", gridIndex: 1,
          nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10 },
          splitLine: { show: false } },
      ],
      series: [
        { name: "收盘价", type: "line", smooth: true, showSymbol: true, symbolSize: 5,
          xAxisIndex: 0, yAxisIndex: 0, data: v.close || [],
          lineStyle: { color: "#e8a33d", width: 2.5 }, itemStyle: { color: "#e8a33d" }, z: 3 },
        { name: "成交量(亿股)", type: "bar", xAxisIndex: 1, yAxisIndex: 1,
          data: v.volume_yi || [], itemStyle: { color: "#4a9eff" }, barMaxWidth: 20 },
      ],
    });
  }, 30);

  const L = v.latest || {};
  const cards = [
    ["最新周", L.period, ""],
    ["收盘(元)", L.close, ""],
    ["周涨跌%", L.chg_pct, ""],
    ["放量倍数", L.vol_ratio, "≥1.5 放量 / ≤0.7 缩量"],
    ["量价形态", L.pattern, ""],
    ["成交额(亿)", L.amount_yi, ""],
    ["量能趋势%", L.vol_trend_pct, "正＝关注度提升"],
    ["量价背离", L.divergence ? "⚠ 是" : "否", "价涨但量萎缩>15%"],
  ];
  const CHG_KEYS = ["周涨跌%", "量能趋势%"];   // 变化类指标 → 箭头 + 红/绿/白
  const cardsHtml = cards.map(([k, val, tip]) => {
    const isNum = typeof val === "number";
    const useChg = isNum && CHG_KEYS.includes(k);
    const c = useChg ? chg(val, { pct: true, digits: 2 }) : null;
    const color = useChg ? c.cls : (k === "量价背离" && L.divergence ? "warn" : "");
    const inner = useChg
      ? c.html
      : esc(isNum ? val.toFixed(2) : (val == null || val === "" ? "--" : String(val)));
    return `
    <div class="fin-vp-card">
      <div class="lbl">${esc(k)}</div>
      <div class="val ${color}">${inner}</div>
      ${tip ? `<div class="hint">${esc(tip)}</div>` : ""}
    </div>`;
  }).join("");

  const rows = [
    { label: "收盘价", values: v.close },
    { label: "成交量(亿股)", values: v.volume_yi },
    { label: "成交额(亿)", values: v.amount_yi },
    { label: "周涨跌 %", values: v.chg_pct },
    { label: "放量倍数", values: v.vol_ratio },
  ]
    .map(
      (r) =>
        `<tr><td class="fin-th-lbl">${r.label}</td>${(r.values || [])
          .map((x) => `<td>${num(x, 2)}</td>`)
          .join("")}</tr>`
    )
    .join("");
  const patRow = `<tr><td class="fin-th-lbl">量价配合</td>${(v.pattern || [])
    .map((p) => `<td>${esc(p)}</td>`)
    .join("")}</tr>`;
  const head = `<tr><th class="fin-th-lbl">科目 \\ 日期</th>${pers
    .map((p) => `<th>${fmtWeek(p)}</th>`)
    .join("")}</tr>`;

  return `
    <div class="fin-vp-banner">最新判读：<b>${esc(v.tip || "")}</b></div>
    <div class="fin-vp-grid">${cardsHtml}</div>
    <div class="muted small" style="margin:2px 0 8px">${esc(v.note || "")}</div>
    <div class="fin-chart" id="finVolChart" style="height:270px"></div>
    <div class="fin-table-wrap"><table class="fin-table"><thead>${head}</thead>
      <tbody>${rows}${patRow}</tbody></table></div>`;
}

/** 首次渲染注入样式（避免改动全局 CSS 文件与 HTML 模板）。 */
const FIN_CSS = `
#pane-stock .fin-tabs{display:flex;gap:6px;flex-wrap:wrap}
#pane-stock .fin-tab{background:transparent;border:1px solid #2a3140;color:#9ab;padding:3px 10px;border-radius:4px;
  cursor:pointer;font-size:12px;line-height:1.6}
#pane-stock .fin-tab:hover{border-color:#e8a33d;color:#e8a33d}
#pane-stock .fin-tab.active{background:#e8a33d;border-color:#e8a33d;color:#111;font-weight:600}
.fin-body{padding:10px 12px;min-height:440px}
.fin-chart{width:100%;height:230px;margin-bottom:10px}
.fin-chart.tall{height:430px}
.fin-table-wrap{overflow:auto;max-height:540px;border:1px solid #232a36;border-radius:4px}
.fin-table{border-collapse:separate;border-spacing:0;width:100%;font-size:12px;white-space:nowrap}
.fin-table th,.fin-table td{border-bottom:1px solid #232a36;padding:5px 10px;text-align:right}
.fin-table th{background:#1b2129;position:sticky;top:0;color:#9ab;font-weight:500;z-index:3}
.fin-table td.fin-th-lbl,.fin-table th.fin-th-lbl{position:sticky;left:0;background:#161b22;
  text-align:left;color:#cbd;z-index:2;min-width:150px}
.fin-table th.fin-th-lbl{z-index:4}
.fin-table tbody tr:hover td{background:rgba(232,163,61,.06)}
.fin-diag{display:flex;gap:16px;flex-wrap:wrap}
.fin-diag-charts{display:flex;gap:8px;flex:1 1 420px;flex-wrap:wrap}
.fin-gauge{flex:1 1 220px;height:300px;min-width:200px}
.fin-diag-detail{flex:1 1 320px;display:flex;gap:16px;flex-wrap:wrap;align-content:flex-start}
.fin-diag-detail .mp-section{min-width:240px}
.fin-val{display:flex;gap:24px;flex-wrap:wrap}
.fin-val .mp-section{min-width:260px}
.fin-vp-banner{background:rgba(232,163,61,.12);border:1px solid #e8a33d;border-radius:6px;
  padding:8px 12px;margin-bottom:10px;font-size:13px;color:#e8c98a}
.fin-vp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;margin-bottom:6px}
.fin-vp-card{background:#161b22;border:1px solid #232a36;border-radius:6px;padding:8px 10px}
.fin-vp-card .lbl{font-size:11px;color:#9ab;margin-bottom:4px}
.fin-vp-card .val{font-size:17px;font-weight:600;color:#e6edf3;font-variant-numeric:tabular-nums}
.fin-vp-card .val.warn{color:#f85149}
.fin-vp-card .val.up{color:#f85149}
.fin-vp-card .val.down{color:#3fb950}
.fin-vp-card .hint{font-size:10px;color:#6b7888;margin-top:3px}
.fin-val-sec{min-width:210px}
.fin-val-sec .fin-vp-grid{grid-template-columns:repeat(auto-fill,minmax(108px,1fr));gap:8px}
.fin-vp-card:hover{border-color:rgba(232,163,61,.4);background:#1a212b}
.fin-vp-card{transition:background .15s,border-color .15s}
/* 数值配色（自包含，不依赖全局 .up/.down）：红=正向/增长、绿=负向/下降、橙=风险警示 */
.fin-table td.up{color:#f85149}
.fin-table td.down{color:#3fb950}
.fin-table td.flat{color:#e6edf3}
.fin-table td.warn{color:#e8a33d}
.fin-dict .warn{color:#e8a33d}
.fin-vp-card .val.flat{color:#e6edf3}
/* 变化箭头：放大 + 浅色底，醒目但不喧宾夺主 */
.arw{display:inline-block;font-size:1.35em;font-weight:800;line-height:1;padding:0 3px;
  margin-right:5px;border-radius:4px;vertical-align:-2px}
.fin-table td.up .arw,.fin-vp-card .val.up .arw{background:rgba(248,81,73,.18)}
.fin-table td.down .arw,.fin-vp-card .val.down .arw{background:rgba(63,185,80,.18)}
.fin-table td.flat .arw,.fin-vp-card .val.flat .arw{background:rgba(230,237,243,.16)}
/* 配色图例 */
.fin-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:11px;color:#8b949e;margin-bottom:8px}
.fin-legend .lg{display:inline-flex;align-items:center;gap:5px}
.fin-legend .lg i{display:inline-block;width:9px;height:9px;border-radius:2px;background:#8b949e}
.fin-legend .lg.sw-up i{background:#f85149}
.fin-legend .lg.sw-down i{background:#3fb950}
.fin-legend .lg.sw-flat i{background:#e6edf3}
.fin-legend .lg.sw-warn i{background:#e8a33d}
.fin-legend .lg.sw-plain i{background:#e6edf3}
/* 指标说明（可展开） */
.fin-dict{margin-top:12px;font-size:12px;color:#9ab}
.fin-dict summary{cursor:pointer;color:#e8a33d;font-size:12px;outline:none}
.fin-dict .fin-table td,.fin-dict .fin-table th{white-space:normal;vertical-align:top}
`;

function ensureStyle() {
  if (typeof document === "undefined") return;
  if (document.getElementById("finStyle")) return;
  const s = document.createElement("style");
  s.id = "finStyle";
  s.textContent = FIN_CSS;
  document.head.appendChild(s);
}

/* ---------- 图表实例管理 ----------
 * 目的（彻底消除隐患）：
 *   ① 全局只注册 1 个 resize 监听——此前每张图各注册一个且重渲染不清理，长会话会累积；
 *   ② 重新渲染前 dispose 旧实例，避免内存/画布泄漏；
 *   ③ 容器不可见（display:none）时跳过 resize，避免尺寸被算成 0×0（图表被压扁的元凶）。
 */
const _liveCharts = new Set();
let _resizeBound = false;

/** 登记图表实例，并惰性注册唯一的全局 resize 监听。 */
function trackChart(ch) {
  if (!ch) return ch;
  _liveCharts.add(ch);
  if (!_resizeBound && typeof window !== "undefined") {
    _resizeBound = true;
    window.addEventListener("resize", () => {
      _liveCharts.forEach((c) => {
        try {
          if (typeof c.isDisposed === "function" && c.isDisposed()) return;
          const el = typeof c.getDom === "function" ? c.getDom() : null;
          if (el && el.offsetParent === null) return;   // 容器不可见 → 跳过
          c.resize();
        } catch (_) { /* 单个实例 resize 失败不影响其它 */ }
      });
    });
  }
  return ch;
}

/** 释放全部已登记图表实例（重新渲染前 / 离开个股页时调用）。 */
export function disposeFinance() {
  _liveCharts.forEach((c) => {
    try {
      if (!(typeof c.isDisposed === "function" && c.isDisposed())) c.dispose();
    } catch (_) { /* ignore */ }
  });
  _liveCharts.clear();
}

/** 主渲染入口。 */
export function renderFinance(root, data, tab, echarts) {
  if (!root) return;
  ensureStyle();
  disposeFinance();   // 重建 DOM 前先释放上一批图表实例，防泄漏
  if (!data || data.error) {
    root.innerHTML = `<div class="muted">财务数据获取失败：${esc(
      (data && data.error) || "未知错误"
    )}</div>`;
    return;
  }
  const t = tab || "indicators";
  let html;
  if (t === "indicators") html = tabIndicators(data, echarts);
  else if (t === "diagnose") html = tabDiagnose(data, echarts);
  else if (t === "trend") html = tabTrend(data, echarts);
  else if (t === "dupont") html = tabDupont(data, echarts);
  else if (t === "quarterly") html = tabQuarterly(data, echarts);
  else if (t === "changes") html = tabChanges(data);
  else if (t === "cashflow") html = tabCashflow(data, echarts);
  else if (t === "balance") html = tabBalance(data, echarts);
  else if (t === "volume") html = tabVolume(data, echarts);
  else html = tabValuation(data);
  // 所有标签统一在顶部加配色图例，明确"数据颜色"的含义
  root.innerHTML = html ? finLegend() + html : html;
}

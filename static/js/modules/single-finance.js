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

const sgn = (v, digits = 2) =>
  v == null || v === "" ? "--" : (v >= 0 ? "+" : "") + Number(v).toFixed(digits);

const cls = (v) => (v == null ? "" : v >= 0 ? "up" : "down");

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

  const body = rows
    .map((r) => {
      const tds = (r.values || [])
        .map((v) => {
          if (r.kind === "pct") return `<td class="${cls(v)}">${num(v, 2)}</td>`;
          if (r.kind === "money") return `<td>${num(v, 2)}</td>`;
          return `<td>${num(v, 2)}</td>`;
        })
        .join("");
      return `<tr><td class="fin-th-lbl">${esc(r.label)}</td>${tds}</tr>`;
    })
    .join("");

  setTimeout(() => {
    if (!echarts || !eps) return;
    const el = document.getElementById("finChartEps");
    if (!el) return;
    const ch = echarts.init(el);
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
    window.addEventListener("resize", () => ch.resize());
  }, 30);

  return `${chart}<div class="fin-table-wrap"><table class="fin-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
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
      const c1 = echarts.init(g1);
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
      window.addEventListener("resize", () => c1.resize());
    }
    const g2 = document.getElementById("finRadar");
    if (g2) {
      const c2 = echarts.init(g2);
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
      window.addEventListener("resize", () => c2.resize());
    }
  }, 30);

  const detailRows = [
    ["ROE%(TTM)", detail.roe_ttm],
    ["ROE%(报告期)", detail.roe_period],
    ["销售毛利率%", detail.gp_margin],
    ["销售净利率%", detail.np_margin],
    ["营收同比增长%", detail.rev_yoy],
    ["净利同比增长%", detail.np_yoy],
    ["资产负债率%", detail.debt_ratio],
    ["流动比率", detail.current_ratio],
    ["经营现金流/净利%", detail.ocf_to_np],
    ["总资产周转率", detail.asset_turnover],
  ]
    .map(
      ([k, v]) =>
        `<div class="mp-row"><span class="lbl">${k}</span><span>${num(v, 2)}</span></div>`
    )
    .join("");

  const dimRows = Object.keys(nameMap)
    .map((k) => {
      const v = dims[k];
      return `<div class="mp-row"><span class="lbl">${nameMap[k]}</span><span>${
        v == null ? "--" : v
      }</span></div>`;
    })
    .join("");

  return `
    <div class="fin-diag">
      <div class="fin-diag-charts">
        <div class="fin-gauge" id="finScoreRing"></div>
        <div class="fin-gauge" id="finRadar"></div>
      </div>
      <div class="fin-diag-detail">
        <div class="mp-section"><div class="mp-h">五维评分</div>${dimRows}</div>
        <div class="mp-section"><div class="mp-h">关键指标（${esc(d.period || "")}）</div>${detailRows}</div>
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
    const ch = echarts.init(el);
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
    window.addEventListener("resize", () => ch.resize());
  }, 30);
  return `<div class="fin-chart tall" id="finTrendChart"></div>
    <div class="muted small" style="margin:-4px 0 8px">
      口径说明：柱状图为 <b>TTM（近 12 个月滚动）</b>；绿线 <b>ROE(TTM)</b> 同为 TTM 口径（可比、平滑）。
      灰虚线为通达信原始 <b>报告期累计 ROE</b> —— 该值是"年初至今"累计：Q1≈全年 1/4、Q2≈1/2、Q3≈3/4、Q4=全年，
      年报后归零重来，所以每年前低后高的"锯齿"是<b>累计口径</b>的必然结果，<b>与经营波动无关</b>，
      不宜与 TTM 柱状图直接对比。
    </div>`;
}

/* ---------------- 标签 4：估值分析 ---------------- */
function tabValuation(data) {
  const c = data.card || {};
  const v = c.valuation || {};
  const lat = c.latest || {};
  const items = [
    ["PE(TTM)", v.pe_ttm, ""],
    ["PB(市净率)", v.pb, ""],
    ["PS(市销率)", v.ps_ttm, ""],
    ["每股收益 TTM(元)", v.eps_ttm, ""],
    ["每股净资产(元)", lat.bvps, ""],
    ["每股营收(元)", v.rev_per_share, ""],
    ["总市值(亿)", (v.price && lat.total_share) ? ((v.price * lat.total_share) / 1e8).toFixed(1) : null, ""],
    ["总资产(亿)", lat.total_assets_yi, ""],
    ["净资产(亿)", lat.total_equity_yi, ""],
    ["总股本(亿股)", lat.total_share ? (lat.total_share / 1e8).toFixed(2) : null, ""],
    ["股东户数", lat.holders, ""],
    ["报告期", lat.period, ""],
  ];
  const rows = items
    .map(
      ([k, val]) =>
        `<div class="mp-row"><span class="lbl">${k}</span><span>${
          typeof val === "number" ? num(val, 2) : val || "--"
        }</span></div>`
    )
    .join("");
  const growthRows = [
    ["营收同比%", lat.rev_yoy],
    ["净利同比%", lat.np_yoy],
    ["扣非净利同比%", lat.np_deduct_yoy],
  ]
    .map(
      ([k, val]) =>
        `<div class="mp-row"><span class="lbl">${k}</span><span class="${cls(val)}">${sgn(
          val
        )}%</span></div>`
    )
    .join("");
  return `<div class="fin-val">
      <div class="mp-section"><div class="mp-h">估值指标</div>${rows}</div>
      <div class="mp-section"><div class="mp-h">成长性</div>${growthRows}</div>
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
    const ch = echarts.init(el);
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
    window.addEventListener("resize", () => ch.resize());
  }, 30);

  const rows = [
    ["销售净利率 %", d.npm],
    ["总资产周转率(次)", d.turnover],
    ["权益乘数(倍)", d.equity_mult],
    ["ROE 面板 %", d.roe],
    ["ROE 杜邦校验 %", d.roe_calc],
  ]
    .map(([k, arr]) => {
      const tds = (arr || []).map((v) => `<td>${num(v, 3)}</td>`).join("");
      return `<tr><td class="fin-th-lbl">${k}</td>${tds}</tr>`;
    })
    .join("");

  const head = `<tr><th class="fin-th-lbl">科目 \\ 日期</th>${pers
    .map((p) => `<th>${fmtQuarter(p)}</th>`)
    .join("")}</tr>`;

  return `
    <div class="mp-section" style="margin-bottom:10px">
      <div class="mp-h">驱动类型：<b style="color:#e8a33d">${esc(d.driver || "")}</b></div>
      <div class="mp-row"><span class="lbl">说明</span><span>${esc(d.driver_desc || "")}</span></div>
      <div class="mp-row"><span class="lbl">恒等式</span><span>ROE = 销售净利率 × 总资产周转率 × 权益乘数</span></div>
    </div>
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
          .map((v) => `<td>${num(v, digits)}</td>`)
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

  setTimeout(() => {
    if (!echarts) return;
    const el = document.getElementById("finQChart");
    if (!el) return;
    const ch = echarts.init(el);
    const rows = q.rows || [];
    const get = (k) => (rows.find((r) => r.key === k) || {}).values || [];
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
    window.addEventListener("resize", () => ch.resize());
  }, 30);

  return `<div class="muted small" style="margin-bottom:6px">${esc(q.note || "")}
      —— 单季数据可暴露被累计值平滑掉的<b>业绩拐点</b>（如中报增长但 Q2 实际下滑）。</div>
    <div class="fin-chart" id="finQChart"></div>
    ${periodTable(pers, q.rows || [])}`;
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
  const body = out
    .map(
      (r) =>
        `<tr><td class="fin-th-lbl">${esc(r.label)}</td><td>${num(r.prev, 2)}</td>` +
        `<td>${num(r.cur, 2)}</td><td class="${cls(r.chg)}">${sgn(r.chg, 1)}%</td></tr>`
    )
    .join("");
  return `<div class="muted small" style="margin-bottom:6px">
      ${esc(fmtPeriod(pers[j]))} → ${esc(fmtPeriod(pers[i]))} 各指标<b>环比</b>变动，
      按变动幅度降序（仅显示两期均有值且上期非零的科目）。</div>
    <div class="fin-table-wrap"><table class="fin-table"><thead>
      <tr><th class="fin-th-lbl">科目</th><th>上期</th><th>本期</th><th>环比</th></tr>
      </thead><tbody>${body}</tbody></table></div>`;
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
    const ch = echarts.init(el);
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
    window.addEventListener("resize", () => ch.resize());
  }, 30);

  const q0 = c.quality || {};
  const cards = [
    ["经营现金流/净利润%", q0.ocf_to_np, ">100 说明利润含金量高"],
    ["销售现金比率%", q0.cash_recovery, ""],
    ["销售商品收现/营收%", q0.sales_cash_to_rev, ""],
    ["每股现金流(元)", q0.cf_per_share, ""],
    ["经营现金流 TTM(亿)", q0.ocf_ttm_yi, ""],
  ]
    .map(
      ([k, v, tip]) =>
        `<div class="mp-row"><span class="lbl">${k}</span><span>${num(v, 2)}${
          tip ? ` <span class="muted small">${tip}</span>` : ""
        }</span></div>`
    )
    .join("");

  return `<div class="muted small" style="margin-bottom:6px">${esc(c.note || "")}</div>
    <div class="fin-chart" id="finCfChart"></div>
    <div class="mp-section"><div class="mp-h">现金流质量（${esc(c.latest_period || "")}）</div>${cards}</div>
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
      const c1 = echarts.init(g1);
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
      window.addEventListener("resize", () => c1.resize());
    }
    const g2 = document.getElementById("finLiabPie");
    if (g2 && la.total_liab_yi) {
      const c2 = echarts.init(g2);
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
      window.addEventListener("resize", () => c2.resize());
    }
  }, 30);

  const r0 = b.ratios || {};
  const cards = [
    ["流动资产占比%", r0.current_assets_pct],
    ["流动负债占比%", r0.current_liab_pct],
    ["资产负债率%", r0.debt_ratio],
    ["流动比率", r0.current_ratio],
    ["速动比率", r0.quick_ratio],
  ]
    .map(([k, v]) => `<div class="mp-row"><span class="lbl">${k}</span><span>${num(v, 2)}</span></div>`)
    .join("");

  return `<div class="fin-diag-charts" style="margin-bottom:10px">
      <div class="fin-gauge" id="finAssetPie"></div>
      <div class="fin-gauge" id="finLiabPie"></div>
    </div>
    <div class="mp-section"><div class="mp-h">结构与偿债（${esc(b.latest_period || "")}）</div>${cards}</div>
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
    const ch = echarts.init(el);
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
    window.addEventListener("resize", () => ch.resize());
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
  const cardsHtml = cards.map(([k, val, tip]) => {
    const isNum = typeof val === "number";
    const txt = isNum
      ? (k === "周涨跌%" && val > 0 ? "+" : "") + val.toFixed(2)
      : (val == null || val === "" ? "--" : String(val));
    return `
    <div class="fin-vp-card">
      <div class="lbl">${esc(k)}</div>
      <div class="val ${k === "量价背离" && L.divergence ? "warn" : ""}">${esc(txt)}</div>
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
.fin-vp-card .hint{font-size:10px;color:#6b7888;margin-top:3px}
`;

function ensureStyle() {
  if (typeof document === "undefined") return;
  if (document.getElementById("finStyle")) return;
  const s = document.createElement("style");
  s.id = "finStyle";
  s.textContent = FIN_CSS;
  document.head.appendChild(s);
}

/** 主渲染入口。 */
export function renderFinance(root, data, tab, echarts) {
  if (!root) return;
  ensureStyle();
  if (!data || data.error) {
    root.innerHTML = `<div class="muted">财务数据获取失败：${esc(
      (data && data.error) || "未知错误"
    )}</div>`;
    return;
  }
  const t = tab || "indicators";
  if (t === "indicators") root.innerHTML = tabIndicators(data, echarts);
  else if (t === "diagnose") root.innerHTML = tabDiagnose(data, echarts);
  else if (t === "trend") root.innerHTML = tabTrend(data, echarts);
  else if (t === "dupont") root.innerHTML = tabDupont(data, echarts);
  else if (t === "quarterly") root.innerHTML = tabQuarterly(data, echarts);
  else if (t === "changes") root.innerHTML = tabChanges(data);
  else if (t === "cashflow") root.innerHTML = tabCashflow(data, echarts);
  else if (t === "balance") root.innerHTML = tabBalance(data, echarts);
  else if (t === "volume") root.innerHTML = tabVolume(data, echarts);
  else root.innerHTML = tabValuation(data);
}

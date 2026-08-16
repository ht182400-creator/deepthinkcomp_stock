// 技术指标纯算法模块（无 ECharts / DOM 依赖，便于单元测试）
// 在 app.js 之前加载，挂到 window.DTIndicators。
// 算法口径与主流行情软件一致：MACD(12,26,9) / KDJ(9) / BOLL(20,2) / RSI(14)。
(function (global) {
  "use strict";

  // EMA: n 日指数移动平均（初值取 n 日 SMA）
  function ema(arr, n) {
    const k = 2 / (n + 1);
    const out = [];
    let prev = null;
    for (let i = 0; i < arr.length; i++) {
      if (i < n - 1) { out.push(null); continue; }
      if (prev === null) {
        let s = 0;
        for (let j = i - n + 1; j <= i; j++) s += arr[j];
        prev = s / n;
      } else {
        prev = arr[i] * k + prev * (1 - k);
      }
      out.push(+prev.toFixed(4));
    }
    return out;
  }

  // MACD：DIF=EMA12-EMA26, DEA=EMA9(DIF), MACD=(DIF-DEA)*2
  function macd(closes) {
    const ema12 = ema(closes, 12);
    const ema26 = ema(closes, 26);
    const dif = ema12.map((v, i) => v != null && ema26[i] != null ? +(v - ema26[i]).toFixed(4) : null);
    // DEA 对齐：取 DIF 首个有效值索引作为偏移，前面补 null 使等长
    const offset = dif.findIndex(v => v != null);
    const deaVals = ema(dif.filter(v => v != null), 9);
    const dea = (offset < 0 ? [] : new Array(offset).fill(null)).concat(deaVals);
    const macdBar = dif.map((v, i) => v != null && dea[i] != null ? +((v - dea[i]) * 2).toFixed(4) : null);
    return { dif, dea, macd: macdBar };
  }

  // KDJ：RSV=(C-L9)/(H9-L9)*100, K/D 为 RSV 的 SMA(1/3)，J=3K-2D
  function kdj(highs, lows, closes, n = 9) {
    const rsv = [], k = [], d = [], j = [];
    for (let i = 0; i < closes.length; i++) {
      if (i < n - 1) { rsv.push(null); k.push(null); d.push(null); j.push(null); continue; }
      const hh = Math.max(...highs.slice(i - n + 1, i + 1));
      const ll = Math.min(...lows.slice(i - n + 1, i + 1));
      const r = hh === ll ? 50 : +((closes[i] - ll) / (hh - ll) * 100).toFixed(2);
      rsv.push(r);
      const kk = k[i - 1] == null ? r : +(r * 1/3 + k[i - 1] * 2/3).toFixed(2);
      const dd = d[i - 1] == null ? r : +(kk * 1/3 + d[i - 1] * 2/3).toFixed(2);
      k.push(kk); d.push(dd); j.push(+(3 * kk - 2 * dd).toFixed(2));
    }
    return { k, d, j };
  }

  // BOLL：中轨 MA20，上轨=MA20+2σ，下轨=MA20-2σ
  function boll(closes, n = 20) {
    const mid = [], upper = [], lower = [];
    for (let i = 0; i < closes.length; i++) {
      if (i < n - 1) { mid.push(null); upper.push(null); lower.push(null); continue; }
      const slice = closes.slice(i - n + 1, i + 1);
      const m = slice.reduce((a, b) => a + b, 0) / n;
      const sigma = Math.sqrt(slice.reduce((s, x) => s + (x - m) ** 2, 0) / n);
      mid.push(+m.toFixed(2));
      upper.push(+(m + 2 * sigma).toFixed(2));
      lower.push(+(m - 2 * sigma).toFixed(2));
    }
    return { mid, upper, lower };
  }

  // RSI：N 日内涨幅均值 / (涨幅均值 + 跌幅均值) × 100
  function rsi(closes, n = 14) {
    const out = [];
    for (let i = 0; i < closes.length; i++) {
      if (i < n) { out.push(null); continue; }
      let gain = 0, loss = 0;
      for (let j = i - n + 1; j <= i; j++) {
        const diff = closes[j] - closes[j - 1];
        if (diff > 0) gain += diff; else loss -= diff;
      }
      const rs = loss === 0 ? Infinity : gain / loss;
      out.push(rs === Infinity ? 100 : +(100 - 100 / (1 + rs)).toFixed(2));
    }
    return out;
  }

  global.DTIndicators = { ema, macd, kdj, boll, rsi };
})(typeof window !== "undefined" ? window : globalThis);

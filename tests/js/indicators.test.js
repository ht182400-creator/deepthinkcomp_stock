// 技术指标算法单元测试（Node 内置 test runner）
// 运行：node --test tests/js/*.test.js   （或单文件 node --test tests/js/indicators.test.js）
// 目的：防止 D1 类"算法改坏但无测试"回归——MACD 的 DEA/柱必须真实渲染。
const test = require("node:test");
const assert = require("node:assert");

// indicators.js 通过 globalThis.DTIndicators 暴露（Node 下 window 未定义）
require("../../static/js/indicators.js");
const { ema, macd, kdj, boll, rsi } = globalThis.DTIndicators;

// 构造一段有起伏的收盘价，足够长以越过各指标预热期。
// MACD 预热：DIF 在第 26 根才有值(26+12-1)，EMA9 再需 9 根 → 至少 34 根才能算出 DEA。
// 这里取 60 根，确保 DEA/MACD 柱真实可计算（D1 回归的关键前提）。
const closes = [];
for (let i = 0; i < 60; i++) {
  closes.push(+(10 + 5 * Math.sin(i / 6) + 0.3 * (i % 4)).toFixed(2));
}

test("ema 长度与常数序列", () => {
  const out = ema(closes, 12);
  assert.strictEqual(out.length, closes.length);
  const flat = ema([5, 5, 5, 5, 5, 5, 5, 5, 5, 5], 3);
  // 常数序列 EMA 在预热期后恒等于该常数（前 n-1 个为 null）
  flat.forEach((v, i) => { if (i >= 2) assert.strictEqual(v, 5); });
});

test("macd: DEA 与 MACD 柱非全 null（D1 回归守护）", () => {
  const { dif, dea, macd: bar } = macd(closes);
  assert.strictEqual(dif.length, closes.length);
  assert.strictEqual(dea.length, closes.length);
  assert.strictEqual(bar.length, closes.length);
  // 关键：D1 曾因 slice(0,N) 取全是 null → DEA 整条不画。这里必须存在非 null 值。
  assert.ok(dea.some(v => v != null), "DEA 不应全为 null");
  assert.ok(bar.some(v => v != null), "MACD 柱不应全为 null");
  // DEA 首个非 null 索引须 >= DIF 首个非 null 索引（对齐正确）
  const difStart = dif.findIndex(v => v != null);
  const deaStart = dea.findIndex(v => v != null);
  assert.ok(deaStart >= difStart, "DEA 对齐不得早于 DIF");
});

test("kdj 长度与 J=3K-2D 关系", () => {
  const highs = closes.map((c, i) => c + (i % 2));
  const lows = closes.map((c, i) => c - (i % 3));
  const { k, d, j } = kdj(highs, lows, closes);
  assert.strictEqual(k.length, closes.length);
  const i = k.findIndex(v => v != null);
  assert.ok(i >= 0);
  assert.strictEqual(+j[i].toFixed(2), +(3 * k[i] - 2 * d[i]).toFixed(2));
});

test("boll 长度与上下轨对称", () => {
  const { mid, upper, lower } = boll(closes);
  assert.strictEqual(mid.length, closes.length);
  const i = mid.findIndex(v => v != null);
  assert.ok(i >= 0);
  assert.ok(upper[i] > mid[i] && mid[i] > lower[i]);
});

test("rsi 单调上涨序列为 100", () => {
  const up = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16];
  const out = rsi(up, 14);
  assert.strictEqual(out.length, up.length);
  const last = out[out.length - 1];
  assert.strictEqual(last, 100);
});

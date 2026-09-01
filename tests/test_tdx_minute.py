# -*- coding: utf-8 -*-
"""
通达信本地分钟线（.lc1）解析 + 聚合单元测试（US-修订：历史分钟 K 全量）。

沙盒无法访问 D:\new_tdx64\vipdoc，故用 struct 构造 .lc1 二进制 fixture，
验证解析与按交易日聚合 m5/m15/m30/m60 的条数 / OHLC 正确性。
"""
import os
import struct
import tempfile
import unittest

import config
from sources.tdx import (
    read_tdx_minute, aggregate_minute, TdxSource, _MIN1, _MIN_PERIODS,
)

# 单条 32 字节结构，与 _MIN1 一致
def _pack(num_date, num_time, price, vol=100000):
    amt = price * vol
    return _MIN1.pack(num_date, num_time, price, price + 1, price - 1, price, amt, vol, 0)


def _date_num(y, mo, da):
    return (y - 2004) * 2048 + mo * 100 + da


def _time_num(hh, mm):
    return hh * 60 + mm


def _build_lc1(tmp_root):
    """构造 2 个交易日 × 240 根 1 分钟线 → sh/minline/sh600000.lc1"""
    mkt, pure = "sh", "600000"
    d = os.path.join(tmp_root, mkt, "minline")
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, f"{mkt}{pure}.lc1")
    rows = []
    for (y, mo, da) in [(2026, 8, 3), (2026, 8, 4)]:
        num = _date_num(y, mo, da)
        # 上午 9:30-11:30 (120 根) + 下午 13:00-15:00 (120 根)
        for step in range(120):
            t = _time_num(9, 30) + step          # 570..689
            rows.append(_pack(num, t, float(step + 1)))
        for step in range(120):
            t = _time_num(13, 0) + step          # 780..899
            rows.append(_pack(num, t, float(121 + step)))
    with open(f, "wb") as fh:
        fh.write(b"".join(rows))
    return f


class TdxMinuteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_root = config.TDX_ROOT
        cls._tmp = tempfile.mkdtemp(prefix="tdx_lc1_")
        cls._lc1 = _build_lc1(cls._tmp)
        config.TDX_ROOT = cls._tmp

    @classmethod
    def tearDownClass(cls):
        config.TDX_ROOT = cls._orig_root
        # 清理临时文件
        try:
            os.remove(cls._lc1)
            os.rmdir(os.path.dirname(cls._lc1))
            os.rmdir(os.path.dirname(os.path.dirname(cls._lc1)))
        except Exception:
            pass

    def test_read_tdx_minute_count_and_fields(self):
        rows = read_tdx_minute("sh600000")
        self.assertEqual(len(rows), 480, "2 交易日 × 240 根 = 480")
        r0 = rows[0]
        self.assertEqual(r0["date"], "2026-08-03")
        self.assertEqual(r0["time"], "09:30")
        self.assertEqual(r0["open"], 1.0)
        self.assertEqual(r0["close"], 1.0)
        # 下午第一根（第 121 根）应为 13:00
        self.assertEqual(rows[120]["time"], "13:00")
        self.assertEqual(rows[120]["close"], 121.0)

    def test_aggregate_m60_eight_bars_per_two_days(self):
        rows = read_tdx_minute("sh600000")
        out = aggregate_minute(rows, 60)
        self.assertEqual(len(out), 8, "每天 4 根 60分 K × 2 天 = 8")
        # 第 1 根（day1 上午）：open=第1根close(1), close=第60根close(60)
        # high=max(price+1)=61（第60根）, low=min(price-1)=0（第1根）
        b0 = out[0]
        self.assertEqual(b0["open"], 1.0)
        self.assertEqual(b0["close"], 60.0)
        self.assertEqual(b0["high"], 61.0)
        self.assertEqual(b0["low"], 0.0)
        # date 字段含交易日与尾根时间
        self.assertTrue(b0["date"].startswith("2026-08-03"))
        self.assertIn(":", b0["date"])

    def test_aggregate_periods_bar_counts(self):
        rows = read_tdx_minute("sh600000")
        for period, per in _MIN_PERIODS.items():
            out = aggregate_minute(rows, per)
            # 每天 240 根 / 每根周期 = 每天若干根 × 2 天
            expected = (240 // per) * 2
            self.assertEqual(len(out), expected, f"{period} 应为 {expected} 根")

    def test_get_kline_m60_full_history(self):
        src = TdxSource()
        out = src.get_kline("sh600000", "m60", limit=0)  # 全量
        self.assertEqual(len(out), 8, "m60 全量 8 根")
        # limit 截断
        out2 = src.get_kline("sh600000", "m60", limit=5)
        self.assertEqual(len(out2), 5)
        # 不支持的周期应抛错（让 fallback 跳过）
        self.assertRaises(RuntimeError, src.get_kline, "sh600000", "year", 10)

    def test_get_minute_history_filters_by_date(self):
        src = TdxSource()
        # 历史某日（YYYYMMDD）→ 当日 240 根分时
        out = src.get_minute("sh600000", "20260803")
        self.assertEqual(len(out), 240)
        self.assertEqual(out[0]["t"], "09:30")
        self.assertEqual(out[0]["price"], 1.0)
        # 均价 = 成交额 / 成交量
        self.assertAlmostEqual(out[0]["avg"], out[0]["price"], places=2)
        # 当日（无 date）应抛 NotImplementedError，回退腾讯/东财
        self.assertRaises(NotImplementedError, src.get_minute, "sh600000", "")
        # 无数据的日期应抛 RuntimeError
        self.assertRaises(RuntimeError, src.get_minute, "sh600000", "20260101")

    def test_missing_file_returns_empty(self):
        self.assertEqual(read_tdx_minute("sz999999"), [])


class QuoteServiceFullHistoryTest(unittest.TestCase):
    """回归：分钟 K 必须返回通达信本地『全量』历史，不得被后端 2000 上限截断。
    构造 >2000 根（11 个交易日 × 240 = 2640）的 .lc1，经 quote_service.get_kline
    验证返回全部 2640 根（而非被截到 2000）。"""

    @classmethod
    def setUpClass(cls):
        cls._orig_root = config.TDX_ROOT
        cls._orig_min = list(config.KLINE_MIN_SOURCES)
        cls._tmp = tempfile.mkdtemp(prefix="tdx_full_")
        mkt, pure = "sh", "600001"
        d = os.path.join(cls._tmp, mkt, "minline")
        os.makedirs(d, exist_ok=True)
        cls._lc1 = os.path.join(d, f"{mkt}{pure}.lc1")
        rows = []
        for day in range(11):
            y, mo, da = 2026, 8, 3 + day
            num = _date_num(y, mo, da)
            for step in range(120):
                rows.append(_pack(num, _time_num(9, 30) + step, float(step + 1)))
            for step in range(120):
                rows.append(_pack(num, _time_num(13, 0) + step, float(121 + step)))
        with open(cls._lc1, "wb") as fh:
            fh.write(b"".join(rows))
        config.TDX_ROOT = cls._tmp
        # 只走本地 tdx，避免回退到网络源影响断言
        config.KLINE_MIN_SOURCES = ["tdx"]

    @classmethod
    def tearDownClass(cls):
        config.TDX_ROOT = cls._orig_root
        config.KLINE_MIN_SOURCES = cls._orig_min
        try:
            os.remove(cls._lc1)
            os.rmdir(os.path.dirname(cls._lc1))
            os.rmdir(os.path.dirname(os.path.dirname(cls._lc1)))
        except Exception:
            pass

    def test_get_kline_m1_returns_full_not_truncated(self):
        import services.quote_service as qs
        qs.kline_cache.invalidate("sh600001_m1")
        out = qs.get_kline("sh600001", "m1", limit=0)
        self.assertEqual(len(out), 2640,
                         "全量 1 分钟应为 2640 根；若被 2000 上限截断会变成 2000（回归 bug）")

    def test_get_kline_m60_full_across_days(self):
        import services.quote_service as qs
        qs.kline_cache.invalidate("sh600001_m60")
        out = qs.get_kline("sh600001", "m60", limit=0)
        self.assertEqual(len(out), 44, "11 天 × 每天 4 根 60分 = 44 根（全量）")
        # 首根交易日应为 2026-08-03
        self.assertTrue(out[0]["date"].startswith("2026-08-03"))

    def test_minute_cache_staleness_refresh(self):
        """缺陷#18 回归：分钟 K 缓存也必须做过期检查。
        先塞一个『陈旧』的 m30 缓存（条数少、最后日期旧），再把 tdx 本地最后日期
        mock 成更新，验证 get_kline 不会直接命中陈旧缓存，而是重拉全量。"""
        import services.quote_service as qs
        from unittest.mock import patch

        key = "sh600001_m30"
        qs.kline_cache.invalidate(key)
        # 陈旧缓存：4 根、最后日期停在 2026-08-03
        stale = [
            {"date": "2026-08-03 10:00", "open": 1, "high": 1, "low": 1, "close": 1, "vol": 1},
            {"date": "2026-08-03 10:30", "open": 1, "high": 1, "low": 1, "close": 1, "vol": 1},
            {"date": "2026-08-03 11:00", "open": 1, "high": 1, "low": 1, "close": 1, "vol": 1},
            {"date": "2026-08-03 11:30", "open": 1, "high": 1, "low": 1, "close": 1, "vol": 1},
        ]
        qs.kline_cache.set(key, stale)
        # mock 通达信本地最后日期为「未来」，强制陈旧缓存过期
        with patch("sources.tdx.tdx_last_date", return_value="2099-01-01"):
            out = qs.get_kline("sh600001", "m30", limit=0)
        # 全量应为 11 天 × 8 根 = 88，而非陈旧的 4 根
        self.assertEqual(len(out), 88,
                         "分钟 K 缓存过期必须重拉全量；若命中陈旧 4 根即回归 #18")
        qs.kline_cache.invalidate(key)


if __name__ == "__main__":
    unittest.main()

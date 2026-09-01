# -*- coding: utf-8 -*-
"""通达信本地源单元测试：.day 二进制解析 / 周月聚合 / limit。"""
import os
import unittest
from unittest.mock import patch

from tests.helpers import make_tdx_file, temp_config


class TestTdx(unittest.TestCase):

    def setUp(self):
        self.tmp = temp_config()
        import config
        config.TDX_ROOT = self.tmp

    def test_read_tdx_day(self):
        from sources.tdx import read_tdx_day
        make_tdx_file(self.tmp, "sh600519", [
            (20260810, 10.0, 11.0, 9.5, 10.5, 100, 123456.78),
            (20260811, 10.5, 12.0, 10.0, 11.5, 200, 234567.89),
        ])
        rows = read_tdx_day("sh600519")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], "2026-08-10")
        self.assertEqual(rows[0]["open"], 10.0)
        self.assertEqual(rows[0]["close"], 10.5)
        self.assertEqual(rows[0]["high"], 11.0)
        self.assertEqual(rows[0]["low"], 9.5)
        self.assertEqual(rows[0]["vol"], 100)
        self.assertEqual(rows[0]["amount"], 123456.78)

    def test_missing_file_returns_empty(self):
        from sources.tdx import read_tdx_day
        self.assertEqual(read_tdx_day("sh999999"), [])

    def test_tdx_last_date(self):
        """tdx_last_date 轻量读尾部最后一条日期（K线缓存同步用）。"""
        from sources.tdx import tdx_last_date
        make_tdx_file(self.tmp, "sh600519", [
            (20260810, 10.0, 11.0, 9.5, 10.5, 100),
            (20260811, 10.5, 12.0, 10.0, 11.5, 200),
        ])
        self.assertEqual(tdx_last_date("sh600519"), "2026-08-11")
        # 不存在的文件 → 空串
        self.assertEqual(tdx_last_date("sh999999"), "")

    def test_aggregate_week(self):
        from sources.tdx import aggregate
        days = [
            {"date": f"2026-08-{d:02d}", "open": 10.0 + i, "close": 10.5 + i,
             "high": 11.0 + i, "low": 9.5 + i, "vol": 100 + i, "amount": 1000 + i * 10}
            for i, d in enumerate(range(1, 11))   # 10 天 → 2 根周线
        ]
        weeks = aggregate(days, 5)
        self.assertEqual(len(weeks), 2)
        w0 = weeks[0]
        self.assertEqual(w0["date"], "2026-08-05")
        self.assertEqual(w0["open"], 10.0)                  # 首日开盘
        self.assertEqual(w0["close"], 14.5)                # 末日收盘
        self.assertEqual(w0["high"], 15.0)                 # 最高
        self.assertEqual(w0["low"], 9.5)                   # 最低
        self.assertEqual(w0["vol"], 100 + 101 + 102 + 103 + 104)
        self.assertEqual(w0["amount"], 1000 + 1010 + 1020 + 1030 + 1040)

    def test_get_kline_periods_and_limit(self):
        from sources.tdx import TdxSource
        records = [(20260801 + i, 10.0 + i, 11.0 + i, 9.0 + i, 10.5 + i, 100 + i)
                   for i in range(30)]                     # 30 个交易日
        make_tdx_file(self.tmp, "sh600519", records)
        src = TdxSource()
        day = src.get_kline("sh600519", "day", 5)
        self.assertEqual(len(day), 5)                      # limit 生效
        week = src.get_kline("sh600519", "week", 10)
        self.assertEqual(len(week), 6)                     # 30/5 = 6 根周线
        month = src.get_kline("sh600519", "month", 10)
        self.assertEqual(len(month), 2)                    # 30/22 → ceil 2 根
        with self.assertRaises(RuntimeError):
            src.get_kline("sh600519", "m5", 10)            # 通达信不支持分钟

    def test_get_kline_empty_raises(self):
        from sources.tdx import TdxSource
        with self.assertRaises(RuntimeError):
            TdxSource().get_kline("sh999999", "day", 10)

    def test_unsupported_methods_raise(self):
        from sources.tdx import TdxSource
        src = TdxSource()
        for m in ("get_quote", "get_minute", "get_fund_flow"):
            with self.assertRaises(NotImplementedError):
                getattr(src, m)("sh600519")


if __name__ == "__main__":
    unittest.main()

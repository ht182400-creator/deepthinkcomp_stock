# -*- coding: utf-8 -*-
"""服务层单元测试：get_all 错误隔离 / 缓存语义（mock 内部，不联网）。"""
import unittest
from unittest.mock import patch

from tests.helpers import temp_config
from core.cache import TtlCache, FileCache


class TestQuoteService(unittest.TestCase):

    def setUp(self):
        self.tmp = temp_config()
        import config
        import services.quote_service as qs
        self.qs = qs
        # 重建缓存实例指向临时目录（FileCache/TtlCache 构造时快照路径，必须重建隔离）
        qs.quote_cache = TtlCache(config.TTL_QUOTE)
        qs.minute_cache = TtlCache(config.TTL_MINUTE)
        qs.fund_cache = TtlCache(config.TTL_FUND)
        qs.kline_cache = FileCache(config.KLINE_CACHE_DIR, config.TTL_KLINE)

    def test_get_all_success(self):
        with patch.object(self.qs, "get_quote", return_value={"code": "sh600519", "name": "贵州茅台", "source": "tencent"}), \
             patch.object(self.qs, "get_minute", return_value=[{"t": "0930", "price": 10.0}]), \
             patch.object(self.qs, "get_fund_flow", return_value=[{"t": "09:31", "main": 100}]):
            d = self.qs.get_all("sh600519")
        self.assertEqual(d["quote"]["name"], "贵州茅台")
        self.assertEqual(len(d["minute"]), 1)
        self.assertEqual(len(d["fund"]), 1)
        self.assertEqual(d["errors"], [])

    def test_get_all_partial_failure_isolated(self):
        """单个数据源失败不应影响其他，错误进 errors 列表。"""
        with patch.object(self.qs, "get_quote", side_effect=RuntimeError("quote down")), \
             patch.object(self.qs, "get_minute", return_value=[]), \
             patch.object(self.qs, "get_fund_flow", return_value=[]):
            d = self.qs.get_all("sh600519")
        self.assertNotIn("quote", d)
        self.assertEqual(len(d["errors"]), 1)
        self.assertIn("quote", d["errors"][0])
        self.assertEqual(d["minute"], [])
        self.assertEqual(d["fund"], [])

    def test_get_all_all_fail(self):
        with patch.object(self.qs, "get_quote", side_effect=RuntimeError("q")), \
             patch.object(self.qs, "get_minute", side_effect=RuntimeError("m")), \
             patch.object(self.qs, "get_fund_flow", side_effect=RuntimeError("f")):
            d = self.qs.get_all("sh600519")
        self.assertEqual(len(d["errors"]), 3)
        self.assertIsNone(d.get("quote"))
        self.assertIsNone(d.get("minute"))
        self.assertIsNone(d.get("fund"))

    def test_get_quote_cache_hit_no_fallback(self):
        """缓存命中时不再走数据源（fallback 不应被调用）。"""
        self.qs.quote_cache.set("quote:sh600519", {"code": "sh600519", "name": "缓存"})
        with patch("core.fallback.fallback", side_effect=AssertionError("不应触发拉取")):
            q = self.qs.get_quote("sh600519")
        self.assertEqual(q["name"], "缓存")

    def test_get_quote_cache_miss_fetches(self):
        with patch("core.fallback.fallback", return_value=({"code": "sh600519", "name": "新拉"}, "tencent")):
            q = self.qs.get_quote("sh600519")
        self.assertEqual(q["name"], "新拉")
        self.assertEqual(q["source"], "tencent")   # 注入 source 标记

    def test_kline_cache_pollution_recover(self):
        """缓存被 npx 写入 5 条小数据（污染），下次访问应自动失效并重拉。"""
        import services.quote_service as qs
        import os
        # 手动制造污染缓存：5 条
        qs.kline_cache.set("sh600519_day", [{"date": "2026-08-07", "open": 1, "close": 2, "high": 3, "low": 0, "vol": 100}] * 1)
        # 兜底：5 条独立 dict（不是同一引用）
        polluted = [{"date": f"2026-08-{i:02d}", "open": 1, "close": 2, "high": 3, "low": 0, "vol": 100} for i in range(1, 6)]
        qs.kline_cache.set("sh600519_day", polluted)
        self.assertEqual(len(qs.kline_cache.get("sh600519_day")), 5)
        # fetch 触发：缓存 < 200 应被检测并重拉
        with patch("core.fallback.fallback", return_value=([{"date": "2026-08-13", "open": 1, "close": 2, "high": 3, "low": 0, "vol": 100}], "tdx")) as fb_mock:
            k = self.qs.get_kline("sh600519", "day", 5)
        self.assertEqual(len(k), 1)  # fresh 返回 1 条
        fb_mock.assert_called_once()  # 确实重新拉取了

    def _recent_rows(self, n=240):
        """最近 n 个自然日（日期按今天往前推，避免 K 线 stale 检查触发重拉）。"""
        from datetime import datetime, timedelta
        base = datetime.now().date()
        rows = []
        for i in range(n):
            d = (base - timedelta(days=n - 1 - i)).isoformat()
            rows.append({"date": d, "open": 1, "close": 2, "high": 3, "low": 0, "vol": 100})
        return rows

    def test_kline_limit_zero_returns_all(self):
        """limit<=0 返回全部（日线本地数据有多少显示多少，不再限制 260）。"""
        import services.quote_service as qs
        all_rows = self._recent_rows(240)
        qs.kline_cache.set("sh600519_day", all_rows)
        with patch("core.fallback.fallback") as fb_mock:
            k = self.qs.get_kline("sh600519", "day", 0)   # 0 = 全部
        self.assertEqual(len(k), 240)
        fb_mock.assert_not_called()
        with patch("core.fallback.fallback") as fb_mock:
            k5 = self.qs.get_kline("sh600519", "day", 5)  # 正数仍截断
        self.assertEqual(len(k5), 5)

    def test_kline_cache_valid_no_refetch(self):
        """缓存条数充足时不重拉。"""
        import services.quote_service as qs
        valid = self._recent_rows(240)
        qs.kline_cache.set("sh600519_day", valid)
        with patch("core.fallback.fallback") as fb_mock:
            k = self.qs.get_kline("sh600519", "day", 260)
        self.assertEqual(len(k), 240)  # cached 240 条，limit 260 取全部
        fb_mock.assert_not_called()

    def test_get_kline_day_period_map(self):
        """day/week/month 走 day 链（通达信），minute 走 min 链。"""
        with patch("core.fallback.fallback", return_value=([{"date": "2026-08-13", "close": 1.0}], "tdx")):
            k = self.qs.get_kline("sh600519", "day", 5)
        self.assertEqual(len(k), 1)

    def test_cache_is_stale_three_scenarios(self):
        """K线缓存同步：vs 通达信本地最后日期，而非 vs 今天。"""
        import services.quote_service as qs
        # 场景1：缓存日期 == 本地日期 → 不刷新
        with patch("sources.tdx.tdx_last_date", return_value="2026-08-13"):
            self.assertFalse(qs._cache_is_stale([{"date": "2026-08-13"}], "sh600519"))
        # 场景2：缓存日期 < 本地日期 → 刷新（通达信更新了）
        with patch("sources.tdx.tdx_last_date", return_value="2026-08-13"):
            self.assertTrue(qs._cache_is_stale([{"date": "2026-08-10"}], "sh600519"))
        # 场景3：本地无数据 → 不刷新（无更新依据）
        with patch("sources.tdx.tdx_last_date", return_value=""):
            self.assertFalse(qs._cache_is_stale([{"date": "2026-08-07"}], "sh999999"))

    def test_get_many_partial(self):
        from concurrent.futures import ThreadPoolExecutor
        def fake_all(code):
            if code == "sh600519":
                return {"code": code, "quote": {"name": "茅台"}}
            raise RuntimeError("down")
        with patch.object(self.qs, "get_all", side_effect=fake_all), \
             patch("concurrent.futures.ThreadPoolExecutor", ThreadPoolExecutor):
            r = self.qs.get_many(["sh600519", "sz000858"])
        self.assertEqual(r["sh600519"]["quote"]["name"], "茅台")
        self.assertIn("error", r["sz000858"])

    def test_get_minute_with_meta_mismatch_rejected(self):
        """在线源返回的数据与请求日期日线不匹配时，应拒绝并 source='none'。"""
        # 日线：2024-11-04 open=1600 close=1580（与在线源返回的 1355/1341 明显不符）
        day_rows = [{"date": "2024-11-04", "open": 1600.0, "close": 1580.0, "high": 1620.0, "low": 1570.0, "vol": 100}]
        fake_minute = [{"t": "0930", "price": 1355.0}, {"t": "1500", "price": 1341.99}]
        with patch.object(self.qs, "get_kline", return_value=day_rows), \
             patch("core.fallback.fallback", return_value=(fake_minute, "tencent")), \
             patch("sources.tdx.tdx_last_minute_date", return_value="2026-08-14"):
            out = self.qs.get_minute_with_meta("sh600519", "2024-11-04")
        self.assertEqual(out["data"], [])
        self.assertEqual(out["meta"]["source"], "none")
        self.assertTrue(out["meta"]["mismatch"])

    def test_get_minute_with_meta_match_accepted(self):
        """在线源返回的数据与请求日期日线匹配时，正常返回。"""
        day_rows = [{"date": "2024-11-04", "open": 1355.0, "close": 1342.0, "high": 1360.0, "low": 1340.0, "vol": 100}]
        fake_minute = [{"t": "0930", "price": 1355.0}, {"t": "1500", "price": 1342.0}]
        with patch.object(self.qs, "get_kline", return_value=day_rows), \
             patch("core.fallback.fallback", return_value=(fake_minute, "tencent")), \
             patch("sources.tdx.tdx_last_minute_date", return_value="2026-08-14"):
            out = self.qs.get_minute_with_meta("sh600519", "2024-11-04")
        self.assertEqual(len(out["data"]), 2)
        self.assertEqual(out["meta"]["source"], "tencent")
        self.assertFalse(out["meta"]["mismatch"])


if __name__ == "__main__":
    unittest.main()

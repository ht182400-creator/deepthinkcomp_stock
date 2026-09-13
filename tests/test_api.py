# -*- coding: utf-8 -*-
"""API 集成测试（FastAPI TestClient，mock 服务层做确定性断言）。
在 import server 前先隔离 config 路径，避免污染真实 data/。
"""
import json
import os
import unittest
from unittest.mock import patch

from tests.helpers import temp_config

_TMP = temp_config()          # 必须在 import server 之前

from fastapi.testclient import TestClient  # noqa: E402
import server as app_module    # noqa: E402
import services.quote_service as qs  # noqa: E402
import services.search_service as ss  # noqa: E402


class TestApi(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app)
        # watchlist 指向临时文件
        cls.tmp_watchlist = os.path.join(_TMP, "data", "watchlist.json")
        app_module.WATCHLIST_FILE = cls.tmp_watchlist

    def test_index_200(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.content), 0)

    def test_quote_returns_structure(self):
        with patch.object(qs, "get_all", return_value={
            "code": "sh600519",
            "quote": {"name": "贵州茅台", "price": 1355.29, "source": "tencent"},
            "minute": [{"t": "0930", "price": 10.0}],
            "fund": [{"t": "09:31", "main": 100}],
            "errors": [],
        }):
            r = self.client.get("/api/quote?code=sh600519")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["quote"]["name"], "贵州茅台")
        self.assertEqual(len(d["minute"]), 1)
        self.assertEqual(d["errors"], [])

    def test_quote_error_still_200(self):
        """服务层全失败时返回 200 + error 结构（前端不崩）。"""
        with patch.object(qs, "get_all", side_effect=RuntimeError("boom")):
            r = self.client.get("/api/quote?code=sh600519")
        self.assertEqual(r.status_code, 200)
        d = r.json()

    def test_announcement_route(self):
        """公告正文路由。"""
        with patch("sources.company.get_announcement_content",
                   return_value={"title": "测试公告", "date": "2026-08-14", "content": "正文", "pdf_url": "x"}):
            r = self.client.get("/api/announcement?code=AN202608140001")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["title"], "测试公告")
        # 缺少 code → error
        r2 = self.client.get("/api/announcement")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("error", r2.json())

    def test_search(self):
        with patch.object(ss, "search_stocks", return_value=[
            {"code": "sh600519", "name": "贵州茅台", "cat": "白酒", "display": "SH600519 贵州茅台 · 白酒"}
        ]):
            r = self.client.get("/api/search?q=茅台")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)

    def test_kline_success(self):
        with patch.object(qs, "get_kline", return_value=[
            {"date": "2026-08-13", "open": 1, "close": 2, "high": 3, "low": 0.5, "vol": 10}
        ]):
            r = self.client.get("/api/kline?code=sh600519&period=day&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)

    def test_kline_failure(self):
        with patch.object(qs, "get_kline", side_effect=RuntimeError("no data")):
            r = self.client.get("/api/kline?code=sh600519&period=day")
        self.assertEqual(r.status_code, 200)
        self.assertIn("error", r.json())

    def test_many(self):
        with patch.object(qs, "get_many", return_value={
            "sh600519": {"code": "sh600519", "quote": {"name": "茅台"}},
        }):
            r = self.client.get("/api/many?codes=sh600519,sz000858")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        keys = list(body.keys()) if isinstance(body, dict) else body
        self.assertIn("sh600519", keys)

    def test_many_empty_codes(self):
        r = self.client.get("/api/many?codes=")
        self.assertEqual(r.status_code, 200)
        self.assertIn("error", r.json())

    def test_watchlist_default(self):
        r = self.client.get("/api/watchlist")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)
        body = r.json()
        codes = [x["code"] if isinstance(x, dict) else x for x in body]
        self.assertIn("sh600519", codes)
        # 新增：返回应包含全部预置池（datalist 用），并标记 in_watchlist
        self.assertGreater(len(body), 10)
        wl = [x for x in body if x.get("in_watchlist")]
        self.assertGreaterEqual(len(wl), 1)
        # 第一项应为 in_watchlist=True（watchlist 在前）
        self.assertTrue(body[0].get("in_watchlist"))

    def test_watchlist_add_remove(self):
        r = self.client.post("/api/watchlist", json={"action": "add", "code": "sz300999"})
        self.assertEqual(r.status_code, 200)
        items = r.json()["items"]
        self.assertIn("sz300999", items)
        r = self.client.post("/api/watchlist", json={"action": "remove", "code": "sz300999"})
        self.assertNotIn("sz300999", r.json()["items"])

    def test_sysinfo(self):
        r = self.client.get("/api/sysinfo")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("python", d)
        self.assertIn("os", d)


class TestMinuteAvgNormalize(unittest.TestCase):
    """分时均价自校准：均价必须与**同分钟价格**同量级。

    回归 bug：腾讯 cum_vol 单位是"股"，若按"手"再除 100，219 元的股票均价显示 2.19；
    旧判据 `avg < 1 才 ×100` 对高价股失效。
    """

    def test_multiplies_when_off_by_100(self):
        """漏乘 100（与 price 差约 100 倍）→ ×100 还原。"""
        out = app_module._normalize_minute_avg([{"t": "14:25", "price": 218.89, "avg": 2.17}])
        self.assertAlmostEqual(out[0]["avg"], 217.0, places=2)

    def test_keeps_correct_value(self):
        """本来就正确（与 price 同量级）→ 不改动。"""
        out = app_module._normalize_minute_avg([{"t": "14:25", "price": 218.89, "avg": 217.51}])
        self.assertEqual(out[0]["avg"], 217.51)

    def test_low_price_still_fixed(self):
        """低价股（旧判据覆盖的场景）依然正确：0.15 → 15.0。"""
        out = app_module._normalize_minute_avg([{"t": "09:30", "price": 15.0, "avg": 0.15}])
        self.assertAlmostEqual(out[0]["avg"], 15.0, places=2)

    def test_missing_or_bad_values_are_safe(self):
        """缺字段 / 非数值 / 非字典元素 → 原样返回，不抛异常。"""
        rows = [{"t": "09:30", "price": 10.0}, {"t": "09:31", "price": "x", "avg": "y"}, None]
        out = app_module._normalize_minute_avg(rows)
        self.assertEqual(len(out), 3)

    def test_no_mutation_of_input(self):
        """不得就地修改入参（应返回新 dict）。"""
        rows = [{"t": "14:25", "price": 218.89, "avg": 2.17}]
        app_module._normalize_minute_avg(rows)
        self.assertEqual(rows[0]["avg"], 2.17)


class TestQuoteMinuteAvgNormalized(unittest.TestCase):
    """回归：/api/quote 返回的分时均价必须已自校准。

    历史 bug：均价归一化只加在 /api/minute、/api/stock/tick、/api/stock/full，
    /api/quote 漏了 → 单股页分时图（single-app.js 读 /api/quote 的 minute）
    涨跌幅正确、均价却小 100 倍（实测 sh688300：现价 179.02 / 均价 1.79）。
    """

    def setUp(self):
        self.client = TestClient(app_module.app)

    def test_quote_normalizes_minute_avg(self):
        raw = [{"t": "0930", "price": 179.02, "avg": 1.79},
               {"t": "1500", "price": 178.69, "avg": 1.773}]
        with patch.object(qs, "get_all", return_value={"code": "sh688300", "minute": raw}):
            items = self.client.get("/api/quote?code=sh688300").json()["minute"]
        self.assertAlmostEqual(items[0]["avg"], 179.0, places=2)
        self.assertAlmostEqual(items[1]["avg"], 177.3, places=2)

    def test_quote_keeps_correct_avg(self):
        """本来就正确的均价不得被二次放大。"""
        raw = [{"t": "0930", "price": 1285.15, "avg": 1285.15}]
        with patch.object(qs, "get_all", return_value={"code": "sh600519", "minute": raw}):
            items = self.client.get("/api/quote?code=sh600519").json()["minute"]
        self.assertEqual(items[0]["avg"], 1285.15)

    def test_quote_minute_without_avg_is_safe(self):
        """缺 avg 字段不得抛异常。"""
        raw = [{"t": "0930", "price": 10.0}]
        with patch.object(qs, "get_all", return_value={"code": "sh600000", "minute": raw}):
            r = self.client.get("/api/quote?code=sh600000")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["minute"][0]["price"], 10.0)


class TestGetMinuteNormalizesAvg(unittest.TestCase):
    """回归：service 层 get_minute 是分时均价归一化的唯一收口点（覆盖所有消费方）。"""

    def test_get_minute_returns_normalized_avg(self):
        raw = [{"t": "0930", "price": 179.02, "avg": 1.79}]
        with patch.object(qs.fb, "fallback", return_value=(raw, "tencent")), \
             patch.object(qs.minute_cache, "get_or_set", return_value=(raw, 0)):
            out = qs.get_minute("sh688300")
        self.assertAlmostEqual(out[0]["avg"], 179.0, places=2)

    def test_get_minute_keeps_correct_avg(self):
        raw = [{"t": "0930", "price": 1285.15, "avg": 1285.15}]
        with patch.object(qs.fb, "fallback", return_value=(raw, "eastmoney")), \
             patch.object(qs.minute_cache, "get_or_set", return_value=(raw, 0)):
            out = qs.get_minute("sh600519")
        self.assertEqual(out[0]["avg"], 1285.15)

    def test_normalize_is_idempotent(self):
        """重复调用不得继续放大（幂等）。"""
        once = qs.normalize_minute_avg([{"t": "0930", "price": 179.02, "avg": 1.79}])
        twice = qs.normalize_minute_avg(once)
        self.assertAlmostEqual(twice[0]["avg"], 179.0, places=2)

    def test_normalize_does_not_mutate_input(self):
        raw = [{"t": "0930", "price": 179.02, "avg": 1.79}]
        qs.normalize_minute_avg(raw)
        self.assertEqual(raw[0]["avg"], 1.79)


if __name__ == "__main__":
    unittest.main()

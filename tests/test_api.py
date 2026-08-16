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


if __name__ == "__main__":
    unittest.main()

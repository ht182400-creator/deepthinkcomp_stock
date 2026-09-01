# -*- coding: utf-8 -*-
"""P2/P3 API 契约测试：策略/持仓/分析/回测/报告/个股详情端点（mock 服务层，离线可跑）。
覆盖 T-P2（删除后无陈旧）、T-P4/T-P5（精选/超预算标注）的 API 面 + period 归一化回归。
"""
import json
import os
import unittest
from unittest.mock import patch

from tests.helpers import temp_config

_TMP = temp_config()          # 必须在 import server 之前

from fastapi.testclient import TestClient  # noqa: E402
import server as app_module    # noqa: E402
import modules.holdings.holdings as H      # noqa: E402
import modules.analysis.analysis as A      # noqa: E402
import services.quote_service as qs        # noqa: E402


def _fake_res():
    def _mk(code, score=0.7, price=50.0, mom=0.5, roe=0.2, sind="化学制品", lots=100, cap=5000):
        return dict(code=code, name=f"股{code}", price=price, score=score, mom=mom,
                    roe=roe, sind=sind, seg="sh000001", lots=lots, capital=cap,
                    selected=code in ("688625",))
    return dict(
        signal_date=20260814, scheme="B", regime_up=True, n_stocks=1687,
        buy=[_mk("688625"), _mk("002484", sind="元件"), _mk("688127"), _mk("300684"),
             _mk("300394", price=267.0, score=0.84)],
        selected=[_mk("688625")],
        observation=[dict(code="300111", name="观1", roe=0.15, price=20.0, fail="未站线")],
        bj_observe=[], per_pos=11250.0, expo_base=0.9,
    )


class TestApiStrategy(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app)
        # 隔离数据路径到临时目录
        cls.tmp_data = os.path.join(_TMP, "data")
        os.makedirs(cls.tmp_data, exist_ok=True)
        cls.holdings_file = os.path.join(cls.tmp_data, "holdings.json")
        cls.settings_file = os.path.join(cls.tmp_data, "settings.json")
        cls.log_file = os.path.join(cls.tmp_data, "analyze.log")
        H.HOLDINGS_FILE = cls.holdings_file
        H.SETTINGS_FILE = cls.settings_file
        A.LOG_FILE = cls.log_file
        # 清空隔离文件
        for p in (cls.holdings_file, cls.settings_file):
            if os.path.exists(p):
                os.remove(p)

    def setUp(self):
        for p in (self.holdings_file, self.settings_file):
            if os.path.exists(p):
                os.remove(p)

    # ---- /api/pool ----
    def test_pool_returns_full(self):
        r = self.client.get("/api/pool?cls=all")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertGreater(d["total"], 1700)          # 1771 只
        it = d["items"][0]
        for k in ("code", "name", "industry", "market"):
            self.assertIn(k, it, f"pool item 缺字段 {k}")

    def test_pool_filter(self):
        r = self.client.get("/api/pool?cls=bj")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(all(i["market"] == "bj" for i in d["items"]))

    # ---- /api/holdings CRUD ----
    def test_holdings_empty(self):
        r = self.client.get("/api/holdings")
        self.assertEqual(r.json(), {"items": []})

    def test_holdings_add_rejects_bad_code(self):
        r = self.client.post("/api/holdings", json={"code": ""})
        self.assertIn("error", r.json())
        # 不在池中
        r = self.client.post("/api/holdings", json={"code": "999999"})
        self.assertIn("error", r.json())

    def test_holdings_add_and_get(self):
        r = self.client.post("/api/holdings", json={"code": "688625", "amount": 12000, "dingtou": True})
        self.assertEqual(r.status_code, 200)
        items = r.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["code"], "688625")
        self.assertEqual(items[0]["name"], "呈和科技")   # 名称来自池
        self.assertTrue(items[0]["dingtou"])
        # 更新
        r = self.client.post("/api/holdings", json={"code": "688625", "amount": 9999})
        self.assertEqual(r.json()["items"][0]["amount"], 9999)

    def test_holdings_delete_and_no_stale(self):
        """T-P2：删除持仓后操作卡不残留陈旧（cards 过滤依赖 holdings 最新态）。"""
        self.client.post("/api/holdings", json={"code": "688625", "amount": 12000})
        self.client.post("/api/holdings", json={"code": "002484", "amount": 15000})
        r = self.client.post("/api/holdings/delete", json={"codes": ["688625"]})
        items = r.json()["items"]
        self.assertEqual([i["code"] for i in items], ["002484"])

    # ---- /api/settings ----
    def test_settings_default_and_save(self):
        r = self.client.get("/api/settings")
        self.assertEqual(r.json()["cash"], 50000)
        r = self.client.post("/api/settings", json={"auto_track": True, "weekly": 8000})
        self.assertTrue(r.json()["auto_track"])
        self.assertEqual(self.client.get("/api/settings").json()["weekly"], 8000)

    # ---- /api/analyze ----
    def test_analyze_flow_and_status(self):
        """提交分析 → mock current_candidates → 状态完成含操作卡/精选。"""
        with patch.object(A.R, "current_candidates", return_value=_fake_res()):
            A.ANALYSIS["running"] = False
            A.ANALYSIS["last_result"] = None
            r = self.client.post("/api/analyze", json={})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["running"])
            # 等后台线程完成
            import time
            for _ in range(30):
                s = self.client.get("/api/analyze/status").json()
                if not s["running"]:
                    break
                time.sleep(0.2)
            self.assertFalse(s["running"])
            self.assertIsNotNone(s["result"])
            res = s["result"]
            self.assertEqual(res["signal_date"], 20260814)
            self.assertEqual(len(res["selected_recommends"]), 1)   # ⭐精选=selected
            self.assertTrue(all(x["is_top"] for x in res["selected_recommends"]))
            # T-P5：更多候选里超预算的标注 fea_ratio > 100
            over = [x for x in res["recommends"] if x["fea_ratio"] > 100]
            self.assertTrue(over, "超预算候选应存在")
            self.assertEqual(over[0]["code"], "300394")

    def test_analyze_concurrent_reject(self):
        A.ANALYSIS["running"] = True
        try:
            r = self.client.post("/api/analyze", json={})
            self.assertIn("error", r.json())
            self.assertTrue(r.json()["running"])
        finally:
            A.ANALYSIS["running"] = False

    def test_analyze_events_sse(self):
        """P4: SSE 进度流——完成态立即推送 progress + done + close。"""
        A.ANALYSIS["running"] = False
        A.ANALYSIS["percent"] = 100
        A.ANALYSIS["message"] = "分析完成"
        A.ANALYSIS["last_result"] = {"signal_date": 20260814, "cards": [], "recommends": []}
        with self.client.stream("GET", "/api/analyze/events") as r:
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.headers.get("content-type", "").startswith("text/event-stream"),
                            "SSE content-type")
            text = "".join(r.iter_text())
        self.assertIn("event: progress", text)
        self.assertIn("event: done", text)
        self.assertIn("event: close", text)
        self.assertIn("20260814", text)
        A.ANALYSIS["last_result"] = None

    def test_analyze_events_sse_running_then_done(self):
        """P4: SSE 在任务运行中持续推送进度，完成后推送 done。"""
        import threading

        def _flip_after_delay():
            import time
            time.sleep(1.5)
            A.ANALYSIS["running"] = False
            A.ANALYSIS["percent"] = 100
            A.ANALYSIS["message"] = "分析完成"
            A.ANALYSIS["last_result"] = {"signal_date": 20260814, "cards": [], "recommends": []}

        A.ANALYSIS["running"] = True
        A.ANALYSIS["percent"] = 5
        A.ANALYSIS["message"] = "构建宇宙..."
        t = threading.Thread(target=_flip_after_delay, daemon=True)
        t.start()
        with self.client.stream("GET", "/api/analyze/events") as r:
            text = "".join(r.iter_text())
        self.assertIn("event: done", text)
        self.assertIn("构建宇宙", text)
        A.ANALYSIS["last_result"] = None
        A.ANALYSIS["running"] = False

    # ---- /api/backtest & /api/curves ----
    def test_backtest_returns_5_schemes(self):
        r = self.client.get("/api/backtest")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for k in ("current_全样本1996+", "B_全样本1996+", "C_全样本1996+",
                  "A_全样本1996+", "E_全样本1996+"):
            self.assertIn(k, d)
            self.assertIn("annualized", d[k])

    def test_curves_returns_both(self):
        r = self.client.get("/api/curves")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("B_全样本1996+", d)
        self.assertIn("current_全样本1996+", d)
        self.assertGreater(len(d["B_全样本1996+"]["dates"]), 100)

    # ---- /api/logs /api/action_log /api/report/md ----
    def test_logs_and_action_log(self):
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write("[2026-08-14 09:00] 分析完成 signal=20260814 持仓2 推荐10\n")
        r = self.client.get("/api/logs")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["items"]), 1)
        r2 = self.client.get("/api/action_log")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("items", r2.json())

    def test_report_md(self):
        """MD 报告基于 last_result 生成。"""
        A.ANALYSIS["last_result"] = {
            "signal_date": 20260814, "ts": "2026-08-14 15:00",
            "summary": {"regime_cn": "全部上涨 · 建议建仓", "held": 1, "buy_pool": 5},
            "cards": [dict(code="688625", name="呈和科技", industry="化学制品", market="sh",
                           amount=12000, score=72, advice="加仓", action="加仓(已持仓)", desc="x")],
            "recommends": [dict(code="300394", name="天孚通信", industry="通信设备",
                                score=84, desc="超预算")],
        }
        r = self.client.get("/api/report/md")
        self.assertEqual(r.status_code, 200)
        t = r.text
        self.assertIn("## 一、持仓操作卡", t)
        self.assertIn("## 二、本周推荐", t)
        self.assertIn("呈和科技", t)
        self.assertIn("不构成个人投资建议", t)

    # ---- period 归一化回归（60 → m60）----
    def test_kline_period_normalize(self):
        """前端传裸数字 period=60 → 服务层收到 m60（P1 修复的兼容 bug 回归）。"""
        calls = []
        def _fake_get_kline(code, period, limit=260):
            calls.append((code, period, limit))
            return []
        with patch.object(qs, "get_kline", side_effect=_fake_get_kline):
            self.client.get("/api/kline?code=sh600519&period=60&limit=5")
        self.assertEqual(calls[0][1], "m60")
        with patch.object(qs, "get_kline", side_effect=_fake_get_kline):
            self.client.get("/api/kline?code=sh600519&period=day")
        self.assertEqual(calls[1][1], "day")

    # ---- /api/stock/* 详情端点 ----
    def test_stock_quote_endpoint(self):
        with patch.object(qs, "get_quote", return_value={"code": "sh600519", "name": "贵州茅台",
                                                         "price": 1341.99, "source": "tencent"}):
            r = self.client.get("/api/stock/quote?code=sh600519")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "贵州茅台")

    def test_stock_news_endpoint(self):
        with patch("sources.company.get_announcements", return_value=[{"date": "2026-08-14", "title": "t", "url": "u"}]):
            r = self.client.get("/api/stock/news?code=sh600519&limit=3")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["items"]), 1)


if __name__ == "__main__":
    unittest.main()

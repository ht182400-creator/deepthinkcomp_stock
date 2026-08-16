# -*- coding: utf-8 -*-
"""东财源单元测试：资金流/报价/分时解析 + 多节点轮换（mock http_get）。"""
import unittest
from unittest.mock import patch

from tests.helpers import FakeResponse


class TestEastmoney(unittest.TestCase):

    def _src(self, responses):
        """responses: [FakeResponse, ...] 依次返回；超出则复用最后一个。"""
        from sources.eastmoney import EastmoneySource
        src = EastmoneySource()
        calls = {"n": 0}

        def _fake_get(url, headers, params=None, limiter_name=None, rate=None, timeout=None):
            idx = min(calls["n"], len(responses) - 1)
            calls["n"] += 1
            return responses[idx]

        patcher = patch("sources.eastmoney.http_get", side_effect=_fake_get)
        patcher.start()
        self.addCleanup(patcher.stop)
        return src

    def test_fund_flow_parse_and_consistency(self):
        """资金流字段解析（实测映射：c1=超大 c2=大 c3=主力 c4=中 c5=小）。"""
        klines = [
            "2026-08-13 09:31,1000000,500000,1500000,200000,100000",
            "2026-08-13 09:32,-500000,100000,-400000,-300000,-200000",
        ]
        src = self._src([FakeResponse(json_data={"data": {"klines": klines}})])
        f = src.get_fund_flow("sh600519")
        self.assertEqual(len(f), 2)
        self.assertEqual(f[0]["t"], "09:31")
        self.assertEqual(f[0]["super_big"], 1000000)   # c[1] f51
        self.assertEqual(f[0]["big"], 500000)         # c[2] f52
        self.assertEqual(f[0]["main"], 1500000)        # c[3] f53 主力
        self.assertEqual(f[0]["mid"], 200000)          # c[4] f54
        self.assertEqual(f[0]["small"], 100000)        # c[5] f55
        # 自洽：main = big + super_big（东财语义：大+超大=主力）
        self.assertEqual(f[0]["main"], f[0]["big"] + f[0]["super_big"])
        # 散户差分（用于资金博弈图）：相邻两根 small 差
        self.assertAlmostEqual(f[1]["small"] - f[0]["small"], -300000.0)

    def test_fund_flow_empty_raises(self):
        src = self._src([FakeResponse(json_data={"data": {"klines": []}})])
        with self.assertRaises(RuntimeError):
            src.get_fund_flow("sh600519")

    def test_quote_parse(self):
        src = self._src([FakeResponse(json_data={"data": {
            "f43": 135529, "f58": "贵州茅台", "f46": 135500,
            "f60": 134290, "f47": 12345, "f48": 56780000, "f170": 92,
        }})])
        q = src.get_quote("sh600519")
        self.assertEqual(q["price"], 1355.29)
        self.assertEqual(q["pre_close"], 1342.90)
        self.assertEqual(q["name"], "贵州茅台")
        self.assertEqual(q["change_pct"], 0.92)
        self.assertEqual(q["amount"], 5678.0)      # /1e4

    def test_quote_empty_raises(self):
        src = self._src([FakeResponse(json_data={"data": {}})])
        with self.assertRaises(RuntimeError):
            src.get_quote("sh600519")

    def test_minute_parse(self):
        trends = [
            "2026-08-13 09:31,1342.90,1355.29,1355.29,0,100,135500.00,1354.10",
            "2026-08-13 09:32,1355.29,1356.00,1356.10,1355.00,200,271200.00,1355.00",
        ]
        src = self._src([FakeResponse(json_data={"data": {"trends": trends}})])
        m = src.get_minute("sh600519")
        self.assertEqual(len(m), 2)
        self.assertEqual(m[0]["t"], "09:31")
        self.assertEqual(m[0]["price"], 1355.29)
        self.assertEqual(m[0]["avg"], 1354.10)
        self.assertEqual(m[1]["vol"], 200)

    def test_node_fallback(self):
        """主节点抛错 → 自动切 delay 节点。"""
        from sources.eastmoney import _get_with_fallback
        ok = FakeResponse(json_data={"data": {"klines": ["2026-08-13 09:31,1,0,0,1,0"]}})

        def _fake(url, headers, params=None, limiter_name=None, rate=None, timeout=None):
            if "push2.eastmoney.com" in url:
                raise RuntimeError("connect error")
            return ok

        with patch("sources.eastmoney.http_get", side_effect=_fake):
            j = _get_with_fallback("/api/qt/stock/fflow/kline/get", {})
        self.assertEqual(j["data"]["klines"][0].split(",")[1], "1")

    def test_5d_fund_flow_parse(self):
        """Sprint 4 US-009：f178 JSON 字符串解析（近 5 日主力）。"""
        from sources.eastmoney import EastmoneySource
        f178 = ('[{"date":"2026-08-13","mainNetAmt":358946672.0},'
                '{"date":"2026-08-12","mainNetAmt":46577744.0},'
                '{"date":"2026-08-11","mainNetAmt":85494864.0},'
                '{"date":"2026-08-10","mainNetAmt":664611600.0},'
                '{"date":"2026-08-07","mainNetAmt":-116062624.0}]')
        src = self._src([FakeResponse(json_data={"data": {"f178": f178}})])
        out = src.get_5d_fund_flow("sh600519")
        self.assertEqual(len(out), 5)
        self.assertEqual(out[0]["date"], "2026-08-13")
        self.assertEqual(out[0]["main"], 358946672.0)
        self.assertEqual(out[4]["main"], -116062624.0)

    def test_5d_fund_flow_empty_nodes(self):
        """f178 空 / 节点失败 → 返回空（不抛错，前端隐藏）。"""
        from sources.eastmoney import EastmoneySource
        src = self._src([FakeResponse(json_data={"data": {"f178": ""}})])
        self.assertEqual(src.get_5d_fund_flow("sh600519"), [])

    def test_all_nodes_fail_raises(self):
        from sources.eastmoney import _get_with_fallback
        with patch("sources.eastmoney.http_get",
                   side_effect=RuntimeError("network down")):
            with self.assertRaises(RuntimeError) as ctx:
                _get_with_fallback("/api/x", {})
        self.assertIn("多节点全失败", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

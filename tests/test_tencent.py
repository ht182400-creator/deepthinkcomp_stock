# -*- coding: utf-8 -*-
"""腾讯源单元测试：报价/分时解析（mock http_get，无网络）。"""
import unittest
from unittest.mock import patch

from tests.helpers import FakeResponse


# 腾讯快照：v_sh600519="1~贵州茅台~600519~1355.29~1342.90~1355.00~...~f[37]=金额"
def _quote_text():
    f = ["1", "贵州茅台", "600519", "1355.29", "1342.90", "1355.00", "12345678",
         "17836", "14517", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
         "0", "0", "0", "0", "0", "0", "0", "0", "0", "0",
         "0", "20260813161452", "12.39", "0.92", "1359.60", "1337.00",
         "1355.29/12345678/9876543210", "12345678", "9876543210.00", "0.26", "20.48",
         "0", "1359.60", "1337.00", "1.68", "16942.23", "16942.23",
         "7.28", "1477.30", "1208.70", "0.92", "32", "1352.62", "15.55", "20.58",
         "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"]
    return f'v_sh600519="{chr(126).join(f)}";'


class TestTencent(unittest.TestCase):

    def _src(self, fake_response):
        from sources.tencent import TencentSource
        src = TencentSource()
        patcher = patch("sources.tencent.http_get", return_value=fake_response)
        patcher.start()
        self.addCleanup(patcher.stop)
        return src

    def test_quote_parse(self):
        src = self._src(FakeResponse(text=_quote_text()))
        q = src.get_quote("sh600519")
        self.assertEqual(q["code"], "600519")
        self.assertEqual(q["name"], "贵州茅台")
        self.assertEqual(q["price"], 1355.29)
        self.assertEqual(q["pre_close"], 1342.90)
        self.assertEqual(round(q["change"], 2), 12.39)
        self.assertAlmostEqual(q["change_pct"], 12.39 / 1342.90 * 100, places=2)
        self.assertEqual(q["amount"], 9876543210.00)

    def test_quote_empty_body_raises(self):
        src = self._src(FakeResponse(text=""))
        with self.assertRaises(RuntimeError):
            src.get_quote("sh600519")

    def test_quote_too_few_fields_raises(self):
        src = self._src(FakeResponse(text='v_sh600519="1~a~600519";'))
        with self.assertRaises(RuntimeError):
            src.get_quote("sh600519")

    def test_minute_parse(self):
        # 腾讯 ifzq 返回的是累计成交量（手）/累计成交额（元）；后端差分为每分钟成交量（手）并计算均价
        body = {
            "code": 0,
            "data": {"sh600519": {"data": {"data": [
                "0930 1342.00 1 134200.00",   # 1手=100股，金额=1342*100=134200
                "0931 1343.50 3 403050.00",   # 3手，金额=1343.5*300=403050
            ]}}},
        }
        src = self._src(FakeResponse(json_data=body))
        m = src.get_minute("sh600519")
        self.assertEqual(len(m), 2)
        self.assertEqual(m[0]["t"], "0930")
        self.assertEqual(m[0]["price"], 1342.00)
        self.assertEqual(m[0]["vol"], 1)            # 每分钟成交量（手）
        self.assertEqual(m[0]["amount"], 134200.00) # 每分钟成交额（元）
        self.assertEqual(m[0]["avg"], 1342.00)     # 累计额 / (累计手数 * 100)
        self.assertEqual(m[1]["t"], "0931")
        self.assertEqual(m[1]["vol"], 2)            # 3 - 1（手）
        self.assertEqual(m[1]["amount"], 268850.00) # 403050 - 134200
        self.assertEqual(m[1]["avg"], 1343.50)      # 403050 / (3 * 100)

    def test_minute_empty_raises(self):
        src = self._src(FakeResponse(json_data={"code": 0, "data": {"sh600519": {}}}))
        with self.assertRaises(RuntimeError):
            src.get_minute("sh600519")

    def test_minute_truncate_after_close(self):
        """收盘后：腾讯 ifzq 持续返回最后一帧（价格定格、vol/amt 微量累加），应截断到价格最后变动位置。"""
        body = {
            "code": 0,
            "data": {"sh600519": {"data": {"data": [
                "1455 1342.00 1 134200",    # 价变
                "1456 1343.50 2 268700",    # 价变
                "1457 1344.00 3 403200",    # 价变
                "1500 1344.00 4 537600",    # 价不变（最后1分钟收盘）
                "1506 1344.00 5 672000",    # 价不变 + vol 伪累加（应截断）
                "1530 1344.00 6 806400",    # 价不变 + vol 伪累加（应截断）
            ]}}},
        }
        src = self._src(FakeResponse(json_data=body))
        m = src.get_minute("sh600519")
        # 期望：截断到 1457（价格最后变动），保留 3 根
        self.assertEqual(len(m), 3)
        self.assertEqual(m[-1]["t"], "1457")
        self.assertEqual(m[-1]["price"], 1344.00)
        self.assertEqual(m[-1]["vol"], 1)          # 3 - 2（手）
        self.assertEqual(m[-1]["amount"], 134500.00) # 403200 - 268700

    def test_unsupported_methods_raise(self):
        from sources.tencent import TencentSource
        src = TencentSource()
        with self.assertRaises(NotImplementedError):
            src.get_kline("sh600519", "day", 10)
        with self.assertRaises(NotImplementedError):
            src.get_fund_flow("sh600519")


if __name__ == "__main__":
    unittest.main()
    def test_quote_contains_order_book_and_turnover(self):
        """验证 quote 含五档盘口 + 换手率 + 高低（市场级盘口数据）"""
        from unittest.mock import patch
        # mock http_get 返回真实格式的 f[0..40] 字符串
        fake = "1~贵州茅台~600519~1355.29~1343.00~1338.00~32353~17836~14517~"                "1355.29~8~1355.01~4~1355.00~29~1354.88~3~1354.85~1~"                "1355.30~2~1355.33~1~1355.49~1~1355.50~8~1355.52~1~"                "~20260813161452~12.29~0.92~1359.60~1337.00~1355.29/32353/4376205567~32353~437621~0.26~20.48"
        from tests.helpers import FakeResponse
        with patch("sources.tencent.http_get", return_value=FakeResponse(text=fake)):
            from sources.tencent import TencentSource
            q = TencentSource().get_quote("sh600519")
        self.assertEqual(q["name"], "贵州茅台")
        self.assertEqual(q["price"], 1355.29)
        self.assertEqual(q["high"], 1359.60)
        self.assertEqual(q["low"], 1337.0)
        self.assertEqual(q["turnover_pct"], 0.26)
        self.assertAlmostEqual(q["amplitude_pct"], 1.68, places=1)   # (1359.6-1337)/1343*100
        self.assertEqual(len(q["order_book"]["bids"]), 5)
        self.assertEqual(len(q["order_book"]["asks"]), 5)
        self.assertEqual(q["order_book"]["bids"][0]["price"], 1355.29)
        self.assertEqual(q["order_book"]["asks"][0]["price"], 1355.30)


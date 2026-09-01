# -*- coding: utf-8 -*-
"""T-P3 回归：B 方案段指数缺失/未成熟时回退父指数（上证）门控，不再无脑放行。
对应 P2 修复的缺陷：段指数(创业板2010/科创2019/北证2021)诞生前，B 曾退化为"永远满仓、无保护"。
"""
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "modules", "strategy"))

import regime_layer2_backtest as R  # noqa: E402


def _make_idx(dates, closes, ma56=None, ma200=None):
    """构造假段指数 dict，接口与 idx_ma_on/idx_close_on 一致。"""
    ma56 = ma56 if ma56 is not None else [None] * len(dates)
    ma200 = ma200 if ma200 is not None else [None] * len(dates)
    return dict(dates=dates, close=closes, ma56=ma56, ma200=ma200)


class TestRegimeBFallback(unittest.TestCase):
    """T-P3：B 方案段指数缺失/未成熟 → 回退上证。"""

    def _mk(self, indices):
        return R.make_regime_fn("B", indices)

    def setUp(self):
        # 上证: dates 1..5, close 升序, ma56 全部有值(成熟)
        self.idx0 = _make_idx([1, 2, 3, 4, 5], [10, 11, 12, 13, 14],
                              ma56=[9, 10, 11, 12, 13])
        # 创业板: 存在但 ma56 未成熟(前 2 根 None) —— 模拟 2010 年新指数诞生初期
        self.gem_immature = _make_idx([1, 2, 3, 4, 5], [20, 21, 22, 23, 24],
                                      ma56=[None, None, 20, 21, 22])
        # 创业板: 成熟
        self.gem_mature = _make_idx([1, 2, 3, 4, 5], [20, 21, 22, 23, 24],
                                    ma56=[19, 20, 21, 22, 23])

    def test_seg_missing_falls_back_to_shanghai(self):
        """段指数缺失(indices 无该 key) → 回退上证门控，不 return True。"""
        fn = self._mk({"sh000001": self.idx0})   # 没有 sz399006
        # code=300xxx → seg_index_for → 'sz399006' → indices 无 → 回退上证
        # 上证 close[3]=12 >= ma56[3]=11 → True
        self.assertTrue(fn("300001", 3))
        # 上证 close[1]=11 >= ma56[1]=10 → True
        self.assertTrue(fn("300001", 1))
        # 用上证全跌的 idx 验证非"永远 True"：close < ma → False
        idx_down = _make_idx([1, 2, 3], [10, 9, 8], ma56=[11, 12, 13])
        fn2 = self._mk({"sh000001": idx_down})
        self.assertFalse(fn2("300001", 2), "回退后必须真实按上证判断，不能无脑放行")

    def test_seg_immature_falls_back_to_shanghai(self):
        """段指数存在但 MA56 未攒够(新指数诞生初期) → 回退上证。"""
        fn = self._mk({"sh000001": self.idx0, "sz399006": self.gem_immature})
        # 300xxx 段指数是 gem_immature；d=1 时其 ma56=None → 回退上证
        # 上证 close[1]=11 >= ma56[1]=10 → True
        self.assertTrue(fn("300001", 1))
        # 用上证下跌 idx 验证回退后不是无脑 True
        idx_down = _make_idx([1, 2, 3], [10, 9, 8], ma56=[11, 12, 13])
        fn2 = self._mk({"sh000001": idx_down, "sz399006": self.gem_immature})
        self.assertFalse(fn2("300001", 2), "未成熟段指数必须回退上证判断")

    def test_seg_mature_uses_own_index(self):
        """段指数成熟 → 直接用段指数门控（不回退）。"""
        fn = self._mk({"sh000001": self.idx0, "sz399006": self.gem_mature})
        # 段指数 gem_mature: close[3]=23 >= ma56[3]=22 → True
        self.assertTrue(fn("300001", 3))
        # 段指数下跌时即使上证上涨也按段指数判 False（不回退）
        gem_down = _make_idx([1, 2, 3], [20, 19, 18], ma56=[21, 22, 23])
        fn2 = self._mk({"sh000001": self.idx0, "sz399006": gem_down})
        self.assertFalse(fn2("300001", 2), "成熟段指数必须用自己的值，不得被上证干扰")

    def test_688_maps_kc50(self):
        """688 代码 → 科创50(sh000688)；缺失时回退上证。"""
        fn = self._mk({"sh000001": self.idx0})
        self.assertEqual(R.seg_index_for("688300"), "sh000688")
        self.assertTrue(fn("688300", 2), "sh000688 缺失 → 回退上证(close>=ma) → True")

    def test_bj_maps_bse50(self):
        """北交所代码 → bj899050；缺失时回退上证。"""
        self.assertEqual(R.seg_index_for("920002"), "bj899050")
        self.assertEqual(R.seg_index_for("430047"), "bj899050")
        self.assertEqual(R.seg_index_for("830799"), "bj899050")

    def test_current_and_c_schemes(self):
        """对照方案：current 用上证；C 恒 True。"""
        fn_cur = R.make_regime_fn("current", {"sh000001": self.idx0})
        self.assertTrue(fn_cur("000001", 3))
        idx_down = _make_idx([1, 2, 3], [10, 9, 8], ma56=[11, 12, 13])
        fn_cur2 = R.make_regime_fn("current", {"sh000001": idx_down})
        self.assertFalse(fn_cur2("000001", 2), "current 下跌必须 False")
        fn_c = R.make_regime_fn("C", {})
        self.assertTrue(fn_c("600000", 999))


if __name__ == "__main__":
    unittest.main()

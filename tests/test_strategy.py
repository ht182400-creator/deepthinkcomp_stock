# -*- coding: utf-8 -*-
"""P2 策略/持仓/分析模块单元测试（mock current_candidates，离线可跑）。"""
import os
import sys
import unittest
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from modules.holdings import holdings as H  # noqa: E402
from modules.analysis import analysis as A  # noqa: E402


def _fake_res(selected_codes=None, buy_codes=None, obs_codes=None, per_pos=None):
    selected_codes = selected_codes or ["688625"]
    buy_codes = buy_codes or ["688625", "002484", "688127", "300684"]
    obs_codes = obs_codes or []
    def _mk(code, score=0.7, price=50.0, mom=0.5, roe=0.2, sind="化学制品", lots=100, cap=5000):
        return dict(code=code, name=f"股{code}", price=price, score=score,
                    mom=mom, roe=roe, sind=sind, seg="sh000001",
                    lots=lots, capital=cap, selected=code in selected_codes)
    return dict(
        signal_date=20260814, scheme="B", regime_up=True, n_stocks=1687,
        buy=[_mk(c) for c in buy_codes],
        selected=[_mk(c) for c in selected_codes],
        observation=[dict(code=c, name=f"观{c}", roe=0.15, price=20.0, fail="未站线")
                     for c in obs_codes],
        bj_observe=[], per_pos=(per_pos if per_pos is not None else 11250.0), expo_base=0.9,
    )


class TestHoldings(unittest.TestCase):

    def setUp(self):
        self._tmp = os.path.join(_ROOT, "data", "_test_holdings.json")
        H.HOLDINGS_FILE = self._tmp
        # 直接写空数组重置（避免 os.remove 被沙箱回收站机制劫持导致残留）
        H._save(self._tmp, [])

    def test_upsert_and_delete(self):
        H.upsert_holding("688625", 12000, True, "呈和科技", "化学制品")
        H.upsert_holding("002484", 15000, False, "江海股份", "元件")
        items = H.get_holdings()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["name"], "呈和科技")
        # 更新已有
        H.upsert_holding("688625", 9999, False, "呈和科技", "化学制品")
        items = H.get_holdings()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["amount"], 9999)
        # 删除
        H.delete_holdings(["688625"])
        self.assertEqual(len(H.get_holdings()), 1)

    def test_settings_defaults(self):
        s = H.get_settings()
        self.assertEqual(s["cash"], 50000)
        self.assertEqual(s["N"], 4)
        H.save_settings({"auto_track": True, "weekly": 8000})
        s = H.get_settings()
        self.assertTrue(s["auto_track"])
        self.assertEqual(s["weekly"], 8000)


class TestCards(unittest.TestCase):

    def test_build_cards_advice(self):
        holdings = [
            dict(code="688625", name="呈和科技", amount=12000, dingtou=True, date=""),
            dict(code="002484", name="江海股份", amount=15000, dingtou=False, date=""),
            dict(code="999999", name="退市股", amount=5000, dingtou=False, date=""),
        ]
        res = _fake_res()
        cards = H.build_cards(res, holdings)
        by_code = {c["code"]: c for c in cards}
        self.assertEqual(by_code["688625"]["advice"], "加仓")     # 在 selected
        self.assertEqual(by_code["002484"]["advice"], "持有")     # 在 buy 但不在 selected
        self.assertEqual(by_code["999999"]["advice"], "清仓")     # 均不在

    def test_build_cards_obs_cut(self):
        holdings = [dict(code="300111", name="观察股", amount=5000, dingtou=False, date="")]
        res = _fake_res(buy_codes=[], selected_codes=[], obs_codes=["300111"])
        cards = H.build_cards(res, holdings)
        self.assertEqual(cards[0]["advice"], "持有")  # 未站线 → 持有观察

    def test_recommend_split(self):
        holdings = [dict(code="688625", name="呈和科技", amount=12000, dingtou=True, date="")]
        res = _fake_res(selected_codes=["688625", "002484", "688127", "300684"],
                        buy_codes=["688625", "002484", "688127", "300684", "600000"])
        sel, more = H.build_recommends(res, holdings, 50000, 4)
        # ⭐精选 = selected 4 只（含持仓 688625 标记 held）
        self.assertEqual(len(sel), 4)
        self.assertTrue(sel[0]["held"])  # 688625 是持仓
        self.assertTrue(sel[0]["is_top"])
        # 📋更多 = buy 池除 selected 外的（600000）
        self.assertEqual(len(more), 1)
        self.assertEqual(more[0]["code"], "600000")
        self.assertFalse(more[0]["is_top"])


class TestAnalysis(unittest.TestCase):

    def test_log_line(self):
        line = A.log_line("test line")
        self.assertIn("test line", line)
        with open(A.LOG_FILE, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("test line", content)

    def test_submit_runs(self):
        # mock current_candidates 避免真实构建宇宙
        with patch.object(A.R, "current_candidates", return_value=_fake_res()):
            A.ANALYSIS["last_result"] = None
            ok = A.submit()
            self.assertTrue(ok)
            # 等线程跑完
            import time
            for _ in range(20):
                if not A.ANALYSIS["running"]:
                    break
                time.sleep(0.2)
            self.assertFalse(A.ANALYSIS["running"])
            self.assertIsNotNone(A.ANALYSIS["last_result"])
            self.assertEqual(A.ANALYSIS["last_result"]["signal_date"], 20260814)

    def test_submit_rejects_concurrent(self):
        A.ANALYSIS["running"] = True
        try:
            self.assertFalse(A.submit())
        finally:
            A.ANALYSIS["running"] = False


class TestRecommendRules(unittest.TestCase):
    """T-P1/T-P4/T-P5：精选⊆买池、精选资金可行、更多候选超预算标注。"""

    def test_selected_subset_of_buy(self):
        """T-P1：selected 必须是 buy 池的子集（精选⊆买池）。"""
        holdings = []
        res = _fake_res(selected_codes=["688625", "002484"], buy_codes=["688625", "002484", "688127"])
        sel, more = H.build_recommends(res, holdings, 50000, 4)
        sel_codes = {s["code"] for s in sel}
        buy_codes = {r["code"] for r in res["buy"]}
        self.assertTrue(sel_codes.issubset(buy_codes), "精选必须⊆买池")

    def test_selected_feasible_budget(self):
        """T-P4：精选的资金可行性——一手价 ≤ 单仓预算（per_pos）。"""
        res = _fake_res(per_pos=11250.0)
        holdings = []
        sel, _ = H.build_recommends(res, holdings, 50000, 4)
        for s in sel:
            self.assertLessEqual(s["one_hand"], 11250.0 + 1e-6,
                                 f"{s['code']} 一手 {s['one_hand']} 元应 ≤ 单仓预算")
            self.assertLessEqual(s["fea_ratio"], 100.0 + 1e-6)

    def test_more_candidates_over_budget_marked(self):
        """T-P5：更多候选超预算 → fea_ratio>100 且 desc 标注'超预算'。"""
        # 高价票 300394 一手 26700 > per_pos 11250
        res = _fake_res(selected_codes=["688625"],
                        buy_codes=["688625", "300394"])
        res["buy"][1]["price"] = 267.0
        holdings = []
        sel, more = H.build_recommends(res, holdings, 50000, 4)
        over = [m for m in more if m["fea_ratio"] > 100]
        self.assertEqual([m["code"] for m in over], ["300394"])
        self.assertIn("超预算", over[0]["desc"])

    def test_persist_dashboard_after_analyze(self):
        """P2 bug 回归：analyze 完成后必须落盘 txt（live_buy_list_<signal>.txt）。"""
        with patch.object(A.R, "current_candidates", return_value=_fake_res()), \
             patch.object(A.R, "format_live_report", return_value="header\nbody"), \
             patch.object(A, "_persist_dashboard") as pd:
            A.ANALYSIS["last_result"] = None
            A.submit()
            import time
            for _ in range(20):
                if not A.ANALYSIS["running"]:
                    break
                time.sleep(0.2)
            self.assertFalse(A.ANALYSIS["running"])
            pd.assert_called_once()
            # 校验落盘参数：res 带 signal_date
            args, _ = pd.call_args
            self.assertEqual(args[0]["signal_date"], 20260814)


if __name__ == "__main__":
    unittest.main()

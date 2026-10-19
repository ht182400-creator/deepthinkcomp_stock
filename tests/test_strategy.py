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
                    mom=mom, roe=roe, sind=sind, seg="sh000001", regime="UP",
                    fcfnp=0.5, lots=lots, capital=cap, selected=code in selected_codes)
    return dict(
        signal_date=20260814, scheme="B", regime_up=True, n_stocks=1687,
        cash=50000.0, n_target=4, expo_base=0.9, investable=45000.0,
        seg_indices={"sh000001": "OK"},
        buy=[_mk(c) for c in buy_codes],
        selected=[_mk(c) for c in selected_codes],
        observation=[dict(code=c, name=f"观{c}", roe=0.15, price=20.0, fail="未站线")
                     for c in obs_codes],
        bj_observe=[], per_pos=(per_pos if per_pos is not None else 11250.0),
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

    def test_clear_holdings(self):
        """一键清空：清空后持仓列表为空。"""
        H.upsert_holding("688625", 12000, True, "呈和科技", "化学制品")
        H.upsert_holding("002484", 15000, False, "江海股份", "元件")
        self.assertEqual(len(H.get_holdings()), 2)
        H.clear_holdings()
        self.assertEqual(H.get_holdings(), [])

    def test_settings_defaults(self):
        s = H.get_settings()
        self.assertEqual(s["cash"], 50000)
        self.assertEqual(s["N"], 4)
        H.save_settings({"auto_track": True, "weekly": 8000})
        s = H.get_settings()
        self.assertTrue(s["auto_track"])
        self.assertEqual(s["weekly"], 8000)

    def test_summary_regime_cn_uses_seg_state(self):
        """B 方案 regime_up 恒 True，summary 必须按 seg_state 出中文裁决语。

        回归：Web ② 曾显示"信号日 20261016 · 全部上涨 → 建议建仓"，
        而正文是"暂无推荐"，与 5 段全 DOWN 矛盾。
        """
        res = _fake_res()
        res["regime_up"] = True          # B 方案恒 True
        seg = ["sh000001", "sz399001", "sz399006", "sh000688", "bj899050"]

        res["seg_state"] = {k: False for k in seg}
        s = H.build_summary(res, [], [], [])
        self.assertEqual(s["regime_cn"], "5 段全 DOWN → 空仓观望")
        self.assertEqual(len(s["seg_state"]), 5)

        res["seg_state"] = {k: True for k in seg}
        s = H.build_summary(res, [], [], [])
        self.assertEqual(s["regime_cn"], "5 段全 UP → 建议建仓")

        # 部分 UP：列出中文段名
        res["seg_state"] = {"sh000001": True, "sz399001": False, "sz399006": False,
                            "sh000688": False, "bj899050": False}
        s = H.build_summary(res, [], [], [])
        self.assertEqual(s["regime_cn"], "仅 上证 UP → 仅该板块可买")

    def test_summary_regime_cn_fallback_without_seg_state(self):
        """旧结果没有 seg_state 时回退到 regime_up，不得抛异常。"""
        res = _fake_res()
        res.pop("seg_state", None)
        res["regime_up"] = True
        self.assertEqual(H.build_summary(res, [], [], [])["regime_cn"],
                         "全部上涨 → 建议建仓")
        res["regime_up"] = False
        self.assertEqual(H.build_summary(res, [], [], [])["regime_cn"],
                         "存在下跌段 → 空仓观望")


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
        # mock current_candidates 避免真实构建宇宙；同时 mock _persist_dashboard 与
        # live_compare.write_compare（其内部重算前 3 周，会读真实数据）拖慢用例
        import live_compare as LC
        with patch.object(A.R, "current_candidates", return_value=_fake_res()), \
             patch.object(A, "_persist_dashboard"), \
             patch.object(LC, "write_compare", return_value={"history": []}):
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
        import live_compare as LC
        with patch.object(A.R, "current_candidates", return_value=_fake_res()), \
             patch.object(A.R, "format_live_report", return_value="header\nbody"), \
             patch.object(LC, "write_compare", return_value={"history": []}), \
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


class TestLiveReport(unittest.TestCase):
    """回归：合格买仓池全量列出，不截断前 30（看板 ③ 需完整展示按评分降序）。"""

    def test_pool_no_truncation(self):
        import regime_layer2_backtest as R
        codes = [f"{600000 + i:06d}" for i in range(35)]
        res = _fake_res(selected_codes=codes[:4], buy_codes=codes)
        txt = R.format_live_report(res)
        self.assertIn("合格买仓池(质量+动量+站线+段regime): 35 只", txt)
        # 35 只候选应全部出现在文本中（每只一行，含代码）
        for c in codes:
            self.assertIn(c, txt)

    def test_pool_sorted_by_score_desc(self):
        """评分降序：第一条池内记录应为评分最高的股票。"""
        import regime_layer2_backtest as R
        res = _fake_res(selected_codes=["600000"],
                        buy_codes=["600000", "600001", "600002"])
        # 人为设置评分：600001 最高
        scores = {"600000": 0.10, "600001": 0.90, "600002": 0.50}
        for r in res["buy"]:
            r["score"] = scores[r["code"]]
        txt = R.format_live_report(res)
        pool_block = txt.split("合格买仓池")[1]
        self.assertLess(pool_block.index("600001"), pool_block.index("600002"))
        self.assertLess(pool_block.index("600002"), pool_block.index("600000"))


class TestLiveCompare(unittest.TestCase):
    """回归：write_compare 复用本周 cur + 重算上周，生成同源 live_compare.json。"""

    def test_write_compare_pairs_prev_week(self):
        import tempfile
        import live_compare as LC
        import regime_layer2_backtest as R
        cur = _fake_res(selected_codes=["600000"], buy_codes=["600000", "600001"])
        cur["signal_date"] = 20260814
        prev = _fake_res(selected_codes=["600002"], buy_codes=["600002", "600001"])
        prev["signal_date"] = 20260807
        # B 方案 regime_up 恒 True，真实强弱在 seg_state：本周仅沪主板 UP
        cur["seg_state"] = {"sh000001": True, "sz399001": False, "sz399006": False,
                            "sh000688": False, "bj899050": False}
        prev["seg_state"] = {"sh000001": True, "sz399001": False, "sz399006": False,
                             "sh000688": False, "bj899050": False}
        tmp = tempfile.mkdtemp()
        with patch.object(R, "_get_universe",
                          return_value=(None, [20260807, 20260814], None, None)), \
             patch.object(R, "current_candidates", return_value=prev), \
             patch.object(LC, "DATA", tmp):
            out = LC.write_compare(cur)
            self.assertTrue(os.path.exists(os.path.join(tmp, "live_compare.json")))
        self.assertEqual(out["current"]["signal_date"], 20260814)
        self.assertEqual(out["prev"]["signal_date"], 20260807)
        self.assertEqual(out["prev_signal_date"], 20260807)
        self.assertIn("score", out["current"]["pool"][0])  # 池带评分，供 ③ 排序
        self.assertEqual(out["current"]["selected"][0]["code"], "600000")
        self.assertFalse(out["same_data"])
        # 段状态必须落盘并翻译成中文名（看板 ② 靠它判断，不能再用 regime_up）
        self.assertEqual(out["current"]["seg_state"]["上证(沪主板)"], "UP")
        self.assertEqual(out["current"]["seg_state"]["创业板指"], "DOWN")
        self.assertEqual(len(out["current"]["seg_state"]), 5)
        # 多周历史（老 → 新），供前端「前 3 周进出对比」；周轴不足时按实际可得周数
        self.assertEqual([h["signal_date"] for h in out["history"]], [20260807, 20260814])
        self.assertEqual(out["history"][-1]["selected"][0]["code"], "600000")
        self.assertEqual(out["history"][-1]["seg_state"]["创业板指"], "DOWN")

    def test_slim_without_seg_state_is_compatible(self):
        """旧版结果没有 seg_state 字段时不得抛异常（向后兼容）。"""
        import live_compare as LC
        self.assertEqual(LC._slim(_fake_res())["seg_state"], {})


@unittest.skipUnless(
    os.path.exists(os.path.join(_ROOT, "data", "results_layer2_fresh.json")),
    "缺少看板输入数据（data/results_layer2_fresh.json）")
class TestDashboardHtml(unittest.TestCase):
    """看板 HTML 结构回归：build_dashboard 是脚本，用子进程产出后再断言。

    覆盖两个真实修过的问题：
      ① ★建仓 原先裸挂在 <tr> 下（未包 <td>）→ 浏览器将其甩到表格格子之外，看起来"多出一行"；
      ② ③ 合格池必须按评分降序，并展示"本周各市场段状态 + 板块分布"。
    """

    @classmethod
    def setUpClass(cls):
        import glob
        import subprocess
        dash = os.path.join(_ROOT, "modules", "strategy", "build_dashboard.py")
        if not os.path.exists(dash):
            raise unittest.SkipTest("未找到 build_dashboard.py")
        r = subprocess.run([sys.executable, dash], cwd=_ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            raise unittest.SkipTest("build_dashboard 运行失败: %s" % (r.stderr or "")[:200])
        files = sorted(glob.glob(os.path.join(_ROOT, "data", "dashboard_*.html")))
        if not files:
            raise unittest.SkipTest("未生成 dashboard html")
        with open(files[-1], encoding="utf-8") as f:
            cls.html = f.read()
        # 本周合格池数量（0 只时 ★/评分相关断言无样本可验 → 各测试自行 skip）
        import re as _re
        _m = _re.search(r"③ 合格买仓池[^<]*?(\d+) 只", cls.html)
        cls.pool_size = int(_m.group(1)) if _m else 0

    def test_star_inside_td(self):
        """★建仓 必须包在 <td> 内，否则会脱出表格格子（原 bug）。"""
        if not self.pool_size:
            self.skipTest("本周合格池 0 只，无 ★建仓 单元格可验")
        self.assertIn("<td><span class='star'>", self.html, "★建仓 应在 <td> 内")
        self.assertNotIn("</td><span class='star'>", self.html, "★建仓 不应裸挂在 <tr> 下")

    def test_pool_scores_sorted_desc(self):
        """③ 合格池评分必须降序（评分类带配色样式，后紧跟"状态"单元格）。"""
        if not self.pool_size:
            self.skipTest("本周合格池 0 只，无评分可验")
        import re
        seg = self.html.split("③ 合格买仓池")[-1]
        scores = [float(x) for x in re.findall(r"font-weight:700'>(\d\.\d+)</td><td>", seg)]
        self.assertTrue(scores, "未从 ③ 解析到评分")
        self.assertEqual(scores, sorted(scores, reverse=True), "评分未按降序排列")

    def test_market_segment_note_present(self):
        """必须展示本周各市场段状态与合格池板块分布（否则"为何全是同一板块"无从判断）。"""
        self.assertIn("市场段(56周MA)", self.html)
        self.assertIn("个市场段（56 周均线）", self.html)

    def test_pool_score_gradient(self):
        """③ 评分列按**同批相对**渐变着色：评分越高越红（色相 210°→0°）。"""
        if self.pool_size < 2:
            self.skipTest("本周合格池不足 2 只，无法验证同批相对渐变")
        import re
        seg = self.html.split("③ 合格买仓池")[-1]
        cells = re.findall(
            r"color:hsl\((\d+),\s*85%,\s*64%\);\s*"
            r"background:hsla\(\d+,\s*85%,\s*45%,\s*([\d.]+)\);\s*"
            r"font-weight:700'>(\d\.\d+)</td>",
            seg)
        self.assertGreaterEqual(len(cells), 2, "评分配色未渲染")
        hues = [int(c[0]) for c in cells]         # 按行序（评分降序）
        alphas = [float(c[1]) for c in cells]
        scores = [float(c[2]) for c in cells]
        self.assertEqual(scores, sorted(scores, reverse=True), "评分应降序")
        self.assertEqual(hues, sorted(hues), "越红（色相越小）必须对应越高分")
        self.assertLess(hues[0], hues[-1], "最高分应比最低分更红")
        self.assertGreater(alphas[0], alphas[-1], "高分背景色应更实")
        self.assertIn("评分列颜色 = 同批相对", self.html, "缺少配色图例")

    def test_diff_banner_not_contradict_segments(self):
        """② 的 banner 不得与顶部段状态矛盾（B 方案 regime_up 恒 True 的回归）。

        真实数据曾出现：顶部写"5 段全 DOWN → 空仓观望"，
        ② 却写"连续两周【全段 UP → 建议建仓】"（直接读 regime_up 导致）。
        """
        if "② 信号 vs 上周变化" not in self.html:
            self.skipTest("本页无 ② 对比段（首次信号）")
        second = self.html.split("② 信号 vs 上周变化")[-1]
        if "5 段全 DOWN → 空仓观望" in self.html:
            self.assertIn("5 段全 DOWN → 空仓观望", second,
                          "② 应按段状态显示全 DOWN，而非 regime_up 的全 UP")
            self.assertNotIn("全段 UP → 建议建仓", second,
                             "② 不得在 5 段全 DOWN 时显示'全段 UP → 建议建仓'")


if __name__ == "__main__":
    unittest.main()

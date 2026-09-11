# -*- coding: utf-8 -*-
"""panels 数据面板层单元测试（R1a / R1）。

覆盖范围：

- ``meta``：数据版本、**字段断言（缺列必须报错）**、元信息/字段映射读写、可复现性检查
- ``universe``：报告期列举、代码→市场映射、板块判定、可交易性过滤、宇宙构建
- ``financial``：公告日归一化、披露截止日、逾期判定、字段抽取、空期处理、**每股回溯(H4)**
- ``price``：周线聚合与 base_date 冻结（R1a；面板未构建时自动 skip）

依赖 ``data/panel`` 下已构建的面板文件；未构建时相关用例自动跳过而非失败。
"""
import os
import sys
import unittest

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config                                              # noqa: E402
from panels import meta as pm                              # noqa: E402
from panels import universe as uni                         # noqa: E402
from panels import financial as fin                        # noqa: E402
from panels import fund_local as fl                        # noqa: E402
from panels import volume_price as vp                      # noqa: E402

_PANEL_READY = os.path.exists(config.FUND_PANEL_FILE)
_LATEST_READY = os.path.exists(config.FUND_LATEST_FILE)


# =====================================================================
# meta
# =====================================================================
class TestMeta(unittest.TestCase):
    """元信息与版本管理（H1/H3/H13）。"""

    def test_tdx_data_version_returns_int_or_none(self):
        """数据版本应为 int（可用）或 None（数据缺失），不得抛异常。"""
        ver = pm.tdx_data_version()
        self.assertTrue(ver is None or isinstance(ver, int))
        if ver is not None:
            self.assertGreater(ver, 19900101)

    def test_assert_fields_pass(self):
        """列名齐全时应通过。"""
        cols = list(config.FUND_FIELDS.values())
        self.assertTrue(pm.assert_fields(cols))

    def test_assert_fields_missing_raises(self):
        """缺列必须抛 KeyError（禁止静默降级 —— H13 核心）。"""
        cols = list(config.FUND_FIELDS.values())[:-3]      # 故意少 3 列
        with self.assertRaises(KeyError):
            pm.assert_fields(cols)

    def test_assert_fields_empty_columns(self):
        """空列集合属于边界场景，必须报错而非通过。"""
        with self.assertRaises(KeyError):
            pm.assert_fields([])

    def test_file_fingerprint(self):
        """指纹：存在的文件返回字符串；不存在的文件返回 None。"""
        self.assertIsNone(pm.file_fingerprint(os.path.join(_ROOT, "_not_exist_.day")))
        fp = pm.file_fingerprint(os.path.join(_ROOT, "config.py"))
        self.assertIsNotNone(fp)
        self.assertIn(":", fp)

    def test_field_map_roundtrip(self):
        """字段映射落盘后可读回，且字段数一致。"""
        tmp = os.path.join(_ROOT, "data", "panel", "_test_field_map.json")
        pm.save_field_map(version="test", path=tmp)
        fields, ver = pm.load_field_map(path=tmp)
        self.assertEqual(ver, "test")
        self.assertEqual(len(fields), len(config.FUND_FIELDS))
        os.remove(tmp)

    def test_field_map_fallback_when_missing(self):
        """映射文件缺失时回退 config，版本标记为 config。"""
        fields, ver = pm.load_field_map(path=os.path.join(_ROOT, "data", "_no_such_.json"))
        self.assertEqual(ver, "config")
        self.assertEqual(len(fields), len(config.FUND_FIELDS))

    def test_meta_roundtrip_and_reproducibility(self):
        """元信息读写 + 可复现性检查（版本一致 → ok）。"""
        tmp = os.path.join(_ROOT, "data", "panel", "_test_meta.json")
        meta = pm.build_meta(base_date=20260630, field_map_version="test", periods=["20260630"])
        pm.save_meta(meta, path=tmp)
        loaded = pm.load_meta(path=tmp)
        self.assertEqual(loaded["base_date"], 20260630)
        self.assertEqual(loaded["meta_version"], pm.PANEL_META_VERSION)
        rep = pm.check_panel_reproducible(loaded)
        self.assertIn("ok", rep)
        os.remove(tmp)

    def test_check_panel_reproducible_missing(self):
        """meta 缺失时必须报告"未构建"，而不是误判为一致。"""
        rep = pm.check_panel_reproducible({})
        self.assertFalse(rep["ok"])


# =====================================================================
# universe
# =====================================================================
class TestUniverse(unittest.TestCase):
    """宇宙构建（H2）。"""

    def test_pure_to_full_all_markets(self):
        """沪/深/北 三市场映射正确（含边界代码段）。"""
        cases = {
            "600519": "sh600519", "688625": "sh688625", "900901": "sh900901",
            "000858": "sz000858", "300750": "sz300750", "301159": "sz301159",
            "920185": "bj920185", "830799": "bj830799", "430047": "bj430047",
        }
        for pure, expect in cases.items():
            self.assertEqual(uni.pure_to_full(pure), expect, "%s 映射错误" % pure)

    def test_pure_to_full_invalid(self):
        """非 6 位数字原样返回（边界）。"""
        self.assertEqual(uni.pure_to_full("abc"), "abc")
        self.assertEqual(uni.pure_to_full(""), "")

    def test_board_of(self):
        """板块判定：科创板/创业板/北交所/主板。"""
        self.assertEqual(uni.board_of("sh688625"), "科创板")
        self.assertEqual(uni.board_of("sz300750"), "创业板")
        self.assertEqual(uni.board_of("sz301159"), "创业板")
        self.assertEqual(uni.board_of("bj920185"), "北交所")
        self.assertEqual(uni.board_of("sh600519"), "主板")

    def test_is_tradable_stock(self):
        """北交所指数段（81/82/89）应被排除；正常个股通过。"""
        self.assertTrue(uni.is_tradable_stock("600519"))
        self.assertTrue(uni.is_tradable_stock("920185"))
        self.assertFalse(uni.is_tradable_stock("810011"))
        self.assertFalse(uni.is_tradable_stock("899050"))
        self.assertFalse(uni.is_tradable_stock("abc"))

    def test_list_gpcw_periods(self):
        """报告期列举：升序、可被 min_period 过滤。"""
        periods = uni.list_gpcw_periods()
        if not periods:
            self.skipTest("无 gpcw 数据")
        self.assertEqual(periods, sorted(periods))
        filtered = uni.list_gpcw_periods(min_period="20200101")
        self.assertTrue(all(p >= "20200101" for p in filtered))
        self.assertLessEqual(len(filtered), len(periods))

    def test_list_gpcw_periods_bad_dir(self):
        """目录不存在时返回空列表而非抛异常（异常场景）。"""
        self.assertEqual(uni.list_gpcw_periods(gpcw_dir=os.path.join(_ROOT, "_no_dir_")), [])


# =====================================================================
# financial（纯函数部分，不依赖面板文件）
# =====================================================================
class TestFinancialPure(unittest.TestCase):
    """财务面板的纯函数逻辑。"""

    def test_normalize_notice_date(self):
        """YYMMDD → YYYYMMDD 归一化（含跨世纪边界与空值）。"""
        s = pd.Series([260815, 190101, 200401, 0, None, float("nan")])
        out = fin.normalize_notice_date(s)
        self.assertEqual(int(out.iloc[0]), 20260815)      # 20xx
        self.assertEqual(int(out.iloc[1]), 20190101)
        self.assertTrue(pd.isna(out.iloc[3]))             # 0 → NA（边界）
        self.assertTrue(pd.isna(out.iloc[4]))
        self.assertTrue(pd.isna(out.iloc[5]))

    def test_normalize_notice_date_empty(self):
        """全空序列不得抛异常。"""
        out = fin.normalize_notice_date(pd.Series([None, None]))
        self.assertEqual(int(out.notna().sum()), 0)

    def test_period_deadline(self):
        """披露截止日：一季报/年报 4-30，半年报 8-31，三季报 10-31；年报跨年。"""
        self.assertEqual(fin.period_deadline("20260331"), 20260430)
        self.assertEqual(fin.period_deadline("20260630"), 20260831)
        self.assertEqual(fin.period_deadline("20260930"), 20261031)
        self.assertEqual(fin.period_deadline("20251231"), 20260430)   # 次年
        self.assertIsNone(fin.period_deadline("20260101"))            # 非法后缀（边界）

    def test_is_period_overdue(self):
        """逾期判定：已过截止日→True；未到→False（H4 核心，避免误报滞后）。"""
        today = 20260910
        self.assertTrue(fin.is_period_overdue("20260630", today=today))    # 8/31 已过
        self.assertFalse(fin.is_period_overdue("20260930", today=today))   # 10/31 未到
        self.assertFalse(fin.is_period_overdue("20261231", today=today))   # 次年 4/30 未到
        self.assertFalse(fin.is_period_overdue("20260101", today=today))   # 非法后缀

    def test_read_period_missing_and_empty(self):
        """文件不存在 / 空文件均返回 None，不抛异常（异常场景）。"""
        self.assertIsNone(fin.read_period("19000101"))
        self.assertIsNone(fin.read_period("29991231"))


# =====================================================================
# financial（面板依赖部分）
# =====================================================================
@unittest.skipUnless(_PANEL_READY, "财务面板未构建（先运行 python -m panels.financial）")
class TestFinancialPanel(unittest.TestCase):
    """已构建面板的校验（H2/H4）。"""

    @classmethod
    def setUpClass(cls):
        cls.panel = pd.read_parquet(config.FUND_PANEL_FILE)

    def test_panel_shape_and_universe(self):
        """面板规模：股票数应显著超过旧宇宙 1771 只（H2 修复的证据）。"""
        self.assertGreater(len(self.panel), 10000)
        self.assertGreater(self.panel["code"].nunique(), 4000)
        self.assertGreaterEqual(self.panel["period"].nunique(), 40)

    def test_all_fields_present(self):
        """面板必须包含全部映射字段（否则抽取环节有静默丢失）。"""
        for key in config.FUND_FIELDS:
            self.assertIn(key, self.panel.columns, "字段缺失: %s" % key)

    def test_key_field_fill_rate(self):
        """关键字段非空率应 ≥80%（低于此说明数据源或抽取有问题）。"""
        for key in ["ROE", "NP_PARENT", "OCF", "CAPEX", "TOTAL_SHARE", "NOTICE_DATE"]:
            rate = self.panel[key].notna().mean()
            self.assertGreaterEqual(rate, 0.80, "%s 非空率仅 %.1f%%" % (key, rate * 100))

    def test_maotai_baseline(self):
        """茅台基线（防止字段取错列）：20260630 半年报 ROE≈17.7、BVPS≈201、总股本=1250081664。"""
        last = self.panel[self.panel["code"] == "600519"].sort_values("period").iloc[-1]
        self.assertEqual(last["period"], "20260630")
        self.assertAlmostEqual(float(last["ROE"]), 17.718, delta=0.5)
        self.assertAlmostEqual(float(last["BVPS"]), 200.99, delta=1.0)
        self.assertEqual(int(last["TOTAL_SHARE"]), 1250081664)
        self.assertAlmostEqual(float(last["HOLDERS"]), 296404, delta=1000)
        self.assertEqual(int(last["notice_date"]), 20260815)

    def test_effective_base_period(self):
        """基准期必须是"已过披露截止日"的最大期（H4）。"""
        base = fin.effective_base_period(self.panel)
        self.assertIsNotNone(base)
        self.assertTrue(fin.is_period_overdue(base))


@unittest.skipUnless(_LATEST_READY, "最新快照未构建")
class TestFinancialLatest(unittest.TestCase):
    """最新快照与每股回溯（H4）。"""

    @classmethod
    def setUpClass(cls):
        cls.latest = pd.read_parquet(config.FUND_LATEST_FILE)

    def test_one_row_per_stock(self):
        """每只股票只能有一行（回溯逻辑不应产生重复）。"""
        self.assertEqual(len(self.latest), self.latest["code"].nunique())

    def test_period_backtracking(self):
        """每股取其最近有数据的报告期；允许各股期数不同（H4 核心）。"""
        self.assertTrue((self.latest["period"] <= "20261231").all())
        self.assertGreater(self.latest["period"].nunique(), 1)

    def test_stale_flag_consistency(self):
        """is_stale 必须与 stale_periods 阈值一致。"""
        expect = self.latest["stale_periods"] >= config.FUND_STALE_PERIODS
        self.assertTrue((self.latest["is_stale"] == expect).all())

    def test_full_code_and_board(self):
        """附带 full / board 列，且无空值。"""
        self.assertTrue(self.latest["full"].notna().all())
        self.assertTrue(self.latest["board"].notna().all())
        self.assertTrue(set(self.latest["board"]).issubset({"主板", "创业板", "科创板", "北交所"}))


@unittest.skipUnless(os.path.exists(config.PRICE_PANEL_FILE),
                     "价格面板未构建（先运行 python -m panels.price）")
class TestPricePanel(unittest.TestCase):
    """价格面板与复权基准冻结（R1a：H1 可复现 / R4 全字段）。"""

    @classmethod
    def setUpClass(cls):
        cls.meta = pm.load_meta() or {}
        # 只读 date 列求最大值，避免把 184MB 面板整表载入内存
        cls.dates = pd.read_parquet(config.PRICE_PANEL_FILE, columns=["date"])["date"]

    def test_panel_file_non_empty(self):
        """面板文件存在且非空。"""
        self.assertTrue(os.path.exists(config.PRICE_PANEL_FILE))
        self.assertGreater(os.path.getsize(config.PRICE_PANEL_FILE), 1024)

    def test_schema_includes_ohlcv_full_fields(self):
        """周线必须保留 OHLCV 全字段（R4：旧实现只留 close，导致量价因子无法计算）。"""
        import pyarrow.parquet as pq
        names = set(pq.read_schema(config.PRICE_PANEL_FILE).names)
        for col in config.PRICE_PANEL_FIELDS + ["code", "date", "year", "week"]:
            self.assertIn(col, names, "价格面板缺少列: %s" % col)

    def test_base_date_frozen_matches_panel(self):
        """meta.base_date 必须等于面板最新交易日（H1：复权基准被冻结）。"""
        self.assertEqual(int(self.meta.get("base_date")), int(self.dates.max()))

    def test_panel_scale(self):
        """面板规模：股票数与周数应达到全市场量级（H2 扩容后的证据）。"""
        codes = pd.read_parquet(config.PRICE_PANEL_FILE, columns=["code"])["code"]
        self.assertGreater(codes.nunique(), 8000)
        self.assertGreater(len(self.dates), 1_000_000)

    def test_maotai_ohlc_consistency(self):
        """茅台周线：根数与 OHLC 逻辑关系（异常场景：high<low / 负成交量）。"""
        df = pd.read_parquet(config.PRICE_PANEL_FILE, filters=[("code", "==", "sh600519")])
        self.assertGreater(len(df), 500)
        self.assertTrue((df["high"] >= df["low"]).all(), "high < low")
        self.assertTrue((df["high"] >= df["close"]).all(), "high < close")
        self.assertTrue((df["low"] <= df["close"]).all(), "low > close")
        self.assertTrue((df["volume"] >= 0).all(), "存在负成交量")

    def test_delisted_stock_present(self):
        """退市股行情应存在（为 R7 提供基础）：抽查乐视退 300104。"""
        df = pd.read_parquet(config.PRICE_PANEL_FILE, filters=[("code", "==", "sz300104")])
        self.assertGreater(len(df), 100, "退市股行情缺失，R7 将无法回测")


# =====================================================================
# fund_local：ROE 口径（报告期累计 → TTM）
# =====================================================================
class TestFundLocalRoeTtm(unittest.TestCase):
    """``_ttm_roe`` 纯函数 + 真实面板口径回归。

    背景：面板 ``ROE`` 是**报告期累计**（Q1≈全年 1/4、Q4=全年），季度序列呈规则锯齿；
    与 TTM 口径的营收/净利混画会误导（"营收在涨、ROE 周期波动"）。
    """

    def test_normal_average_equity(self):
        """标准场景：5 期，第 5 期用 (期末 + 去年同期)/2 平均净资产。"""
        # 第 5 期(i=4)：np_ttm=10000 万元=1e8 元，(2e8+1.8e8)/2=1.9e8 → 52.63%
        out = fl._ttm_roe([10000.0] * 5, [1.8e8, 1.8e8, 1.8e8, 1.8e8, 2.0e8])
        self.assertEqual(len(out), 5)
        self.assertAlmostEqual(out[4], 52.63, delta=0.01)

    def test_first_period_fallback_to_period_end(self):
        """窗口首期无同比数据 → 退化为期末净资产口径（非报错）。"""
        out = fl._ttm_roe([10000.0], [2.0e8])       # 1e8 / 2e8 = 50%
        self.assertAlmostEqual(out[0], 50.0, delta=0.01)

    def test_empty_input(self):
        """边界：空输入 → 空输出，不抛异常。"""
        self.assertEqual(fl._ttm_roe([], []), [])

    def test_none_and_nan_and_zero_equity(self):
        """异常：None / NaN / 非正净资产 → 该期返回 None（不画假点）。"""
        out = fl._ttm_roe([None, float("nan"), 10000.0, 10000.0], [1e8, 1e8, 0.0, -1e8])
        self.assertEqual(out, [None, None, None, None])

    def test_ragged_lengths(self):
        """异常：两序列不等长 → 越界侧返回 None，不抛 IndexError。"""
        out = fl._ttm_roe([10000.0, 10000.0, 10000.0], [2e8])
        self.assertEqual(len(out), 3)
        self.assertAlmostEqual(out[0], 50.0, delta=0.01)
        self.assertIsNone(out[1])
        self.assertIsNone(out[2])

    def test_non_numeric_string(self):
        """异常：非法值（字符串）→ None，不抛异常。"""
        self.assertEqual(fl._ttm_roe(["abc"], ["xyz"]), [None])


@unittest.skipUnless(_PANEL_READY, "财务面板未构建，跳过")
class TestFundLocalRoeTtmPanel(unittest.TestCase):
    """真实面板回归：688300 的 ROE(TTM) 必须平滑，且与报告期口径显著不同。"""

    @classmethod
    def setUpClass(cls):
        cls.card = fl.get_fund_card("sh688300", periods=12)
        if cls.card.get("error"):
            raise unittest.SkipTest("688300 无财务数据: %s" % cls.card.get("error"))

    def test_roe_ttm_series_present_and_aligned(self):
        """trend 必须含 roe_ttm，且与 periods 等长、无 NaN 缺口。"""
        tr = self.card["trend"]
        self.assertIn("roe_ttm", tr)
        self.assertEqual(len(tr["roe_ttm"]), len(tr["periods"]))
        self.assertTrue(all(v is not None for v in tr["roe_ttm"]))

    def test_roe_ttm_removes_sawtooth(self):
        """锯齿消除：报告期口径 Q1 会断崖（相对前一期跌幅 >40%），TTM 口径不会。"""
        tr = self.card["trend"]
        pers, roe, roe_ttm = tr["periods"], tr["roe"], tr["roe_ttm"]
        q1_idx = [i for i, p in enumerate(pers) if str(p).endswith("0331") and i > 0]
        self.assertTrue(q1_idx, "样本内无 Q1 报告期，无法验证锯齿")
        for i in q1_idx:
            period_drop = (roe[i - 1] - roe[i]) / abs(roe[i - 1])
            ttm_drop = (roe_ttm[i - 1] - roe_ttm[i]) / abs(roe_ttm[i - 1])
            self.assertGreater(period_drop, 0.4, "报告期口径在 Q1 未出现断崖（预期特征）")
            self.assertLess(abs(ttm_drop), 0.2, "TTM 口径不应出现 Q1 断崖")

    def test_roe_ttm_in_reasonable_range(self):
        """数值合理性：TTM ROE 应落在 0~100 之间（超出说明单位换算出错）。"""
        for v in self.card["trend"]["roe_ttm"]:
            self.assertGreater(v, 0.0)
            self.assertLess(v, 100.0)

    def test_latest_roe_ttm_matches_series_tail(self):
        """latest.roe_ttm 应与 trend.roe_ttm 末位一致（同一期）。"""
        self.assertEqual(self.card["latest"]["roe_ttm"], self.card["trend"]["roe_ttm"][-1])

    def test_diagnose_exposes_both_calibers(self):
        """诊断同时暴露 TTM 与报告期两种 ROE，且 TTM 用于打分（TTM > 报告期，半年报场景）。"""
        d = fl.diagnose("sh688300")
        self.assertNotIn("error", d)
        self.assertIsNotNone(d["detail"]["roe_ttm"])
        self.assertIsNotNone(d["detail"]["roe_period"])
        period = str(d["period"])
        if period.endswith("0630"):
            # 半年报：报告期值≈全年一半 → TTM 必然明显更大
            self.assertGreater(d["detail"]["roe_ttm"], d["detail"]["roe_period"])


# =====================================================================
# volume_price：本地量价指标（永不失败，替代东财资金流）
# =====================================================================
class TestVolumePrice(unittest.TestCase):
    """``panels.volume_price.get_volume_price`` 纯函数 + 边界场景。"""

    def setUp(self):
        self._orig_cache = dict(vp._PANEL_CACHE)
        vp._PANEL_CACHE.clear()

    def tearDown(self):
        vp._PANEL_CACHE.clear()
        vp._PANEL_CACHE.update(self._orig_cache)

    def _make_df(self, code, rows):
        """rows: [(date, close, volume, amount), ...]"""
        df = pd.DataFrame(rows, columns=["date", "close", "volume", "amount"])
        df["code"] = code
        df["p6"] = vp._pure(code)
        return df[["code", "date", "close", "volume", "amount", "p6"]]

    def test_normal_returns_all_fields(self):
        """正常 8 周数据应返回完整字段与 latest。"""
        rows = [
            (20240101, 100, 1e8, 1e10), (20240108, 102, 1.5e8, 1.5e10),
            (20240115, 101, 8e7, 8e9), (20240122, 103, 1.6e8, 1.6e10),
            (20240129, 104, 1.7e8, 1.7e10), (20240205, 105, 1.8e8, 1.8e10),
            (20240212, 106, 1.9e8, 1.9e10), (20240219, 107, 2.0e8, 2.0e10),
        ]
        vp._PANEL_CACHE["df"] = self._make_df("sh688300", rows)
        out = vp.get_volume_price("688300", weeks=8)
        self.assertNotIn("error", out)
        self.assertEqual(out["code"], "688300")
        self.assertEqual(len(out["periods"]), 8)
        self.assertEqual(len(out["close"]), 8)
        self.assertEqual(len(out["volume_yi"]), 8)
        self.assertEqual(len(out["amount_yi"]), 8)
        self.assertEqual(len(out["chg_pct"]), 8)
        self.assertEqual(len(out["vol_ratio"]), 8)
        self.assertEqual(len(out["pattern"]), 8)
        self.assertIn("latest", out)
        self.assertIn("tip", out)
        self.assertIn("note", out)
        self.assertEqual(out["source"], "local_price_panel")

    def test_vol_ratio_first_none_and_value(self):
        """放量倍数：首期无窗口返回 None，第二期按前 5 期均值计算。"""
        rows = [(20240101, 100, 1e8, 1e10), (20240108, 102, 1.5e8, 1.5e10)]
        vp._PANEL_CACHE["df"] = self._make_df("sh600519", rows)
        out = vp.get_volume_price("600519", weeks=2)
        self.assertIsNone(out["vol_ratio"][0])
        self.assertAlmostEqual(out["vol_ratio"][1], 1.5, places=2)

    def test_pattern_mapping(self):
        """量价配合 2×2 映射：齐升 / 缩量上涨 / 放量下跌 / 缩量下跌。"""
        rows = [
            (20240101, 100, 1e8, 1e10),   # 基准，pattern="--"
            (20240108, 102, 1.5e8, 1.5e10),  # 涨 + 放量 -> 量价齐升
            (20240115, 103, 8e7, 8e9),       # 涨 + 缩量 -> 缩量上涨
            (20240122, 101, 1.6e8, 1.6e10),  # 跌 + 放量 -> 放量下跌
            (20240129, 100, 7e7, 7e9),       # 跌 + 缩量 -> 缩量下跌
            (20240205, 102, 1.2e8, 1.2e10),  # 涨 + 放量 -> 量价齐升
        ]
        vp._PANEL_CACHE["df"] = self._make_df("sh600519", rows)
        out = vp.get_volume_price("600519", weeks=6)
        self.assertEqual(out["pattern"][1], "量价齐升")
        self.assertEqual(out["pattern"][2], "缩量上涨")
        self.assertEqual(out["pattern"][3], "放量下跌")
        self.assertEqual(out["pattern"][4], "缩量下跌")
        self.assertEqual(out["pattern"][5], "量价齐升")

    def test_vol_trend_and_divergence(self):
        """近 4 周量能较之前萎缩 >15%，且价格上涨，触发量价背离。"""
        rows = [
            (20240101, 100, 2e8, 2e10), (20240108, 101, 2e8, 2e10),
            (20240115, 102, 2e8, 2e10), (20240122, 103, 2e8, 2e10),
            (20240129, 104, 1e8, 1e10), (20240205, 105, 1e8, 1e10),
            (20240212, 106, 1e8, 1e10), (20240219, 107, 1e8, 1e10),
        ]
        vp._PANEL_CACHE["df"] = self._make_df("sh688300", rows)
        out = vp.get_volume_price("688300", weeks=8)
        self.assertAlmostEqual(out["latest"]["vol_trend_pct"], -50.0, delta=0.1)
        self.assertTrue(out["latest"]["divergence"])
        self.assertIn("上涨缺乏承接", out["tip"])

    def test_divergence_false_when_price_down(self):
        """价格下跌时，即使量能萎缩也不判定为上涨背离。"""
        rows = [
            (20240101, 108, 2e8, 2e10), (20240108, 107, 2e8, 2e10),
            (20240115, 106, 2e8, 2e10), (20240122, 105, 2e8, 2e10),
            (20240129, 104, 1e8, 1e10), (20240205, 103, 1e8, 1e10),
            (20240212, 102, 1e8, 1e10), (20240219, 101, 1e8, 1e10),
        ]
        vp._PANEL_CACHE["df"] = self._make_df("sh688300", rows)
        out = vp.get_volume_price("688300", weeks=8)
        self.assertFalse(out["latest"]["divergence"])

    def test_empty_panel_returns_no_data_error(self):
        """空面板应返回'无量价数据'，不抛异常。"""
        vp._PANEL_CACHE["df"] = pd.DataFrame(
            columns=["code", "date", "close", "volume", "amount", "p6"]
        )
        out = vp.get_volume_price("688300", weeks=8)
        self.assertIn("error", out)
        self.assertEqual(out["error"], "无量价数据")

    def test_code_not_found_returns_no_data_error(self):
        """代码不在面板中应返回'无量价数据'。"""
        vp._PANEL_CACHE["df"] = self._make_df("sh600519", [(20240101, 100, 1e8, 1e10)])
        out = vp.get_volume_price("688300", weeks=8)
        self.assertIn("error", out)
        self.assertEqual(out["error"], "无量价数据")

    def test_panel_unavailable_returns_error(self):
        """面板文件缺失/不可用时返回友好错误。"""
        vp._PANEL_CACHE["df"] = None
        out = vp.get_volume_price("688300", weeks=8)
        self.assertIn("error", out)
        self.assertIn("价格面板不可用", out["error"])

    def test_weeks_param_limits_periods(self):
        """weeks 参数应正确截取最近 N 周。"""
        rows = [
            (20240101, 100, 1e8, 1e10), (20240108, 101, 1e8, 1e10),
            (20240115, 102, 1e8, 1e10), (20240122, 103, 1e8, 1e10),
            (20240129, 104, 1e8, 1e10), (20240205, 105, 1e8, 1e10),
            (20240212, 106, 1e8, 1e10), (20240219, 107, 1e8, 1e10),
            (20240226, 108, 1e8, 1e10), (20240304, 109, 1e8, 1e10),
        ]
        vp._PANEL_CACHE["df"] = self._make_df("sh600519", rows)
        out = vp.get_volume_price("600519", weeks=3)
        self.assertEqual(len(out["periods"]), 3)
        self.assertEqual(out["periods"][-1], "20240304")

    def test_zero_weeks_returns_empty_error(self):
        """weeks=0 属于边界，应返回无量价数据。"""
        vp._PANEL_CACHE["df"] = self._make_df("sh600519", [(20240101, 100, 1e8, 1e10)])
        out = vp.get_volume_price("600519", weeks=0)
        self.assertIn("error", out)


@unittest.skipUnless(os.path.exists(config.PRICE_PANEL_FILE),
                     "价格面板未构建（先运行 python -m panels.price）")
class TestVolumePricePanel(unittest.TestCase):
    """真实面板回归：sh688300 本地量价指标必须正常且数值合理。"""

    @classmethod
    def setUpClass(cls):
        cls.out = vp.get_volume_price("sh688300", weeks=12)
        if cls.out.get("error"):
            raise unittest.SkipTest("688300 无量价数据: %s" % cls.out["error"])

    def test_no_error_and_aligned(self):
        """返回无错，且各序列等长。"""
        self.assertNotIn("error", self.out)
        self.assertEqual(len(self.out["periods"]), 12)
        self.assertEqual(len(self.out["close"]), 12)
        self.assertEqual(len(self.out["volume_yi"]), 12)

    def test_latest_fields(self):
        """latest 必须包含所有展示字段。"""
        L = self.out["latest"]
        for k in ["period", "close", "chg_pct", "vol_ratio", "pattern",
                  "amount_yi", "vol_trend_pct", "divergence"]:
            self.assertIn(k, L)

    def test_pattern_in_enum(self):
        """量价形态必须是 4 种合法值之一。"""
        self.assertIn(self.out["latest"]["pattern"],
                      ["量价齐升", "缩量上涨", "放量下跌", "缩量下跌"])

    def test_vol_ratio_reasonable(self):
        """放量倍数应为有限正数。"""
        r = self.out["latest"]["vol_ratio"]
        self.assertIsNotNone(r)
        self.assertGreater(r, 0)
        self.assertTrue(0.1 < r < 20)

    def test_divergence_is_bool(self):
        """背离标志必须是布尔值。"""
        self.assertIsInstance(self.out["latest"]["divergence"], bool)


if __name__ == "__main__":
    unittest.main()

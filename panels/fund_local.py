# -*- coding: utf-8 -*-
"""个股财务卡（**本地离线**，取自财务面板 65 列）。

**背景**：`server.py` 的 ``/api/stock/fundamentals`` 原先走网络抓取（`sources/company.py`），
存在三个问题：① **没有历史序列**（把单期快照复制 N 份，如
``gross_margin=[snap.get("gross_margin")] * len(years)``）；② 营收是**反推的近似值**；
③ 依赖网络、可能失败。

本模块改用**本地财务面板**（实测 **248,528 行 × 65 列**，茅台含 2001 年至今完整季度序列），
提供**真实历史趋势** + **零网络** + **TTM / 成长 / 杠杆 / 现金流质量** 等全指标。

**⚠️ 单位对照（实测确认，极易踩坑）**

| 字段 | 单位 | 处理 |
|---|---|---|
| ``ROE`` / ``GP_MARGIN`` / ``NP_MARGIN`` / ``DEBT_RATIO`` / ``*_YOY`` / ``OCF_TO_NP`` / ``CURRENT_RATIO`` | **百分数** | 直接用 |
| ``EPS`` / ``BVPS`` | 元 | 直接用 |
| ``NP_PARENT`` / ``TOTAL_ASSETS`` / ``TOTAL_LIAB`` / ``TOTAL_EQUITY`` / ``OCF`` / ``CAPEX`` | **元** | ÷1e8 → 亿元 |
| **``NP_TTM`` / ``REV_TTM`` / ``REV_TTM_RECENT``** | **万元** ⚠️ | ÷1e4 → 亿元 |
| ``TOTAL_SHARE`` | 股 | 直接 |
| ``HOLDERS`` | 户 | 直接 |

> 实测基准（贵州茅台 20260630）：ROE 17.72、GP_MARGIN 89.56、DEBT_RATIO 15.19、
> EPS 35.57、BVPS 200.99、``NP_PARENT`` 4.45e10（**元** = 445 亿）、
> ``NP_TTM`` 8.14e6（**万元** = 814 亿）、``TOTAL_SHARE`` 1.25e9（股）。
"""
import logging
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config                                          # noqa: E402

LOG = logging.getLogger(__name__)

_YUAN = 1e8             # 元 → 亿元
_WAN = 1e4              # 万元 → 亿元

#: 计算 TTM ROE 时"平均净资产"的同比回溯期数（季报 = 4 期）。
#: 面板 ``ROE`` 是**报告期累计**口径（Q1≈全年 1/4、Q4=全年），季度序列上必然呈
#: "每年前低后高、Q1 断崖"的规则锯齿，与 TTM 口径的营收/净利混画会误导，
#: 故统一派生 ``roe_ttm`` 作为可比口径（详见 ``_ttm_roe`` 文档）。
_ROE_AVG_LAG = 4

#: 盈利能力打分时 ROE 的满分区（百分数）；与 ``0`` 构成线性映射区间。
_ROE_FULL_SCORE = 30.0

#: 最新一期核心指标（面板列名 → 输出名）
_LATEST = {
    "ROE": "roe", "ROE_WEIGHTED": "roe_weighted",
    "GP_MARGIN": "gp_margin", "NP_MARGIN": "np_margin", "OP_MARGIN": "op_margin",
    "DEBT_RATIO": "debt_ratio", "CURRENT_RATIO": "current_ratio", "QUICK_RATIO": "quick_ratio",
    "OCF_TO_NP": "ocf_to_np", "OCF_TO_REV": "ocf_to_rev",
    "REV_YOY": "rev_yoy", "NP_YOY": "np_yoy", "NP_DEDUCT_YOY": "np_deduct_yoy",
    "EPS": "eps", "EPS_DEDUCT": "eps_deduct", "BVPS": "bvps",
    "AR_TURNOVER": "ar_turnover", "INV_TURNOVER": "inv_turnover",
    "ASSET_TURNOVER": "asset_turnover", "EQUITY_TURNOVER": "equity_turnover",
    "HOLDERS": "holders",
}

#: 历史趋势序列（面板列名 → 输出名，含单位换算标记）
#: ⚠️ ``ROE``（→ ``roe``）是**报告期累计**口径的原始值，季报序列呈规则锯齿；
#: 与同为 TTM 口径的 ``REV_TTM`` / ``NP_TTM`` **不可直接对比**。
#: 需要可比口径请用 ``get_fund_card`` 额外派生的 ``trend["roe_ttm"]``（见 ``_ttm_roe``）。
_TREND = [
    ("REV_TTM", "rev_ttm_yi", _WAN),        # 万元 → 亿元
    ("NP_TTM", "np_ttm_yi", _WAN),          # 万元 → 亿元
    ("ROE", "roe", 1.0),                    # ⚠️ 报告期累计
    ("GP_MARGIN", "gp_margin", 1.0),
    ("NP_MARGIN", "np_margin", 1.0),
    ("DEBT_RATIO", "debt_ratio", 1.0),
    ("REV_YOY", "rev_yoy", 1.0),
    ("NP_YOY", "np_yoy", 1.0),
    ("EPS", "eps", 1.0),                 # 累计 EPS（元），供前端图表
    ("BVPS", "bvps", 1.0),
]

_PANEL_CACHE = {}


def _load_panel():
    """载入财务面板（进程内缓存）。

    Returns:
        pandas.DataFrame | None
    """
    if "df" in _PANEL_CACHE:
        return _PANEL_CACHE["df"]
    try:
        import pandas as pd
        df = pd.read_parquet(config.FUND_PANEL_FILE)
        df["p6"] = df["code"].astype(str).str.zfill(6)
        _PANEL_CACHE["df"] = df
        LOG.info("[fund_local] 财务面板载入: %s", df.shape)
        return df
    except Exception as exc:
        LOG.error("[fund_local] 载入面板异常: %s", exc)
        if isinstance(exc, ImportError) or "No module named" in str(exc):
            # 典型场景：服务进程由"另一个 python"启动，该环境没装 pandas/pyarrow
            LOG.error("[fund_local] 缺少 pandas/pyarrow —— 请用**启动服务的那个 python**执行："
                      "\n         %s -m pip install pandas pyarrow", sys.executable)
        LOG.debug("[fund_local] 载入面板堆栈:\n%s", traceback.format_exc())
        _PANEL_CACHE["df"] = None
        return None


def _pure(code):
    """``"sh600519"`` / ``"600519"`` → ``"600519"``。"""
    c = str(code or "").strip().lower()
    if c[:2] in ("sh", "sz", "bj"):
        c = c[2:]
    return c.zfill(6)


def _f(v, scale=1.0, digits=2):
    """安全转 float 并缩放。

    Returns:
        float | None
    """
    try:
        if v is None:
            return None
        x = float(v) / scale if scale != 1.0 else float(v)
        return round(x, digits)
    except Exception:
        return None


def _num(v):
    """安全转 float；``None`` / 非数 / ``NaN`` 一律返回 ``None``。

    ⚠️ 面板缺失值经 ``_f`` 转换后可能是 ``NaN``（``float(nan)`` 不会抛异常），
    直接参与乘除会把整条派生序列污染成 ``NaN``，故此处显式用 ``x != x`` 判 NaN。
    """
    try:
        x = float(v)
    except Exception:
        return None
    return None if x != x else x


def _ttm_roe(np_ttm_wan, equity_yuan, lag=_ROE_AVG_LAG):
    """把"报告期累计 ROE"换算为 **TTM ROE**（滚动 12 个月，可比口径）。

    **为什么必须换算**（本地面板实测 688300）：

    ==========  ==========  ================
    period      面板 ROE    同期 REV_TTM 口径
    ==========  ==========  ================
    20240331      3.70      近一年滚动
    20240630      8.55      近一年滚动
    20240930     12.83      近一年滚动
    20241231     16.67      近一年滚动
    ==========  ==========  ================

    面板 ``ROE``（通达信"净资产收益率"）是**年初至今累计值**：Q1 ≈ 全年 1/4、
    Q2 ≈ 1/2、Q3 ≈ 3/4、Q4 = 全年，年报后归零重来 → 季度序列上必然是
    "每年前低后高、Q1 断崖"的**规则锯齿**，**与经营恶化无关**。
    而营收/净利用的是 ``REV_TTM`` / ``NP_TTM``（近一年滚动）→ 单调平滑。
    两种口径混画即产生"营收在涨、ROE 却周期波动"的错觉。

    本函数按 ``NP_TTM / 平均净资产 × 100`` 统一到 TTM 口径：

    - **单位**：``NP_TTM`` 为**万元**（×1e4 → 元）；``TOTAL_EQUITY`` 为**元**。
    - **平均净资产** = ``(期末净资产 + 去年同期净资产) / 2``（回溯 ``lag`` 期）；
      窗口首期无同比数据时退化为**期末净资产**（近似口径）。
    - 任一输入缺失 / 净资产非正 → 该期返回 ``None``（前端折线断开，不画假点）。

    Args:
        np_ttm_wan: 近一年归母净利润（万元）序列，按 period 升序。
        equity_yuan: 净资产（元）序列，与前者等长且期次对齐。
        lag: 同比回溯期数（季报 = 4）。

    Returns:
        list[float | None]: TTM ROE（百分数）序列，与输入等长。
    """
    out = []
    for i, np_raw in enumerate(np_ttm_wan):
        np_ttm = _num(np_raw)
        eq = _num(equity_yuan[i]) if i < len(equity_yuan) else None
        eq_prev = _num(equity_yuan[i - lag]) if i - lag >= 0 else None
        if np_ttm is None or eq is None:
            out.append(None)
            continue
        try:
            # 平均净资产：优先 (期末 + 去年同期)/2；同比期缺失/非正时退化为期末
            avg_eq = (eq + eq_prev) / 2.0 if (eq_prev is not None and eq_prev > 0) else eq
            if avg_eq <= 0:
                out.append(None)
                continue
            out.append(round(np_ttm * _WAN / avg_eq * 100.0, 2))
        except Exception as exc:            # pragma: no cover - 极端数值保护
            LOG.warning("[fund_local] TTM ROE 计算异常 i=%d: %s", i, exc)
            out.append(None)
    return out


def get_fund_card(code, price=None, periods=12):
    """组装个股财务卡（本地离线）。

    Args:
        code: 证券代码（``sh600519`` 或 ``600519``）。
        price: 当前股价（用于算 PE/PB）；``None`` 则不算估值。
        periods: 返回最近多少期的趋势。

    Returns:
        dict: ``{code, latest, trend, valuation, source}``；失败返回 ``{"error": ...}``。

        - ``trend`` 含 ``roe``（**报告期累计**，原始值）与 ``roe_ttm``（**TTM，可比口径**）；
          ``latest`` 同样含 ``roe`` 与 ``roe_ttm``。
    """
    p6 = _pure(code)
    df = _load_panel()
    if df is None:
        return {"error": "财务面板不可用"}
    try:
        sub = df[df["p6"] == p6]
        if sub.empty:
            return {"error": "无财务数据", "code": p6}
        sub = sub.sort_values("period")
        last = sub.iloc[-1]

        latest = {"period": str(last.get("period")), "code": p6}
        for col, key in _LATEST.items():
            if col in sub.columns:
                latest[key] = _f(last.get(col), digits=2)
        # 金额类（元 → 亿元）
        latest["total_assets_yi"] = _f(last.get("TOTAL_ASSETS"), _YUAN)
        latest["total_equity_yi"] = _f(last.get("TOTAL_EQUITY"), _YUAN)
        latest["np_parent_yi"] = _f(last.get("NP_PARENT"), _YUAN)
        latest["rev_ttm_yi"] = _f(last.get("REV_TTM"), _WAN)
        latest["np_ttm_yi"] = _f(last.get("NP_TTM"), _WAN)
        latest["ocf_ttm_yi"] = _f(last.get("OCF_TTM"), _YUAN)
        latest["total_share"] = _f(last.get("TOTAL_SHARE"), digits=0)
        latest["notice_date"] = str(last.get("notice_date") or last.get("NOTICE_DATE") or "")

        n = int(periods)
        tail = sub.tail(n)
        trend = {"periods": [str(x) for x in tail["period"].tolist()]}
        for col, key, scale in _TREND:
            if col in sub.columns:
                trend[key] = [_f(v, scale) for v in tail[col].tolist()]

        # TTM ROE（派生口径）：多取 _ROE_AVG_LAG 期，保证窗口**首期**也能取到
        # "去年同期净资产"算平均，否则前 4 期会静默退化成期末口径、口径不一致。
        win = sub.tail(n + _ROE_AVG_LAG)
        trend["roe_ttm"] = _ttm_roe(
            win["NP_TTM"].tolist() if "NP_TTM" in win.columns else [],
            win["TOTAL_EQUITY"].tolist() if "TOTAL_EQUITY" in win.columns else [],
        )[-n:]
        # 最新一期与 trend 末位同 period，直接取末值
        latest["roe_ttm"] = trend["roe_ttm"][-1] if trend["roe_ttm"] else None

        val = {}
        try:
            px = float(price) if price else None
            if px:
                bvps = latest.get("bvps")
                val["price"] = px
                val["pb"] = round(px / bvps, 2) if bvps else None
                sh = latest.get("total_share")
                np_ttm_yi = latest.get("np_ttm_yi")
                if sh and np_ttm_yi:
                    eps_ttm = (np_ttm_yi * _YUAN) / sh          # 亿元 → 元 / 股
                    val["eps_ttm"] = round(eps_ttm, 3)
                    val["pe_ttm"] = round(px / eps_ttm, 2) if eps_ttm > 0 else None
                if sh and latest.get("rev_ttm_yi"):
                    rps = (latest["rev_ttm_yi"] * _YUAN) / sh       # 每股营收（元）
                    val["rev_per_share"] = round(rps, 3)
                    val["ps_ttm"] = round(px / rps, 2) if rps > 0 else None
        except Exception as exc:
            LOG.error("[fund_local] 估值计算异常 %s: %s", p6, exc)

        return {"code": p6, "latest": latest, "trend": trend,
                "valuation": val, "n_periods_total": int(len(sub)),
                "source": "local_fund_panel"}
    except Exception as exc:
        LOG.error("[fund_local] 组装财务卡异常 %s: %s\n%s", p6, exc, traceback.format_exc())
        return {"error": str(exc), "code": p6}


#: 财务指标表定义：(输出 key, 显示名, 面板列, 缩放, 类型)
#: 类型 ``pct`` = 百分数 / ``money`` = 已转亿元 / ``plain`` = 原值
_TABLE_ROWS = [
    ("eps", "每股收益(元)", "EPS", 1.0, "plain"),
    ("eps_deduct", "扣非每股收益(元)", "EPS_DEDUCT", 1.0, "plain"),
    ("bvps", "每股净资产(元)", "BVPS", 1.0, "plain"),
    ("ocf_ps", "每股经营现金流(元)", "OCF_PS", 1.0, "plain"),
    ("rev_yi", "营业总收入(亿)", "REV_TTM", _WAN, "money"),
    ("np_yi", "归母净利润(亿)", "NP_TTM", _WAN, "money"),
    ("npd_yi", "扣非净利润(亿)", "NP_DEDUCT_TTM", _WAN, "money"),
    ("ocf_yi", "经营现金流(亿)", "OCF_TTM", _YUAN, "money"),
    ("ta_yi", "总资产(亿)", "TOTAL_ASSETS", _YUAN, "money"),
    ("te_yi", "净资产(亿)", "TOTAL_EQUITY", _YUAN, "money"),
    ("roe", "净资产收益率%", "ROE", 1.0, "pct"),
    ("roe_w", "加权净资产收益率%", "ROE_WEIGHTED", 1.0, "pct"),
    ("gp_margin", "销售毛利率%", "GP_MARGIN", 1.0, "pct"),
    ("np_margin", "销售净利率%", "NP_MARGIN", 1.0, "pct"),
    ("op_margin", "营业利润率%", "OP_MARGIN", 1.0, "pct"),
    ("debt_ratio", "资产负债率%", "DEBT_RATIO", 1.0, "pct"),
    ("current_ratio", "流动比率", "CURRENT_RATIO", 1.0, "plain"),
    ("quick_ratio", "速动比率", "QUICK_RATIO", 1.0, "plain"),
    ("ocf_to_np", "经营现金流/净利润%", "OCF_TO_NP", 1.0, "pct"),
    ("rev_yoy", "营收同比增长%", "REV_YOY", 1.0, "pct"),
    ("np_yoy", "净利同比增长%", "NP_YOY", 1.0, "pct"),
    ("npd_yoy", "扣非净利同比增长%", "NP_DEDUCT_YOY", 1.0, "pct"),
    ("ar_turnover", "应收账款周转率", "AR_TURNOVER", 1.0, "plain"),
    ("inv_turnover", "存货周转率", "INV_TURNOVER", 1.0, "plain"),
    ("asset_turnover", "总资产周转率", "ASSET_TURNOVER", 1.0, "plain"),
    ("equity_turnover", "净资产周转率", "EQUITY_TURNOVER", 1.0, "plain"),
    ("holders", "股东户数", "HOLDERS", 1.0, "plain"),
]


def get_fin_table(code, periods=6):
    """财务指标表（**多期横向**，最近 ``periods`` 期）。

    对应通达信"财务分析 → 财务指标"的科目表。

    Args:
        code: 证券代码。
        periods: 返回期数（默认 6）。

    Returns:
        dict: ``{periods: [...], rows: [{key,label,kind,values:[...]}], latest_period}``
    """
    p6 = _pure(code)
    df = _load_panel()
    if df is None:
        return {"error": "财务面板不可用"}
    try:
        sub = df[df["p6"] == p6]
        if sub.empty:
            return {"error": "无财务数据", "code": p6}
        sub = sub.sort_values("period").tail(int(periods))
        pers, rows = [str(x) for x in sub["period"].tolist()], []
        for key, label, col, scale, kind in _TABLE_ROWS:
            if col not in sub.columns:
                continue
            if kind == "money":
                vals = [_f(v, scale) for v in sub[col].tolist()]
            else:
                vals = [_f(v, 1.0, digits=(2 if kind == "pct" else 4)) for v in sub[col].tolist()]
            rows.append({"key": key, "label": label, "kind": kind, "values": vals})
        return {"code": p6, "periods": pers, "rows": rows,
                "latest_period": pers[-1] if pers else "", "source": "local_fund_panel"}
    except Exception as exc:
        LOG.error("[fund_local] 财务表异常 %s: %s\n%s", p6, exc, traceback.format_exc())
        return {"error": str(exc), "code": p6}


def _score(v, lo, hi):
    """把 ``v`` 从 ``[lo, hi]`` 线性映射到 ``[0, 100]``（超界截断），``None`` 透传。"""
    try:
        if v is None:
            return None
        if hi == lo:
            return 50.0
        x = (float(v) - lo) / (hi - lo) * 100.0
        return round(max(0.0, min(100.0, x)), 1)
    except Exception:
        return None


def _avg(vals):
    """非空值均值。"""
    arr = [v for v in vals if v is not None]
    return round(sum(arr) / len(arr), 1) if arr else None


def diagnose(code):
    """财务诊断：**综合评分 + 五维雷达**（盈利 / 成长 / 偿债 / 现金流 / 运营）。

    评分口径（每维 0~100，由若干指标线性映射后取均值；阈值取 A 股常见区间）：

    | 维度 | 指标 | 满分区 | 零分区 |
    |---|---|---|---|
    | 盈利能力 | **ROE(TTM)** / 毛利率 / 净利率 | 30% / 60% / 30% | 0% |
    | 成长能力 | 营收同比 / 净利同比 | +30% / +50% | -30% |
    | 偿债能力 | 资产负债率（反向）/ 流动比率 | 0% / 2.0 | 80% / 0.5 |
    | 现金流 | 经营现金流/净利 | 100% | 0% |
    | 运营效率 | 总资产周转率 | 1.0 | 0.05 |

    ⚠️ **ROE 必须用 TTM 口径**：面板 ``ROE`` 是"报告期累计"（半年报≈全年一半），
    直接按"全年 30% 满分"的阈值打分会在中报/季报期**系统性低估盈利能力**
    （茅台 20260630 面板 ROE 17.72 实为半年值，TTM 约 32.6）→ 改用 ``roe_ttm``。

    Returns:
        dict: ``{score, dims:{...}, detail:{...}, period}``
    """
    p6 = _pure(code)
    df = _load_panel()
    if df is None:
        return {"error": "财务面板不可用"}
    try:
        sub = df[df["p6"] == p6]
        if sub.empty:
            return {"error": "无财务数据", "code": p6}
        sub = sub.sort_values("period")
        r = sub.iloc[-1]

        def g(col):
            return _f(r.get(col), 1.0, digits=4)

        # ROE(TTM)：多取 _ROE_AVG_LAG 期以便取到"去年同期净资产"算平均
        win = sub.tail(_ROE_AVG_LAG + 1)
        roe_ttm_list = _ttm_roe(
            win["NP_TTM"].tolist() if "NP_TTM" in win.columns else [],
            win["TOTAL_EQUITY"].tolist() if "TOTAL_EQUITY" in win.columns else [],
        )
        roe_ttm = roe_ttm_list[-1] if roe_ttm_list else None
        roe_period = g("ROE")
        # TTM 缺失（面板无 TTM/净资产列）时退回报告期值，避免整维丢分
        roe_used = roe_ttm if roe_ttm is not None else roe_period

        profit = _avg([_score(roe_used, 0, _ROE_FULL_SCORE), _score(g("GP_MARGIN"), 0, 60),
                       _score(g("NP_MARGIN"), 0, 30)])
        growth = _avg([_score(g("REV_YOY"), -30, 30), _score(g("NP_YOY"), -30, 50)])
        solvency = _avg([_score(-(g("DEBT_RATIO") or 0), -80, 0) if g("DEBT_RATIO") is not None else None,
                         _score(g("CURRENT_RATIO"), 0.5, 2.0)])
        cash = _score(g("OCF_TO_NP"), 0, 100)
        oper = _score(g("ASSET_TURNOVER"), 0.05, 1.0)
        dims = {"profit": profit, "growth": growth, "solvency": solvency,
                "cash": cash, "oper": oper}
        score = _avg(list(dims.values()))
        return {"code": p6, "period": str(r.get("period")), "score": score, "dims": dims,
                "detail": {"roe_ttm": roe_ttm, "roe_period": roe_period,
                           "gp_margin": g("GP_MARGIN"),
                           "np_margin": g("NP_MARGIN"), "rev_yoy": g("REV_YOY"),
                           "np_yoy": g("NP_YOY"), "debt_ratio": g("DEBT_RATIO"),
                           "current_ratio": g("CURRENT_RATIO"),
                           "ocf_to_np": g("OCF_TO_NP"), "asset_turnover": g("ASSET_TURNOVER")},
                "source": "local_fund_panel"}
    except Exception as exc:
        LOG.error("[fund_local] 诊断异常 %s: %s\n%s", p6, exc, traceback.format_exc())
        return {"error": str(exc), "code": p6}


def dupont(code, periods=6):
    """**杜邦分析**：``ROE = 销售净利率 × 总资产周转率 × 权益乘数``。

    **实测校验**（贵州茅台 20260630）：净利率 50.75% × 周转率 0.296 × 权益乘数 1.18
    = **17.73%**，与面板 ``ROE`` 17.72 几乎一致（误差 <2%，源于年化/平均口径差异）。

    三因子分别对应三种盈利模式：

    | 因子 | 面板列 | 含义 | 典型行业 |
    |---|---|---|---|
    | 销售净利率 | ``NP_MARGIN`` | 产品溢价 / 成本控制 | 白酒、医药、软件 |
    | 总资产周转率 | ``ASSET_TURNOVER`` | 资产运营效率 | 零售、贸易、快消 |
    | 权益乘数 | ``EQUITY_MULT`` | 财务杠杆 | 银行、地产、券商 |

    同时给出**驱动类型判定**，直接回答"这家公司的 ROE 靠什么撑起来"。

    Returns:
        dict: ``{periods, roe, npm, turnover, equity_mult, roe_calc, driver, driver_desc}``
    """
    p6 = _pure(code)
    df = _load_panel()
    if df is None:
        return {"error": "财务面板不可用"}
    try:
        sub = df[df["p6"] == p6]
        if sub.empty:
            return {"error": "无财务数据", "code": p6}
        sub = sub.sort_values("period").tail(int(periods))

        def g(col):
            return [_f(v, 1.0, digits=4) for v in sub[col].tolist()] if col in sub.columns else []

        npm, to, em, roe = g("NP_MARGIN"), g("ASSET_TURNOVER"), g("EQUITY_MULT"), g("ROE")
        calc = [round(((a or 0) / 100) * (b or 0) * (c or 0) * 100, 3)
                for a, b, c in zip(npm, to, em)]

        # 驱动类型（基于最新一期）
        ln = npm[-1] if npm else None
        lt = to[-1] if to else None
        le = em[-1] if em else None
        hi_npm = ln is not None and ln >= 15
        hi_to = lt is not None and lt >= 1.5
        hi_em = le is not None and le >= 3.0
        if hi_em:
            # 优先判杠杆：银行/地产/券商的"高净利率"多为行业口径特性（如银行无销售成本），
            # 真正压倒性的特征是权益乘数 —— 实测工商银行净利率 37.88% 但权益乘数 13.1，
            # 若按"净利率优先"会误判为高利润率型。
            drv = "高杠杆型"
            desc = (f"权益乘数 {le} 偏高（≥3），ROE 主要由杠杆驱动"
                    f"（净利率 {ln}% 虽不低，但属行业口径特性），需关注偿债与利率风险")
        elif hi_npm and hi_to:
            drv = "均衡型"
            desc = f"净利率 {ln}%（≥15）与周转率 {lt}（≥1.5）双高，盈利与运营俱佳"
        elif hi_npm:
            drv = "高利润率型"
            desc = f"净利率 {ln}% 显著偏高，周转率 {lt} 偏低 → 靠产品溢价 / 成本控制驱动"
        elif hi_to:
            drv = "高周转型"
            desc = f"周转率 {lt} 较高（≥1.5），净利率 {ln}% 偏薄 → 靠薄利多销 / 运营效率驱动"
        else:
            drv = "一般型"
            desc = f"净利率 {ln}%、周转率 {lt}、权益乘数 {le} 均不突出"

        return {"code": p6, "periods": [str(x) for x in sub["period"].tolist()],
                "roe": roe, "npm": npm, "turnover": to, "equity_mult": em,
                "roe_calc": calc, "driver": drv, "driver_desc": desc,
                "source": "local_fund_panel"}
    except Exception as exc:
        LOG.error("[fund_local] 杜邦分析异常 %s: %s\n%s", p6, exc, traceback.format_exc())
        return {"error": str(exc), "code": p6}


def get_quarterly(code, periods=8):
    """**单季度拆分**（把"年初至今累计"还原为"当季发生额"）。

    **面板口径**（实测茅台 20260630）：

    | 字段 | 口径 | 单位 |
    |---|---|---|
    | ``REV_Q`` | **已是单季** | 万元 |
    | ``REV_TOTAL`` | 累计 | 万元 |
    | ``NP_PARENT`` / ``OCF`` / ``CAPEX`` | **累计** | 元 |

    → 营收直接取 ``REV_Q``；净利 / 经营现金流 / 资本开支需**同一会计年度内相邻期相减**
    （Q1 无上期，单季 = 其累计值）。

    **为什么重要**：中报增长 10%，可能是 Q1 涨 20% + Q2 持平甚至下滑，
    累计值会把**拐点平滑掉**，单季数据才能看清趋势。

    Returns:
        dict: ``{periods, rows:[{key,label,values}], note}``
    """
    p6 = _pure(code)
    df = _load_panel()
    if df is None:
        return {"error": "财务面板不可用"}
    try:
        sub = df[df["p6"] == p6]
        if sub.empty:
            return {"error": "无财务数据", "code": p6}
        # 多取 4 期：保证窗口内首年的 Q2/Q3/Q4 也能找到"同年内上一期"做差分，
        # 否则首年会退化成累计值（实测曾出现 20250630=454 累计 vs 20250930=192 单季的口径混用）
        cut = int(periods)
        sub = sub.sort_values("period").tail(cut + 4)
        pers = [str(x) for x in sub["period"].tolist()]

        def diff_within_year(col, scale):
            """同年内相邻期差分（累计 → 单季）。"""
            if col not in sub.columns:
                return []
            out, prev_by_year = [], {}
            for p, v in zip(pers, sub[col].tolist()):
                y = p[:4]
                prev = prev_by_year.get(y)
                cur = (v if v is not None else None)
                out.append(_f(cur, scale) if prev is None
                           else (_f(cur - prev, scale) if cur is not None else None))
                prev_by_year[y] = cur
            return out

        def direct(col, scale):
            return [_f(v, scale) for v in sub[col].tolist()] if col in sub.columns else []

        rows = [
            {"key": "rev_q", "label": "营业总收入(亿)", "values": direct("REV_Q", _WAN)[-cut:]},
            {"key": "np_q", "label": "归母净利润(亿)",
             "values": diff_within_year("NP_PARENT", _YUAN)[-cut:]},
            {"key": "ocf_q", "label": "经营现金流(亿)",
             "values": diff_within_year("OCF", _YUAN)[-cut:]},
            {"key": "capex_q", "label": "资本开支(亿)",
             "values": diff_within_year("CAPEX", _YUAN)[-cut:]},
        ]
        return {"code": p6, "periods": pers[-cut:], "rows": rows,
                "note": "营收取 REV_Q（已是单季）；净利/现金流/资本开支由累计值同年度内差分得到",
                "source": "local_fund_panel"}
    except Exception as exc:
        LOG.error("[fund_local] 单季拆分异常 %s: %s\n%s", p6, exc, traceback.format_exc())
        return {"error": str(exc), "code": p6}


def get_balance(code, periods=6):
    """**资产负债结构**（资产 / 负债 / 权益的构成与占比）。

    面板字段（**单位均为元**）：``TOTAL_ASSETS`` / ``CA_TOTAL``（流动资产）/
    ``NCA_TOTAL``（非流动资产）/ ``TOTAL_LIAB`` / ``CL_TOTAL``（流动负债）/
    ``NCL_TOTAL``（非流动负债）/ ``TOTAL_EQUITY``。

    Returns:
        dict: ``{periods, rows, latest:{...}, ratios}``
    """
    p6 = _pure(code)
    df = _load_panel()
    if df is None:
        return {"error": "财务面板不可用"}
    try:
        sub = df[df["p6"] == p6]
        if sub.empty:
            return {"error": "无财务数据", "code": p6}
        sub = sub.sort_values("period").tail(int(periods))
        pers = [str(x) for x in sub["period"].tolist()]
        money = [("ta", "总资产(亿)", "TOTAL_ASSETS"), ("ca", "流动资产(亿)", "CA_TOTAL"),
                 ("nca", "非流动资产(亿)", "NCA_TOTAL"), ("tl", "总负债(亿)", "TOTAL_LIAB"),
                 ("cl", "流动负债(亿)", "CL_TOTAL"), ("ncl", "非流动负债(亿)", "NCL_TOTAL"),
                 ("te", "净资产(亿)", "TOTAL_EQUITY")]
        rows = [{"key": k, "label": lb, "values": [_f(v, _YUAN) for v in sub[c].tolist()]}
                for k, lb, c in money if c in sub.columns]
        last = sub.iloc[-1]
        ta = _f(last.get("TOTAL_ASSETS"), _YUAN)
        ca = _f(last.get("CA_TOTAL"), _YUAN)
        cl = _f(last.get("CL_TOTAL"), _YUAN)
        tl = _f(last.get("TOTAL_LIAB"), _YUAN)
        ratios = {
            "current_assets_pct": round(ca / ta * 100, 2) if (ca and ta) else None,
            "current_liab_pct": round(cl / tl * 100, 2) if (cl and tl) else None,
            "debt_ratio": _f(last.get("DEBT_RATIO"), 1.0, digits=2),
            "current_ratio": _f(last.get("CURRENT_RATIO"), 1.0, digits=3),
            "quick_ratio": _f(last.get("QUICK_RATIO"), 1.0, digits=3),
        }
        return {"code": p6, "periods": pers, "rows": rows,
                "latest_period": pers[-1] if pers else "",
                "latest": {"total_assets_yi": ta, "current_assets_yi": ca,
                           "noncurrent_assets_yi": _f(last.get("NCA_TOTAL"), _YUAN),
                           "total_liab_yi": tl, "current_liab_yi": cl,
                           "noncurrent_liab_yi": _f(last.get("NCL_TOTAL"), _YUAN),
                           "equity_yi": _f(last.get("TOTAL_EQUITY"), _YUAN)},
                "ratios": ratios, "source": "local_fund_panel"}
    except Exception as exc:
        LOG.error("[fund_local] 资产负债异常 %s: %s\n%s", p6, exc, traceback.format_exc())
        return {"error": str(exc), "code": p6}


def get_cashflow(code, periods=6):
    """**现金流分析**：经营现金流 / 资本开支 / **自由现金流(FCF)** 与现金流质量。

    - ``OCF``（经营现金流净额）与 ``CAPEX``（购建长期资产支出）均为**累计**（元）
      → 同年度内差分得单季；
    - **FCF = OCF − CAPEX**（企业真正可自由支配的现金）；
    - 质量指标：``OCF_TO_NP``（经营现金流 / 净利润，>100% 说明利润含金量高）、
      ``CASH_RECOVERY``（销售现金比率）、``SALES_CASH_TO_REV``。

    Returns:
        dict: ``{periods, rows, latest, quality}``
    """
    p6 = _pure(code)
    df = _load_panel()
    if df is None:
        return {"error": "财务面板不可用"}
    try:
        sub = df[df["p6"] == p6]
        if sub.empty:
            return {"error": "无财务数据", "code": p6}
        # 同 get_quarterly：多取 4 期保证窗口内首年可做年内差分
        sub = sub.sort_values("period").tail(int(periods) + 4)
        pers = [str(x) for x in sub["period"].tolist()]

        def q(col, scale=_YUAN):
            """同年内差分 → 单季。"""
            if col not in sub.columns:
                return []
            out, prev_y = [], {}
            for p, v in zip(pers, sub[col].tolist()):
                y = p[:4]
                prev = prev_y.get(y)
                out.append(_f(v, scale) if prev is None
                           else (_f(v - prev, scale) if v is not None else None))
                prev_y[y] = v
            return out

        ocf, capex = q("OCF"), q("CAPEX")
        fcf = [round(a - b, 2) if (a is not None and b is not None) else None
               for a, b in zip(ocf, capex)]
        rows = [{"key": "ocf_q", "label": "经营现金流(亿)", "values": ocf},
                {"key": "capex_q", "label": "资本开支(亿)", "values": capex},
                {"key": "fcf_q", "label": "自由现金流 FCF(亿)", "values": fcf}]
        last = sub.iloc[-1]
        return {"code": p6, "periods": pers, "rows": rows,
                "latest_period": pers[-1] if pers else "",
                "quality": {"ocf_to_np": _f(last.get("OCF_TO_NP"), 1.0, digits=2),
                            "cash_recovery": _f(last.get("CASH_RECOVERY"), 1.0, digits=2),
                            "sales_cash_to_rev": _f(last.get("SALES_CASH_TO_REV"), 1.0, digits=2),
                            "cf_per_share": _f(last.get("CF_PS"), 1.0, digits=3),
                            "ocf_ttm_yi": _f(last.get("OCF_TTM"), _YUAN)},
                "note": "FCF = 经营现金流 − 资本开支（单季，由累计值同年度内差分）",
                "source": "local_fund_panel"}
    except Exception as exc:
        LOG.error("[fund_local] 现金流分析异常 %s: %s\n%s", p6, exc, traceback.format_exc())
        return {"error": str(exc), "code": p6}


def main():
    """命令行自检（默认茅台）。

    Returns:
        dict: 财务卡。
    """
    import json
    card = get_fund_card("600519", price=1400.0)
    print(json.dumps(card, ensure_ascii=False, indent=1))
    return card


if __name__ == "__main__":      # pragma: no cover
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(message)s")
    main()

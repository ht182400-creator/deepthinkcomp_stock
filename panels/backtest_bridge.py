# -*- coding: utf-8 -*-
"""回测桥接：把面板数据接入**既有**回测引擎，用于数据改造验收（W1）。

**设计原则：零改动复用**。``modules/strategy/regime_layer2_backtest.run_backtest_layer2``
的输入结构固定为::

    stocks[纯代码] = {
        "dates": [YYYYMMDD, ...],       # 升序周线日期
        "close": {date: close},
        "sind":  行业,
        "fund":  [ {notice, np, te, ta, tl, ocf, capex}, ... ],   # 按报告期升序
        "name":  名称,
        "di":    {date: idx},
    }

本模块从面板构造**同构**结构，从而"旧引擎 + 新数据"可跑、且与旧数据路径公平对比。

**为什么需要 `WARMUP` 对齐**：旧引擎 ``warmup=220`` 周先预热，
财务面板自 2010 起（且质量门要求 ≥3 期），故有效持仓期约从 2013 年开始。
新旧两条路径在同一窗口上对比才公平。

**行业说明**：东财行业接口临时限流，当前行业从 ``fundamentals_broad.json``
（1771 只全覆盖）取；面板新增的股票行业为空，这会**削弱**金融股过滤与行业上限，
属已知偏差（详见对比结果中的说明）。
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_STRATEGY = os.path.join(_ROOT, "modules", "strategy")
if _STRATEGY not in sys.path:
    sys.path.insert(0, _STRATEGY)

import config                                          # noqa: E402
from panels import universe as uni                     # noqa: E402
from panels import industry as panel_industry          # noqa: E402

LOG = logging.getLogger(__name__)

# 指数代码（regime 方案 B 需要）
INDEX_SYMBOLS = ["sh000001", "sh000985", "sh000688", "sz399006", "sz399001", "bj899050"]
MA_SHORT = 56           # 与旧引擎一致
MA_LONG = 200           # 与旧引擎一致
MIN_WEEKS = 60          # 与旧引擎 build_index_weekly 一致
_TRADING_DAYS_PER_WEEK = 5      # 周成交额 → 日均成交额 的换算（A 股每周 5 个交易日）


def _now():
    """当前时间字符串（统一落盘时间戳格式）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 财务面板中构造 fund 记录所需的列
_FUND_COLS = ["code", "period", "notice_date", "NP_PARENT", "NP_TTM",
              "OCF", "OCF_TTM", "CAPEX", "TOTAL_EQUITY", "TOTAL_ASSETS", "TOTAL_LIAB"]
_WAN = 10000.0                  # 万元 → 元
_QUARTERS = {"0331": 1, "0630": 2, "0930": 3, "1231": 4}


def _quarter_index(period):
    """报告期 → 季度序号（0331→1 / 0630→2 / 0930→3 / 1231→4）。"""
    return _QUARTERS.get(str(period)[4:], 4)


def _load_fund(mode="ttm"):
    """从财务面板构造 ``{纯代码: [fund 记录, ...]}``。

    **⚠️ 口径关键（实测教训）**：季报的净利润/现金流是"**年初至今累计值**"，
    一季报仅为全年的约 1/4。若直接用于 ``ROE ≥ 10%`` 这类门槛，会在季报期
    误杀大批股票（实测合格池 96 只 → 41 只）。因此：

    - ``mode="annual"``：仅取年报（累计值即全年），字段用 ``NP_PARENT`` / ``OCF`` / ``CAPEX``；
    - ``mode="ttm"``：全部报告期，净利用 ``NP_TTM``（近一年归母净利，万元→元）、
      现金流用 ``OCF_TTM``（近一年经营现金流净额），
      Capex 无"近一年"字段，按 ``4 / 季度序号`` 年化近似。

    Args:
        mode: ``"ttm"`` 或 ``"annual"``。

    Returns:
        dict: ``{6 位代码: [{notice,np,te,ta,tl,ocf,capex}, ...]}``
    """
    out = {}
    try:
        df = pd.read_parquet(config.FUND_PANEL_FILE, columns=_FUND_COLS)
        if mode == "annual":
            df = df[df["period"].astype(str).str.endswith("1231")].copy()
            df["NP_USE"] = df["NP_PARENT"]                     # 年报累计 = 全年
            df["OCF_USE"] = df["OCF"]
            df["CAPEX_USE"] = df["CAPEX"]
        else:
            df = df.copy()
            k = df["period"].map(lambda p: 4.0 / _quarter_index(p))
            df["NP_USE"] = df["NP_TTM"] * _WAN                 # 万元 → 元
            df["OCF_USE"] = df["OCF_TTM"]
            df["CAPEX_USE"] = df["CAPEX"] * k                  # 近似年化
        df = df.dropna(subset=["notice_date", "NP_USE", "OCF_USE", "CAPEX_USE",
                               "TOTAL_EQUITY", "TOTAL_ASSETS", "TOTAL_LIAB"])
        for code, g in df.groupby("code", sort=False):
            g = g.sort_values("period")
            recs = []
            for row in g.itertuples(index=False):
                recs.append({
                    "notice": int(row.notice_date),
                    "np": float(row.NP_USE),
                    "te": float(row.TOTAL_EQUITY),
                    "ta": float(row.TOTAL_ASSETS),
                    "tl": float(row.TOTAL_LIAB),
                    "ocf": float(row.OCF_USE),
                    "capex": float(row.CAPEX_USE),
                })
            if recs:
                out[str(code)] = recs
        LOG.info("[bridge] 财务载入: mode=%s, %d 只有数据（平均 %.1f 期）",
                 mode, len(out), sum(len(v) for v in out.values()) / max(1, len(out)))
    except Exception as exc:
        LOG.error("[bridge] 载入财务面板异常: %s\n%s", exc, traceback.format_exc())
    return out


def _load_prices():
    """从价格面板构造 ``{完整代码: {dates, close, di}}``。"""
    out = {}
    try:
        df = pd.read_parquet(config.PRICE_PANEL_FILE, columns=["code", "date", "close"])
        for code, g in df.groupby("code", sort=False):
            g = g.sort_values("date")
            dates = g["date"].tolist()
            closes = g["close"].tolist()
            out[str(code)] = {"dates": dates, "close": dict(zip(dates, closes)),
                              "di": {d: i for i, d in enumerate(dates)}}
        LOG.info("[bridge] 价格载入: %d 只标的", len(out))
    except Exception as exc:
        LOG.error("[bridge] 载入价格面板异常: %s\n%s", exc, traceback.format_exc())
    return out


def _ma(values, n):
    """简单移动平均（前 n-1 位为 None），与旧引擎 ma_series 口径一致。"""
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _load_indices(prices=None):
    """从价格面板构造指数周线（供 regime 使用）。

    Returns:
        dict: ``{symbol: {"dates":[...], "close":[...], "ma56":[...], "ma200":[...]}}``
    """
    prices = prices if prices is not None else _load_prices()
    indices = {}
    for sym in INDEX_SYMBOLS:
        item = prices.get(sym)
        if not item or len(item["dates"]) < MIN_WEEKS:
            LOG.warning("[bridge] 指数 %s 数据不足（%d 根），regime 将回退上证",
                        sym, len(item["dates"]) if item else 0)
            continue
        closes = [item["close"][d] for d in item["dates"]]
        indices[sym] = {"dates": item["dates"], "close": closes,
                        "ma56": _ma(closes, MA_SHORT), "ma200": _ma(closes, MA_LONG)}
    LOG.info("[bridge] 指数载入: %s", list(indices.keys()))
    return indices


def _load_industry_map():
    """行业映射：优先东财 ``industry.json``，回退 ``fundamentals_broad.json``。

    Returns:
        dict: ``{6 位代码: 行业名}``（统一返回 dict，便于调用方直接使用）。
    """
    inds = panel_industry.load_industry()
    if inds:
        LOG.info("[bridge] 行业来源: 东财 industry.json（%d 条）", len(inds))
        return inds
    inds = {}
    try:
        path = os.path.join(_ROOT, "modules", "strategy", "fundamentals_broad.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            inds = {str(k).zfill(6): (v.get("industry") or "") for k, v in raw.items()}
            LOG.warning("[bridge] 行业来源回退 fundamentals_broad.json（仅 %d 只；"
                        "新增股票行业为空 → 金融过滤与行业上限会被削弱，属已知偏差）", len(inds))
    except Exception as exc:
        LOG.error("[bridge] 读取行业回退源异常: %s\n%s", exc, traceback.format_exc())
    return inds


def _load_names():
    """名称映射（来自 data/stock_list.json，5500 只）。"""
    names = {}
    try:
        path = os.path.join(config.DATA_DIR, "stock_list.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
            for item in payload.get("items") or []:
                full = str(item.get("code") or "")
                pure = full[2:] if full[:2] in ("sh", "sz", "bj") else full
                if pure:
                    names[pure] = item.get("name") or pure
        LOG.info("[bridge] 名称载入: %d 条", len(names))
    except Exception as exc:
        LOG.error("[bridge] 读取名称异常: %s\n%s", exc, traceback.format_exc())
    return names


def build_stocks(mode="ttm", universe=None):
    """构造旧引擎可直接消费的 ``stocks`` 结构。

    Args:
        mode: ``"ttm"``（全部报告期）或 ``"annual"``（仅年报）。
        universe: 限定纯代码集合；缺省使用面板中全部有财务与价格的股票。

    Returns:
        tuple[dict, list]: ``(stocks, global_dates)``
    """
    funds = _load_fund(mode=mode)
    prices = _load_prices()
    inds = _load_industry_map()
    names = _load_names()
    stocks = {}
    for pure, fund in funds.items():
        full = uni.pure_to_full(pure)
        pr = prices.get(full)
        if not pr or len(pr["dates"]) < config.PRICE_MIN_BARS:
            continue
        if universe is not None and pure not in universe:
            continue
        stocks[pure] = {
            "dates": pr["dates"],
            "close": pr["close"],
            "sind": inds.get(pure, ""),
            "fund": fund,
            "name": names.get(pure, pure),
            "di": pr["di"],
        }
    idx = prices.get("sh000001") or {}
    global_dates = idx.get("dates") or []
    LOG.info("[bridge] stocks 构建完成: %d 只 | mode=%s | 全局周轴 %d 根",
             len(stocks), mode, len(global_dates))
    return stocks, global_dates


def _market_up_series(prices=None, ma=56):
    """上证指数 vs 长期均线的市场状态序列（与全局周轴对齐）。

    用于个股级策略的 ``bear_expo``（E8 实验）：市场走弱时降仓。
    判定：周线收盘价 ≥ MA(``ma`` 周) → ``True``。

    > **注意**：不能用 ``make_regime_fn("B")`` 的 ``fn(None, d)`` —— B 方案是"分市场"
    > （``seg_index_for`` 需要个股代码），传 ``None`` 会抛 ``AttributeError``（实测踩坑）。

    Args:
        prices: ``{完整代码: {dates, close}}``；缺省自行加载。
        ma: 均线周数（默认 56 周 ≈ 1 年）。

    Returns:
        list[bool] | None: 与上证周线等长的状态序列。
    """
    try:
        prices = prices or _load_prices()
        idx = prices.get("sh000001") or {}
        dates = idx.get("dates") or []
        cmap = idx.get("close") or {}     # 注意: _load_prices 的 close 是 {日期: 价格} 字典, 不是 list
        if not dates or not cmap:
            LOG.error("[bridge] 市场状态: 上证指数数据缺失")
            return None
        vals = [cmap.get(d) for d in dates]
        if any(v is None for v in vals):
            LOG.error("[bridge] 市场状态: 上证指数价格存在空缺（共 %d 期）", len(vals))
            return None
        out, s = [], 0.0
        for i, c in enumerate(vals):
            s += c
            if i >= ma:
                s -= vals[i - ma]
            avg = (s / (i + 1)) if i < ma else (s / ma)
            out.append(bool(c >= avg))
        n_up = sum(1 for v in out if v)
        LOG.info("[bridge] 市场状态序列: %d 期（MA=%d 周），多头占比 %.1f%%",
                 len(out), ma, 100.0 * n_up / len(out))
        return out
    except Exception as exc:
        LOG.error("[bridge] 市场状态计算异常: %s\n%s", exc, traceback.format_exc())
        return None


def run_one(mode="ttm", n_hold=15, universe=None, tag=None, start_date="2014-01-01",
            keep_equity=False, universe_by_period=None,
            stop_fixed=None, stop_trail=None, stop_port=None, bear_expo=None,
            market_ma=56):
    """跑一套回测（方案 B / 个股级 regime）。

    Args:
        mode: 财务口径（``"ttm"`` / ``"annual"``）。
        n_hold: 目标持仓数（与历史回测一致，便于对比）。
        universe: 限定宇宙；``None`` = 面板全部。
        tag: 结果标签。
        start_date: 回测起始日（默认 2014-01-01）。旧引擎为纯 Python 双层循环，
            **限制窗口是控制耗时的必要手段**（5561 只 × 全历史会耗时数十分钟）。

    Returns:
        dict: ``{"tag":.., "mode":.., "n_stocks": int, "stats": {...}}``
    """
    import regime_layer2_backtest as R           # 延迟导入（重依赖）
    tag = tag or mode
    try:
        stocks, global_dates = build_stocks(mode=mode, universe=universe)
        if not stocks or not global_dates:
            LOG.error("[bridge] %s: 数据为空，跳过", tag)
            return {"tag": tag, "mode": mode, "stats": {}}
        prices = _load_prices()
        indices = _load_indices(prices=prices)
        fn = R.make_regime_fn("B", indices)
        mus = _market_up_series(prices=prices, ma=market_ma) if bear_expo is not None else None
        res = R.run_backtest_layer2(
            stocks, global_dates, "B", fn, "stock",
            N=n_hold, mom_window=52, val_window=260, cost_per_side=0.0012,
            tail_expo=0.0, warmup=220, price_cap=300.0, ind_cap=0.35,
            start_date=start_date, universe_by_period=universe_by_period,
            stop_fixed=stop_fixed, stop_trail=stop_trail, stop_port=stop_port,
            bear_expo=bear_expo, market_up_series=mus)
        stats = {k: v for k, v in res.items() if k not in ("equity_curve", "t_start")}
        LOG.info("[bridge] %s 完成: 宇宙 %d 只 | 年化 %.2f%% 夏普 %.3f 回撤 %.2f%% "
                 "空仓 %.1f%% 换手 %.2f%% 均池 %.1f",
                 tag, len(stocks), stats.get("annualized", 0) * 100, stats.get("sharpe", 0),
                 stats.get("max_drawdown", 0) * 100, stats.get("empty_frac", 0) * 100,
                 stats.get("avg_turnover", 0) * 100, stats.get("avg_quality_pool", 0))
        out = {"tag": tag, "mode": mode, "n_stocks": len(stocks), "stats": stats}
        if keep_equity:
            eq = res.get("equity_curve") or []
            ts = int(res.get("t_start") or 0)
            out["equity"] = list(eq)
            out["dates"] = [int(d) for d in global_dates[ts: ts + len(eq)]]
        return out
    except Exception as exc:
        LOG.error("[bridge] %s 回测异常: %s\n%s", tag, exc, traceback.format_exc())
        return {"tag": tag, "mode": mode, "stats": {}}


def _legacy_universe():
    """旧宇宙：``fundamentals_broad.json`` 中的股票代码（约 1771 只）。

    Returns:
        set[str]: 6 位纯代码集合；文件缺失返回空集合。
    """
    try:
        path = os.path.join(_ROOT, "modules", "strategy", "fundamentals_broad.json")
        if not os.path.exists(path):
            LOG.error("[bridge] 旧宇宙文件不存在: %s", path)
            return set()
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        codes = {str(k).zfill(6) for k in raw.keys()}
        LOG.info("[bridge] 旧宇宙载入: %d 只", len(codes))
        return codes
    except Exception as exc:
        LOG.error("[bridge] 读取旧宇宙异常: %s\n%s", exc, traceback.format_exc())
        return set()


def _ordered_codes():
    """``fundamentals_broad.json`` 的键**有序**列表（顺序有明确含义）。

    **依据**（[docs/10 §6.7](../docs/10-改造方案自审与优化建议.md)）：
    `fetch_fund_broad.py` 先 ``fund = dict(existing)``（基础池 = CSI300 + 中证500），
    再逐个 ``fund[code] = ...`` 追加补充池（``daily_broad.json``）；
    ``fetch_names.py`` 不存在 → ``enrich_names`` 为恒等函数，**不改动键顺序**。

    **实测验证**：
    | 位置 | 实测内容 | 说明 |
    |---|---|---|
    | 前 8 只 | 000001 / 000002 / 000063 / 000100 / 000157 / 000166 / 000301 / 000333 | 平安银行 / 万科A / 中兴 / TCL / 中联重科 / 申万宏源 / 东方盛虹 / 美的 —— **CSI300 蓝筹** |
    | 末 8 只 | 920971 ~ 920992 | **北交所**，绝不可能属于 CSI800 |

    Returns:
        list[str]: 6 位纯代码，按文件原顺序。
    """
    try:
        path = os.path.join(_ROOT, "modules", "strategy", "fundamentals_broad.json")
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return [str(k).zfill(6) for k in raw.keys()]
    except Exception as exc:
        LOG.error("[bridge] 读取有序代码异常: %s\n%s", exc, traceback.format_exc())
        return []


def _prefix_universe(n):
    """取有序代码的前 ``n`` 只（≈ CSI800 主体）。

    Returns:
        set[str]: 6 位纯代码集合。
    """
    return set(_ordered_codes()[:int(n)])


def _suffix_universe(n):
    """取有序代码的后 ``n`` 只（≈ daily_broad 补充部分，含北交所）。

    Returns:
        set[str]: 6 位纯代码集合。
    """
    codes = _ordered_codes()
    return set(codes[-int(n):]) if codes else set()


def compare_hA(n_hold=15, start_date="2014-01-01", save=True):
    """**E5 实验**：验证 H-A —— E1 的优势是否来自 **CSI800 部分**。

    做法：按 ``fundamentals_broad.json`` 的键顺序切分宇宙（顺序 = CSI800 在前、补充在后）：

    | 实验 | 宇宙 | 含义 |
    |---|---|---|
    | **E1** | 全部 1771 只 | 基线（实测可用 1689 只） |
    | **P300** | 前 300 只 | ≈ 沪深 300 |
    | **P500** | 前 500 只 | 大盘主体 |
    | **P800** | 前 800 只 | ≈ 沪深 300 + 中证 500 |
    | **S900** | 后 900 只 | daily_broad 补充部分 |

    **判据**：
    - 若某前缀 ≈ E1，且后缀明显差 → **H-A 成立**（优势来自指数成分池）；
    - 若各前缀相近而全量最优 → 说明补充部分亦有贡献，"指数成分"解释不完整。

    Returns:
        list[dict]: 各实验结果。
    """
    plan = [("E1_full1771", _legacy_universe())]
    for _n in (300, 500, 800):
        _u = _prefix_universe(_n)
        if _u:
            plan.append(("P%d_prefix" % _n, _u))
    _tot = len(_ordered_codes())
    if _tot > 900:
        _u = _suffix_universe(900)
        if _u:
            plan.append(("S900_suffix", _u))
    for _n in (300, 500):
        _u = build_size_universe(as_of="20131231", n=_n)
        if _u:
            plan.append(("M%d_size2013" % _n, _u))
    LOG.info("[bridge] E5 宇宙切分: 文件共 %d 只 → %s", _tot,
             ", ".join("%s(%d)" % (t, len(u)) for t, u in plan))

    results = []
    for tag, univ in plan:
        results.append(run_one(mode="annual", n_hold=n_hold, universe=univ,
                               tag=tag, start_date=start_date))
    table = _format_table(results)
    LOG.info("[bridge] ===== E5 H-A 验证：按宇宙序位切分（N=%d, 起 %s）=====\n%s",
             n_hold, start_date, table)
    if save:
        try:
            payload = {
                "generated_at": _now(), "kind": "E5_universeSplit",
                "n_hold": n_hold, "start_date": start_date,
                "total_codes_in_file": _tot, "results": results,
                "note": ("按 fundamentals_broad.json 键顺序切分（CSI800 在前、daily_broad 补充在后）；"
                         "用于验证 H-A：E1 优势是否来自指数成分池"),
            }
            with open(config.BACKTEST_BASELINE_FILE, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            LOG.info("[bridge] E5 结果已落盘 %s", config.BACKTEST_BASELINE_FILE)
        except Exception as exc:
            LOG.error("[bridge] 落盘 E5 结果异常: %s\n%s", exc, traceback.format_exc())
    return results


def build_liquidity_universe(as_of="20131231", window=52, min_adv=None, top_frac=None):
    """按 ``as_of`` **之前** ``window`` 周的日均成交额构建股票池（**无前视**）。

    这是 R2b（规模/流动性显式过滤）的轻量实现：旧宇宙 ``fundamentals_broad.json``
    隐含了"大盘偏好"（CSI300+500 宽池），扩到全市场后该隐含因子消失导致回撤恶化
    （见 [docs/10 §6.5](../docs/10-改造方案自审与优化建议.md)）。本函数把该偏好
    **显式化、可调参**：用回测起点前的成交额分位选池，避免用未来数据筛历史。

    Args:
        as_of: 截止日（YYYYMMDD），只使用该日及之前的数据。
        window: 回看周数（默认 52 周 ≈ 1 年）。
        min_adv: 日均成交额下限（元）；与 ``top_frac`` 二选一。
        top_frac: 取成交额最高的前 N 比例（如 0.3 表示前 30%）。

    Returns:
        set[str]: 入选的 6 位纯代码集合。
    """
    try:
        df = pd.read_parquet(config.PRICE_PANEL_FILE, columns=["code", "date", "amount"])
        df = df[df["date"] <= int(as_of)]
        if df.empty:
            LOG.error("[bridge] as_of=%s 之前无价格数据", as_of)
            return set()
        df = df.sort_values(["code", "date"]).groupby("code", as_index=False).tail(window)
        adv = df.groupby("code")["amount"].mean() / _TRADING_DAYS_PER_WEEK      # 周均 → 日均
        adv = adv.dropna()
        if min_adv is not None:
            sel = adv[adv >= float(min_adv)]
            tag = "日均成交额 ≥ %.2f 亿" % (float(min_adv) / 1e8)
        elif top_frac is not None:
            cutoff = adv.quantile(1.0 - float(top_frac))
            sel = adv[adv >= cutoff]
            tag = "日均成交额前 %.0f%%（阈值 %.2f 亿）" % (float(top_frac) * 100, cutoff / 1e8)
        else:
            LOG.error("[bridge] 必须指定 min_adv 或 top_frac")
            return set()
        codes = {str(c)[2:] if str(c)[:2] in ("sh", "sz", "bj") else str(c) for c in sel.index}
        LOG.info("[bridge] 流动性池（%s，as_of=%s，%d 周）: %d 只 / 全市场 %d 只",
                 tag, as_of, window, len(codes), adv.shape[0])
        return codes
    except Exception as exc:
        LOG.error("[bridge] 构建流动性池异常: %s\n%s", exc, traceback.format_exc())
        return set()


def _adjust_dates(start_year=2013, end_year=2026):
    """生成半年度调整日（每年 6/30 与 12/31，与沪深300调整节奏一致）。

    Returns:
        list[int]: ``[20130630, 20131231, 20140630, ...]``
    """
    out = []
    for y in range(int(start_year), int(end_year) + 1):
        out.append(y * 10000 + 630)
        out.append(y * 10000 + 1231)
    return out


def _latest_disclosed_period(adj):
    """返回 ``adj`` 日时**已披露**的最新报告期（按法定披露截止日推断）。

    规则：一季报/年报 → 4/30、半年报 → 8/31、三季报 → 10/31。
    这是**时点对齐**的关键：避免用"尚未公告"的财报（否则构成前视）。

    Args:
        adj: 调整日，形如 ``20140630``。

    Returns:
        int: 报告期，形如 ``20140331``。
    """
    y, md = int(adj) // 10000, int(adj) % 10000
    if md >= 1031:
        return y * 10000 + 930
    if md >= 831:
        return y * 10000 + 630
    if md >= 430:
        return y * 10000 + 331
    return (y - 1) * 10000 + 1231


def build_rolling_universe(n=300, start="20131231", end="20260630", metric="mktcap"):
    """**R0a 去前视**：按半年度调整日**滚动**构建"时点可见"的规模前 N 池。

    **为什么需要**：`fundamentals_broad.json`（2026 年抓取）含"指数成分前视偏差"
    （见 [docs/10 §6.9](../docs/10-改造方案自审与优化建议.md)）。本函数每期只用
    **当时可见**的信息重排规模，模拟真实指数调整，从而得到无前视基线。

    **规模口径**（``metric``）：
    - ``"mktcap"``（默认）：``(amount / volume) × TOTAL_SHARE``
      —— ``amount/volume`` 是**成交均价**（元/股），**不受价格面板"前复权"影响**
      （价格面板 ``close`` 为前复权价，实测万科 A 的"2013 年收盘价"显示 2193 元，不可用）；
    - ``"equity"``：直接用 ``TOTAL_EQUITY``（净资产），最保守。

    **时点对齐**（两处均无前视）：
    1. 价格：取 ``adj`` 日**之前最后一根周线**；
    2. 财务：取 ``adj`` 日**已披露**的最新报告期（``_latest_disclosed_period``）。

    Args:
        n: 每期取规模前多少只。
        start / end: 起止调整日（YYYYMMDD）。
        metric: ``"mktcap"`` 或 ``"equity"``。

    Returns:
        dict: ``{调整日(int): set(6 位纯代码)}``；异常返回空 dict。
    """
    try:
        cols = ["code", "date", "amount", "volume"]
        px = pd.read_parquet(config.PRICE_PANEL_FILE, columns=cols)
        px = px[(px["date"] <= int(end))].copy()
        px["pure"] = px["code"].map(
            lambda c: str(c)[2:] if str(c)[:2] in ("sh", "sz", "bj") else str(c))
        fcols = ["code", "period", "TOTAL_EQUITY"] + (["TOTAL_SHARE"] if metric == "mktcap" else [])
        fd = pd.read_parquet(config.FUND_PANEL_FILE, columns=fcols)
        fd["period_i"] = fd["period"].astype(int)

        out = {}
        for adj in _adjust_dates(int(str(start)[:4]), int(str(end)[:4])):
            if adj < int(start) or adj > int(end):
                continue
            p = px[px["date"] <= adj].sort_values(["code", "date"])
            p = p.groupby("pure", as_index=False).tail(1)
            cut = _latest_disclosed_period(adj)
            f = fd[fd["period_i"] <= cut].sort_values(["code", "period_i"])
            f = f.groupby("code", as_index=False).tail(1)
            if p.empty or f.empty:
                continue
            m = p.merge(f, left_on="pure", right_on="code", how="inner")
            if metric == "mktcap":
                m["vwap"] = m["amount"] / m["volume"]
                m.loc[m["volume"] <= 0, "vwap"] = None
                m["size"] = (m["vwap"] * m["TOTAL_SHARE"]).abs()
            else:
                m["size"] = m["TOTAL_EQUITY"].abs()
            m = m.dropna(subset=["size"])
            if m.empty:
                continue
            top = m.nlargest(int(n), "size")
            out[adj] = {str(c).zfill(6) for c in top["pure"].tolist()}
            LOG.info("[bridge] 滚动池 %d: %d 只（口径=%s，报告期<=%d，规模区间 %.1f~%.1f 亿，可比 %d）",
                     adj, len(out[adj]), metric, cut,
                     top["size"].min() / 1e8, top["size"].max() / 1e8, len(m))
        return out
    except Exception as exc:
        LOG.error("[bridge] 滚动池构建异常: %s\n%s", exc, traceback.format_exc())
        return {}


def compare_rolling(n_hold=15, start_date="2014-01-01", save=True):
    """**E6 实验**：滚动定池（**去前视**）vs 含前视池 vs 静态池。

    | 实验 | 定池方式 | 前视 |
    |---|---|---|
    | **P300** | `fundamentals_broad` 顺序前 300（= 2026 年沪深300） | ⚠️ **有** |
    | **M300** | 2013 年末净资产前 300（一次定池，不随指数调整） | ✅ 无 |
    | **R300_dyn** | **半年度滚动，成交均价×总股本 前 300** | ✅ **无** |
    | **R800_dyn** | 半年度滚动，前 800 | ✅ 无 |

    **判据**：
    - 若 ``R300_dyn`` ≈ ``M300``（约 4%）→ 真实水平确认，且**动态调整未带来额外收益**；
    - 若 ``R300_dyn`` 明显高于 ``M300`` → 动态调整本身有效（仍是可信收益）。

    Returns:
        list[dict]: 各实验结果。
    """
    plan = []
    _u = _prefix_universe(300)
    if _u:
        plan.append(("P300_prefix(前视)", _u, None))
    _u = build_size_universe(as_of="20131231", n=300)
    if _u:
        plan.append(("M300_size2013", _u, None))
    for _tag, _n in (("R300_dyn", 300), ("R800_dyn", 800)):
        _by = build_rolling_universe(n=_n, start="20131231", end="20260630", metric="mktcap")
        if _by:
            _union = set().union(*_by.values())     # 并集：保证每期完整，同时减少引擎遍历量
            plan.append((_tag, _union, _by))

    results = []
    for tag, univ, by_period in plan:
        results.append(run_one(mode="annual", n_hold=n_hold, universe=univ,
                               tag=tag, start_date=start_date,
                               universe_by_period=by_period))
    table = _format_table(results)
    LOG.info("[bridge] ===== E6 R0a 去前视：滚动定池对比（N=%d, 起 %s）=====\n%s",
             n_hold, start_date, table)
    if save:
        try:
            payload = {
                "generated_at": _now(), "kind": "E6_rollingUniverse",
                "n_hold": n_hold, "start_date": start_date, "results": results,
                "note": ("滚动定池用半年度调整日 + 当时可见的成交均价×总股本（无前视）+ "
                         "已披露财报口径，模拟真实指数调整；用于替代含前视的 fundamentals_broad"),
            }
            with open(config.BACKTEST_BASELINE_FILE, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            LOG.info("[bridge] E6 结果已落盘 %s", config.BACKTEST_BASELINE_FILE)
        except Exception as exc:
            LOG.error("[bridge] 落盘 E6 结果异常: %s\n%s", exc, traceback.format_exc())
    return results


def compare_risk(n_hold=15, start_date="2014-01-01", save=True):
    """**E8 实验**：市场层风控 vs 组合层风控（无前视滚动池 P300）。

    **背景（E7 的结论）**：单票止损（固定 / 移动）对组合回撤**几乎无效**
    （SF1 固定 -15% 后回撤仍为 -51.83%，分毫未动），说明回撤来自**系统性下跌**而非个股踩雷。
    根因：引擎在 ``regime_scope='stock'`` 下 ``expo`` 恒为 0.9 ——
    **个股级 regime 只做入场筛选，完全没有市场层面的仓位管理**。

    | 实验 | 规则 |
    |---|---|
    | **BASE** | 无风控（年化 8.30% / 回撤 -51.83%） |
    | **MB1** | 熊市半仓：市场 regime 转弱 → 暴露 0.9→0.5 |
    | **MB2** | 熊市空仓：→ 暴露 0.0 |
    | **SP1** | 组合回撤 -20% → 暴露减半 |
    | **SP2** | 组合回撤 -15% → 暴露减半 |
    | **BEST** | 熊市半仓 **+** 组合 -20% 减半（两层叠加） |

    **判据**：最大回撤降至 **-30% 以内**且年化损失 < 2pp。

    Returns:
        list[dict]: 各实验结果。
    """
    _by = build_rolling_universe(n=300, start="20131231", end="20260630", metric="mktcap")
    if not _by:
        LOG.error("[bridge] E8: 滚动池构建失败，跳过")
        return []
    _union = set().union(*_by.values())
    plan = [
        ("BASE_无风控", {}),
        ("MB1_熊市半仓", {"bear_expo": 0.5}),
        ("MB2_熊市空仓", {"bear_expo": 0.0}),
        ("SP1_组合-20%降半", {"stop_port": -0.20}),
        ("SP2_组合-15%降半", {"stop_port": -0.15}),
        ("BEST_熊半仓+组合-20%", {"bear_expo": 0.5, "stop_port": -0.20}),
    ]
    results = []
    for tag, kw in plan:
        results.append(run_one(mode="annual", n_hold=n_hold, universe=_union,
                               universe_by_period=_by, tag=tag,
                               start_date=start_date, **kw))
    table = _format_table(results)
    LOG.info("[bridge] ===== E8 市场层 vs 组合层风控（无前视滚动池 P300，N=%d，起 %s）=====\n%s",
             n_hold, start_date, table)
    if save:
        try:
            payload = {
                "generated_at": _now(), "kind": "E8_riskControl",
                "n_hold": n_hold, "start_date": start_date, "results": results,
                "note": ("单票止损无效（E7），改用市场层降仓（bear_expo）与组合层降仓（stop_port）；"
                         "判据：回撤 -30% 以内且年化损失 < 2pp"),
            }
            with open(config.BACKTEST_BASELINE_FILE, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            LOG.info("[bridge] E8 结果已落盘 %s", config.BACKTEST_BASELINE_FILE)
        except Exception as exc:
            LOG.error("[bridge] 落盘 E8 结果异常: %s\n%s", exc, traceback.format_exc())
    return results


def compare_stops(n_hold=15, start_date="2014-01-01", save=True):
    """**E7 实验**：止损规则对回撤的改善 —— 全部在**无前视滚动池**上测。

    **背景**：R0a 确认新基线 ``R300_dyn`` = 年化 8.30% / 夏普 0.287 / **最大回撤 -51.83%** /
    Calmar 仅 **0.16**。回撤是当前唯一的结构性问题，且**不需要新模型或新数据**即可改善。

    | 实验 | 规则 |
    |---|---|
    | **BASE** | 无止损（基线） |
    | **SF1** | 固定止损：单票自**买入价**跌破 -15% → 清仓 |
    | **SF2** | 固定止损 -25% |
    | **ST1** | 移动止损：单票自**持仓期最高价**回撤 -15% → 清仓 |
    | **ST2** | 移动止损 -25% |
    | **SP1** | 组合级：净值自历史峰值回撤 -20% → **暴露减半** |

    **判据**：最大回撤显著下降（目标 **-30% 以内**）且年化损失 < 2pp → 值得上线。

    Returns:
        list[dict]: 各实验结果。
    """
    _by = build_rolling_universe(n=300, start="20131231", end="20260630", metric="mktcap")
    if not _by:
        LOG.error("[bridge] E7: 滚动池构建失败，跳过")
        return []
    _union = set().union(*_by.values())
    plan = [
        ("BASE_无止损", {}),
        ("SF1_固定-15%", {"stop_fixed": -0.15}),
        ("SF2_固定-25%", {"stop_fixed": -0.25}),
        ("ST1_移动-15%", {"stop_trail": -0.15}),
        ("ST2_移动-25%", {"stop_trail": -0.25}),
        ("SP1_组合-20%降半", {"stop_port": -0.20}),
    ]
    results = []
    for tag, kw in plan:
        results.append(run_one(mode="annual", n_hold=n_hold, universe=_union,
                               universe_by_period=_by, tag=tag,
                               start_date=start_date, **kw))
    table = _format_table(results)
    LOG.info("[bridge] ===== E7 止损规则对比（无前视滚动池 P300，N=%d，起 %s）=====\n%s",
             n_hold, start_date, table)
    if save:
        try:
            payload = {
                "generated_at": _now(), "kind": "E7_stopLoss",
                "n_hold": n_hold, "start_date": start_date, "results": results,
                "note": ("全部在无前视滚动池 R300_dyn 上测试；判据：回撤目标 -30% 以内且年化损失 < 2pp"),
            }
            with open(config.BACKTEST_BASELINE_FILE, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            LOG.info("[bridge] E7 结果已落盘 %s", config.BACKTEST_BASELINE_FILE)
        except Exception as exc:
            LOG.error("[bridge] 落盘 E7 结果异常: %s\n%s", exc, traceback.format_exc())
    return results


def build_size_universe(as_of="20131231", n=300):
    """用 ``as_of`` 时点的**净资产规模**排序取前 ``n`` 只（**无前视**）。

    **为什么不用市值**：价格面板为**前复权价**（实测万科 A 2013 年显示 **2193 元**），
    前复权价 × 总股本 ≠ 市值，且复权因子因股而异（偏差不均匀）→ **不能用于市值排序**。
    改用 ``TOTAL_EQUITY``（净资产）作规模代理：**复权无关、无前视、口径统一**。

    取舍：净资产前 300 ≠ 市值前 300（银行股 PB<1 会被高估、高估值成长股被低估），
    但**规模维度的信息量一致**，足以回答"用当时可见的规模信息选池能否复现 P300"。

    原市值口径 = ``as_of`` 前最后一周末收盘价 × ``as_of`` 前最新一期 ``TOTAL_SHARE``。

    **用途（E5b）**：校验 E5 中 ``P300_prefix`` 的 14.59% 是否来自**前视偏差**。
    ``fundamentals_broad.json`` 是 2026 年抓取的，其"前 300 只"是 **2026 年的 CSI300 成分**；
    而用 2013 年末市值排序，则是**当时真实可得的信息**。两者差距即为前视偏误。

    Args:
        as_of: 截止日（YYYYMMDD）。
        n: 取前多少只。

    Returns:
        set[str]: 入选的 6 位纯代码集合。
    """
    try:
        fd = pd.read_parquet(config.FUND_PANEL_FILE,
                             columns=["code", "period", "TOTAL_EQUITY"]).dropna(subset=["TOTAL_EQUITY"])
        fd = fd[fd["period"].astype(str) <= str(as_of)]      # period 为字符串，字典序等价日期序
        if fd.empty:
            LOG.error("[bridge] 规模池: as_of=%s 之前无财务数据", as_of)
            return set()
        fd = fd.sort_values(["code", "period"]).groupby("code", as_index=False).tail(1)
        fd["size"] = fd["TOTAL_EQUITY"].abs()
        top = fd.nlargest(int(n), "size")
        codes = {str(c).zfill(6) for c in top["code"].tolist()}
        LOG.info("[bridge] 规模池（as_of=%s 净资产前 %d，无前视）: 命中 %d 只；"
                 "净资产区间 %.1f~%.1f 亿；可比 %d 只",
                 as_of, n, len(codes), top["size"].min() / 1e8,
                 top["size"].max() / 1e8, len(fd))
        return codes
    except Exception as exc:
        LOG.error("[bridge] 市值池构建异常: %s\n%s", exc, traceback.format_exc())
        return set()


def compare_liquidity(n_hold=15, start_date="2014-01-01", save=True):
    """**E4 实验**：在 E3（TTM + 全宇宙）之上叠加规模/流动性过滤，验证能否恢复 E1 水平。

    | 实验 | 说明 |
    |---|---|
    | E1 | 年报 + 旧宇宙（基线，13.07% / 夏普 0.449 / 回撤 -44.5%） |
    | E3 | TTM + 全宇宙（6.58% / 0.182 / -55.34%） |
    | **E4a** | TTM + 流动性池（日均成交额 ≥ 5000 万） |
    | **E4b** | TTM + 流动性池（日均成交额 ≥ 1 亿） |
    | **E4c** | TTM + 流动性池（日均成交额 ≥ 2 亿） |

    **判据**：若某个 E4 达到或超过 E1 → 证明"**覆盖更全 + 显式约束**"优于
    "窄宇宙 + 隐含约束"，数据升级的价值成立。

    Returns:
        list[dict]: 各实验结果。
    """
    legacy = _legacy_universe()
    plan = []
    if legacy:
        plan.append(("E1_annual_legacyUniv", "annual", legacy))
    plan.append(("E3_ttm_fullUniv", "ttm", None))
    for name, thr in [("E4a_liq50m", 5e7), ("E4b_liq100m", 1e8), ("E4c_liq200m", 2e8)]:
        uni = build_liquidity_universe(as_of="20131231", window=52, min_adv=thr)
        if uni:
            plan.append((name, "ttm", uni))

    results = []
    for tag, mode, univ in plan:
        results.append(run_one(mode=mode, n_hold=n_hold, universe=univ,
                               tag=tag, start_date=start_date))
    table = _format_table(results)
    LOG.info("[bridge] ===== E4 规模/流动性过滤对比（N=%d, 起 %s）=====\n%s",
             n_hold, start_date, table)
    if save:
        try:
            payload = {
                "generated_at": _now(),
                "kind": "E4_liquidity",
                "n_hold": n_hold, "start_date": start_date,
                "results": results,
                "note": ("E4 在 E3 基础上叠加'日均成交额'过滤（用回测起点前 52 周数据定池，无前视）；"
                         "判据：达到或超过 E1 即证明'覆盖更全+显式约束'优于'窄宇宙+隐含约束'"),
            }
            with open(config.BACKTEST_BASELINE_FILE, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            LOG.info("[bridge] E4 结果已落盘 %s", config.BACKTEST_BASELINE_FILE)
        except Exception as exc:
            LOG.error("[bridge] 落盘 E4 结果异常: %s\n%s", exc, traceback.format_exc())
    return results


def analyze_years(n_hold=15, start_date="2014-01-01", save=True):
    """**H-B 检验**：按年拆解收益，判断"收益是否集中在少数年份"。

    过拟合与"单一年份 beta"的典型征兆：总年化看似不错，但拆开后收益几乎
    全部来自 1~2 个年份（2015 杠杆牛 / 2019-2020 结构牛），其余年份为 0 或负。
    这类曲线**不可外推**。同时输出"剔除最好年份后的年化"作为鲁棒性上界。

    Returns:
        dict: ``{tag: {"years": {...}, "ann":.., "ann_ex_best":..}}``
    """
    legacy = _legacy_universe()
    plan = [("E1_annual_legacyUniv", "annual", legacy), ("E3_ttm_fullUniv", "ttm", None)]
    for _name, _thr in [("E4a_liq50m", 5e7), ("E4b_liq100m", 1e8), ("E4c_liq200m", 2e8)]:
        _uni = build_liquidity_universe(as_of="20131231", window=52, min_adv=_thr)
        if _uni:
            plan.append((_name, "ttm", _uni))
    out = {}
    for tag, mode, univ in plan:
        r = run_one(mode=mode, n_hold=n_hold, universe=univ, tag=tag,
                    start_date=start_date, keep_equity=True)
        eq, ds = r.get("equity") or [], r.get("dates") or []
        if len(eq) < 2 or len(ds) != len(eq):
            LOG.error("[bridge] %s 净值/日期不可用（%d/%d）", tag, len(eq), len(ds))
            continue
        year_end = {}
        for i, d in enumerate(ds):
            year_end[int(d) // 10000] = eq[i]
        years = sorted(year_end)
        rets = {}
        for j, y in enumerate(years):
            base = eq[0] if j == 0 else year_end[years[j - 1]]
            rets[y] = (year_end[y] / base - 1) if base else 0.0
        n = len(years)
        ann = (1 + (eq[-1] - 1)) ** (1.0 / n) - 1 if n else 0.0
        best = max(rets.items(), key=lambda kv: kv[1])
        worst = min(rets.items(), key=lambda kv: kv[1])
        pos = sum(1 for v in rets.values() if v > 0)
        rest = {y: v for y, v in rets.items() if y != best[0]}
        comp = 1.0
        for v in rest.values():
            comp *= (1 + v)
        ann_ex = comp ** (1.0 / max(1, len(rest))) - 1
        out[tag] = {"years": rets, "ann": ann, "best": list(best), "worst": list(worst),
                    "positive_years": "%d/%d" % (pos, n), "ann_ex_best": ann_ex}
        body = "\n".join(
            "  %d: %+7.2f%%%s" % (y, rets[y] * 100,
                                  "   <-- 最好" if y == best[0] else
                                  ("   <-- 最差" if y == worst[0] else ""))
            for y in years)
        LOG.info("[bridge] ===== %s 分年收益（共 %d 年）=====\n%s\n"
                 "  正收益年份 %d/%d | 最好 %d(%+.2f%%) | 最差 %d(%+.2f%%)\n"
                 "  复合年化 %+.2f%% | **剔除最好年份后年化 %+.2f%%**",
                 tag, n, body, pos, n, best[0], best[1] * 100,
                 worst[0], worst[1] * 100, ann * 100, ann_ex * 100)
    if save and out:
        try:
            payload = {
                "generated_at": _now(), "kind": "H-B_yearly",
                "n_hold": n_hold, "start_date": start_date, "results": out,
                "note": ("分年收益用于检验'收益是否集中在少数年份'；"
                         "ann_ex_best = 剔除最好年份后的复合年化（鲁棒性上界）"),
            }
            with open(config.BACKTEST_YEARLY_FILE, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            LOG.info("[bridge] 分年结果已落盘 %s", config.BACKTEST_YEARLY_FILE)
        except Exception as exc:
            LOG.error("[bridge] 落盘分年结果异常: %s\n%s", exc, traceback.format_exc())
    return out


def _format_table(results):
    """把结果格式化为对齐的对比表（字符串）。"""
    head = ("%-24s %8s %8s %9s %8s %8s %8s" %
            ("实验", "年化", "夏普", "最大回撤", "空仓%", "换手%", "均池"))
    lines = [head, "-" * len(head)]
    for item in results:
        s = item.get("stats") or {}
        lines.append("%-24s %7.2f%% %8.3f %8.2f%% %7.1f%% %7.2f%% %8.1f" % (
            item.get("tag", "?"),
            s.get("annualized", 0) * 100, s.get("sharpe", 0),
            s.get("max_drawdown", 0) * 100, s.get("empty_frac", 0) * 100,
            s.get("avg_turnover", 0) * 100, s.get("avg_quality_pool", 0)))
    return "\n".join(lines)


def compare(n_hold=15, start_date="2014-01-01", save=True, include_full_universe=False):
    """分解实验：隔离"财务时效"与"宇宙扩容"各自的贡献。

    +----+------------------+--------------------------------------------+
    | E1 | 年报 + 旧宇宙     | 基线（旧数据口径，宇宙 1771 只）             |
    | E2 | TTM  + 旧宇宙     | E2 vs E1 = **财务时效**的贡献（行业齐全，干净）|
    | E3 | TTM  + 全宇宙     | E3 vs E2 = **宇宙扩容**的贡献（行业缺失，有偏差）|
    +----+------------------+--------------------------------------------+

    Args:
        n_hold: 目标持仓数。
        start_date: 回测起始日（控制耗时的关键）。
        save: 是否落盘对比结果。
        include_full_universe: 是否把 E3（5561 只）纳入（耗时约 3~4 倍）。

    Returns:
        list[dict]: 各实验的结果。
    """
    legacy = _legacy_universe()
    if not legacy:
        LOG.error("[bridge] 旧宇宙为空，对比中止")
        return []
    plan = [
        ("E1_annual_legacyUniv", "annual", legacy),
        ("E2_ttm_legacyUniv", "ttm", legacy),
    ]
    if include_full_universe:
        plan.append(("E3_ttm_fullUniv", "ttm", None))

    results = []
    for tag, mode, univ in plan:
        results.append(run_one(mode=mode, n_hold=n_hold, universe=univ,
                               tag=tag, start_date=start_date))

    table = _format_table(results)
    LOG.info("[bridge] ===== 数据改造验收对比（N=%d, 起 %s）=====\n%s",
             n_hold, start_date, table)
    if save:
        try:
            payload = {
                "generated_at": _now(),
                "n_hold": n_hold, "start_date": start_date,
                "legacy_universe": len(legacy),
                "results": results,
                "note": ("E2 vs E1 隔离财务时效（TTM）的贡献；"
                         "E3 vs E2 隔离宇宙扩容的贡献（行业数据缺失，属已知偏差）"),
            }
            with open(config.BACKTEST_BASELINE_FILE, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            LOG.info("[bridge] 对比结果已落盘 %s", config.BACKTEST_BASELINE_FILE)
        except Exception as exc:
            LOG.error("[bridge] 落盘对比结果异常: %s\n%s", exc, traceback.format_exc())
    return results


if __name__ == "__main__":      # pragma: no cover - 手动执行入口
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="[%(asctime)s.%(msecs)03d] %(levelname)-5s %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    # 用法：python -m panels.backtest_bridge [full|liq]
    #   不带参数 → E1/E2（财务口径对比）
    #   full     → 追加 E3（全宇宙）
    #   liq      → E4 规模/流动性过滤对比（E1/E3/E4a/E4b/E4c）
    _arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if _arg == "liq":
        compare_liquidity()
    elif _arg == "years":
        analyze_years()
    elif _arg == "hA":
        compare_hA()
    elif _arg == "roll":
        compare_rolling()
    elif _arg == "stop":
        compare_stops()
    elif _arg == "risk":
        compare_risk()
    else:
        compare(include_full_universe=(_arg == "full"))

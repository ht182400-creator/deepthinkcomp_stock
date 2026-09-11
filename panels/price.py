# -*- coding: utf-8 -*-
"""价格面板构建（R1a）。

**解决的隐患（docs/10 H1）**：``read_qfq()`` 前复权锚定"最新交易日"，
每次发生除权除息都会重算**全部历史价格** → 同一策略间隔一个月跑两次回测结果不同，
且历史选股结果会系统性漂移（``price_cap`` 等绝对价格阈值的判定被改变）。

本模块把**复权后的周线**落盘为 Parquet，回测只读快照、不再重算，
并把复权基准日 ``base_date`` 写入 ``meta.json``，便于识别版本漂移。

**同时解决 R4**：周线保留 ``open/high/low/close/volume/amount`` 全字段。
旧实现 ``build_universe_layer2`` 只保留 close，
导致波动率 / 换手率 / 流动性因子无法计算。
"""
import logging
import os
import sys
import time
import traceback

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))      # .../panels
_ROOT = os.path.dirname(_HERE)                          # 项目根
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_STRATEGY = os.path.join(_ROOT, "modules", "strategy")
if _STRATEGY not in sys.path:
    sys.path.insert(0, _STRATEGY)

import config                                          # noqa: E402
from panels import meta as panel_meta                  # noqa: E402

LOG = logging.getLogger(__name__)

_MARKETS = ("sh", "sz", "bj")
_LDAY_SUFFIX = ".day"
_DATE_FMT = "%Y%m%d"
_PROGRESS_STEP = 300        # 每处理 N 只输出一次进度


def _load_tdx():
    """导入通达信读取器并一次性加载权息表（避免逐只重复读 18MB CSV）。

    Returns:
        tuple: ``(tdx_day_reader 模块, xdxr_map)``；失败返回 ``(None, None)``。
    """
    try:
        import tdx_day_reader as tdr
        xdxr = tdr._load_xdxr_map()
        LOG.info("[price] 权息表加载完成，覆盖 %d 只标的", len(xdxr or {}))
        return tdr, xdxr
    except Exception as exc:
        LOG.error("[price] 加载通达信读取器失败: %s\n%s", exc, traceback.format_exc())
        return None, None


def list_lday_codes(markets=_MARKETS):
    """扫描 ``vipdoc/{market}/lday`` 得到全部代码（**含已退市**）。

    Args:
        markets: 市场目录列表。

    Returns:
        list[tuple]: ``[(code, market), ...]``，code 为带前缀完整代码。
    """
    out = []
    try:
        for market in markets:
            d = os.path.join(config.TDX_ROOT, market, "lday")
            if not os.path.isdir(d):
                LOG.warning("[price] 目录不存在: %s", d)
                continue
            for name in os.listdir(d):
                if not name.endswith(_LDAY_SUFFIX):
                    continue
                pure = name[:-len(_LDAY_SUFFIX)]
                if pure.startswith(market):
                    pure = pure[len(market):]
                out.append((market + pure, market))
        LOG.info("[price] lday 扫描到 %d 个标的（含退市）", len(out))
        return out
    except Exception as exc:
        LOG.error("[price] 扫描 lday 异常: %s\n%s", exc, traceback.format_exc())
        return out


def to_weekly(bars):
    """日线（升序）→ ISO 周线，保留 OHLCV 全字段。

    Args:
        bars: ``read_qfq`` 返回的日线列表（含 date/open/high/low/close/volume/amount）。

    Returns:
        pandas.DataFrame | None: 列 = ``date/year/week/open/high/low/close/volume/amount``。
    """
    if not bars:
        return None
    try:
        df = pd.DataFrame(bars)
        need = {"date", "open", "high", "low", "close", "volume"}
        if not need.issubset(df.columns):
            LOG.error("[price] 日线字段缺失，需要 %s，实际 %s", need, list(df.columns))
            return None
        dt = pd.to_datetime(df["date"].astype(str), format=_DATE_FMT, errors="coerce")
        iso = dt.dt.isocalendar()
        df = df.assign(_y=iso["year"].values, _w=iso["week"].values)
        df = df.dropna(subset=["_y", "_w"])
        if df.empty:
            return None
        agg = {
            "date": ("date", "max"),
            "open": ("open", "first"),
            "high": ("high", "max"),
            "low": ("low", "min"),
            "close": ("close", "last"),
            "volume": ("volume", "sum"),
        }
        if "amount" in df.columns:
            agg["amount"] = ("amount", "sum")
        wk = (df.groupby(["_y", "_w"], sort=True)
                .agg(**agg)
                .reset_index()
                .rename(columns={"_y": "year", "_w": "week"}))
        return wk
    except Exception as exc:
        LOG.error("[price] 周线聚合异常: %s\n%s", exc, traceback.format_exc())
        return None


def latest_trade_date(codes=None):
    """取数据中的最新交易日（复权基准日 base_date）。

    Args:
        codes: 限定代码；缺省用上证指数（最快且必然存在）。

    Returns:
        int | None: YYYYMMDD。
    """
    tdr, _ = _load_tdx()
    if tdr is None:
        return None
    try:
        probe = (codes or ["sh000001"])[0]
        bars = tdr.read_day(probe)
        if not bars:
            return None
        return int(bars[-1]["date"])
    except Exception as exc:
        LOG.error("[price] 获取最新交易日异常: %s\n%s", exc, traceback.format_exc())
        return None


def build_price_panel(codes=None, limit=None, save=True, markets=_MARKETS):
    """构建全市场前复权周线面板并落盘。

    Args:
        codes: 指定 ``(code, market)`` 列表；缺省扫描 ``lday``（含退市股）。
        limit: 仅处理前 N 只（用于冒烟验证）。
        save: 是否落盘。
        markets: 市场目录。

    Returns:
        dict: ``{"codes": int, "rows": int, "skipped": int, "base_date": int|None}``
    """
    result = {"codes": 0, "rows": 0, "skipped": 0, "base_date": None}
    tdr, xdxr = _load_tdx()
    if tdr is None:
        LOG.error("[price] 通达信读取器不可用，构建中止")
        return result

    targets = codes or list_lday_codes(markets=markets)
    if limit:
        targets = targets[:limit]
    frames = []
    t0 = time.time()
    for i, (code, _market) in enumerate(targets, 1):
        try:
            bars = tdr.read_qfq(code, _xdxr_map=xdxr)
            if not bars:
                result["skipped"] += 1
                continue
            wk = to_weekly(bars)
            if wk is None or len(wk) < config.PRICE_MIN_BARS:
                result["skipped"] += 1
                continue
            wk.insert(0, "code", code)
            frames.append(wk)
            result["codes"] += 1
        except Exception as exc:
            result["skipped"] += 1
            LOG.warning("[price] %s 处理失败，跳过: %s", code, exc)
        if i % _PROGRESS_STEP == 0:
            LOG.info("[price] 已处理 %d/%d（成功 %d，跳过 %d，耗时 %.0fs）",
                     i, len(targets), result["codes"], result["skipped"], time.time() - t0)

    if not frames:
        LOG.error("[price] 无可用价格数据")
        return result

    panel = pd.concat(frames, ignore_index=True)
    panel = panel[["code", "date", "year", "week",
                   "open", "high", "low", "close", "volume", "amount"]]
    panel = panel.sort_values(["code", "year", "week"]).reset_index(drop=True)
    result["rows"] = len(panel)
    result["base_date"] = int(panel["date"].max()) if len(panel) else None
    LOG.info("[price] 面板构建完成: %d 只 × %d 行 | base_date=%s | 耗时 %.0fs",
             result["codes"], result["rows"], result["base_date"], time.time() - t0)

    if save:
        try:
            os.makedirs(os.path.dirname(config.PRICE_PANEL_FILE), exist_ok=True)
            panel.to_parquet(config.PRICE_PANEL_FILE, index=False, compression="zstd")
            size_mb = os.path.getsize(config.PRICE_PANEL_FILE) / 1024 / 1024
            LOG.info("[price] 已落盘 %s (%.1f MB)", config.PRICE_PANEL_FILE, size_mb)
        except Exception as exc:
            LOG.error("[price] 落盘价格面板异常: %s\n%s", exc, traceback.format_exc())
    return result


def load_price_panel(columns=None):
    """读取价格面板（回测入口应使用本函数，而非重新计算复权）。

    Args:
        columns: 需要的列；缺省全部。

    Returns:
        pandas.DataFrame | None
    """
    try:
        if not os.path.exists(config.PRICE_PANEL_FILE):
            LOG.warning("[price] 价格面板不存在: %s", config.PRICE_PANEL_FILE)
            return None
        return pd.read_parquet(config.PRICE_PANEL_FILE, columns=columns)
    except Exception as exc:
        LOG.error("[price] 读取价格面板异常: %s\n%s", exc, traceback.format_exc())
        return None


def main(limit=None, save=True):
    """构建入口：价格面板 + 更新元信息（记录 base_date）。

    Returns:
        dict: 构建统计。
    """
    try:
        panel_meta.save_field_map()
        result = build_price_panel(limit=limit, save=save)
        if save and result["rows"]:
            prev = panel_meta.load_meta() or {}
            meta = panel_meta.build_meta(
                base_date=result["base_date"],
                field_map_version=panel_meta.load_field_map()[1],
                periods=prev.get("periods"),
                extra={
                    "price_codes": result["codes"],
                    "price_rows": result["rows"],
                    "price_skipped": result["skipped"],
                    "price_fields": config.PRICE_PANEL_FIELDS,
                    "price_note": "前复权周线快照；回测只读本面板以保证可复现（H1）",
                },
            )
            panel_meta.save_meta(meta)
        return result
    except Exception as exc:
        LOG.error("[price] 构建异常: %s\n%s", exc, traceback.format_exc())
        return {"codes": 0, "rows": 0, "skipped": 0, "base_date": None}


if __name__ == "__main__":      # pragma: no cover - 手动执行入口
    import json
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="[%(asctime)s.%(msecs)03d] %(levelname)-5s %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    # 用法：python -m panels.price [limit]
    #   带 limit  → 冒烟模式（只处理前 N 只，**不落盘**，避免污染正式面板）
    #   不带 limit → 全量构建并落盘
    _limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(json.dumps(main(limit=_limit, save=_limit is None), ensure_ascii=False, indent=1))

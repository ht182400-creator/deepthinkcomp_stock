# -*- coding: utf-8 -*-
"""宇宙构建（docs/10 隐患 H2）。

**旧链路**：宇宙 = ``fundamentals_broad.json``（1771 只），而财务源 ``gpcw`` 有 5561 只
→ 数据升级价值损失约 68%，且造成"回测 / 实盘口径分裂"。

**新链路**：宇宙 = ``gpcw`` 各期代码**并集**（≈5561 只），与财务面板天然对齐。

退市股不在 ``gpcw`` 中（实测确认），由 R7 叠加 ``baostock`` 财务后单独纳入。
"""
import logging
import os
import re
import traceback

import config

LOG = logging.getLogger(__name__)

_PERIOD_RE = re.compile(r"^gpcw(\d{8})\.dat$")
_PURE_RE = re.compile(r"^\d{6}$")

# 市场前缀判定规则（与 modules/strategy/tdx_day_reader.code_to_market 保持一致，避免分叉）
_BJ_PREFIX = ("92", "83", "43", "87", "88", "8", "4")
_SH_PREFIX = ("688", "60", "90")
_BJ_INDEX_PREFIX = ("81", "82", "89")     # 北交所指数段，非个股


def list_gpcw_periods(gpcw_dir=None, min_period=None, max_period=None):
    """列出可用的 ``gpcw`` 报告期（升序）。

    Args:
        gpcw_dir: 财务数据目录；缺省 ``config.GPCW_DIR``。
        min_period: 起始报告期（含），如 ``"20100101"``。
        max_period: 结束报告期（含）。

    Returns:
        list[str]: 形如 ``["20100331", "20100630", ...]``。
    """
    gpcw_dir = gpcw_dir or config.GPCW_DIR
    min_period = min_period or config.GPCW_MIN_PERIOD
    out = []
    try:
        for name in os.listdir(gpcw_dir):
            m = _PERIOD_RE.match(name)
            if not m:
                continue
            period = m.group(1)
            if min_period and period < min_period:
                continue
            if max_period and period > max_period:
                continue
            out.append(period)
        out.sort()
        LOG.info("[universe] 可用报告期 %d 个（%s ~ %s）",
                 len(out), out[0] if out else "-", out[-1] if out else "-")
        return out
    except Exception as exc:
        LOG.error("[universe] 扫描报告期异常 %s: %s\n%s", gpcw_dir, exc, traceback.format_exc())
        return []


def pure_to_full(pure):
    """6 位纯代码 → 带市场前缀的完整代码（sh/sz/bj）。

    Args:
        pure: 6 位数字代码，如 ``"600519"``。

    Returns:
        str: 带前缀代码，如 ``"sh600519"``。
    """
    pure = str(pure).strip()
    if not _PURE_RE.match(pure):
        return pure
    if pure.startswith(_BJ_PREFIX):
        return "bj" + pure
    if pure.startswith(_SH_PREFIX):
        return "sh" + pure
    return "sz" + pure


def is_tradable_stock(pure):
    """判断纯代码是否为可交易个股（排除指数 / 基金 / 债券 / B 股）。

    注：本判定用于 ``gpcw`` 的代码集；``gpcw`` 本身已只含个股，
    此处仅作防御性过滤。
    """
    pure = str(pure)
    if not _PURE_RE.match(pure):
        return False
    if pure.startswith(_BJ_INDEX_PREFIX):     # 北交所指数段
        return False
    return True


def build_universe(periods=None, gpcw_dir=None):
    """构建宇宙：``gpcw`` 各期代码并集。

    Args:
        periods: 指定报告期列表；缺省按 ``config.GPCW_MIN_PERIOD`` 自动列举。
        gpcw_dir: 财务数据目录。

    Returns:
        dict: ``{"stocks": {pure: {...}}, "periods": [...], "stats": {...}}``
              ``stocks[pure]`` 含 ``full`` / ``market`` / ``first_period`` /
              ``last_period`` / ``n_periods``。
    """
    from panels import financial as panel_fin     # 局部导入，避免循环依赖

    periods = periods or list_gpcw_periods(gpcw_dir=gpcw_dir)
    stocks = {}
    ok_periods = []
    try:
        for i, period in enumerate(periods, 1):
            df = panel_fin.read_period(period, gpcw_dir=gpcw_dir)
            if df is None or len(df) == 0:
                LOG.warning("[universe] 报告期 %s 无数据，跳过", period)
                continue
            ok_periods.append(period)
            for raw in df.index:
                pure = str(raw).zfill(6)
                if not is_tradable_stock(pure):
                    continue
                item = stocks.get(pure)
                if item is None:
                    full = pure_to_full(pure)
                    stocks[pure] = {
                        "full": full,
                        "market": full[:2],
                        "first_period": period,
                        "last_period": period,
                        "n_periods": 1,
                    }
                else:
                    item["last_period"] = period
                    item["n_periods"] += 1
            if i % 10 == 0 or i == len(periods):
                LOG.info("[universe] 已扫描 %d/%d 期，累计股票 %d 只",
                         i, len(periods), len(stocks))
    except Exception as exc:
        LOG.error("[universe] 构建宇宙异常: %s\n%s", exc, traceback.format_exc())

    stats = {
        "n_stocks": len(stocks),
        "n_periods": len(ok_periods),
        "first_period": ok_periods[0] if ok_periods else None,
        "last_period": ok_periods[-1] if ok_periods else None,
        "by_market": {},
        "by_board": {},
    }
    for item in stocks.values():
        stats["by_market"][item["market"]] = stats["by_market"].get(item["market"], 0) + 1
        board = board_of(item["full"])
        stats["by_board"][board] = stats["by_board"].get(board, 0) + 1

    LOG.info("[universe] 宇宙构建完成: %d 只 / %d 期 | 市场=%s | 板块=%s",
             stats["n_stocks"], stats["n_periods"], stats["by_market"], stats["by_board"])
    return {"stocks": stocks, "periods": ok_periods, "stats": stats}


def board_of(full):
    """按完整代码判定板块（主板 / 创业板 / 科创板 / 北交所）。

    Args:
        full: 带前缀代码，如 ``"sh688625"``。

    Returns:
        str: ``"主板" | "创业板" | "科创板" | "北交所"``。
    """
    pure = full[2:] if full[:2] in ("sh", "sz", "bj") else full
    if pure.startswith("688"):
        return "科创板"
    if pure.startswith(("300", "301")):
        return "创业板"
    if full.startswith("bj") or pure.startswith(("92", "83", "43", "87", "88")):
        return "北交所"
    return "主板"


if __name__ == "__main__":      # pragma: no cover - 手动执行入口
    import json
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO,
                         format="[%(asctime)s] %(levelname)-5s %(name)s:%(lineno)d  %(message)s")
    result = build_universe()
    print(json.dumps(result["stats"], ensure_ascii=False, indent=1))

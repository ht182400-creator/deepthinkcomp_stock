# -*- coding: utf-8 -*-
"""本地**量价指标**（零网络、**永不失败**）。

**背景**：个股页的"主力资金流"依赖东方财富接口，实测对部分标的
（如 ``sh688300`` 等科创板）**长期无数据**，且前端每 10s 刷新会持续报错刷屏
（已在 ``services/quote_service.get_fund_flow`` 加失败熔断缓解）。

但**资金流本身无法本地化** —— 通达信 ``.day`` 只有 OHLCV 总量，
**没有分档成交**（超大单/大单/中单/小单），算不出"主力净流入"。

本模块提供**可本地计算的量价替代指标**，回答类似的问题：
"今天这波拉升有量吗？""是不是缩量上涨（危险）？"

| 指标 | 算法 | 判读 |
|---|---|---|
| **放量倍数** | 本期量 / 前 5 期均量 | ≥1.5 明显放量；≤0.7 明显缩量 |
| **量价配合** | 价涨跌 × 量能增减 2×2 | 量价齐升（健康）/ 缩量上涨（**背离警惕**）/ 放量下跌（抛压）/ 缩量下跌（抛压减弱） |
| **量能趋势** | 近 4 期均量 vs 前 4 期均量 | 上升＝关注度提高；下降＝关注度退潮 |
| **量价背离** | 价创新高区间但量能萎缩 | 上涨缺乏承接，需警惕 |

**数据**：``data/panel/price_panel.parquet``（周线；``volume`` 单位为股，
``amount`` 单位为元，实测 ``amount/volume`` 即成交均价）。
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

_PANEL_CACHE = {}


def _pure(code):
    """``"sh600519"`` / ``"600519"`` → ``"600519"``。"""
    c = str(code or "").strip().lower()
    if c[:2] in ("sh", "sz", "bj"):
        c = c[2:]
    return c.zfill(6)


def _load_price_panel():
    """载入价格面板（进程内缓存）。

    Returns:
        pandas.DataFrame | None
    """
    if "df" in _PANEL_CACHE:
        return _PANEL_CACHE["df"]
    try:
        import pandas as pd
        df = pd.read_parquet(config.PRICE_PANEL_FILE)
        df["p6"] = df["code"].map(lambda c: _pure(str(c)))
        _PANEL_CACHE["df"] = df
        LOG.info("[volprice] 价格面板载入: %s", df.shape)
        return df
    except Exception as exc:
        LOG.error("[volprice] 载入价格面板异常: %s\n%s", exc, traceback.format_exc())
        _PANEL_CACHE["df"] = None
        return None


def _f(v, scale=1.0, digits=2):
    """安全转换并缩放。"""
    try:
        if v is None:
            return None
        x = float(v) / scale if scale != 1.0 else float(v)
        return round(x, digits)
    except Exception:
        return None


def get_volume_price(code, weeks=12):
    """计算本地量价指标。

    Args:
        code: 证券代码（``sh600519`` 或 ``600519``）。
        weeks: 取最近多少周。

    Returns:
        dict: ``{periods, close, volume_yi, amount_yi, chg_pct, vol_ratio, pattern,
        latest, note}``
    """
    p6 = _pure(code)
    df = _load_price_panel()
    if df is None:
        return {"error": "价格面板不可用（需 pandas + pyarrow）", "code": p6}
    try:
        sub = df[df["p6"] == p6]
        if sub.empty:
            return {"error": "无量价数据", "code": p6}
        sub = sub.sort_values("date").tail(int(weeks))
        if sub.empty:
            return {"error": "无量价数据", "code": p6}
        pers = [str(x) for x in sub["date"].tolist()]
        close = [_f(v, 1.0, digits=3) for v in sub["close"].tolist()]
        vol = [_f(v, 1e8, digits=4) for v in sub["volume"].tolist()]      # 股 → 亿股
        amt = [_f(v, 1e8, digits=3) for v in sub["amount"].tolist()]      # 元 → 亿元

        # 周涨跌 %
        chg = [None]
        for i in range(1, len(close)):
            if close[i] and close[i - 1]:
                chg.append(round((close[i] / close[i - 1] - 1) * 100, 2))
            else:
                chg.append(None)

        # 放量倍数 = 本期量 / 前 5 期均量
        vol_ratio = []
        for i in range(len(vol)):
            win = [v for v in vol[max(0, i - 5):i] if v is not None]
            base = (sum(win) / len(win)) if win else None
            vol_ratio.append(round(vol[i] / base, 2) if (base and vol[i] is not None) else None)

        # 量价配合（2×2）
        pattern = []
        for c, r in zip(chg, vol_ratio):
            if c is None or r is None:
                pattern.append("--")
                continue
            up, vol_up = c > 0, r >= 1.0
            pattern.append("量价齐升" if (up and vol_up) else
                           "缩量上涨" if up else
                           "放量下跌" if vol_up else "缩量下跌")

        def _avg4(arr, a, b):
            seg = [v for v in arr[a:b] if v is not None]
            return round(sum(seg) / len(seg), 4) if seg else None

        recent = _avg4(vol, max(0, len(vol) - 4), len(vol))
        prior = _avg4(vol, max(0, len(vol) - 8), max(0, len(vol) - 4))
        vol_trend = None
        if recent and prior and prior > 0:
            vol_trend = round((recent / prior - 1) * 100, 2)      # % 正＝放量

        # 量价背离：最近 4 周价格上涨，但量能较前 4 周萎缩 >15%
        divergence = False
        if len(close) >= 8 and close[-1] and close[-5]:
            price_up = close[-1] > close[-5]
            if price_up and vol_trend is not None and vol_trend < -15:
                divergence = True

        latest = {
            "period": pers[-1] if pers else "",
            "close": close[-1] if close else None,
            "chg_pct": chg[-1] if chg else None,
            "vol_ratio": vol_ratio[-1] if vol_ratio else None,
            "pattern": pattern[-1] if pattern else None,
            "amount_yi": amt[-1] if amt else None,
            "vol_trend_pct": vol_trend,
            "divergence": divergence,
        }
        tip = "缩量上涨且量能萎缩 >15% → 上涨缺乏承接，警惕回落" if divergence else (
            "量价配合正常" if (latest.get("pattern") in ("量价齐升", "缩量下跌")) else
            "关注量价背离风险" if latest.get("pattern") == "缩量上涨" else
            "放量下跌，抛压明显")

        return {"code": p6, "periods": pers, "close": close, "volume_yi": vol,
                "amount_yi": amt, "chg_pct": chg, "vol_ratio": vol_ratio,
                "pattern": pattern, "latest": latest, "tip": tip,
                "note": "放量倍数＝本期量/前5期均量；量价配合＝价涨跌×量能增减；全部由本地周线计算，不依赖网络",
                "source": "local_price_panel"}
    except Exception as exc:
        LOG.error("[volprice] 量价计算异常 %s: %s\n%s", p6, exc, traceback.format_exc())
        return {"error": str(exc), "code": p6}


def main():
    """命令行自检。"""
    import json
    r = get_volume_price("600519", weeks=8)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return r


if __name__ == "__main__":      # pragma: no cover
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(message)s")
    main()

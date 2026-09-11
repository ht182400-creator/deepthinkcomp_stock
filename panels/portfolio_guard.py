# -*- coding: utf-8 -*-
"""组合级风控（组合回撤降仓）—— 实盘落地版。

**回测依据**（[docs/10 §6.12](../docs/10-方案自审与优化建议.md)）：

| 实验 | 规则 | 年化 | 夏普 | 最大回撤 | Calmar |
|---|---|---|---|---|---|
| BASE | 无风控 | 8.30% | 0.287 | -51.83% | 0.160 |
| **SP2** | **组合回撤 -15% → 暴露减半** | **6.58%** | **0.274** | **-35.29%** | **0.186** |

- 单票止损（固定/移动 4 种）对回撤**几乎零作用** → **不做**；
- 均线择时（上证 MA56）**净负贡献** → **不做**；
- 组合回撤降仓**唯一有效**：回撤改善 **16.5pp**，Calmar **+16%**，夏普几乎不变。

**实盘落地规则**：

```
每周五收盘后：
    peak  = max(历史峰值总资产, 当前总资产)
    总资产 = 持仓市值 + 现金
    dd    = 总资产 / peak - 1

    dd > -15%  → 目标暴露 90%（正常）
    dd ≤ -15%  → 目标暴露 45%（减半）

    若当前持仓市值 > 总资产 × 目标暴露：
        超出部分 = 当前持仓市值 − 总资产 × 目标暴露
        按各持仓市值占比等比卖出（取整到 100 股）
```

**关于股数（关键设计）**：`holdings.json` 只有 ``amount``（投入金额），无股数。
本模块**零录入负担**：首次见到某持仓时用**当时最新价**记录 ``entry_price``，
之后按 ``股数 = amount / entry_price`` 推算市值。

> 若录入时点与真实成交时点相差较远，估算会有偏差 —— 可在 ``state`` 文件里手动修正 ``entry_price``。

⚠️ **局限**：
1. `cash` 依赖 ``settings.json`` 手工维护（买入后需扣减）；
2. 出入金会造成总资产跳变，需同步调整 ``peak_asset``；
3. 判断频率为**周频**（与回测一致），不建议日内频繁切换。
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config                                          # noqa: E402

LOG = logging.getLogger(__name__)

# ---- 风控参数（与回测 SP2 一致；改动需同步重跑回测）----
NORMAL_EXPO = 0.90          # 正常暴露
REDUCED_EXPO = 0.45         # 降仓后暴露（= NORMAL_EXPO × 0.5）
DRAWDOWN_TRIGGER = -0.15    # 触发阈值：组合自峰值回撤 ≤ -15%
LOT = 100                   # A 股整手股数


def _holdings_module():
    """延迟导入持仓模块（避免循环依赖）。"""
    try:
        sys.path.insert(0, os.path.join(_ROOT, "modules", "holdings"))
        import holdings as H                            # type: ignore
        return H
    except Exception as exc:
        LOG.error("[guard] 导入 holdings 失败: %s\n%s", exc, traceback.format_exc())
        return None


def _load_state(path=None):
    """读取风控状态文件。

    Returns:
        dict: ``{peak_asset, peak_date, entries, history}``
    """
    path = path or config.PORTFOLIO_STATE_FILE
    default = {"peak_asset": 0.0, "peak_date": "", "entries": {}, "history": []}
    try:
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
        for k, v in default.items():
            st.setdefault(k, v)
        return st
    except Exception as exc:
        LOG.error("[guard] 读取状态异常 %s: %s\n%s", path, exc, traceback.format_exc())
        return default


def _save_state(state, path=None):
    """原子写状态文件。"""
    path = path or config.PORTFOLIO_STATE_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as exc:
        LOG.error("[guard] 落盘状态异常 %s: %s\n%s", path, exc, traceback.format_exc())


def _latest_prices(codes):
    """取各持仓的最新价（复用面板；周线最新值即为当前真实价）。

    Args:
        codes: 6 位纯代码集合。

    Returns:
        dict: ``{6 位代码: 最新价}``
    """
    out = {}
    try:
        from panels import backtest_bridge as B
        prices = B._load_prices()
        for pure in codes:
            full = None
            for pfx in ("sh", "sz", "bj"):
                if (pfx + pure) in prices:
                    full = pfx + pure
                    break
            if not full:
                continue
            rec = prices.get(full) or {}
            ds = rec.get("dates") or []
            cmap = rec.get("close") or {}
            if ds and cmap.get(ds[-1]):
                out[pure] = float(cmap[ds[-1]])
        LOG.info("[guard] 最新价: %d/%d 只命中", len(out), len(codes))
    except Exception as exc:
        LOG.error("[guard] 取价异常: %s\n%s", exc, traceback.format_exc())
    return out


def build_state(update=True, path=None):
    """计算当前组合状态（总资产 / 峰值 / 回撤 / 目标暴露）。

    Args:
        update: 是否把最新观测写入状态文件（并更新峰值）。
        path: 状态文件路径。

    Returns:
        dict: 含 ``asset`` / ``peak_asset`` / ``drawdown`` / ``target_expo`` / ``positions`` 等。
    """
    st = _load_state(path=path)
    H = _holdings_module()
    if H is None:
        return {"error": "holdings 模块不可用"}
    holdings = H.get_holdings() or []
    settings = H.get_settings() or {}
    cash = float(settings.get("cash") or 0.0)

    codes = {str(h.get("code", "")).zfill(6) for h in holdings if h.get("code")}
    prices = _latest_prices(codes) if codes else {}
    today = datetime.now().strftime("%Y-%m-%d")

    entries = st.get("entries") or {}
    positions, unknown = [], []
    for h in holdings:
        code = str(h.get("code", "")).zfill(6)
        amount = float(h.get("amount") or 0.0)
        px = prices.get(code)
        if not code or amount <= 0:
            continue
        ent = entries.get(code)
        if ent is None and px:
            # 首次见到该持仓: 以当前价作为入场价基准（零录入负担）
            ent = {"amount": amount, "entry_price": float(px), "entry_date": today}
            entries[code] = ent
        if ent and ent.get("entry_price"):
            shares = amount / float(ent["entry_price"])
            mv = (px * shares) if px else amount
        else:
            shares, mv = None, amount
            unknown.append(code)
        positions.append({
            "code": code, "name": h.get("name", code),
            "amount": round(amount, 2),
            "entry_price": round(float(ent["entry_price"]), 3) if ent else None,
            "price": round(px, 3) if px else None,
            "shares": round(shares, 1) if shares else None,
            "market_value": round(mv, 2),
            "pnl_pct": round((mv / amount - 1.0) * 100, 2) if amount else 0.0,
        })

    mv_total = sum(p["market_value"] for p in positions)
    asset = mv_total + cash
    peak = max(float(st.get("peak_asset") or 0.0), asset)
    dd = (asset / peak - 1.0) if peak > 0 else 0.0
    target = NORMAL_EXPO if dd > DRAWDOWN_TRIGGER else REDUCED_EXPO

    # 需卖出金额 = 当前持仓市值 − 目标持仓市值
    over = mv_total - asset * target
    advise = []
    if over > 0 and mv_total > 0:
        ratio = over / mv_total
        for p in positions:
            sell_mv = p["market_value"] * ratio
            sh = p.get("shares") or 0
            sell_sh = int(round(sell_mv / p["price"] / LOT)) * LOT if p.get("price") else 0
            advise.append({
                "code": p["code"], "name": p["name"], "price": p["price"],
                "sell_shares": sell_sh, "sell_lots": sell_sh // LOT,
                "sell_value": round(sell_sh * (p["price"] or 0), 2),
            })

    state = {
        "asset": round(asset, 2), "market_value": round(mv_total, 2), "cash": round(cash, 2),
        "peak_asset": round(peak, 2), "peak_date": st.get("peak_date") or today,
        "drawdown": round(dd * 100, 2), "target_expo": target,
        "triggered": dd <= DRAWDOWN_TRIGGER,
        "positions": positions, "advise": advise, "unknown_entries": unknown,
        "checked_at": today,
    }
    if update:
        if asset >= float(st.get("peak_asset") or 0.0):
            st["peak_asset"], st["peak_date"] = asset, today
        st["entries"] = entries
        hist = st.get("history") or []
        hist.append({"date": today, "asset": round(asset, 2),
                     "drawdown": round(dd * 100, 2), "target_expo": target})
        st["history"] = hist[-260:]
        _save_state(st, path=path)
    LOG.info("[guard] 总资产 %.0f（持仓 %.0f + 现金 %.0f）| 峰值 %.0f | 回撤 %.2f%% | 目标暴露 %.0f%%%s",
             asset, mv_total, cash, peak, dd * 100, target * 100,
             "  ← 已触发降仓" if dd <= DRAWDOWN_TRIGGER else "")
    return state


def reset_peak(value=None, path=None):
    """重置峰值（出入金后使用）。

    Args:
        value: 新峰值；``None`` 时取当前总资产。
    """
    st = _load_state(path=path)
    v = float(value) if value is not None else float(build_state(update=False, path=path).get("asset") or 0)
    st["peak_asset"] = v
    st["peak_date"] = datetime.now().strftime("%Y-%m-%d")
    _save_state(st, path=path)
    LOG.info("[guard] 峰值已重置为 %.2f", v)
    return v


def main():
    """命令行：打印当前风控状态。

    Returns:
        dict: 状态。
    """
    st = build_state(update=True)
    print(json.dumps(st, ensure_ascii=False, indent=1))
    return st


if __name__ == "__main__":      # pragma: no cover
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="[%(asctime)s.%(msecs)03d] %(levelname)-5s %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    main()

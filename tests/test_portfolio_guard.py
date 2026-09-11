# -*- coding: utf-8 -*-
"""组合级风控（``panels/portfolio_guard.py``）单元测试。

覆盖：
1. 首次见到持仓 → 自动记录 ``entry_price`` 并推算股数/市值；
2. 组合回撤触发降仓 → 目标暴露 0.45、等比卖出建议（整手取整）；
3. 峰值随新高更新、``reset_peak`` 可用。

回测依据见 [docs/10 §6.12](../docs/10-改造方案自审与优化建议.md)：
组合回撤 -15% → 暴露减半，使最大回撤 -51.83% → -35.29%、Calmar 0.160 → 0.186。
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "modules", "holdings")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import holdings as H                    # noqa: E402
from panels import portfolio_guard as G  # noqa: E402


@pytest.fixture
def env(monkeypatch, tmp_path):
    """隔离持仓 / 设置 / 状态文件。"""
    hf, sf, stf = tmp_path / "holdings.json", tmp_path / "settings.json", tmp_path / "state.json"
    monkeypatch.setattr(H, "HOLDINGS_FILE", str(hf))
    monkeypatch.setattr(H, "SETTINGS_FILE", str(sf))
    sf.write_text(json.dumps({"cash": 20000.0, "N": 4}), encoding="utf-8")
    monkeypatch.setattr(G.config, "PORTFOLIO_STATE_FILE", str(stf))
    return {"hf": hf, "sf": sf, "stf": stf}


def _write(hf, rows):
    hf.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def test_first_seen_records_entry_price(env, monkeypatch):
    """首次见到持仓：以当时价作为 entry_price，推算股数与市值。"""
    _write(env["hf"], [{"code": "600001", "name": "测试甲", "amount": 30000}])
    monkeypatch.setattr(G, "_latest_prices", lambda codes: {"600001": 15.0})

    st = G.build_state(update=True)

    pos = st["positions"][0]
    assert pos["entry_price"] == 15.0
    assert pos["shares"] == pytest.approx(2000.0)        # 30000 / 15
    assert pos["market_value"] == pytest.approx(30000.0)
    assert st["asset"] == pytest.approx(50000.0)         # 30000 + 20000 cash
    assert st["target_expo"] == G.NORMAL_EXPO            # 无回撤 → 正常暴露
    assert not st["triggered"]

    # 状态文件应已写入峰值与 entries
    saved = json.loads(env["stf"].read_text(encoding="utf-8"))
    assert saved["peak_asset"] == pytest.approx(50000.0)
    assert saved["entries"]["600001"]["entry_price"] == 15.0


def test_drawdown_triggers_reduction_with_lot_rounding(env, monkeypatch):
    """价格下跌致回撤 -16% → 触发降仓，并给出整手卖出建议。"""
    _write(env["hf"], [{"code": "600001", "name": "测试甲", "amount": 30000}])
    monkeypatch.setattr(G, "_latest_prices", lambda codes: {"600001": 15.0})
    G.build_state(update=True)                            # 建档，entry_price=15，peak=50000

    # 价格跌到 11 元 → mv=22000，asset=42000，dd=-16%
    monkeypatch.setattr(G, "_latest_prices", lambda codes: {"600001": 11.0})
    st = G.build_state(update=True)

    assert st["market_value"] == pytest.approx(22000.0)
    assert st["asset"] == pytest.approx(42000.0)
    assert st["drawdown"] == pytest.approx(-16.0, abs=0.1)
    assert st["triggered"] is True
    assert st["target_expo"] == G.REDUCED_EXPO            # 0.45

    # 目标持仓 = 42000*0.45 = 18900；需卖出 22000-18900 = 3100 元
    # 股价 11 → 3100/11 ≈ 281.8 股 → 取整 3 手 = 300 股
    adv = st["advise"][0]
    assert adv["sell_shares"] == 300
    assert adv["sell_lots"] == 3
    assert adv["sell_value"] == pytest.approx(3300.0)

    # 峰值不被下调
    saved = json.loads(env["stf"].read_text(encoding="utf-8"))
    assert saved["peak_asset"] == pytest.approx(50000.0)


def test_peak_updates_on_new_high_and_reset(env, monkeypatch):
    """创新高时峰值上移；reset_peak 可手动重置（出入金场景）。"""
    _write(env["hf"], [{"code": "600001", "name": "测试甲", "amount": 30000}])
    monkeypatch.setattr(G, "_latest_prices", lambda codes: {"600001": 15.0})
    G.build_state(update=True)

    monkeypatch.setattr(G, "_latest_prices", lambda codes: {"600001": 18.0})
    st = G.build_state(update=True)                       # mv=36000 → asset=56000
    assert st["asset"] == pytest.approx(56000.0)
    assert st["peak_asset"] == pytest.approx(56000.0)

    G.reset_peak(value=60000.0)
    saved = json.loads(env["stf"].read_text(encoding="utf-8"))
    assert saved["peak_asset"] == pytest.approx(60000.0)


def test_empty_holdings_is_safe(env, monkeypatch):
    """无持仓时不崩溃，总资产 = 现金。"""
    _write(env["hf"], [])
    monkeypatch.setattr(G, "_latest_prices", lambda codes: {})
    st = G.build_state(update=True)

    assert st["asset"] == pytest.approx(20000.0)
    assert st["market_value"] == 0.0
    assert not st["triggered"]
    assert st["advise"] == []

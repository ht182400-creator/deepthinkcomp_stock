# -*- coding: utf-8 -*-
"""modules/analysis —— 分析管线（P2）。

job: 后台线程跑 current_candidates(B) → 持仓卡/推荐/自动调仓 → 落盘 txt/html/md
状态: ANALYSIS 全局 dict（running/message/percent/result），供 API 轮询
"""
import os
import sys
import json
import threading
import subprocess
from datetime import datetime

# 确保 modules/strategy 可导入
_HERE = os.path.dirname(os.path.abspath(__file__))       # .../modules/analysis
_MODULES = os.path.dirname(_HERE)                         # .../modules
_ROOT = os.path.dirname(_MODULES)                         # 项目根
_STRAT = os.path.join(_MODULES, "strategy")
for _p in (_ROOT, _STRAT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import regime_layer2_backtest as R  # noqa: E402
from modules.holdings import holdings as H  # noqa: E402

DATA_DIR = os.path.join(_ROOT, "data")
ACTION_LOG_FILE = os.path.join(DATA_DIR, "action_log.json")
LOG_FILE = os.path.join(DATA_DIR, "logs", "analyze.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

ANALYSIS = {"running": False, "message": "", "percent": 0,
            "last_result": None, "last_ts": None}


def log_line(s):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {s}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    return line


def get_action_log():
    if os.path.exists(ACTION_LOG_FILE):
        try:
            with open(ACTION_LOG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_action_log(items):
    tmp = ACTION_LOG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ACTION_LOG_FILE)


def _auto_rebalance(cards, holdings, settings, res, actions):
    """自动跟踪：清仓→移除、加仓→+newpos，写 action_log。"""
    newpos = settings.get("newpos", 5000)
    holdings_map = {h["code"]: h for h in holdings}
    changed = []
    for card in cards:
        code = card["code"]
        if card["advice"] == "清仓":
            changed.append(dict(code=code, name=card["name"], op="卖出",
                                detail=f"金额 {card['amount']:.0f} → 0（清仓）"))
        elif card["advice"] == "加仓":
            old = holdings_map[code]["amount"]
            holdings_map[code]["amount"] = old + newpos
            changed.append(dict(code=code, name=card["name"], op="加仓",
                                detail=f"金额 {old:.0f} → {old+newpos:.0f}（+新建仓预算）"))
        else:
            changed.append(dict(code=code, name=card["name"], op="维持",
                                detail=f"金额 {card['amount']:.0f} 不变"))
    if changed:
        actions.append(dict(ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            signal=res["signal_date"], items=changed))
        holdings = [h for h in holdings if h["code"] not in
                    {c["code"] for c in cards if c["advice"] == "清仓"}]
        H._save(H.HOLDINGS_FILE, holdings)
    _save_action_log((actions + get_action_log())[:200])
    log_line(f"自动调仓: {len(changed)} 项变更")
    return holdings


def _persist_dashboard(res, txt):
    """落盘 txt + 生成 dashboard html（保持与老项目行为一致）。"""
    txt_path = os.path.join(DATA_DIR, f"live_buy_list_{res['signal_date']}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    log_line(f"已写 txt: {txt_path}")
    try:
        dashboard_py = os.path.join(_ROOT, "modules", "strategy", "build_dashboard.py")
        if os.path.exists(dashboard_py):
            r = subprocess.run([sys.executable, dashboard_py],
                               cwd=_ROOT, capture_output=True, text=True, timeout=180)
            log_line("dashboard html 已刷新" if r.returncode == 0
                     else f"dashboard 刷新失败 rc={r.returncode} {r.stderr[:120]}")
        else:
            log_line("[warn] build_dashboard.py 未迁移，跳过 html 生成")
    except Exception as e:
        log_line(f"dashboard 落盘异常: {e}")


def run_analyze(force_refresh=False, auto_track=False):
    """后台线程入口。"""
    try:
        ANALYSIS["running"] = True
        ANALYSIS["message"] = "构建宇宙 (读取通达信 .day 前复权)..."
        ANALYSIS["percent"] = 5
        log_line(f"开始分析 force_refresh={force_refresh} auto_track={auto_track}")

        settings = H.get_settings()
        cash = settings.get("cash", 50000)
        N = settings.get("N", 4)

        res = R.current_candidates(scheme="B", cash=cash, N=N)
        ANALYSIS["percent"] = 60
        ANALYSIS["message"] = "生成持仓操作卡..."

        holdings = H.get_holdings()
        cards = H.build_cards(res, holdings)
        selected_recs, recommends = H.build_recommends(res, holdings, cash, N)

        actions = []
        if auto_track and settings.get("auto_track"):
            ANALYSIS["message"] = "自动跟踪调仓..."
            holdings = _auto_rebalance(cards, holdings, settings, res, actions)

        result = dict(
            ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            signal_date=res["signal_date"], regime_up=res["regime_up"],
            scheme=res["scheme"], n_stocks=res["n_stocks"],
            cards=cards, recommends=recommends,
            selected_recommends=selected_recs,
            summary=H.build_summary(res, cards, selected_recs, recommends),
        )
        ANALYSIS["last_result"] = result
        ANALYSIS["last_ts"] = result["ts"]
        ANALYSIS["percent"] = 100
        ANALYSIS["message"] = "分析完成"
        log_line(f"分析完成 signal={res['signal_date']} 持仓{len(cards)} 推荐{len(recommends)}")

        # 落盘 txt + dashboard html
        try:
            txt = R.format_live_report(res)
            _persist_dashboard(res, txt)
        except Exception as e:
            log_line(f"落盘 dashboard 异常: {e}")
    except Exception as e:
        log_line(f"分析异常: {e}")
        ANALYSIS["message"] = f"异常: {e}"
    finally:
        ANALYSIS["running"] = False


def submit(force_refresh=False, auto_track=False):
    if ANALYSIS["running"]:
        return False
    t = threading.Thread(target=run_analyze,
                         args=(force_refresh, auto_track), daemon=True)
    t.start()
    log_line(f"提交分析任务 force_refresh={force_refresh} auto_track={auto_track}")
    return True

# -*- coding: utf-8 -*-
"""modules/holdings —— 持仓管理模块（P2）。

store: JSON CRUD（原子写） + settings
cards: 持仓操作卡（评分/建议/本周操作/说明）
recommend: 本周推荐（⭐精选 selected + 📋更多候选 buy 池其余）
"""
import os
import json

_HERE = os.path.dirname(os.path.abspath(__file__))       # .../modules/holdings
_MODULES = os.path.dirname(_HERE)                         # .../modules
_ROOT = os.path.dirname(_MODULES)                         # 项目根
DATA_DIR = os.path.join(_ROOT, "data")
HOLDINGS_FILE = os.path.join(DATA_DIR, "holdings.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

DEFAULT_SETTINGS = {"auto_track": False, "weekly": 10000, "newpos": 5000,
                    "cash": 50000, "N": 4}


def _load(p, default):
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _save(p, obj):
    """原子写：先写 .tmp 再 rename，避免写一半损坏。"""
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _mkt(code):
    if code.startswith(("920", "8", "4")):
        return "bj"
    if code.startswith(("60", "68", "90")):
        return "sh"
    return "sz"


# ---------------- 持仓 ----------------
def get_holdings():
    return _load(HOLDINGS_FILE, [])


def upsert_holding(code, amount, dingtou, name="", industry=""):
    holdings = get_holdings()
    for h in holdings:
        if h["code"] == code:
            h["amount"] = amount
            h["dingtou"] = dingtou
            if name:
                h["name"] = name
            if industry:
                h["industry"] = industry
            break
    else:
        holdings.append(dict(code=code, name=name, industry=industry,
                             amount=amount, dingtou=dingtou,
                             date=""))  # date 由上层补
    _save(HOLDINGS_FILE, holdings)
    return holdings


def delete_holdings(codes):
    codes = set(codes)
    holdings = [h for h in get_holdings() if h["code"] not in codes]
    _save(HOLDINGS_FILE, holdings)
    return holdings


def clear_holdings():
    """清空全部持仓记录（一键清空，不可撤销）。"""
    _save(HOLDINGS_FILE, [])
    return []


# ---------------- 设置 ----------------
def get_settings():
    s = DEFAULT_SETTINGS.copy()
    s.update(_load(SETTINGS_FILE, {}))
    return s


def save_settings(body):
    s = get_settings()
    for k in ("auto_track", "weekly", "newpos", "cash", "N"):
        if k in body:
            s[k] = body[k]
    _save(SETTINGS_FILE, s)
    return s


# ---------------- 持仓操作卡 ----------------
def build_cards(res, holdings):
    """对每只持仓按 current_candidates 结果判定建议。"""
    buy_map = {r["code"]: r for r in res["buy"]}
    sel_map = {r["code"]: r for r in res["selected"]}
    obs_map = {}
    for r in res["observation"] + res.get("bj_observe", []):
        obs_map.setdefault(r["code"], r)

    cards = []
    for h in holdings:
        code = h["code"]
        r = buy_map.get(code) or obs_map.get(code)
        base = dict(code=code, name=h.get("name", code),
                    industry=h.get("industry", ""), market=_mkt(code),
                    amount=h.get("amount", 0), dingtou=h.get("dingtou", False),
                    date=h.get("date", ""))
        if code in sel_map:
            base.update(score=round((sel_map[code].get("score") or 0) * 100, 1),
                        advice="加仓", action="买入",
                        desc="入选本周建仓清单（质量+动量+站线全过）")
        elif code in buy_map:
            base.update(score=round((buy_map[code].get("score") or 0) * 100, 1),
                        advice="持有", action="持有",
                        desc="通过质量+动量+站线+段regime，未进本轮建仓")
        elif code in obs_map:
            fail = obs_map[code].get("fail", "")
            if "段regime" in fail or "DOWN" in fail:
                base.update(score=50.0, advice="减仓", action="观望",
                            desc=f"板块指数在 56 周线下方（{fail}）")
            elif "动量负" in fail:
                base.update(score=45.0, advice="减仓", action="减仓",
                            desc="近 52 周收益为负（动量转弱）")
            elif "未站线" in fail:
                base.update(score=58.0, advice="持有", action="观望",
                            desc="未站上 56 周均线，等信号回暖")
            else:
                base.update(score=50.0, advice="观望", action="观望",
                            desc=f"观察中（{fail}）")
        else:
            base.update(score=30.0, advice="清仓", action="卖出",
                        desc="未通过质量门（ROE/FCF）或数据缺失，建议剔除")
        cards.append(base)
    return cards


# ---------------- 本周推荐 ----------------
def build_recommends(res, holdings, cash, N):
    """⭐精选（selected，已过资金可行性筛选）+ 📋更多候选（buy 池其余）。"""
    held = {h["code"]: h for h in holdings}
    sel_codes = {r["code"] for r in res["selected"]}
    per_pos = res.get("per_pos") or (cash * res.get("expo_base", 0.9) / N)

    def _row(r, is_top):
        is_held = r["code"] in held
        one_hand = r.get("price", 0) * 100
        lots = r.get("lots", 0)
        cap = r.get("capital", 0)
        return dict(
            code=r["code"], name=r.get("name", r["code"]),
            industry=r.get("sind", ""), market=_mkt(r["code"]),
            score=round((r.get("score") or 0) * 100, 1),
            advice="加仓" if is_held else "买入",
            action="加仓(已持仓)" if is_held else "建议建仓",
            held=is_held, is_top=is_top,
            price=r.get("price", 0),
            one_hand=round(one_hand, 1),
            fea_ratio=round(one_hand / per_pos * 100, 1) if per_pos > 0 else 0,
            lots=lots, capital=cap,
            desc=(f"ROE {r.get('roe', 0)*100:.1f}% · 52w动量 +{r.get('mom', 0)*100:.0f}%"
                  f" · 段 {r.get('seg', '')} UP"))

    # ⭐ 精选
    selected_recs = [_row(r, True) for r in res["selected"]]
    # 📋 更多候选（buy 池中除 selected 外，超预算标注）
    recs = [r for r in res["buy"] if r["code"] not in sel_codes]
    recs.sort(key=lambda r: (0 if r["code"] in held else 1, -r.get("score", 0)))
    recommends = []
    for r in recs[:12]:
        row = _row(r, False)
        if row["fea_ratio"] > 100:
            row["desc"] += f" · 一手 {row['one_hand']:.0f}元 > 单仓预算{per_pos:.0f}元(超预算)"
        recommends.append(row)
    return selected_recs, recommends


#: 市场段英文代码 → 中文名（与 regime_layer2_backtest.SEG_CN 保持一致）
_SEG_CN = {"sh000001": "上证", "sz399001": "深成指", "sz399006": "创业板指",
           "sh000688": "科创50", "bj899050": "北证50"}


def _regime_cn(res):
    """把市场状态翻译成中文裁决语。

    **背景**：方案 B 是分市场段各自裁决，``res['regime_up']`` 恒为 True
    （见 ``regime_layer2_backtest.current_candidates`` 里的
    ``market_up = ... if scheme not in ('B','C') else True``）。若直接按它显示
    "全部上涨 → 建议建仓"，就会与看板顶部的"5 段全 DOWN"自相矛盾。
    因此优先按 ``seg_state`` 汇总，仅在没有段数据时回退到 ``regime_up``。
    """
    seg = res.get("seg_state") or {}
    if not seg:
        return "全部上涨 → 建议建仓" if res.get("regime_up") else "存在下跌段 → 空仓观望"
    ups = [k for k, v in seg.items() if v]
    if not ups:
        return f"{len(seg)} 段全 DOWN → 空仓观望"
    if len(ups) == len(seg):
        return f"{len(seg)} 段全 UP → 建议建仓"
    names = "、".join(_SEG_CN.get(k, k) for k in ups)
    return f"仅 {names} UP → 仅该板块可买"


def build_summary(res, cards, selected_recs, recommends):
    return dict(
        held=len(cards),
        buy_pool=len(res["buy"]),
        selected=len(res["selected"]),
        obs=len(res["observation"]),
        recommend=len(recommends),
        total_amt=sum(c.get("amount", 0) for c in cards),
        regime_cn=_regime_cn(res),
        # 段状态原样带出，供前端/报告展示"哪些段 UP"（英文键 → True/False）
        seg_state=dict(res.get("seg_state") or {}),
    )

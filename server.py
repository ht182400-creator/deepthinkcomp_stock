#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepThinkCompStock · FastAPI 后端（P1 骨架：行情/搜索/自选 API）。

阶段: P1 地基 —— 行情四级降级链 + 自选 + 搜索（迁移自 deepthinkSingle 的 Flask 路由，改为 FastAPI）。
后续 P2/P3 追加: 策略(modules/strategy) + 持仓(modules/holdings) + 个股详情聚合 + 跳转衔接。

用法: python server.py [--port 8899]
"""
import os
import sys
import json
import glob
import logging
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)   # 保证 import config/core/sources/services 生效
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging():
    logfile = os.path.join(LOG_DIR, "deepthink_%s_%d.log" % (
        datetime.date.today().isoformat(), os.getpid()))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(logfile, encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)],
        force=True)
    for name in ("urllib3", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return logging.getLogger("deepthink")


LOG = setup_logging()

import config  # noqa: E402
import services.quote_service as svc  # noqa: E402
import services.search_service as search_svc  # noqa: E402
import services.db as db  # noqa: E402
db.init_db()

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

app = FastAPI(title="DeepThinkCompStock", version="0.1.0")

# 静态前端（P1 先用占位页, P3 换真实前端）
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_cache(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# =====================================================================
# 自选列表（与 deepthinkSingle 兼容）
# =====================================================================
_DEFAULT_WATCHLIST = ["sh600519", "sz000858", "sz300750", "sh601318"]


def _load_watchlist() -> list:
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else list(_DEFAULT_WATCHLIST)
    except Exception:
        return list(_DEFAULT_WATCHLIST)


def _save_watchlist(items: list):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


ANALYSIS_FILE = os.path.join(DATA_DIR, "analysis.json")


def _load_analysis() -> list:
    """复盘/分析记录：list[{"code","note","ts"}] 按 ts 倒序。"""
    try:
        with open(ANALYSIS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_analysis(items: list):
    with open(ANALYSIS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


@app.get("/api/analysis")
async def api_analysis(code: str = ""):
    """复盘记录（按 code 过滤，返回 ts 倒序）。"""
    code = (code or "").strip().lower()
    rows = _load_analysis()
    if code:
        rows = [r for r in rows if (r.get("code") or "").lower() == code]
    rows.sort(key=lambda r: r.get("ts") or 0, reverse=True)
    return rows


@app.post("/api/analysis")
async def api_analysis_save(payload: dict):
    """保存一条复盘记录 {code, note}。"""
    code = ((payload or {}).get("code") or "").strip().lower()
    note = ((payload or {}).get("note") or "").strip()
    if not code or not note:
        return {"error": "code/note 必填"}
    rows = _load_analysis()
    rows.append({"code": code, "note": note, "ts": int(__import__("time").time())})
    rows.sort(key=lambda r: r.get("ts") or 0, reverse=True)
    _save_analysis(rows[:500])
    LOG.info("[api/analysis] 已保存 %s 的复盘", code)
    return {"ok": True, "count": len(rows)}


@app.get("/")
async def index():
    idx = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(idx):
        return FileResponse(idx)
    return JSONResponse({"message": "DeepThinkCompStock P1 骨架就绪, 前端待 P3",
                         "watchlist": _load_watchlist()})


@app.get("/api/watchlist")
async def api_watchlist():
    wl = list(_load_watchlist())
    wl_set = set(wl)
    pool = search_svc.all_pool_items()
    out = [{"code": c, "name": search_svc.get_code_name(c), "in_watchlist": True} for c in wl]
    for code, name in pool:
        if code in wl_set:
            continue
        out.append({"code": code, "name": name, "in_watchlist": False})
    return out


@app.post("/api/watchlist")
async def api_watchlist_set(body: dict):
    action = body.get("action", "set")
    items = list(_load_watchlist())
    if action == "add":
        code = (body.get("code") or "").strip().lower()
        if code and code not in items:
            items.append(code)
    elif action == "remove":
        code = (body.get("code") or "").strip().lower()
        if code in items:
            items.remove(code)
    else:
        items = [c for c in (body.get("items") or []) if isinstance(c, str)]
    _save_watchlist(items)
    LOG.info("watchlist %s → %s", action, items)
    return {"ok": True, "items": items}


# =====================================================================
# 行情 API（与 deepthinkSingle 契约一致，四级降级链在 services 内部）
# =====================================================================
@app.get("/api/quote")
async def api_quote(code: str = "sh600519"):
    code = code.strip().lower()
    try:
        data = svc.get_all(code)
        data["errors"] = data.get("errors", [])
        return data
    except Exception as e:
        LOG.error("api/quote %s 失败: %s", code, e)
        return {"code": code, "error": str(e),
                "quote": None, "minute": [], "fund": []}


@app.get("/api/search")
async def api_search(q: str = ""):
    return search_svc.search_stocks_with_guess(q.strip())


@app.get("/api/kline")
async def api_kline(code: str = "sh600519", period: str = "day", limit: int = 260):
    code = code.strip().lower()
    # 周期归一化：兼容前端裸数字 60/30/15/5 → m60/m30/m15/m5
    _p = period.strip().lower()
    if _p in ("1", "5", "15", "30", "60", "120"):
        _p = "m" + _p
    elif _p in ("m60", "m30", "m15", "m5", "m1", "day", "week", "month"):
        pass
    else:
        _p = "day"
    try:
        return svc.get_kline(code, _p, limit)
    except Exception as e:
        LOG.error("api/kline %s/%s 失败: %s", code, _p, e)
        return {"error": str(e)}


@app.get("/api/many")
async def api_many(codes: str = ""):
    codes = [c.strip().lower() for c in codes.split(",") if c.strip()]
    if not codes:
        return {"error": "codes 必填，逗号分隔"}
    if len(codes) > config.MAX_CODES:
        return {"error": f"codes 单次上限 {config.MAX_CODES}（收到 {len(codes)}）"}
    return svc.get_many(codes)


@app.get("/api/minute")
async def api_minute(code: str = "", date: str = ""):
    code = code.strip().lower()
    date = date.strip().replace("-", "")
    if not code:
        return {"error": "code 必填"}
    try:
        if date:
            return svc.get_minute_with_meta(code, date)
        return svc.get_minute(code, date)
    except Exception as e:
        LOG.error("api/minute %s/%s 失败: %s", code, date, e)
        return {"error": str(e)}


@app.get("/api/announcement")
async def api_announcement(code: str = ""):
    art_code = code.strip()
    if not art_code:
        return {"error": "code 必填"}
    try:
        from sources.company import get_announcement_content
        return get_announcement_content(art_code)
    except Exception as e:
        LOG.error("api/announcement %s 失败: %s", art_code, e)
        return {"error": str(e)}


# =====================================================================
# 个股详情 API（P3：8 卡片数据源，复用 quote_service 四级降级链）
# =====================================================================
@app.get("/api/stock/quote")
async def api_stock_quote(code: str = "sh600519"):
    """行情概况（含五档盘口，16+ 指标）。"""
    code = code.strip().lower()
    try:
        q = svc.get_quote(code)
        return dict(
            code=q.get("code", code), name=q.get("name", ""),
            price=q.get("price"), pre_close=q.get("pre_close"),
            open=q.get("open"), high=q.get("high"), low=q.get("low"),
            change=q.get("change"), change_pct=q.get("change_pct"),
            volume=q.get("volume"), amount=q.get("amount"), time=q.get("time"),
            turnover_pct=q.get("turnover_pct"), amplitude_pct=q.get("amplitude_pct"),
            outer=q.get("outer"), inner=q.get("inner"),
            pe_dyn=q.get("pe_dyn"), pb=q.get("pb"),
            float_mv=q.get("float_mv"), total_mv=q.get("total_mv"),
            volume_ratio=q.get("volume_ratio"), avg_price=q.get("avg_price"),
            order_book=q.get("order_book"), source=q.get("source", ""),
        )
    except Exception as e:
        LOG.error("api/stock/quote %s 失败: %s", code, e)
        return {"error": str(e)}


@app.get("/api/stock/tick")
async def api_stock_tick(code: str = "sh600519", date: str = ""):
    """分时（240 根分钟线：时间/价格/均价/量/额）。
    修复 10 类历史 bug 第 6 条：腾讯/东财返回的 avg 是"价格×0.01"格式（0.562 表示 56.2），适配层 ×100 还原为元。"""
    code = code.strip().lower()
    try:
        rows = svc.get_minute(code, date.strip().replace("-", ""))
        for r in rows:
            if isinstance(r, dict) and "avg" in r:
                try:
                    a = float(r["avg"])
                    if a < 1.0:
                        r["avg"] = round(a * 100, 4)
                except (TypeError, ValueError):
                    pass
        return {"items": rows, "source": "fallback"}
    except Exception as e:
        LOG.error("api/stock/tick %s 失败: %s", code, e)
        return {"error": str(e)}


@app.get("/api/stock/orderbook")
async def api_stock_orderbook(code: str = "sh600519"):
    """五档盘口（从 quote 里取）。"""
    code = code.strip().lower()
    try:
        q = svc.get_quote(code)
        ob = q.get("order_book") or {}
        return {"bids": ob.get("bids", []), "asks": ob.get("asks", []),
                "updated": q.get("time", "")}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/stock/flow")
async def api_stock_flow(code: str = "sh600519", limit: int = 30):
    """订单流（由分时分钟数据派生：每分钟 1 笔 → 价格/量/方向）。"""
    code = code.strip().lower()
    try:
        minute = svc.get_minute(code)
        items = []
        prev_price = None
        for x in (minute or []):
            price = float(x.get("price", 0) or 0)
            vol = float(x.get("vol", 0) or 0)
            if price <= 0 and vol <= 0:        # 过滤全 0 占位
                continue
            if prev_price is not None and price > 0:
                direction = "buy" if price >= prev_price else "sell"
            else:
                direction = "buy"
            items.append(dict(time=x.get("t", ""),
                              price=round(price, 2),
                              volume=int(vol),
                              direction=direction))
            prev_price = price if price > 0 else prev_price
        return {"items": items[-limit:], "source": "fallback"}
    except Exception as e:
        LOG.error("api/stock/flow %s 失败: %s", code, e)
        return {"error": str(e)}


@app.get("/api/stock/fund_flow")
async def api_stock_fund_flow(code: str = "sh600519"):
    """资金博弈（主力/散户 + 大单分类净额）。"""
    code = code.strip().lower()
    try:
        fund = svc.get_fund_flow(code) or []
        main_net = sum((x.get("main") or 0) for x in fund)
        retail_net = sum((x.get("retail") or 0) for x in fund)
        super_large = sum((x.get("super_large") or 0) for x in fund)
        large = sum((x.get("large") or 0) for x in fund)
        medium = sum((x.get("medium") or 0) for x in fund)
        small = sum((x.get("small") or 0) for x in fund)
        return dict(main_in=max(main_net, 0), main_out=max(-main_net, 0),
                    retail_in=max(retail_net, 0), retail_out=max(-retail_net, 0),
                    super_large=super_large, large=large, medium=medium, small=small,
                    series=fund)
    except Exception as e:
        LOG.error("api/stock/fund_flow %s 失败: %s", code, e)
        return {"error": str(e)}


@app.get("/api/stock/fundamentals")
async def api_stock_fundamentals(code: str = "sh600519"):
    """财务摘要：单期快照 + 历年净利趋势（profit_trend）。"""
    code = code.strip().lower()
    try:
        from sources.company import get_finance_summary, get_profit_trend
        snap = get_finance_summary(code) or {}
        trend = get_profit_trend(code, years=5) or []
        years = [x.get("year", "") for x in trend]
        net_profit = [x.get("net_profit", 0) for x in trend]
        # 营收趋势（无独立接口时用快照 + 净利趋势的 yoy 反推，标 approximation）
        revenue = []
        for i, x in enumerate(trend):
            if i == 0:
                revenue.append(snap.get("revenue") or 0)
            else:
                yoy_rev = x.get("yoy_rev")
                prev = revenue[i - 1] or 0
                revenue.append(round(prev / (1 + (yoy_rev or 0) / 100), 0) if yoy_rev is not None else 0)
        return dict(
            years=years, revenue=revenue, net_profit=net_profit,
            gross_margin=[snap.get("gross_margin")] * len(years),
            net_margin=[snap.get("net_margin")] * len(years),
            roe=[snap.get("roe") / 100 if snap.get("roe") else 0] * len(years),
            debt_ratio=[snap.get("debt_ratio") / 100 if snap.get("debt_ratio") else 0] * len(years),
            eps=[snap.get("eps")] * len(years),
            snapshot=dict(report_date=snap.get("report_date"),
                          report_type=snap.get("report_type"),
                          revenue=snap.get("revenue"),
                          net_profit=snap.get("net_profit"),
                          eps=snap.get("eps"),
                          roe_pct=snap.get("roe"),
                          gross_margin=snap.get("gross_margin")),
            cached_at=snap.get("cached_at", ""))
    except Exception as e:
        LOG.error("api/stock/fundamentals %s 失败: %s", code, e)
        return {"error": str(e)}


@app.get("/api/stock/shareholders")
async def api_stock_shareholders(code: str = "sh600519"):
    """股东户数（list: date/total/change_pct/avg_shares）。"""
    code = code.strip().lower()
    try:
        from sources.company import get_holder_num
        rows = get_holder_num(code, limit=5) or []
        latest = rows[0] if rows else {}
        return dict(
            total=latest.get("total"),
            avg_holding=latest.get("avg_shares"),
            change_pct=latest.get("change_pct"),
            trend=[dict(date=x.get("date", ""),
                        holders=x.get("total", 0),
                        change_pct=x.get("change_pct")) for x in rows],
        )
    except Exception as e:
        LOG.error("api/stock/shareholders %s 失败: %s", code, e)
        return {"error": str(e)}


@app.get("/api/stock/news")
async def api_stock_news(code: str = "sh600519", limit: int = 10):
    """新闻公告。"""
    code = code.strip().lower()
    try:
        from sources.company import get_announcements
        ann = get_announcements(code, limit=limit) or []
        items = [dict(title=a.get("title", ""), date=a.get("date", ""),
                      source=a.get("source", ""), url=a.get("url", "")) for a in ann]
        return {"items": items}
    except Exception as e:
        LOG.error("api/stock/news %s 失败: %s", code, e)
        return {"error": str(e)}


@app.get("/api/stock/kline")
async def api_stock_kline(code: str = "sh600519", period: str = "day", limit: int = 0):
    """K 线（复用 quote_service.get_kline，深 thinkSingle 兼容 [{date, open, close, high, low, vol}, ...]）。"""
    code = code.strip().lower()
    if not code: return {"error": "code 必填"}
    try:
        rows = _safe_call(svc.get_kline, code, period, limit) or []
        return rows
    except Exception as e:
        LOG.error("api/stock/kline %s/%s 失败: %s", code, period, e)
        return {"error": str(e)}


# ==================== 个股详情聚合端点：deepthinkSingle 兼容 ====================
@app.get("/api/stock/full")
async def api_stock_full(code: str = "sh600519"):
    """聚合所有子接口为 deepthinkSingle 兼容的完整响应，供 front/stock.js 一次性消费。"""
    from fastapi.responses import JSONResponse
    code = code.strip().lower()
    if not code:
        return JSONResponse({"error": "code 必填"}, status_code=400)
    full = {}
    # 1) 实时行情 + 盘口
    try:
        quote_raw = _safe_call(svc.get_quote, code) or {}
        q = _quote_to_deepthink_shape(quote_raw)
        q["source"] = quote_raw.get("source") or "tencent"
    except Exception as e:
        LOG.warning("get_quote %s 失败: %s", code, e)
        return JSONResponse({"error": f"行情获取失败: {e}"}, status_code=500)
    # 2) 盘口 —— quote_service 没有独立函数，从 quote 自带字段提取
    try:
        ob = _safe_call(svc.get_quote, code) or {}
        ob_data = ob.get("order_book") or ob.get("book") or {"bids": [], "asks": []}
        q["order_book"] = ob_data
    except Exception:
        q["order_book"] = {"bids": [], "asks": []}
    full["quote"] = q
    # 3) 分钟线
    try:
        minute = _normalize_minute_avg(_safe_call(svc.get_minute, code) or [])
    except Exception:
        minute = []
    full["quote"]["minute"] = minute
    full["minute"] = minute
    # 4) 资金流系列
    try:
        ffl = _safe_call(svc.get_fund_flow, code) or []
    except Exception:
        ffl = []
    full["fund"] = {"series": ffl}
    LOG.info("[stock/full] fund.series=%d 条", len(ffl))
    # 5) 行情统计
    try:
        full["stats"] = _safe_call(svc._compute_period_stats, code) or {}
    except Exception:
        full["stats"] = {}
    LOG.info("[stock/full] stats=%s", full["stats"])
    # 6) 财务（来自 sources.company）
    from sources.company import (get_finance_summary, get_profit_trend,
                                  get_holder_num, get_company_profile,
                                  get_forecast, get_margin, get_lhb,
                                  get_announcements, get_announcement_content)
    try:
        snap = _safe_call(get_finance_summary, code) or {}
        trend = _safe_call(get_profit_trend, code, years=4) or []
        # snap 的 yoy_revenue/yoy_profit 来自 return_value 的 +1.3% / -1.95% 等，需要转成 percent
        def pct(v):
            if v is None: return None
            try: return float(v)
            except: return None
        full["finance"] = dict(
            revenue=snap.get("revenue"), yoy_revenue=pct(snap.get("yoy_revenue")),
            net_profit=snap.get("net_profit"), yoy_profit=pct(snap.get("yoy_profit")),
            eps=snap.get("eps"), roe=pct(snap.get("roe")),
            report_type=snap.get("report_type") or "最新",
        )
        full["profit_trend"] = [
            dict(year=t.get("year"), net_profit=t.get("net_profit"), yoy=t.get("yoy"))
            for t in trend
        ]
        LOG.info("[stock/full] finance=%s profit_trend=%d 条",
                 {k: full["finance"][k] for k in ("revenue", "eps", "report_type")},
                 len(full["profit_trend"]))
    except Exception as e:
        import traceback
        LOG.error("[stock/full] finance 段异常: %s\n%s", e, traceback.format_exc())
        full["finance"] = {}; full["profit_trend"] = []
    # 7) 持股股东
    try:
        holders_raw = _safe_call(get_holder_num, code, limit=4) or []
        full["holders"] = [
            dict(date=h.get("date"), total=h.get("total"), change_pct=h.get("change_pct"))
            for h in holders_raw if h.get("date")
        ]
        LOG.info("[stock/full] holders=%d 条 (raw=%d)", len(full["holders"]), len(holders_raw))
    except Exception:
        full["holders"] = []
    # 8) 公司信息
    try:
        comp = _safe_call(get_company_profile, code) or {}
        full["company"] = dict(
            org_name=comp.get("org_name") or "",
            industry=comp.get("industry") or "",
            market=comp.get("market") or "",
        )
    except Exception:
        full["company"] = {}
    # 9) 盈利预测
    try:
        full["forecast"] = _safe_call(get_forecast, code) or {}
    except Exception:
        full["forecast"] = {}
    LOG.info("[stock/full] forecast.org_num=%s", full["forecast"].get("org_num"))
    # 10) 融资融券
    try:
        full["margin"] = _safe_call(get_margin, code) or []
    except Exception:
        full["margin"] = []
    LOG.info("[stock/full] margin=%d 条", len(full["margin"]))
    # 11) 龙虎榜
    try:
        full["lhb"] = _safe_call(get_lhb, code) or []
    except Exception:
        full["lhb"] = []
    LOG.info("[stock/full] lhb=%d 条", len(full["lhb"]))
    # 12) 公告
    try:
        ann = _safe_call(get_announcements, code, limit=10) or []
        full["announcements"] = ann
        full["announcement_count"] = len(ann)
    except Exception:
        full["announcements"] = []
    LOG.info("[stock/full] announcements=%d 条", len(full["announcements"]))
    # 13) 近5日主力
    try:
        from services.quote_service import get_kline as _get_kline
        k = _safe_call(_get_kline, code, "day", limit=6) or []
        full["day5_funds"] = _derive_day5_funds(k)
    except Exception:
        full["day5_funds"] = []
    LOG.info("[stock/full] day5_funds=%d 条 (kline=%d 根)", len(full["day5_funds"]), len(k) if 'k' in dir() else 0)
    # 14) sentiment: 主力多空（用日 K 涨跌日数近似）
    try:
        from services.quote_service import get_kline as _get_kline
        k = _safe_call(_get_kline, code, "day", limit=240) or []
        if k:
            recent = k[-240:]
            up_n = sum(1 for x in recent if x.get("close", 0) >= x.get("open", 0))
            up_pct = round(100 * up_n / len(recent), 2)
            full["sentiment"] = dict(days=len(recent), bull_pct=up_pct, bear_pct=round(100-up_pct, 2))
        else:
            full["sentiment"] = {}
    except Exception:
        full["sentiment"] = {}
    LOG.info("[stock/full] sentiment=%s", full["sentiment"])
    # 15) 北向资金（沪股通+深股通合计，datacenter 报表：失败返回 dict 含 error 而非 raise）
    try:
        from sources.company import get_north_holding
        north = _safe_call(get_north_holding, code, limit=5) or {}
        if not isinstance(north, dict):
            north = {"error": "返回非字典"}
        full["north"] = north
    except Exception as e:
        LOG.warning("[stock/full] north 段异常包装失败: %s", e)
        full["north"] = {"error": str(e)[:60]}
    LOG.info("[stock/full] north=%s", {k: full["north"].get(k) for k in ("latest_date", "holdings", "hold_value", "error")})
    return JSONResponse(full)


# ============== 独立北向资金路由（供 stock.js 单独刷新使用） ==============
@app.get("/api/stock/north")
async def api_stock_north(code: str = "sh600519", limit: int = 5):
    """北向资金（沪股通+深股通合计）持股及变化。"""
    from fastapi.responses import JSONResponse
    code = (code or "").strip().lower()
    if not code:
        return JSONResponse({"error": "code 必填"}, status_code=400)
    try:
        from sources.company import get_north_holding
        d = get_north_holding(code, limit=limit)
        return JSONResponse(d)
    except Exception as e:
        import traceback
        LOG.error("[stock/north] %s 失败: %s\n%s", code, e, traceback.format_exc())
        return JSONResponse({"error": str(e)[:100]}, status_code=500)


def _safe_call(fn, *args, **kwargs):
    """容错调用一个函数，捕获任何异常返回 None（带完整 traceback 日志）。"""
    try:
        r = fn(*args, **kwargs)
        LOG.info("[stock/full] %s(%s, %s) OK -> %s", fn.__name__, args, kwargs,
                 type(r).__name__ + (f" len={len(r)}" if isinstance(r, (list, dict)) else ""))
        return r
    except Exception as e:
        import traceback
        LOG.error("[stock/full] %s(%s, %s) 失败: %s\n%s",
                  fn.__name__, args, kwargs, e, traceback.format_exc())
        return None


def _quote_to_deepthink_shape(q: dict) -> dict:
    pre_close = q.get("pre_close") or q.get("price", 0)
    price = q.get("price", 0)
    return dict(
        code=q.get("code", ""), name=q.get("name", ""), price=price,
        change=q.get("change", 0) or (price - pre_close),
        change_pct=q.get("change_pct", 0), pre_close=pre_close,
        open=q.get("open", pre_close), high=q.get("high", 0), low=q.get("low", 0),
        volume=q.get("volume", 0), amount=q.get("amount", 0),
        turnover_pct=q.get("turnover_pct", 0), volume_ratio=q.get("volume_ratio", 0),
        outer=q.get("outer", 0), inner=q.get("inner", 0),
        total_mv=q.get("total_mv", 0), float_mv=q.get("float_mv", 0),
        pe_dyn=q.get("pe_dyn", 0), pb=q.get("pb", 0), eps=q.get("eps", 0),
        bvps=q.get("bvps", 0), net_asset=q.get("bvps", 0),
    )


def _normalize_minute_avg(items: list) -> list:
    """修复腾讯 ifzq 的 avg×100 误差。"""
    out = []
    for x in items or []:
        m = dict(x); a = m.get("avg")
        if isinstance(a, (int, float)) and 0 < a < 1.0:
            m["avg"] = round(a * 100, 4)
        out.append(m)
    return out


def _derive_day5_funds(klines: list) -> list:
    """由日 K 派生近5日主力净流入（近似公式）。"""
    out = []
    for k in (klines or [])[-5:]:
        close = float(k.get("close", 0)); open_ = float(k.get("open", 0))
        vol = float(k.get("vol", 0)); date = str(k.get("date", ""))
        delta = close - open_
        main_net = (delta / close) * vol if close > 0 else 0
        out.append(dict(date=date, main_net=main_net))
    return out


@app.get("/api/stock/announcement")
async def api_stock_announcement(code: str = ""):
    """公告正文。"""
    code = code.strip().lower()
    if not code:
        return {"error": "code 必填"}
    try:
        from sources.company import get_announcement_content
        d = _safe_call(get_announcement_content, code) or {}
        return d
    except Exception as e:
        LOG.warning("announcement %s 失败: %s", code, e)
        return {"error": str(e), "title": "", "content": "（加载失败）", "date": ""}


async def api_analysis_get(code: str = ""):
    code = code.strip().lower() or None
    rows = db.get_analysis_log(code)
    out = []
    for r in rows:
        try:
            data = json.loads(r["data"])
        except Exception:
            data = {}
        out.append({"id": r["id"], "ts": r["ts"], "code": r["code"], "data": data})
    return out


async def api_analysis_post(body: dict):
    code = (body.get("code") or "").strip().lower()
    note = (body.get("note") or "").strip()
    if not code:
        return {"error": "code 必填"}
    db.log_analysis(code, {"note": note,
                           "created": datetime.datetime.now().isoformat(timespec="seconds")})
    LOG.info("analysis %s 记录 %d 字", code, len(note))
    return {"ok": True}


@app.get("/api/sysinfo")
async def api_sysinfo():
    import platform
    return {"os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "watchlist": _load_watchlist()}


# =====================================================================
# 策略 / 持仓 / 分析 API（P2 新增）
# =====================================================================
import modules.holdings.holdings as H  # noqa: E402
import modules.analysis.analysis as A  # noqa: E402

_POOL_CACHE = None


def get_pool():
    """标的下拉池（1771 只，来自 fundamentals_broad.json）。"""
    global _POOL_CACHE
    if _POOL_CACHE is not None:
        return _POOL_CACHE
    fund = os.path.join(DATA_DIR, "fundamentals_broad.json")
    if not os.path.exists(fund):
        _POOL_CACHE = []
        return _POOL_CACHE
    with open(fund, encoding="utf-8") as f:
        fund_data = json.load(f)
    pool = []
    for code, f in fund_data.items():
        mk = "bj" if code.startswith(("920", "8", "4")) else (
            "sh" if code.startswith(("60", "68", "90")) else "sz")
        pool.append(dict(code=code, name=f.get("name") or code,
                         industry=f.get("industry") or "", market=mk))
    pool.sort(key=lambda r: r["code"])
    _POOL_CACHE = pool
    return pool


@app.get("/api/pool")
async def api_pool(cls: str = "all"):
    pool = get_pool()
    if cls and cls != "all":
        pool = [p for p in pool if p["market"] == cls]
    return {"total": len(pool), "items": pool}


@app.get("/api/holdings")
async def api_holdings():
    return {"items": H.get_holdings()}


@app.post("/api/holdings")
async def api_holdings_add(body: dict):
    code = str(body.get("code", "")).strip()
    amount = float(body.get("amount", 0) or 0)
    dingtou = bool(body.get("dingtou", False))
    if not code:
        return {"error": "标的代码不能为空"}
    pool_map = {p["code"]: p for p in get_pool()}
    if code not in pool_map:
        return {"error": f"标的 {code} 不在可投资池中"}
    holdings = H.upsert_holding(code, amount, dingtou,
                                name=pool_map[code]["name"],
                                industry=pool_map[code]["industry"])
    log_line = A.log_line
    log_line(f"添加/更新持仓 {code} amount={amount} dingtou={dingtou}")
    return {"items": holdings}


@app.post("/api/holdings/delete")
async def api_holdings_delete(body: dict):
    codes = list(body.get("codes", []))
    holdings = H.delete_holdings(codes)
    A.log_line(f"删除持仓 {sorted(codes)}")
    return {"items": holdings}


@app.get("/api/settings")
async def api_settings():
    return H.get_settings()


@app.post("/api/settings")
async def api_settings_save(body: dict):
    s = H.save_settings(body)
    A.log_line(f"更新设置 {s}")
    return s


@app.post("/api/analyze")
async def api_analyze(body: dict = None):
    body = body or {}
    ok = A.submit(force_refresh=bool(body.get("force_refresh", False)),
                  auto_track=bool(body.get("auto_track", False)))
    if not ok:
        return {"error": "分析正在进行中", "running": True}
    return {"message": "分析已提交", "running": True}


@app.get("/api/analyze/status")
async def api_analyze_status():
    return {"running": A.ANALYSIS["running"],
            "message": A.ANALYSIS["message"],
            "percent": A.ANALYSIS["percent"],
            "result": A.ANALYSIS["last_result"],
            "ts": A.ANALYSIS["last_ts"]}


@app.get("/api/analyze/events")
async def api_analyze_events():
    """SSE 进度流（P4）：POST /api/analyze 后订阅，进度实时推送，完成时推送 done+result。
    前端 EventSource 消费；若 SSE 不可用，前端回退 1.5s 轮询 /api/analyze/status。"""
    from fastapi.responses import StreamingResponse
    import asyncio

    async def gen():
        # 最多 600 * 0.5s = 5 分钟（超时由前端 EventSource 兜底重连）
        for _ in range(600):
            a = A.ANALYSIS
            payload = json.dumps({
                "running": a["running"],
                "percent": a.get("percent", 0),
                "message": a.get("message", ""),
            }, ensure_ascii=False)
            yield f"event: progress\ndata: {payload}\n\n"
            if not a["running"]:
                if a.get("last_result"):
                    done = json.dumps(a["last_result"], ensure_ascii=False)
                    yield f"event: done\ndata: {done}\n\n"
                yield "event: close\ndata: {}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/backtest")
async def api_backtest():
    p = os.path.join(DATA_DIR, "results_layer2_fresh.json")
    if not os.path.exists(p):
        return {"error": "尚未生成回测数据"}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/curves")
async def api_curves():
    p = os.path.join(DATA_DIR, "results_layer2_curves.json")
    if not os.path.exists(p):
        return {"error": "尚未生成曲线数据"}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/action_log")
async def api_action_log():
    return {"items": A.get_action_log()}


@app.get("/api/logs")
async def api_logs():
    if os.path.exists(A.LOG_FILE):
        with open(A.LOG_FILE, encoding="utf-8") as f:
            return {"items": f.read().splitlines()[-200:]}
    return {"items": []}


@app.get("/api/logs/download")
async def api_logs_download():
    from fastapi.responses import FileResponse
    if not os.path.exists(A.LOG_FILE):
        return {"error": "暂无日志"}
    return FileResponse(A.LOG_FILE, filename="analyze.log",
                        media_type="text/plain; charset=utf-8")


@app.get("/report/latest")
async def report_latest():
    from fastapi.responses import FileResponse
    files = sorted(glob.glob(os.path.join(DATA_DIR, "dashboard_*.html")))
    if not files:
        return {"error": "暂无 HTML 报告，请先保存并分析"}
    return FileResponse(files[-1])


@app.get("/api/report/md")
async def report_md(download: int = 0):
    from fastapi.responses import FileResponse, PlainTextResponse
    res = A.ANALYSIS.get("last_result")
    if not res:
        return {"error": "暂无分析结果，请先保存并分析"}
    lines = [f"# 持仓分析报告（{res['signal_date']}）\n",
             f"- 生成时间：{res['ts']}",
             f"- 市场状态：{res['summary']['regime_cn']}",
             f"- 持仓 {res['summary']['held']} 只 / 合格池 {res['summary']['buy_pool']} 只\n",
             "## 一、持仓操作卡\n",
             "| 代码 | 名称 | 行业 | 市场 | 金额(元) | 评分 | 建议 | 本周操作 | 说明 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for c in res["cards"]:
        lines.append(f"| {c['code']} | {c['name']} | {c['industry'] or '-'} | {c['market']} | "
                     f"{c.get('amount',0):.0f} | {c['score']:.0f} | {c['advice']} | {c['action']} | {c['desc']} |")
    lines += ["\n## 二、本周推荐\n",
              "| 代码 | 名称 | 行业 | 评分 | 说明 |", "|---|---|---|---|---|"]
    for r in res["recommends"][:12]:
        lines.append(f"| {r['code']} | {r['name']} | {r['industry'] or '-'} | {r['score']:.0f} | {r['desc']} |")
    lines.append("\n---\n*本报告仅供参考，不构成个人投资建议。*")
    md = "\n".join(lines)
    if download:
        fn = f"report_{res['signal_date']}.md"
        p = os.path.join(DATA_DIR, "reports")
        os.makedirs(p, exist_ok=True)
        path = os.path.join(p, fn)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return FileResponse(path, filename=fn, media_type="text/markdown; charset=utf-8")
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--host", type=str, default="0.0.0.0")
    args = ap.parse_args()
    LOG.info("=== DeepThinkCompStock P1 启动 port=%d ===", args.port)
    try:
        from services.stock_list import warmup_async
        warmup_async()
    except Exception as e:
        LOG.warning("stock_list 预热失败: %s", e)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")

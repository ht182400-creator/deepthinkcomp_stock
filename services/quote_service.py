# -*- coding: utf-8 -*-
"""
服务层：业务逻辑 + 数据源降级编排。所有入口在这里。
"""
import config
import core.fallback as fb
import logging
LOG = logging.getLogger("deepthink")
from core.cache import TtlCache, FileCache
from sources.tencent import TencentSource
from sources.eastmoney import EastmoneySource
from sources.tdx import TdxSource
from sources.npx import NpxSource

# ---------- 数据源注册（编排器） ----------
fb.register(TencentSource.name, TencentSource())
fb.register(EastmoneySource.name, EastmoneySource())
fb.register(TdxSource.name, TdxSource())
fb.register(NpxSource.name, NpxSource())

# ---------- 缓存实例 ----------
quote_cache = TtlCache(config.TTL_QUOTE)
minute_cache = TtlCache(config.TTL_MINUTE)
fund_cache = TtlCache(config.TTL_FUND)
kline_cache = FileCache(config.KLINE_CACHE_DIR, config.TTL_KLINE)
# 低频/静态数据缓存：公司财务、股东、融资融券、龙虎榜、盈利预测、净利趋势等每日级数据
static_cache = TtlCache(config.TTL_STATIC)


def _cached_static(key: str, fetcher):
    """低频数据走 static_cache（默认 10min TTL），降低 30s 轮询带来的外网请求压力。"""
    return static_cache.get_or_set(key, fetcher)[0]

_orch = fb.orchestrator()


# =====================================================================
# 报价 + 分时
# =====================================================================
def get_quote(code: str) -> dict:
    def _fetch():
        result, _src = fb.fallback(config.QUOTE_SOURCES, "get_quote", code)
        result["source"] = _src
        return result
    return quote_cache.get_or_set(f"quote:{code}", _fetch)[0]


def get_minute(code: str, date: str = "") -> list:
    """当日分时(date="") 或历史某日分时(date="YYYYMMDD")；当日走腾讯/东财，历史日优先通达信本地 .lc1。"""
    if date:
        key = f"minute:{code}:{date}"
        # 历史分时：通达信本地优先（突破腾讯近 30 天限制），无则回退腾讯/东财
        chain = ["tdx"] + config.QUOTE_SOURCES
        return minute_cache.get_or_set(
            key,
            lambda: fb.fallback(chain, "get_minute", code, date=date)[0])[0]
    return minute_cache.get_or_set(f"minute:{code}",
                                   lambda: fb.fallback(config.QUOTE_SOURCES, "get_minute", code)[0])[0]


def _minute_matches_day(code: str, date_dash: str, minute_rows: list) -> bool:
    """校验在线源返回的分时数据是否真的是请求日期的。

    腾讯/东财的免费接口对较远历史日期会忽略 date 参数，直接返回最近交易日数据，
    导致不同日期历史分时走势图完全一样。我们用该日日线 OHLC 做交叉验证：
    首根 price 应接近 open，末根 price 应接近 close（允许 1% 或 0.05 元容差）。
    """
    if not minute_rows:
        return False
    try:
        day_rows = get_kline(code, "day", limit=0)
        day = next((k for k in day_rows if k.get("date") == date_dash), None)
        if not day:
            return False
        first_price = float(minute_rows[0]["price"])
        last_price = float(minute_rows[-1]["price"])
        o, c = float(day["open"]), float(day["close"])
        tol = max(abs(o) * 0.01, 0.05)
        return abs(first_price - o) <= tol and abs(last_price - c) <= tol
    except Exception as e:
        LOG.warning("_minute_matches_day %s %s 校验失败: %s", code, date_dash, e)
        return False


def get_minute_with_meta(code: str, date: str) -> dict:
    """历史某日分时 + 来源/本地数据元信息。

    返回 {data: [...], meta: {source, local_last_date, requested_date, mismatch}}。
    - source：实际命中的数据源（"tdx" / "tencent" / "eastmoney" / "none"）。
    - local_last_date：本地通达信 .lc1 最后一根分钟线日期，无则 ""。
    - requested_date：请求的历史日期（YYYY-MM-DD）。
    - mismatch：在线源数据与请求日期日线不匹配时为 True。

    用途：当本地分钟数据落后（请求日期 > local_last_date），source 会回退到腾讯/东财；
    但免费在线源对较远日期会返回最近交易日数据，因此增加日线 OHLC 校验，
    不匹配时返回空数据 + source="none"，避免前端画出错误走势。
    """
    from sources.tdx import tdx_last_minute_date
    d8 = date.replace("-", "")
    date_dash = f"{d8[:4]}-{d8[4:6]}-{d8[6:8]}"
    chain = ["tdx"] + config.QUOTE_SOURCES
    res, used = fb.fallback(chain, "get_minute", code, date=date)
    local_last = tdx_last_minute_date(code)
    mismatch = False
    if used != "tdx" and res:
        if not _minute_matches_day(code, date_dash, res):
            mismatch = True
            res = []
            used = "none"
    return {
        "data": res,
        "meta": {
            "source": used,
            "local_last_date": local_last,
            "requested_date": date_dash,
            "mismatch": mismatch,
        },
    }


# =====================================================================
# 主力资金（东财，多节点在 eastmoney 内部处理）
# =====================================================================
def get_fund_flow(code: str) -> list:
    return fund_cache.get_or_set(f"fund:{code}",
                                 lambda: fb.fallback(["eastmoney"], "get_fund_flow", code)[0])[0]


# =====================================================================
# K线（日/周/月：通达信→npx；分钟：npx→eastmoney；+文件缓存）
# =====================================================================
# 缓存最小条数阈值：低于此视为污染缓存，强制重新拉取。
# 日/周/月来自通达信 .day（全量历史），下限用于剔除明显残缺缓存。
# 分钟 K：现在通达信本地 .lc1 优先（全量历史），故也设下限剔除「旧 npx 当日切片」
# （m60 约 4 根）。tdx 全量远大于此下限不会被误杀；仅当无本地数据回退 npx 当日时
# 才可能反复重拉（边缘情况，用户已配置 vipdoc 主路径不触发）。
_MIN_CACHE_ROWS = {"day": 200, "week": 50, "month": 20}
_MIN_CACHE_ROWS_MIN = {"m60": 10, "m30": 20, "m15": 40, "m5": 40, "m1": 100}

_PERIOD_TYPE = {
    "day": "day", "week": "day", "month": "day",
    "m1": "min", "m5": "min", "m15": "min", "m30": "min", "m60": "min",
}


def _slice(rows: list, limit: int) -> list:
    """limit<=0 表示返回全部（日线本地数据有多少显示多少）；>0 截最近 N 条。"""
    if rows and limit and limit > 0:
        return rows[-limit:]
    return rows


def _compute_period_stats(code: str) -> dict:
    """基于本地日 K 计算 60/360/今年涨幅 + 一年最高/最低（最右侧"行情"小卡用）"""
    out = {}
    try:
        rows = get_kline(code, "day", limit=0)  # 全量
    except Exception:
        return out
    if not rows:
        return out
    last = rows[-1]
    cur = float(last["close"])
    cur_date = last["date"]  # 'YYYY-MM-DD'
    if len(rows) >= 60:
        ago = float(rows[-60]["close"])
        out["pct_60d"] = round((cur / ago - 1) * 100, 2)
    if len(rows) >= 250:
        ago = float(rows[-250]["close"])
        out["pct_360d"] = round((cur / ago - 1) * 100, 2)
    year = cur_date[:4]
    for k in rows:
        if k["date"] >= f"{year}-01-01":
            ago = float(k["close"])
            out["pct_ytd"] = round((cur / ago - 1) * 100, 2)
            break
    # 滚动一年最高最低
    cutoff = f"{int(cur_date[:4]) - 1}-{cur_date[5:]}"
    last_year = [k for k in rows if k["date"] >= cutoff]
    if last_year:
        out["hi_1y"] = round(max(float(k["high"]) for k in last_year), 2)
        out["lo_1y"] = round(min(float(k["low"]) for k in last_year), 2)
    return out


def _cache_is_stale(rows: list, code: str) -> bool:
    """日 K 缓存是否过期：比较缓存最后 K 线日期 vs 通达信本地最后日期。
    - 通达信有更新（本地日期 > 缓存日期）→ 过期重拉
    - 通达信没更新（本地日期 <= 缓存日期）→ 缓存已最新，不重拉
    这样"每次看日K都刷新"的问题不会发生（本地没更新就不刷），
    通达信本地滞后时也用缓存（数据源就这么多，无法更新）。
    返回 (是否过期, 本地最后日期)。"""
    try:
        from sources.tdx import tdx_last_date
        local = tdx_last_date(code)
    except Exception:
        local = ""
    if not local or not rows:
        return False
    last = (rows[-1].get("date") or "")[:10]
    return bool(last) and local > last


def get_kline(code: str, period: str = "day", limit: int = 260) -> list:
    ptype = _PERIOD_TYPE.get(period, "day")
    key = f"{code}_{period}"
    if ptype == "day":
        chain = config.KLINE_DAY_SOURCES     # tdx → npx → eastmoney
    else:
        chain = config.KLINE_MIN_SOURCES     # npx → eastmoney

    # 日/周/月 与 分钟 K 均从数据源拉「全量」存入缓存（通达信本地有多少存多少，
    # 含跨交易日完整分钟历史）；返回时统一按请求 limit 截断（limit=0 → 全量）。
    # 注意：绝不能给分钟 K 设下限（如 2000），否则会截断 1 分钟长序列。
    fetch_limit = 0

    def _fetch():
        return fb.fallback(chain, "get_kline", code, period, fetch_limit)[0]

    cached = kline_cache.get(key)
    if cached is not None:
        # 缓存条数过少视为污染（日线/周线/月线 or 分钟 K 全量下限）
        min_rows = _MIN_CACHE_ROWS.get(period) or _MIN_CACHE_ROWS_MIN.get(period)
        if min_rows and len(cached) < min_rows:
            LOG.warning("K线缓存污染(code=%s period=%s rows=%d), 强制重拉", code, period, len(cached))
            kline_cache.invalidate(key)
        elif (ptype == "day" or ptype == "min") and _cache_is_stale(cached, code):
            # 日 K / 分钟 K：通达信本地有更新（本地最后日期 > 缓存最后日期）→ 重拉最新
            LOG.info("K线缓存过期(code=%s period=%s last=%s), 重拉通达信最新", code, period, cached[-1].get("date", "?"))
            kline_cache.invalidate(key)
        else:
            return _slice(cached, limit)
    rows = _fetch()
    if rows:
        kline_cache.set(key, rows)
    return _slice(rows, limit)


# =====================================================================
# 单标的聚合（报价 + 分时 + 主力）
# =====================================================================
def get_all(code: str) -> dict:
    result = {"code": code, "errors": []}
    try:
        result["quote"] = get_quote(code)
    except Exception as e:
        result["errors"].append(f"quote: {e}")
    try:
        result["minute"] = get_minute(code)
    except Exception as e:
        result["errors"].append(f"minute: {e}")
    try:
        result["fund"] = get_fund_flow(code)
    except Exception as e:
        result["errors"].append(f"fund: {e}")
    # 右侧"行情"小卡：基于日 K 计算 60/360/今年涨幅 + 一年最高最低（依赖 kline_cache，再走静态缓存）
    try:
        result["stats"] = _cached_static(f"stats:{code}", lambda: _compute_period_stats(code))
    except Exception as e:
        result["errors"].append(f"stats: {e}")
    # 公司综合：公告 / 财务 / 股东户数（低频，走 static_cache 10min TTL）
    try:
        from sources.company import get_announcements, get_finance_summary, get_holder_num
        result["announcements"] = _cached_static(f"ann:{code}", lambda: get_announcements(code, limit=10))
    except Exception as e:
        result["errors"].append(f"announcements: {e}")
    try:
        result["finance"] = _cached_static(f"finance:{code}", lambda: get_finance_summary(code))
    except Exception as e:
        result["errors"].append(f"finance: {e}")
    try:
        result["holders"] = _cached_static(f"holders:{code}", lambda: get_holder_num(code, limit=4))
    except Exception as e:
        result["errors"].append(f"holders: {e}")
    # 综合数据扩展：融资融券 / 龙虎榜 / 公司信息 / 盈利预测 / 净利趋势（低频）
    try:
        from sources.company import get_margin, get_lhb, get_company_profile, get_forecast, get_profit_trend
        result["margin"] = _cached_static(f"margin:{code}", lambda: get_margin(code, limit=2))
    except Exception as e:
        result["errors"].append(f"margin: {e}")
    try:
        result["lhb"] = _cached_static(f"lhb:{code}", lambda: get_lhb(code, limit=3))
    except Exception as e:
        result["errors"].append(f"lhb: {e}")
    try:
        result["company"] = _cached_static(f"company:{code}", lambda: get_company_profile(code))
    except Exception as e:
        result["errors"].append(f"company: {e}")
    try:
        result["forecast"] = _cached_static(f"forecast:{code}", lambda: get_forecast(code))
    except Exception as e:
        result["errors"].append(f"forecast: {e}")
    try:
        result["profit_trend"] = _cached_static(f"profit:{code}", lambda: get_profit_trend(code, years=4))
    except Exception as e:
        result["errors"].append(f"profit_trend: {e}")
    # 多空情绪：主力资金当日多空占比（基于已拉的 fund 分钟数据，作为舆情近似，实时不缓存）
    try:
        result["sentiment"] = _compute_sentiment(result.get("fund") or [])
    except Exception as e:
        result["errors"].append(f"sentiment: {e}")
    # Sprint 4 US-009：近 5 日主力净流入（东财 f178，低频）
    try:
        result["day_fund_5d"] = _cached_static(f"day5d:{code}", lambda: EastmoneySource().get_5d_fund_flow(code))
    except Exception as e:
        result["errors"].append(f"day_fund_5d: {e}")
    return result


def _compute_sentiment(fund_minutes: list) -> dict:
    """多空情绪：当日分钟级主力资金净流入正负占比。
    多头% = 净流入为正的分钟数 / 总分钟数（简化版，替代第三方舆情）。"""
    if not fund_minutes:
        return {}
    mains = [x.get("main", 0) for x in fund_minutes]
    mains = [m for m in mains if m is not None]
    if len(mains) < 30:
        return {}
    up = sum(1 for v in mains if v > 0)
    down = sum(1 for v in mains if v <= 0)
    total = len(mains)
    return {
        "bull_pct": round(up / total * 100, 1),
        "bear_pct": round(down / total * 100, 1),
        "days": total,
    }


# =====================================================================
# 批量聚合（Sprint 3 自选批量用，先预留实现）
# =====================================================================
from concurrent.futures import ThreadPoolExecutor  # noqa: E402


def get_many(codes: list) -> dict:
    """并发拉取多只标的：/api/quote?codes=a,b,c 支持。
    单只失败不阻塞其他，返回 {code: 结果或错误}。"""
    results = {}
    with ThreadPoolExecutor(max_workers=config.POOL_MAX_WORKERS) as pool:
        futs = {pool.submit(get_all, c): c for c in codes}
        for fut in futs:
            code = futs[fut]
            try:
                results[code] = fut.result()
            except Exception as e:
                results[code] = {"code": code, "error": str(e)}
    return results

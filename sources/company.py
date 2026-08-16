# -*- coding: utf-8 -*-
"""
公司综合数据源（东财 f10/announcement/shareholder 接口）。
- 公告/资讯：np-anotice-stock.eastmoney.com/api/security/ann
- 财务摘要：datacenter-web.eastmoney.com/api/data/get?type=RPT_F10_FINANCE_MAINFINADATA
- 股东户数：emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax
"""
import config
from sources.base import Source, http_get, pure_code


UA = config.USER_AGENT
EM_HEADERS = {"Referer": "https://data.eastmoney.com/", "User-Agent": UA}
EMWEB_HEADERS = {"Referer": "https://emweb.securities.eastmoney.com/", "User-Agent": UA}
ANN_HEADERS = {"Referer": "https://data.eastmoney.com/", "User-Agent": UA}


def _to_em_secid(code: str) -> str:
    """sh600519 → 1.600519；sz000858 → 0.000858；bj → 0.xxxxxx"""
    raw = code.lower()
    c = pure_code(code)
    if raw.startswith("sh"):
        return "1." + c
    if raw.startswith("sz"):
        return "0." + c
    if raw.startswith("bj"):
        return "0." + c
    return "1." + c


def _secucode(code: str) -> str:
    """sh600519 → 600519.SH；sz000858 → 000858.SZ；bj → bj code .BJ"""
    raw = code.lower()
    c = pure_code(code)
    if raw.startswith("sh"):
        return c + ".SH"
    if raw.startswith("sz"):
        return c + ".SZ"
    if raw.startswith("bj"):
        return c + ".BJ"
    return c + ".SH"


def get_announcements(code: str, limit: int = 10) -> list:
    """公告/资讯列表（最近 N 条）：title, date, code"""
    secucode = _secucode(code)
    scode = secucode.split(".")[0]
    url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    params = {"sr": -1, "page_size": limit, "page_index": 1, "ann_type": "A",
              "client_source": "web", "stock_list": scode, "f_node": 0, "s_node": 0}
    j = http_get(url, ANN_HEADERS, params=params, limiter_name="eastmoney",
                 rate=config.RATE_LIMIT_EM).json()
    items = j.get("data", {}).get("list", []) or []
    out = []
    for it in items:
        out.append({
            "title": it.get("title", "").strip(),
            "date": (it.get("notice_date") or "")[:10],
            "code": it.get("art_code", ""),
        })
    return out


def get_announcement_content(art_code: str) -> dict:
    """公告正文（modal 用）：title, date, content(纯文本), pdf_url"""
    url = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
    params = {"art_code": art_code, "client_source": "web", "page_index": 1}
    j = http_get(url, ANN_HEADERS, params=params, limiter_name="eastmoney",
                 rate=config.RATE_LIMIT_EM).json()
    data = j.get("data") or {}
    if not data:
        return {}
    content = data.get("notice_content") or ""
    # 去 HTML 标签
    import re
    text = re.sub(r"<[^>]+>", "\n", content)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return {
        "title": data.get("notice_title") or "",
        "date": (data.get("notice_date") or "")[:10],
        "content": text,
        "pdf_url": data.get("attach_url") or "",
    }


def get_finance_summary(code: str) -> dict:
    """财务摘要（最新报告期）：revenue, net_profit, eps, gross_margin, etc."""
    secucode = _secucode(code)
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {"reportName": "RPT_F10_FINANCE_MAINFINADATA",
              "columns": "ALL",
              "filter": f'(SECUCODE="{secucode}")',  # 东财 v1 要求双引号
              "pageNumber": 1, "pageSize": 1,
              "sortColumns": "REPORT_DATE", "sortTypes": -1, "source": "WEB"}
    j = http_get(url, EM_HEADERS, params=params, limiter_name="eastmoney",
                 rate=config.RATE_LIMIT_EM).json()
    if not j.get("success"):
        return {}
    rows = (j.get("result") or {}).get("data", []) or []
    if not rows:
        return {}
    r = rows[0]
    return {
        "report_date": (r.get("REPORT_DATE") or "")[:10],
        "report_type": r.get("REPORT_DATE_NAME") or "",
        "revenue": r.get("TOTALOPERATEREVE"),         # 总营收（元）
        "net_profit": r.get("PARENTNETPROFIT"),       # 归母净利（元）
        "yoy_revenue": r.get("TOTALOPERATEREVETZ"),   # 营收同比%
        "yoy_profit": r.get("PARENTNETPROFITTZ"),     # 净利同比%
        "eps": r.get("EPSJB"),                        # 每股收益（元）
        "roe": r.get("ROEJQ"),                        # ROE%
        "gross_margin": r.get("MLR"),                 # 毛利率%
    }


def get_holder_num(code: str, limit: int = 4) -> list:
    """股东户数（最近 N 期）：date, total, change_pct"""
    secucode = _secucode(code)  # 600519.SH
    scode = secucode.split(".")[0]
    code_prefix = secucode.split(".")[1]  # SH
    url = "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax"
    params = {"code": f"{code_prefix}{scode}"}
    j = http_get(url, EMWEB_HEADERS, params=params, limiter_name="eastmoney",
                 rate=config.RATE_LIMIT_EM).json()
    items = j.get("gdrs", []) or []
    out = []
    for it in items[:limit]:
        out.append({
            "date": (it.get("END_DATE") or "")[:10],
            "total": it.get("HOLDER_TOTAL_NUM"),
            "change_pct": it.get("TOTAL_NUM_RATIO"),
            "avg_shares": it.get("AVG_FREE_SHARES"),
        })
    return out


def _dc_get(report_name: str, filter_str: str, sort: str = "", limit: int = 5,
            headers=None) -> list:
    """东财 datacenter v1 统一查询（报表名 + 过滤条件），返回 rows 列表。"""
    params = {"reportName": report_name, "columns": "ALL", "filter": filter_str,
              "pageNumber": 1, "pageSize": limit, "source": "WEB"}
    if sort:
        params["sortColumns"] = sort
        params["sortTypes"] = -1
    j = http_get("https://datacenter-web.eastmoney.com/api/data/v1/get",
                 headers or EM_HEADERS, params=params, limiter_name="eastmoney",
                 rate=config.RATE_LIMIT_EM).json()
    if not j.get("success"):
        return []
    return (j.get("result") or {}).get("data", []) or []


def get_margin(code: str, limit: int = 2) -> list:
    """融资融券（最近 N 交易日）：date, rzye(融资余额), rqye(融券余额), rzrqye(两融合计), rzyezb(融资占比%)"""
    scode = _secucode(code).split(".")[0]
    rows = _dc_get("RPTA_WEB_RZRQ_GGMX", f'(SCODE="{scode}")', sort="DATE", limit=limit)
    out = []
    for r in rows:
        out.append({
            "date": (r.get("DATE") or "")[:10],
            "rzye": r.get("RZYE"),          # 融资余额（元）
            "rqye": r.get("RQYE"),          # 融券余额（元）
            "rzrqye": r.get("RZRQYE"),      # 两融合计（元）
            "rzyezb": r.get("RZYEZB"),      # 融资余额占比（%）
        })
    return out


def get_lhb(code: str, limit: int = 3) -> list:
    """龙虎榜（最近上榜记录）：date, amount(成交额), explain(说明), change_pct"""
    scode = _secucode(code).split(".")[0]
    rows = _dc_get("RPT_DAILYBILLBOARD_DETAILSNEW", f'(SECURITY_CODE="{scode}")',
                   sort="TRADE_DATE", limit=limit)
    out = []
    for r in rows:
        out.append({
            "date": (r.get("TRADE_DATE") or "")[:10],
            "amount": r.get("BILLBOARD_DEAL_AMT"),
            "explain": r.get("EXPLAIN") or "",
            "change_pct": r.get("CHANGE_RATE"),
        })
    return out


def get_north_holding(code: str, limit: int = 5) -> dict:
    """北向资金（沪股通+深股通合计）持股变化。
    报表 RPT_MUTUAL_HOLDSTOCKNORTH_STA：返回最新 N 个交易日。
    真实字段（实测）：
      TRADE_DATE 日期, HOLD_SHARES 持股(股), HOLD_MARKET_CAP 市值(元),
      HOLD_SHARES_RATIO 持股占比(%, 自由流通股比),
      CHANGE_RATE 持股变化率(% 环比)
    返回 dict：
      {
        "latest_date": "2026-08-15",
        "holdings": 持股(万股),
        "hold_value": 持股市值(元),
        "ratio": 持股占比(%) ,
        "change_pct": 持股变化率(%) ,
        "rows": 历史 N 条 [{"date","holdings","hold_value","ratio","change_pct"}, ...]
      }
    失败时返回 {"error": "原因"} 而非 raise，方便上层吃掉。
    """
    try:
        scode = _secucode(code).split(".")[0]
        rows = _dc_get("RPT_MUTUAL_HOLDSTOCKNORTH_STA",
                       f'(SECURITY_CODE="{scode}")',
                       sort="TRADE_DATE", limit=limit)
        if not rows:
            return {"error": "无北向持股数据"}
        out_rows = []
        for r in rows:
            out_rows.append({
                "date": (r.get("TRADE_DATE") or "")[:10],
                "holdings": round((r.get("HOLD_SHARES") or 0) / 1e4, 2),
                "hold_value": round(r.get("HOLD_MARKET_CAP") or 0, 2),
                "ratio": Number(r.get("HOLD_SHARES_RATIO")),
                "change_pct": Number(r.get("CHANGE_RATE")),
            })
        latest = rows[0]
        return {
            "latest_date": (latest.get("TRADE_DATE") or "")[:10],
            "holdings": round((latest.get("HOLD_SHARES") or 0) / 1e4, 2),
            "hold_value": round(latest.get("HOLD_MARKET_CAP") or 0, 2),
            "ratio": Number(latest.get("HOLD_SHARES_RATIO")),
            "change_pct": Number(latest.get("CHANGE_RATE")),
            "rows": out_rows,
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:60]}"}


def Number(v):
    """安全转 float，None/空字符串/非数返回 None。"""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def get_company_profile(code: str) -> dict:
    """公司基本信息：org_name(全称), industry(申万行业), market, main_business(主营)"""
    secucode = _secucode(code)
    scode = secucode.split(".")[0]
    code_prefix = secucode.split(".")[1]
    url = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax"
    params = {"code": f"{code_prefix}{scode}"}
    j = http_get(url, EMWEB_HEADERS, params=params, limiter_name="eastmoney",
                 rate=config.RATE_LIMIT_EM).json()
    jb = (j.get("jbzl") or [{}])[0]
    out = {
        "org_name": jb.get("ORG_NAME") or "",
        "industry": jb.get("EM2016") or "",
        "market": jb.get("TRADE_MARKET") or "",
        "csrc_industry": jb.get("INDUSTRYCSRC1") or "",
    }
    return out


def get_forecast(code: str) -> dict:
    """分析师盈利预测：机构数/买入/增持 + 年度 EPS 预测"""
    scode = _secucode(code).split(".")[0]
    rows = _dc_get("RPT_WEB_RESPREDICT", f'(SECURITY_CODE="{scode}")', limit=1)
    if not rows:
        return {}
    r = rows[0]
    return {
        "org_num": r.get("RATING_ORG_NUM"),          # 评级机构数
        "buy_num": r.get("RATING_BUY_NUM"),          # 买入
        "add_num": r.get("RATING_ADD_NUM"),          # 增持
        "eps_years": [
            {"year": r.get("YEAR1"), "mark": r.get("YEAR_MARK1"), "eps": r.get("EPS1")},
            {"year": r.get("YEAR2"), "mark": r.get("YEAR_MARK2"), "eps": r.get("EPS2")},
            {"year": r.get("YEAR3"), "mark": r.get("YEAR_MARK3"), "eps": r.get("EPS3")},
            {"year": r.get("YEAR4"), "mark": r.get("YEAR_MARK4"), "eps": r.get("EPS4")},
        ],
    }


def get_profit_trend(code: str, years: int = 4) -> list:
    """年度归母净利（净利同比柱状图数据）：[year, net_profit]"""
    secucode = _secucode(code)
    params = {"reportName": "RPT_F10_FINANCE_MAINFINADATA", "columns": "ALL",
              "filter": f'(SECUCODE="{secucode}")', "pageNumber": 1, "pageSize": years * 4,
              "sortColumns": "REPORT_DATE", "sortTypes": -1, "source": "WEB"}
    j = http_get("https://datacenter-web.eastmoney.com/api/data/v1/get",
                 EM_HEADERS, params=params, limiter_name="eastmoney",
                 rate=config.RATE_LIMIT_EM).json()
    if not j.get("success"):
        return []
    rows = (j.get("result") or {}).get("data", []) or []
    # 取每年年报（REPORT_DATE 为 XXXX-12-31），去重
    by_year = {}
    for r in rows:
        rd = (r.get("REPORT_DATE") or "")[:10]
        if rd and rd.endswith("-12-31"):
            y = rd[:4]
            by_year.setdefault(y, r)
    out = []
    for y in sorted(by_year, reverse=True)[:years]:
        r = by_year[y]
        out.append({"year": y, "net_profit": r.get("PARENTNETPROFIT"),
                    "yoy": r.get("PARENTNETPROFITTZ")})
    return out


class CompanySource(Source):
    name = "company"

    def get_quote(self, code: str) -> dict:
        raise NotImplementedError("company 源不提供行情")

    def get_minute(self, code: str) -> list:
        raise NotImplementedError("company 源不提供分时")

    def get_kline(self, code: str, period: str, limit: int) -> list:
        raise NotImplementedError("company 源不提供 K 线")

    def get_fund_flow(self, code: str) -> list:
        raise NotImplementedError("company 源不提供资金流")
# -*- coding: utf-8 -*-
"""
东方财富数据源（兜底 + 主力资金）：多节点自动轮换（push2 → push2delay）。
- 主力资金（分钟级）：/api/qt/stock/fflow/kline/get?klt=1
  字段顺序实测（fields2="f51,f52,f53,f54,f55,f56"，kline 返回 6 列 = time + 5 数值，f56 缺失）：
    c[1]=f51超大单, c[2]=f52大单, c[3]=f53主力(大+超大), c[4]=f54中单, c[5]=f55小单
- 报价兜底：/api/qt/stock/get
- 分时兜底：/api/qt/stock/trends2/get
"""
import config
from sources.base import Source, http_get, to_secid, pure_code

HEADERS = {"Referer": "https://data.eastmoney.com/", "User-Agent": config.USER_AGENT}
HOSTS = config.FUND_HOSTS


def _get_with_fallback(path: str, params: dict) -> dict:
    """东财多节点轮换：主节点失败自动切 delay 节点。返回 JSON dict。"""
    last_err = None
    for host in HOSTS:
        try:
            url = f"https://{host}{path}"
            r = http_get(url, HEADERS, params=params, limiter_name="eastmoney",
                         rate=config.RATE_LIMIT_EM)
            return r.json()
        except Exception as e:
            last_err = e
    raise RuntimeError(f"东财多节点全失败: {last_err}")


class EastmoneySource(Source):
    name = "eastmoney"

    def get_fund_flow(self, code: str) -> list:
        secid = to_secid(code)
        j = _get_with_fallback("/api/qt/stock/fflow/kline/get", {
            "lmt": "240", "klt": "1", "secid": secid,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56",
        })
        klines = j.get("data", {}).get("klines", [])
        if not klines:
            raise RuntimeError(f"东财资金流无数据: {code}")
        out = []
        for k in klines:
            c = k.split(",")
            if len(c) < 6:
                continue
            out.append({
                "t": c[0][11:16] if len(c[0]) > 11 else c[0],
                "super_big": float(c[1]),    # f51 超大单
                "big": float(c[2]),          # f52 大单
                "main": float(c[3]),          # f53 主力（大+超大）
                "mid": float(c[4]),           # f54 中单
                "small": float(c[5]),         # f55 小单
            })
        return out

    def get_day_fund_flow(self, code: str, days: int = 20) -> list:
        """日级主力净流入（近 N 日）：[main, main, ...]，供多空情绪计算。
        klt=101 日线资金流。"""
        secid = to_secid(code)
        j = _get_with_fallback("/api/qt/stock/fflow/kline/get", {
            "lmt": str(days), "klt": "101", "secid": secid,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56",
        })
        klines = j.get("data", {}).get("klines", [])
        out = []
        for k in klines:
            c = k.split(",")
            if len(c) < 4:
                continue
            out.append({"date": c[0][:10], "main": float(c[3])})  # c[3]=f53 主力
        return out

    def get_5d_fund_flow(self, code: str) -> list:
        """近 5 日主力净流入（东财 push2delay quote f178，JSON 字符串）。
        f178 = '[{"date":"...","mainNetAmt":...}, ...]'（旧→新 5 天）"""
        import json as _json
        secid = to_secid(code)
        last_err = None
        for host in HOSTS:
            try:
                j = http_get(f"https://{host}/api/qt/stock/get",
                             {"Referer": "https://quote.eastmoney.com/", "User-Agent": config.USER_AGENT},
                             params={"secid": secid, "fields": "f178"},
                             limiter_name="eastmoney", rate=config.RATE_LIMIT_EM).json()
                raw = (j.get("data") or {}).get("f178") or ""
                if isinstance(raw, str):
                    raw = _json.loads(raw) if raw.startswith("[") else []
                out = []
                for it in raw:
                    if isinstance(it, dict) and it.get("date") and it.get("mainNetAmt") is not None:
                        out.append({"date": it["date"], "main": it["mainNetAmt"]})
                # 无数据不算失败（正常场景：非两融/停牌等），返回空
                return out
            except Exception as e:
                last_err = e
        raise RuntimeError(f"东财 5 日资金流全失败: {last_err}")

    def get_quote(self, code: str) -> dict:
        secid = to_secid(code)
        j = _get_with_fallback("/api/qt/stock/get", {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f168,f169,f170",
        })
        d = j.get("data", {})
        if not d:
            raise RuntimeError(f"东财快照无数据: {code}")
        price = d.get("f43", 0) / 100
        pre_close = d.get("f60", 0) / 100
        return {
            "code": pure_code(code),
            "name": d.get("f58", ""),
            "price": price,
            "pre_close": pre_close,
            "open": d.get("f46", 0) / 100,
            "change": round(price - pre_close, 3),
            "change_pct": round(d.get("f170", 0) / 100, 2),
            "volume": d.get("f47", 0),
            "amount": d.get("f48", 0) / 1e4,
        }

    def get_minute(self, code: str) -> list:
        secid = to_secid(code)
        j = _get_with_fallback("/api/qt/stock/trends2/get", {
            "secid": secid, "ndays": "1", "iscr": "0",
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        })
        trends = j.get("data", {}).get("trends", [])
        if not trends:
            raise RuntimeError(f"东财分时无数据: {code}")
        out = []
        for ln in trends:
            c = ln.split(",")
            if len(c) < 8:
                continue
            t = c[0]
            out.append({
                "t": t[11:16] if len(t) > 15 else t,
                "price": float(c[2]),
                "avg": float(c[7]),
                "vol": float(c[5]),
                "amount": float(c[6]),
            })
        return out

    def get_kline(self, code: str, period: str, limit: int) -> list:
        raise NotImplementedError("东财 K 线 HTTP 接口不稳，用 npx/通达信")

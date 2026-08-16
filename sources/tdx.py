# -*- coding: utf-8 -*-
"""
通达信本地数据源：历史日/周/月 K 权威源（0.01s，含全历史）。
.day 每条 32 字节: <iiiiifii> 日期(YYYYMMDD) 开 高 低 收(×100) 额(float) 量(手) 保留
周/月 K 从日线本地聚合（无网络依赖）。
"""
import struct
import os

import config
from sources.base import Source


def read_tdx_day(code: str) -> list:
    """读本地通达信 .day 全部记录 → [{date,open,close,high,low,vol},...]"""
    mkt, pure = code[:2], code[2:]
    f = os.path.join(config.TDX_ROOT, mkt, "lday", f"{mkt}{pure}.day")
    if not os.path.exists(f):
        return []
    try:
        with open(f, "rb") as fh:
            data = fh.read()
    except Exception:
        return []
    n = len(data) // 32
    out = []
    for i in range(n):
        d, o, h, l, c, amt, vol, _r = struct.unpack("<iiiiifii", data[i * 32:(i + 1) * 32])
        if d <= 0 or c <= 0:
            continue
        out.append({
            "date": f"{d // 10000:04d}-{d % 10000 // 100:02d}-{d % 100:02d}",
            "open": o / 100.0,
            "close": c / 100.0,
            "high": h / 100.0,
            "low": l / 100.0,
            "vol": vol,
            "amount": round(amt, 2),
        })
    return out


def tdx_last_minute_date(code: str) -> str:
    """轻量读通达信 .lc1 最后一条 1 分钟线的日期（YYYY-MM-DD），不解析全部记录。
    用于判断本地分钟数据源是否更新（与请求的历史分时日期对比）。"""
    mkt, pure = code[:2], code[2:]
    f = os.path.join(config.TDX_ROOT, mkt, "minline", f"{mkt}{pure}.lc1")
    if not os.path.exists(f):
        return ""
    try:
        size = os.path.getsize(f)
        if size < 32:
            return ""
        with open(f, "rb") as fh:
            fh.seek(size - 32)
            data = fh.read(32)
        d, _t, _o, _h, _l, _c, _amt, _vol, _r = _MIN1.unpack_from(data, 0)
        if _c <= 0:
            return ""
        y, rem = divmod(d, 2048)
        y += 2004
        mo, da = divmod(rem, 100)
        return f"{y:04d}-{mo:02d}-{da:02d}"
    except Exception:
        return ""


def tdx_last_date(code: str) -> str:
    """轻量读通达信 .day 最后一条日期（YYYY-MM-DD），不解析全部记录。
    用于判断本地数据源是否更新（缓存同步）。"""
    mkt, pure = code[:2], code[2:]
    f = os.path.join(config.TDX_ROOT, mkt, "lday", f"{mkt}{pure}.day")
    if not os.path.exists(f):
        return ""
    try:
        size = os.path.getsize(f)
        if size < 32:
            return ""
        with open(f, "rb") as fh:
            fh.seek(size - 32)
            data = fh.read(32)
        d, _o, _h, _l, _c, _amt, _vol, _r = struct.unpack("<iiiiifii", data)
        if d <= 0:
            return ""
        return f"{d // 10000:04d}-{d % 10000 // 100:02d}-{d % 100:02d}"
    except Exception:
        return ""


def aggregate(days: list, n_per: int) -> list:
    """日线 → 周期线（每 n_per 根聚合 OHLCV）"""
    out = []
    for i in range(0, len(days), n_per):
        chunk = days[i:i + n_per]
        out.append({
            "date": chunk[-1]["date"],
            "open": chunk[0]["open"],
            "close": chunk[-1]["close"],
            "high": max(x["high"] for x in chunk),
            "low": min(x["low"] for x in chunk),
            "vol": sum(x["vol"] for x in chunk),
            "amount": round(sum(x.get("amount", 0) for x in chunk), 2),
        })
    return out


# 分钟 K 周期 → 每根包含的 1 分钟根数
_MIN_PERIODS = {"m1": 1, "m5": 5, "m15": 15, "m30": 30, "m60": 60}

# 通达信 .lc1 单条结构（32 字节，小端，无文件头）：
#  date(uint16: 年=(n/2048)+2004, 月, 日) time(uint16: 距午夜分钟数)
#  open/high/low/close(float32) amount(float32) vol(uint32) reserved(uint32)
#  注意 date/time 为无符号 uint16；2026+ 的日期编码值 > 32767，必须用 'H' 而非有符号 'h'。
_MIN1 = struct.Struct("<HHfffffII")


def read_tdx_minute(code: str) -> list:
    """读本地通达信 .lc1 全部 1 分钟线 → [{date,time,open,high,low,close,amount,vol},...]（跨交易日全量）。

    路径：vipdoc/{mkt}/minline/{mkt}{pure}.lc1。vol 单位=股。
    """
    mkt, pure = code[:2], code[2:]
    f = os.path.join(config.TDX_ROOT, mkt, "minline", f"{mkt}{pure}.lc1")
    if not os.path.exists(f):
        return []
    try:
        with open(f, "rb") as fh:
            data = fh.read()
    except Exception:
        return []
    n = len(data) // 32
    out = []
    ap = out.append
    for i in range(n):
        d, t, o, h, l, c, amt, vol, _r = _MIN1.unpack_from(data, i * 32)
        if c <= 0:
            continue
        y, rem = divmod(d, 2048)
        y += 2004
        mo, da = divmod(rem, 100)
        hh, mm = divmod(t, 60)
        ap({
            "date": f"{y:04d}-{mo:02d}-{da:02d}",
            "time": f"{hh:02d}:{mm:02d}",
            "open": round(o, 2), "high": round(h, 2),
            "low": round(l, 2), "close": round(c, 2),
            "amount": amt, "vol": vol,
        })
    return out


def aggregate_minute(rows1m: list, period_min: int) -> list:
    """1 分钟全量 → 目标周期 K。按交易日分组，组内每 period_min 根聚合成一根；
    末组不足 period_min 根也合成一根（如交易日尾盘）。"""
    out, bucket, cur = [], [], None

    def flush():
        if bucket:
            out.append({
                "date": f"{bucket[0]['date']} {bucket[-1]['time']}",
                "open": bucket[0]["open"],
                "close": bucket[-1]["close"],
                "high": max(x["high"] for x in bucket),
                "low": min(x["low"] for x in bucket),
                "vol": sum(x["vol"] for x in bucket),
                "amount": round(sum(x["amount"] for x in bucket), 2),
            })

    for r in rows1m:
        if r["date"] != cur:
            flush()
            bucket = []
            cur = r["date"]
        bucket.append(r)
        if len(bucket) >= period_min:
            flush()
            bucket = []
    flush()
    return out


class TdxSource(Source):
    name = "tdx"

    def get_kline(self, code: str, period: str, limit: int) -> list:
        if period in ("day", "week", "month"):
            days = read_tdx_day(code)
            if not days:
                raise RuntimeError(f"通达信本地无 {code} 日线数据")
            if period == "day":
                rows = days
            elif period == "week":
                rows = aggregate(days, 5)
            else:
                rows = aggregate(days, 22)
            return rows if not limit else rows[-limit:]
        ppm = _MIN_PERIODS.get(period)
        if ppm is None:
            raise RuntimeError(f"通达信不支持周期: {period}")
        rows1m = read_tdx_minute(code)
        if not rows1m:
            raise RuntimeError(f"通达信本地无 {code} 分钟线数据")
        rows = aggregate_minute(rows1m, ppm)
        return rows if not limit else rows[-limit:]

    def get_quote(self, code: str) -> dict:
        raise NotImplementedError("通达信只提供历史 K")

    def get_minute(self, code: str, date: str = "") -> list:
        """当日分时(date="") 走腾讯/东财（实时）；历史某日(date=YYYYMMDD)走本地 .lc1。"""
        if not date:
            raise NotImplementedError("当日分时走腾讯/东财（实时）")
        d8 = date.replace("-", "")
        date_dash = f"{d8[:4]}-{d8[4:6]}-{d8[6:8]}"
        rows1m = read_tdx_minute(code)
        out = []
        for r in rows1m:
            if r["date"] != date_dash:
                continue
            avg = round(r["amount"] / r["vol"], 2) if r["vol"] else r["close"]
            out.append({
                "t": r["time"], "price": r["close"], "avg": avg,
                "vol": r["vol"], "amount": r["amount"],
            })
        if not out:
            raise RuntimeError(f"通达信本地无 {code} {date_dash} 分时数据")
        return out

    def get_fund_flow(self, code: str) -> list:
        raise NotImplementedError("通达信只提供历史 K")

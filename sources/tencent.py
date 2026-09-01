# -*- coding: utf-8 -*-
"""
腾讯自选股数据源（首选）：分时 + 报价。
- 分时：ifzq.gtimg.cn/appstock/app/minute/query
- 报价：qt.gtimg.cn/q=code
数据来自腾讯自选股（交易所官方行情）。
"""
import config
from sources.base import Source, http_get, pure_code

UA = config.USER_AGENT
HEADERS = {"Referer": "https://gu.qq.com/", "User-Agent": UA}


class TencentSource(Source):
    name = "tencent"

    def get_quote(self, code: str) -> dict:
        r = http_get(f"https://qt.gtimg.cn/q={code}", HEADERS, limiter_name="tencent",
                     rate=config.RATE_LIMIT_TX)
        r.encoding = "gbk"
        body = r.text.strip()
        if "=" not in body:
            raise RuntimeError(f"腾讯快照无数据: {code}")
        f = body.split("=", 1)[1].strip('"').split("~")
        if len(f) < 32:
            raise RuntimeError(f"腾讯快照字段不足: {code}")
        price = float(f[3] or 0)
        pre_close = float(f[4] or 0)
        change = price - pre_close
        change_pct = change / pre_close * 100 if pre_close else 0
        # 五档盘口：f[9..18] = 买1~买5（价/量），f[19..28] = 卖1~卖5
        bids, asks = [], []
        for i in range(5):
            try: bids.append({"price": float(f[9 + 2*i] or 0), "vol": float(f[10 + 2*i] or 0)})
            except Exception: bids.append(None)
            try: asks.append({"price": float(f[19 + 2*i] or 0), "vol": float(f[20 + 2*i] or 0)})
            except Exception: asks.append(None)
        # 字段映射（按实测）：f[30]=时间, f[33]=最高, f[34]=最低, f[38]=换手率(%)
        high = float(f[33]) if len(f) > 33 and f[33] else 0
        low  = float(f[34]) if len(f) > 34 and f[34] else 0
        turnover = float(f[38]) if len(f) > 38 and f[38] else 0
        # 扩展指标（按实测）：f[7]=外盘(手) f[8]=内盘(手) f[39]=PE(动) f[44]=流通市值(亿)
        #                   f[45]=总市值(亿) f[46]=市净率 f[49]=量比 f[51]=均价
        outer_vol = float(f[7] or 0) if len(f) > 7 else 0
        inner_vol = float(f[8] or 0) if len(f) > 8 else 0
        pe_dyn = float(f[39] or 0) if len(f) > 39 and f[39] else 0
        float_mv = float(f[44] or 0) if len(f) > 44 and f[44] else 0
        total_mv = float(f[45] or 0) if len(f) > 45 and f[45] else 0
        pb = float(f[46] or 0) if len(f) > 46 and f[46] else 0
        volume_ratio = float(f[49] or 0) if len(f) > 49 and f[49] else 0
        avg_price = float(f[51] or 0) if len(f) > 51 and f[51] else 0
        # 振幅按 (high-low)/pre_close 计算（腾讯字段不可靠）
        amplitude = (high - low) / pre_close * 100 if pre_close and high and low else 0
        return {
            "code": pure_code(code),
            "name": f[1],
            "price": price,
            "pre_close": pre_close,
            "open": float(f[5] or 0),
            "high": high,
            "low": low,
            "change": round(change, 3),
            "change_pct": round(change_pct, 2),
            "volume": float(f[6] or 0),
            "amount": float(f[37] or 0) if len(f) > 37 else 0,
            "time": f[30] if len(f) > 30 else "",
            "turnover_pct": turnover,
            "amplitude_pct": round(amplitude, 2),
            "outer": outer_vol,            # 外盘(手)
            "inner": inner_vol,            # 内盘(手)
            "pe_dyn": pe_dyn,              # 市盈率(动)
            "pb": pb,                      # 市净率
            "float_mv": float_mv,          # 流通市值(亿)
            "total_mv": total_mv,          # 总市值(亿)
            "volume_ratio": volume_ratio,  # 量比
            "avg_price": avg_price,        # 均价
            "order_book": {"bids": bids, "asks": asks},
        }

    def get_minute(self, code: str, date: str = "") -> list:
        # date 格式 YYYYMMDD（可选，缺省为当日）；历史某日必须填
        url = f"https://ifzq.gtimg.cn/appstock/app/minute/query?code={code}"
        if date:
            url += f"&date={date}"
        j = http_get(url, HEADERS, limiter_name="tencent", rate=config.RATE_LIMIT_TX).json()
        node = j.get("data", {}).get(code, {})
        rows = node.get("data", {}).get("data", [])
        if not rows:
            raise RuntimeError(f"腾讯分时无数据: {code} date={date or 'today'}")
        # 腾讯 ifzq 分时：每条 "time price cum_vol cum_amount"
        # cum_vol 单位为"股"，cum_amount 单位为"元"，均是从开盘开始的累计值。
        # 后端直接差分得到每分钟的成交量/成交额，并计算出正确均价。
        out = []
        prev_vol = 0.0
        prev_amt = 0.0
        for ln in rows:
            p = ln.split()
            if len(p) < 4:
                continue
            t, price, cum_vol, cum_amt = p[0], float(p[1]), float(p[2]), float(p[3])
            minute_vol = max(0.0, cum_vol - prev_vol)
            minute_amt = max(0.0, cum_amt - prev_amt)
            prev_vol = cum_vol
            prev_amt = cum_amt
            out.append({
                "t": t,
                "price": price,
                    # 腾讯 ifzq：cum_vol 单位为"手"（1手=100股），cum_amt 单位为"元"
                # 均价 = 元/股 = cum_amt / (cum_vol * 100)
                "avg": round(cum_amt / (cum_vol * 100), 3) if cum_vol else price,
                "vol": minute_vol,      # 每分钟成交量（手）
                "amount": minute_amt,   # 每分钟成交额（元）
            })
        # 截断收盘后的伪数据：腾讯 ifzq 在收盘后仍持续返回"最后一帧"（价格定格、vol/amt 微量累加）
        # 找到价格最后变动的位置，保留到 +1
        if len(out) >= 2:
            last_change = 0
            for i in range(1, len(out)):
                if out[i]["price"] != out[i - 1]["price"]:
                    last_change = i
            out = out[: last_change + 1]
        return out

    def get_kline(self, code: str, period: str, limit: int) -> list:
        raise NotImplementedError("日 K 用通达信本地；分钟 K 用 npx")

    def get_fund_flow(self, code: str) -> list:
        raise NotImplementedError("腾讯公开接口无主力资金数据")

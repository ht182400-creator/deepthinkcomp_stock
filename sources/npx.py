# -*- coding: utf-8 -*-
"""
npx westock-data-skillhub 数据源（腾讯自选股 CLI 封装，离线补全/分钟 K）。
调用：npx.cmd -y westock-data-skillhub@1.0.5 kline <code> --period <p> --limit <n>
输出 markdown 表格，动态表头解析（日线 close/vol vs 分钟线 last/volume）。
"""
import re
import subprocess
import sys

from sources.base import Source

_KLINE_RE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{4}/\d{2}/\d{2} \d{2}:\d{2})\s*\|")


def parse_kline(text: str) -> list:
    """markdown 表格 → [{date,open,close,high,low,vol},...]"""
    header = None
    out = []
    for ln in text.splitlines():
        line = ln.strip()
        if line.startswith("|") and "date" in line.lower():
            header = [c.strip().lower() for c in line.strip("|").split("|")]
            continue
        if "---" in line or not line.startswith("|") or not header:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        try:
            rec = {col: val for col, val in zip(header, cells)}
            out.append({
                "date": rec.get("date", ""),
                "open": float(rec.get("open", 0) or 0),
                "close": float((rec.get("close") or rec.get("last") or 0)),
                "high": float(rec.get("high", 0) or 0),
                "low": float(rec.get("low", 0) or 0),
                "vol": float((rec.get("volume") or rec.get("vol") or 0)),
            })
        except (ValueError, TypeError):
            pass
    return out


def kline_npx(code: str, period: str, limit: int) -> list:
    """直接调用 npx（不经缓存/编排）。"""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run(
            ["npx.cmd", "-y", "westock-data-skillhub@1.0.5", "kline",
             code, "--period", period, "--limit", str(limit)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, creationflags=flags,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"npx kline 超时: {code} {period}")
    except Exception as e:
        raise RuntimeError(f"npx 调用失败: {e}")
    if r.returncode != 0:
        raise RuntimeError(f"npx 错误: {r.stderr[:200]}")
    return parse_kline(r.stdout)


class NpxSource(Source):
    name = "npx"

    def get_kline(self, code: str, period: str, limit: int) -> list:
        return kline_npx(code, period, limit)

    def get_quote(self, code: str) -> dict:
        raise NotImplementedError("npx 用于 K 线，报价走腾讯/东财")

    def get_minute(self, code: str) -> list:
        raise NotImplementedError("npx 分时走腾讯")

    def get_fund_flow(self, code: str) -> list:
        raise NotImplementedError("npx 主力资金走东财")

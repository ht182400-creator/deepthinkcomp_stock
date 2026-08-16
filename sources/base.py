# -*- coding: utf-8 -*-
"""
数据源抽象基类 + 通用工具。
所有数据源适配器实现 Source 接口，由 core.fallback 编排降级。
"""
from abc import ABC, abstractmethod

import requests

import config
from core.rate_limiter import acquire


class Source(ABC):
    """统一数据源接口。新增数据源只需实现本类并注册。"""

    name: str = "base"

    @abstractmethod
    def get_quote(self, code: str) -> dict:
        """行情快照：{code,name,price,pre_close,open,change,change_pct,volume,amount}"""
        raise NotImplementedError

    @abstractmethod
    def get_minute(self, code: str) -> list:
        """当日分时：[{t,price,avg,vol,amount},...]"""
        raise NotImplementedError

    @abstractmethod
    def get_kline(self, code: str, period: str, limit: int) -> list:
        """K线：[{date,open,close,high,low,vol},...]"""
        raise NotImplementedError

    @abstractmethod
    def get_fund_flow(self, code: str) -> list:
        """分钟级主力资金：[{t,main,super_big,big,mid,small},...]"""
        raise NotImplementedError


# ---------- 通用工具 ----------
def to_secid(code: str) -> str:
    """sh600519 → 1.600519；sz000001 → 0.000001"""
    code = code.strip().lower()
    if "." in code:
        return code
    pure = code[2:] if code.startswith(("sh", "sz", "bj")) else code
    if pure.startswith(("6", "9", "5")):
        return f"1.{pure}"
    return f"0.{pure}"


def pure_code(code: str) -> str:
    """sh600519 → 600519；600519.sh → 600519"""
    code = code.strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        code = code[2:]
    return code.replace(".sh", "").replace(".sz", "").replace(".bj", "")


def http_get(url: str, headers: dict, params: dict = None, limiter_name: str = None,
             rate: float = None, timeout: float = None) -> requests.Response:
    """带限流的 GET 请求。限流失败抛 RuntimeError。"""
    timeout = timeout or config.HTTP_TIMEOUT
    if limiter_name and not acquire(limiter_name, rate or 2.0):
        raise RuntimeError(f"限流: {limiter_name}")
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r

# -*- coding: utf-8 -*-
"""
令牌桶限流：控制对单个数据源的请求频率，避免被封 IP。
默认东财 2 req/s、腾讯 5 req/s（config 可调）。
线程安全。
"""
import threading
import time


class TokenBucket:
    def __init__(self, rate: float, capacity: float = None):
        self.rate = rate                      # 每秒补充令牌数
        # 显式 capacity=0 是合法值（空桶），不能与「未指定」混淆
        self.capacity = capacity if capacity is not None else rate
        self._tokens = self.capacity
        self._last = time.time()
        self._lock = threading.Lock()

    def acquire(self, block: bool = True, timeout: float = 5.0) -> bool:
        """取一个令牌。block=True 等待；返回是否成功。"""
        deadline = time.time() + timeout
        while True:
            with self._lock:
                now = time.time()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return True
                wait = (1 - self._tokens) / self.rate
            if not block or time.time() + wait > deadline:
                return False
            time.sleep(min(wait, 0.05))


# 全局限流器（按源）
_buckets = {}
_buckets_lock = threading.Lock()


def limiter(name: str, rate: float) -> TokenBucket:
    with _buckets_lock:
        if name not in _buckets:
            _buckets[name] = TokenBucket(rate)
        return _buckets[name]


def acquire(name: str, rate: float, timeout: float = 5.0) -> bool:
    return limiter(name, rate).acquire(timeout=timeout)

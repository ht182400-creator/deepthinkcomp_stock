# -*- coding: utf-8 -*-
"""
熔断器：数据源连续失败 N 次 → 熔断 T 秒（直接走备用源），半开后放行试探。
状态机：CLOSED（正常）→ OPEN（熔断）→ HALF_OPEN（半开试探）→ CLOSED/OPEN
线程安全（单实例）。
"""
import threading
import time


class CircuitBreaker:
    """按"数据源名"隔离的熔断器。"""

    def __init__(self, fail_threshold: int = 5, reset_seconds: float = 60,
                 half_open_max: int = 1):
        self.fail_threshold = fail_threshold
        self.reset_seconds = reset_seconds
        self.half_open_max = half_open_max
        self._lock = threading.Lock()
        self._fails = 0
        self._state = "CLOSED"          # CLOSED / OPEN / HALF_OPEN
        self._opened_at = 0.0
        self._half_trials = 0

    @property
    def state(self) -> str:
        with self._lock:
            # OPEN 超时后自动转 HALF_OPEN（进入试探窗口）
            if self._state == "OPEN" and time.time() - self._opened_at >= self.reset_seconds:
                self._state = "HALF_OPEN"
                self._half_trials = 0
            return self._state

    def allow(self) -> bool:
        """是否允许请求进入。OPEN 一律拒绝；HALF_OPEN 限量放行。"""
        with self._lock:
            st = self._state
            # OPEN 超时后自动转 HALF_OPEN（进入试探窗口）
            if st == "OPEN" and time.time() - self._opened_at >= self.reset_seconds:
                st = self._state = "HALF_OPEN"
                self._half_trials = 0
            if st == "CLOSED":
                return True
            if st == "OPEN":
                return False
            # HALF_OPEN：限量试探
            if self._half_trials < self.half_open_max:
                self._half_trials += 1
                return True
            return False

    def record_success(self):
        with self._lock:
            self._fails = 0
            self._state = "CLOSED"
            self._half_trials = 0

    def record_failure(self):
        with self._lock:
            if self._state == "CLOSED":
                self._fails += 1
                if self._fails >= self.fail_threshold:
                    self._open()
            elif self._state == "HALF_OPEN":
                self._open()   # 半开试探失败 → 立即熔断

    def _open(self):
        self._state = "OPEN"
        self._opened_at = time.time()
        self._half_trials = 0

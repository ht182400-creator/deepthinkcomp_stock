# -*- coding: utf-8 -*-
"""核心熔断器单元测试：状态机 / 阈值 / 半开试探 / 死锁回归。"""
import time
import unittest

from core.circuit_breaker import CircuitBreaker


class TestCircuitBreaker(unittest.TestCase):

    def setUp(self):
        self.cb = CircuitBreaker(fail_threshold=3, reset_seconds=0.3, half_open_max=1)

    def test_initial_closed_allows(self):
        self.assertEqual(self.cb.state, "CLOSED")
        self.assertTrue(self.cb.allow())

    def test_open_after_threshold(self):
        self.assertTrue(self.cb.allow())
        for _ in range(3):
            self.cb.record_failure()
        self.assertEqual(self.cb.state, "OPEN")
        self.assertFalse(self.cb.allow())          # 熔断拒绝
        self.assertFalse(self.cb.allow())          # 继续拒绝

    def test_not_open_below_threshold(self):
        for _ in range(2):                        # 失败 2 次 < 阈值 3
            self.cb.record_failure()
        self.assertEqual(self.cb.state, "CLOSED")
        self.assertTrue(self.cb.allow())

    def test_success_resets_fail_count(self):
        self.cb.record_failure()
        self.cb.record_failure()
        self.cb.record_success()
        self.cb.record_failure()
        self.cb.record_failure()                  # 2 次，仍 CLOSED
        self.assertEqual(self.cb.state, "CLOSED")

    def test_open_auto_half_open_after_reset(self):
        for _ in range(3):
            self.cb.record_failure()
        self.assertFalse(self.cb.allow())         # OPEN
        time.sleep(0.35)                          # 超过 reset_seconds
        self.assertEqual(self.cb.state, "HALF_OPEN")
        self.assertTrue(self.cb.allow())          # 半开放行 1 个
        self.assertFalse(self.cb.allow())         # 已用完试探名额

    def test_half_open_success_closes(self):
        for _ in range(3):
            self.cb.record_failure()
        time.sleep(0.35)
        self.assertTrue(self.cb.allow())          # 半开试探放行
        self.cb.record_success()                  # 试探成功 → CLOSED
        self.assertEqual(self.cb.state, "CLOSED")
        self.assertTrue(self.cb.allow())

    def test_half_open_failure_reopens(self):
        for _ in range(3):
            self.cb.record_failure()
        time.sleep(0.35)
        self.assertTrue(self.cb.allow())          # 半开试探
        self.cb.record_failure()                  # 试探失败 → 立即 OPEN
        self.assertEqual(self.cb.state, "OPEN")
        self.assertFalse(self.cb.allow())

    def test_no_deadlock_stress(self):
        """回归测试：早期 allow() 在锁内再取锁导致死锁。
        连续 100 次状态流转必须在 2s 内完成（有死锁会卡死）。"""
        import threading
        result = {"done": False}

        def _stress():
            cb = CircuitBreaker(fail_threshold=2, reset_seconds=0.05)
            for _ in range(50):
                cb.allow()
                cb.record_failure()
                cb.record_success()
                cb.allow()
                cb.state
            result["done"] = True

        t = threading.Thread(target=_stress, daemon=True)
        t.start()
        t.join(timeout=2.0)
        self.assertTrue(result["done"], "熔断器疑似死锁/挂起")

    def test_half_open_max_limit(self):
        cb = CircuitBreaker(fail_threshold=1, reset_seconds=0.1, half_open_max=3)
        cb.record_failure()
        time.sleep(0.15)
        self.assertEqual(cb.state, "HALF_OPEN")
        allowed = [cb.allow() for _ in range(6)]
        self.assertEqual(sum(1 for a in allowed if a), 3)   # 只放行 3 个


if __name__ == "__main__":
    unittest.main()

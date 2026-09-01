# -*- coding: utf-8 -*-
"""限流器单元测试：令牌桶补充 / 容量 / 超时。"""
import time
import unittest

from core.rate_limiter import TokenBucket


class TestTokenBucket(unittest.TestCase):

    def test_initial_full(self):
        tb = TokenBucket(rate=2.0, capacity=2.0)
        self.assertTrue(tb.acquire(block=False))   # 桶满 → 立即拿
        self.assertTrue(tb.acquire(block=False))
        self.assertFalse(tb.acquire(block=False))  # 耗尽

    def test_refill_over_time(self):
        tb = TokenBucket(rate=10.0, capacity=1.0)
        self.assertTrue(tb.acquire(block=False))
        self.assertFalse(tb.acquire(block=False))
        time.sleep(0.15)                           # 补充 1.5 个
        self.assertTrue(tb.acquire(block=False))

    def test_capacity_caps_burst(self):
        tb = TokenBucket(rate=1.0, capacity=1.0)
        self.assertTrue(tb.acquire(block=False))   # 消耗初始令牌
        time.sleep(0.5)                            # 只补充 0.5，未达 1 个
        self.assertFalse(tb.acquire(block=False))
        time.sleep(0.6)                            # 累计补充 1.1 → 1 个
        self.assertTrue(tb.acquire(block=False))
        self.assertFalse(tb.acquire(block=False))  # 桶容量为 1，突发上限

    def test_block_timeout(self):
        tb = TokenBucket(rate=100.0, capacity=0.0)  # 容量 0，永不补充（rate 无效）
        t0 = time.time()
        ok = tb.acquire(block=True, timeout=0.2)
        self.assertFalse(ok)
        self.assertLess(time.time() - t0, 2.0)     # 不挂死

    def test_block_success(self):
        tb = TokenBucket(rate=1000.0, capacity=1.0)
        ok = tb.acquire(block=True, timeout=1.0)
        self.assertTrue(ok)

    def test_zero_capacity_never_acquires(self):
        """容量 0 → 永远无法获取（wait 无限逼近，超时后返回 False）。"""
        tb = TokenBucket(rate=1000.0, capacity=0.0)
        ok = tb.acquire(block=True, timeout=0.2)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()

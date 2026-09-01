# -*- coding: utf-8 -*-
"""TTL 缓存 + 文件缓存单元测试（含降级缓存 stale 语义）。"""
import json
import os
import tempfile
import time
import unittest

from core.cache import TtlCache, FileCache


class TestTtlCache(unittest.TestCase):

    def test_set_get(self):
        c = TtlCache(ttl=60)
        c.set("k", 42)
        self.assertEqual(c.get("k"), 42)

    def test_miss_returns_none(self):
        c = TtlCache(ttl=60)
        self.assertIsNone(c.get("nope"))

    def test_expired_returns_none(self):
        c = TtlCache(ttl=0.1)
        c.set("k", 1)
        time.sleep(0.15)
        self.assertIsNone(c.get("k"))

    def test_stale_returns_old_value(self):
        """降级缓存：过期仍返回旧值（数据源全挂时兜底）。"""
        c = TtlCache(ttl=0.1)
        c.set("k", "old")
        time.sleep(0.15)
        self.assertIsNone(c.get("k"))          # 正常读已过期
        self.assertEqual(c.get_stale("k"), "old")   # 降级读仍返回

    def test_invalidate(self):
        c = TtlCache(ttl=60)
        c.set("k", 1)
        c.invalidate("k")
        self.assertIsNone(c.get("k"))

    def test_get_or_set_cache_hit(self):
        c = TtlCache(ttl=60)
        c.set("k", "cached")
        val, from_cache = c.get_or_set("k", lambda: "fetched")
        self.assertEqual(val, "cached")
        self.assertTrue(from_cache)

    def test_get_or_set_miss_fetches(self):
        c = TtlCache(ttl=60)
        val, from_cache = c.get_or_set("k", lambda: "fetched")
        self.assertEqual(val, "fetched")
        self.assertFalse(from_cache)
        # 第二次走缓存
        val2, from_cache2 = c.get_or_set("k", lambda: "fetched2")
        self.assertEqual(val2, "fetched")
        self.assertTrue(from_cache2)


class TestFileCache(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fc_")
        self.c = FileCache(self.tmp, default_ttl=3600)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_set_get(self):
        self.c.set("sh600519_day", [{"date": "2026-08-13", "close": 1355.29}])
        got = self.c.get("sh600519_day")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["close"], 1355.29)

    def test_miss_returns_none(self):
        self.assertIsNone(self.c.get("nope"))

    def test_expired_by_mtime(self):
        p = self.c._path("k")
        self.c.set("k", [1])
        old = os.path.getmtime(p) - 9999       # 人为把 mtime 调旧
        os.utime(p, (old, old))
        self.assertIsNone(self.c.get("k"))
        self.assertEqual(self.c.get_stale("k"), [1])   # 降级读仍在

    def test_corrupt_file_returns_none(self):
        self.c.set("k", [1])
        with open(self.c._path("k"), "w", encoding="utf-8") as f:
            f.write("{ broken json")
        self.assertIsNone(self.c.get("k"))
        self.assertIsNone(self.c.get_stale("k"))


if __name__ == "__main__":
    unittest.main()

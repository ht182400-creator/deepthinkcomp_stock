# -*- coding: utf-8 -*-
"""数据源公共工具单元测试。"""
import unittest

from sources.base import to_secid, pure_code


class TestToSecid(unittest.TestCase):

    def test_sh_starts_6(self):
        self.assertEqual(to_secid("sh600519"), "1.600519")

    def test_sh_starts_9(self):
        self.assertEqual(to_secid("sh900901"), "1.900901")

    def test_sh_starts_5_etf(self):
        self.assertEqual(to_secid("sh510300"), "1.510300")

    def test_sz_starts_0(self):
        self.assertEqual(to_secid("sz000858"), "0.000858")

    def test_sz_starts_3(self):
        self.assertEqual(to_secid("sz300750"), "0.300750")

    def test_sz_starts_1_2(self):
        self.assertEqual(to_secid("sz159915"), "0.159915")
        self.assertEqual(to_secid("sz200002"), "0.200002")

    def test_bj(self):
        self.assertEqual(to_secid("bj430047"), "0.430047")

    def test_pure_code_no_prefix(self):
        self.assertEqual(to_secid("600519"), "1.600519")
        self.assertEqual(to_secid("000858"), "0.000858")

    def test_already_dotted(self):
        self.assertEqual(to_secid("1.600519"), "1.600519")

    def test_upper_and_space(self):
        self.assertEqual(to_secid("  SH600519 "), "1.600519")


class TestPureCode(unittest.TestCase):

    def test_prefix_stripped(self):
        self.assertEqual(pure_code("sh600519"), "600519")
        self.assertEqual(pure_code("SZ000858"), "000858")

    def test_dot_variant(self):
        self.assertEqual(pure_code("sh600519.sh"), "600519")


if __name__ == "__main__":
    unittest.main()

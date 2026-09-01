# -*- coding: utf-8 -*-
"""npx 源单元测试：markdown 表头动态解析（日线 vs 分钟线）。"""
import unittest

from sources.npx import parse_kline

DAY_MD = """| date | open | close | high | low | volume |
| --- | --- | --- | --- | --- | --- |
| 2026-08-13 | 1355.00 | 1355.29 | 1358.00 | 1352.00 | 34567.0 |
| 2026-08-12 | 1342.00 | 1355.00 | 1356.00 | 1340.00 | 30000.0 |
"""

MIN_MD = """| date | open | last | high | low | volume |
| --- | --- | --- | --- | --- | --- |
| 2026-08-13 10:30 | 1355.00 | 1356.20 | 1357.00 | 1354.80 | 1200.0 |
| 2026-08-13 10:35 | 1356.20 | 1355.90 | 1356.50 | 1355.00 | 800.0 |
"""


class TestParseKline(unittest.TestCase):

    def test_day_header(self):
        rows = parse_kline(DAY_MD)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], "2026-08-13")
        self.assertEqual(rows[0]["open"], 1355.00)
        self.assertEqual(rows[0]["close"], 1355.29)    # close 列
        self.assertEqual(rows[0]["vol"], 34567.0)      # volume 列

    def test_minute_header(self):
        """分钟线用 last 列作为 close。"""
        rows = parse_kline(MIN_MD)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], "2026-08-13 10:30")
        self.assertEqual(rows[0]["close"], 1356.20)    # last 列
        self.assertEqual(rows[1]["close"], 1355.90)
        self.assertEqual(rows[0]["vol"], 1200.0)

    def test_empty_text(self):
        self.assertEqual(parse_kline(""), [])

    def test_garbage_lines_skipped(self):
        md = "not a table\n\n| date | open | close | high | low | volume |\n| --- | --- | --- | --- | --- | --- |\n| 2026-08-13 | x | y | z | w | v |\n| 2026-08-12 | 1 | 2 | 3 | 4 | 5 |\n"
        rows = parse_kline(md)
        self.assertEqual(len(rows), 1)                 # 坏行被跳过
        self.assertEqual(rows[0]["close"], 2.0)

    def test_short_row_skipped(self):
        md = "| date | open | close | high | low | volume |\n| --- | --- | --- | --- | --- | --- |\n| 2026-08-13 | 1 | 2 | 3 |\n"
        self.assertEqual(parse_kline(md), [])


if __name__ == "__main__":
    unittest.main()

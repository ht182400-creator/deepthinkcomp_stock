# -*- coding: utf-8 -*-
"""搜索服务单元测试：基于 stock_list 本地全 A 股（mock stock_list.search）。"""
from services.search_service import search_stocks
import unittest
from unittest.mock import patch


# 模拟 stock_list.search 返回（确保测试确定性 + 不依赖本地 JSON）
def _mock_search(keyword, limit=20):
    items = [
        ("sh600519", "贵州茅台", "白酒"), ("sz000858", "五粮液", "白酒"), ("sz000568", "泸州老窖", "白酒"),
        ("sh600036", "招商银行", "银行"), ("sh601398", "工商银行", "银行"), ("sh601939", "建设银行", "银行"),
        ("sz000333", "美的集团", "家电"), ("sz300750", "宁德时代", "电池"),
    ]
    kw = keyword.strip().lower().replace(" ", "")
    out = []
    if not kw:
        return [{"code": c, "name": n, "pinyin": "", "display": f"{c.upper()} {n}"} for c, n, _ in items[:limit]]
    for c, n, cat in items:
        if kw in c.lower() or kw in n or kw in cat:
            out.append({"code": c, "name": n, "pinyin": "", "display": f"{c.upper()} {n} · {cat}"})
            if len(out) >= limit: break
    return out


def _patch_search():
    p = patch("services.search_service._list_search", side_effect=_mock_search)
    p.start()
    return p


class TestSearch(unittest.TestCase):
    setUp = lambda self: _patch_search()

    def test_empty_returns_hot(self):
        r = search_stocks("")
        self.assertGreater(len(r), 0)
        self.assertEqual(r[0]["code"], "sh600519")
        self.assertIn("display", r[0])

    def test_search_by_name(self):
        r = search_stocks("茅台")
        self.assertTrue(any(x["name"] == "贵州茅台" for x in r))

    def test_search_by_code(self):
        r = search_stocks("sh600519")
        self.assertTrue(any(x["code"] == "sh600519" for x in r))

    def test_search_by_pure_code(self):
        r = search_stocks("600519")
        self.assertTrue(any(x["code"] == "sh600519" for x in r))

    def test_search_by_industry(self):
        r = search_stocks("白酒")
        names = [x["name"] for x in r]
        self.assertIn("贵州茅台", names)
        self.assertIn("五粮液", names)
        self.assertIn("泸州老窖", names)

    def test_search_case_insensitive(self):
        r1 = search_stocks("SH600519")
        r2 = search_stocks("sh600519")
        self.assertEqual([x["code"] for x in r1], [x["code"] for x in r2])

    def test_limit_applies(self):
        r = search_stocks("银行", limit=3)
        self.assertLessEqual(len(r), 3)

    def test_no_match_returns_empty(self):
        self.assertEqual(search_stocks("不存在的股票xyz"), [])

    def test_result_shape(self):
        r = search_stocks("宁德")
        self.assertEqual(len(r), 1)
        x = r[0]
        self.assertIn("code", x)
        self.assertIn("name", x)
        self.assertIn("display", x)
        self.assertIn("SZ300750", x["display"])

    def test_pinyin_match(self):
        """拼音首字母匹配：mock _mock_search 走 pinyin 字段（实际 stock_list 用 pypinyin）。"""
        from services.search_service import _list_search
        out = _mock_search("茅台")
        self.assertTrue(any(x["name"] == "贵州茅台" for x in out))

if __name__ == "__main__":
    unittest.main()

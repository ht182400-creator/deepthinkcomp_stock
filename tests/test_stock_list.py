# -*- coding: utf-8 -*-
"""全 A 股清单服务单元测试：拼音首字母 / 市场前缀 / 本地 JSON 持久化（mock 网络）。"""
import json
import os
import unittest
from unittest.mock import patch

from tests.helpers import FakeResponse, temp_config


def _clist_body():
    """东财 clist 返回（100 条中含茅台/中微）。"""
    diff = [
        {"f12": "600519", "f14": "贵州茅台"},
        {"f12": "688012", "f14": "中微公司"},
        {"f12": "000858", "f14": "五粮液"},
    ]
    return {"data": {"total": 3, "diff": diff}}


class TestStockList(unittest.TestCase):

    def setUp(self):
        self.tmp = temp_config()
        import services.stock_list as sl
        sl.STOCK_LIST_FILE = os.path.join(self.tmp, "stock_list.json")

    def test_pinyin_abbr(self):
        from services.stock_list import _to_pinyin_abbr
        self.assertEqual(_to_pinyin_abbr("中微公司"), "zwgs")
        self.assertEqual(_to_pinyin_abbr("贵州茅台"), "gzmt")
        self.assertEqual(_to_pinyin_abbr("abc"), "")     # 非中文 → 空

    def test_em_prefix(self):
        from services.stock_list import _to_em_prefix
        self.assertEqual(_to_em_prefix("600519", "贵州茅台"), "sh600519")
        self.assertEqual(_to_em_prefix("000858", "五粮液"), "sz000858")
        self.assertEqual(_to_em_prefix("688012", "中微公司"), "sh688012")
        self.assertEqual(_to_em_prefix("830799", "北交所股"), "bj830799")

    def test_fetch_all_stocks(self):
        from services.stock_list import fetch_all_stocks
        with patch("services.stock_list.http_get", return_value=FakeResponse(json_data=_clist_body())):
            items = fetch_all_stocks(limit_pages=1)
        self.assertGreaterEqual(len(items), 3)
        zw = [x for x in items if x["name"] == "中微公司"]
        self.assertEqual(zw[0]["pinyin"], "zwgs")

    def test_save_load_local(self):
        from services.stock_list import save_local, load_local
        items = [{"code": "sh600519", "name": "贵州茅台", "pinyin": "gzmt"}]
        save_local(items)
        loaded = load_local()
        self.assertEqual(loaded[0]["code"], "sh600519")

    def test_save_load_ttl_expired(self):
        """过期本地 JSON → load_local 返回 None。"""
        from services.stock_list import save_local, load_local, STOCK_LIST_TTL
        save_local([{"code": "sh600519", "name": "贵州茅台", "pinyin": "gzmt"}])
        # 模拟 TTL 过期
        with open(os.path.join(self.tmp, "stock_list.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        data["updated_at"] = data["updated_at"] - STOCK_LIST_TTL - 10
        with open(os.path.join(self.tmp, "stock_list.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertIsNone(load_local())

    def test_search_pinyin_and_code(self):
        """search：pinyin 首字母 / 代码 / 名称匹配。"""
        from services.stock_list import search
        items = [
            {"code": "sh600519", "name": "贵州茅台", "pinyin": "gzmt"},
            {"code": "sh688012", "name": "中微公司", "pinyin": "zwgs"},
            {"code": "sz000858", "name": "五粮液", "pinyin": "wly"},
        ]
        with patch("services.stock_list._ensure_loaded", return_value=items):
            self.assertTrue(any(x["code"] == "sh688012" for x in search("zwgs")))   # 拼音
            self.assertTrue(any(x["code"] == "sh600519" for x in search("600519"))) # 代码
            self.assertTrue(any(x["code"] == "sz000858" for x in search("五粮液")))  # 名称
            self.assertEqual(search("不存在xyz"), [])


if __name__ == "__main__":
    unittest.main()
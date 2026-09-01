# -*- coding: utf-8 -*-
"""
测试工具：临时路径隔离、mock Response、假数据构造。
所有测试通过本模块保持环境干净（不污染真实 data/、logs/、watchlist.json）。
"""
import os
import sys
import json
import tempfile

# 项目根加入 sys.path，保证 `import core / sources / services / config` 可用
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class FakeResponse:
    """requests.Response 最小替身。"""

    def __init__(self, text="", json_data=None, status_code=200):
        self.text = text
        self._json = json_data
        self.status_code = status_code
        self.encoding = "utf-8"

    def json(self):
        if self._json is not None:
            return self._json
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def temp_config():
    """把 config 的路径类参数指向临时目录；返回临时目录。
    必须在 import 任何 service 之前调用（或在测试 setUp 中 patch）。"""
    tmp = tempfile.mkdtemp(prefix="deepthink_test_")
    import config
    config.DATA_DIR = os.path.join(tmp, "data")
    config.LOG_DIR = os.path.join(tmp, "logs")
    config.KLINE_CACHE_DIR = os.path.join(tmp, "data", "kline_cache")
    config.SQLITE_PATH = os.path.join(tmp, "data", "market.db")
    config.WATCHLIST_FILE = os.path.join(tmp, "data", "watchlist.json")
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.KLINE_CACHE_DIR, exist_ok=True)
    return tmp


def make_tdx_file(tmp_root: str, code: str, records: list):
    """构造通达信 .day 文件。records: [(date_int, o, h, l, c, vol, amount?)]，价格元，日期 YYYYMMDD int。"""
    import struct
    mkt, pure = code[:2], code[2:]
    d = os.path.join(tmp_root, mkt, "lday")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{code}.day")
    buf = b""
    for rec in records:
        date_i, o, h, l, c, vol = rec[:6]
        amt = rec[6] if len(rec) > 6 else 0.0
        buf += struct.pack("<iiiiifii", date_i,
                           int(round(o * 100)), int(round(h * 100)),
                           int(round(l * 100)), int(round(c * 100)),
                           float(amt), vol, 0)
    with open(path, "wb") as f:
        f.write(buf)
    return path

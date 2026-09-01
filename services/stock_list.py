# -*- coding: utf-8 -*-
"""
全 A 股清单服务：启动时从东财拉取（含代码/中文名/拼音首字母）→ 本地 JSON → 搜索匹配。
- 全 A 股约 5549 条（含沪深主板/创业板/科创板/北交所）
- 拼音首字母：预计算存本地（避免搜索时计算 5k+ 次）
- 启动策略：本地 JSON 不存在或 >24h → 后台拉取一次（不阻塞首屏）
"""
import json
import logging
import os
import threading
import time
from typing import Optional

import config
from sources.base import http_get

LOG = logging.getLogger(__name__)

DATA_DIR = os.path.join(config.DATA_DIR if hasattr(config, "DATA_DIR") else "data", "")
STOCK_LIST_FILE = os.path.join(DATA_DIR, "stock_list.json")
STOCK_LIST_TTL = 86400  # 24h

_FIELDS = "f12,f14"  # 代码 + 中文名
_MKT_FILTERS = (
    "m:0+t:6,m:0+t:13,m:0+t:80,"  # 深主板/创业板/北交所
    "m:1+t:2,m:1+t:23,m:1+t:14"  # 沪主板/科创板/北交所
)
_BASE_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
_PAGE_SIZE = 100
_PAGES_NEEDED = 60  # 东财硬限制每页 ~100 条，全 A 股 5549 条需要 ~56 页

HEADERS = {"Referer": "https://quote.eastmoney.com/", "User-Agent": config.USER_AGENT}


def _to_pinyin_abbr(name: str) -> str:
    """中文名 → 拼音首字母（'中微公司' → 'zwgs'）。去非中文字符。"""
    if not name or any(ord(c) < 0x4E00 or ord(c) > 0x9FA5 for c in name):
        return ""
    try:
        from pypinyin import lazy_pinyin
        return "".join(s[0] for s in lazy_pinyin(name) if s and s[0].isalpha()).lower()
    except Exception:
        return ""


def _to_em_prefix(code: str, name: str) -> str:
    """6位代码 → sh/sz/bj 前缀（按 code 首位或名称含 ST/BJ 区分）。"""
    if code.startswith("6") or code.startswith("9"):
        return "sh" + code
    if code.startswith("0") or code.startswith("3"):
        return "sz" + code
    if code.startswith("4") or code.startswith("8"):
        return "bj" + code
    return "sh" + code


def fetch_all_stocks(limit_pages: int = _PAGES_NEEDED) -> list:
    """从东财 clist 拉全 A 股（分页）。"""
    out = []
    for pn in range(1, limit_pages + 1):
        params = {"pn": pn, "pz": _PAGE_SIZE, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                  "fid": "f12", "fs": _MKT_FILTERS, "fields": _FIELDS}  # fid=f12 按代码升序，覆盖所有股票不漏
        try:
            r = http_get(_BASE_URL, HEADERS, params=params,
                         limiter_name="eastmoney", rate=config.RATE_LIMIT_EM)
            j = r.json()
            data = j.get("data") or {}
            page_items = data.get("diff", []) or []
            if not page_items:
                LOG.info("stock_list 拉取 pn=%d 空，停止", pn)
                break
            for it in page_items:
                code = it.get("f12") or ""
                name = it.get("f14") or ""
                if not code or not name:
                    continue
                out.append({"code": _to_em_prefix(code, name), "name": name,
                            "pinyin": _to_pinyin_abbr(name)})
            total = data.get("total") or 0
            LOG.info("stock_list 拉取 pn=%d, 已收 %d/%d", pn, len(out), total)
            if len(out) >= total or len(out) >= 5500:
                break
            time.sleep(0.1)  # 限流保护
        except Exception as e:
            LOG.warning("stock_list 拉取 pn=%d 失败: %s", pn, e)
            break
    return out


def save_local(items: list):
    """写本地 JSON（含 pinyin）。"""
    os.makedirs(os.path.dirname(STOCK_LIST_FILE), exist_ok=True)
    payload = {"updated_at": int(time.time()), "count": len(items), "items": items}
    with open(STOCK_LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def load_local() -> Optional[list]:
    """读本地 JSON，过期返回 None。"""
    if not os.path.exists(STOCK_LIST_FILE):
        return None
    try:
        with open(STOCK_LIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if int(time.time()) - data.get("updated_at", 0) > STOCK_LIST_TTL:
            return None
        return data.get("items") or []
    except Exception:
        return None


_CACHED: Optional[list] = None
_LOADED_AT: float = 0
_LOCK = threading.Lock()


def _ensure_loaded() -> list:
    """懒加载：内存为空/过期 → 读本地或后台拉取。返回当前可用列表。"""
    global _CACHED, _LOADED_AT
    with _LOCK:
        if _CACHED and time.time() - _LOADED_AT < STOCK_LIST_TTL:
            return _CACHED
        local = load_local()
        if local:
            _CACHED = local
            _LOADED_AT = time.time()
            return _CACHED
        # 本地无/过期 → 立即同步拉前 3 页（≈1.6s，覆盖头部热门）
        LOG.info("stock_list 本地无/过期 → 同步拉前 3 页")
        items = fetch_all_stocks(limit_pages=3)
        if items:
            save_local(items)
            _CACHED = items
            _LOADED_AT = time.time()
        return _CACHED or []


def warmup_async():
    """应用启动时后台异步预热（不阻塞首屏）。"""
    def _bg():
        global _CACHED, _LOADED_AT
        if _CACHED and time.time() - _LOADED_AT < STOCK_LIST_TTL:
            return
        local = load_local()
        if local:
            with _LOCK:
                _CACHED = local
                _LOADED_AT = time.time()
            return
        try:
            items = fetch_all_stocks()
            if items:
                save_local(items)
                with _LOCK:
                    _CACHED = items
                    _LOADED_AT = time.time()
                LOG.info("stock_list 后台预热完成: %d 条", len(items))
        except Exception as e:
            LOG.warning("stock_list 后台预热失败: %s", e)
    t = threading.Thread(target=_bg, daemon=True)
    t.start()


def search(keyword: str, limit: int = 20) -> list:
    """本地全 A 股搜索：code / name / pinyin 首字母。"""
    items = _ensure_loaded()
    kw = keyword.strip().lower().replace(" ", "")
    if not kw:
        # 空关键词返回前 limit 条（用作热门默认）
        return [{"code": it["code"], "name": it["name"], "pinyin": it.get("pinyin", "")}
                for it in items[:limit]]
    out = []
    for it in items:
        code_l = it["code"].lower()
        code_pure = code_l[2:] if code_l.startswith(("sh", "sz", "bj")) else code_l
        py = it.get("pinyin") or ""
        if (kw in code_l or kw in it["name"] or kw in py
                or (kw.isdigit() and kw == code_pure)):
            out.append({"code": it["code"], "name": it["name"], "pinyin": py})
            if len(out) >= limit:
                break
    return out
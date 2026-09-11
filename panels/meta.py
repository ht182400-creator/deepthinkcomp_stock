# -*- coding: utf-8 -*-
"""面板元信息与版本管理。

为"回测可复现"提供依据（docs/10 隐患 H1/H3/H13）：

- 记录复权基准日 ``base_date``、通达信数据版本 ``tdx_version``、字段映射版本；
- 提供列名存在性断言，避免 gpcw 升级后 **静默取空值** 导致"买池为空"；
- 提供面板版本比对，提示"数据已更新，回测结果不可直接对比"。

本模块只负责元信息的读写与校验，不含业务逻辑。
"""
import hashlib
import json
import logging
import os
import struct
import traceback
from datetime import datetime

import config

LOG = logging.getLogger(__name__)

PANEL_META_VERSION = "1.0"          # 元信息结构版本，结构变更时递增
_FINGERPRINT_TAIL = 4096            # 指纹取样字节数（取文件末尾）
_SH_INDEX_DAY = "sh000001.day"      # 上证指数日线，用于判定通达信数据版本
_DAY_RECORD_SIZE = 32               # .day 每根 32 字节


def tdx_data_version():
    """通达信数据版本 = 上证指数日线末根日期（YYYYMMDD）。

    Returns:
        int | None: 末根日期；文件缺失或解析失败返回 None。
    """
    try:
        path = os.path.join(config.TDX_ROOT, "sh", "lday", _SH_INDEX_DAY)
        if not os.path.exists(path):
            LOG.warning("[meta] 上证指数日线缺失，无法判定数据版本: %s", path)
            return None
        with open(path, "rb") as fh:
            fh.seek(-_DAY_RECORD_SIZE, os.SEEK_END)
            raw = fh.read(_DAY_RECORD_SIZE)
        # .day 结构: <iiiiifii，第 0 个 int 即 YYYYMMDD
        return struct.unpack("<iiiiifii", raw)[0]
    except Exception as exc:
        LOG.error("[meta] 读取数据版本异常: %s\n%s", exc, traceback.format_exc())
        return None


def file_fingerprint(path):
    """计算文件指纹（大小 + 末尾字节 md5），用于识别数据文件是否变化。

    Args:
        path: 目标文件路径。

    Returns:
        str | None: 形如 ``"123456:abcdef0123"``；文件不存在或失败返回 None。
    """
    try:
        if not os.path.exists(path):
            return None
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - _FINGERPRINT_TAIL))
            tail = fh.read()
        return "%d:%s" % (size, hashlib.md5(tail).hexdigest()[:16])
    except Exception as exc:
        LOG.error("[meta] 计算指纹异常 %s: %s\n%s", path, exc, traceback.format_exc())
        return None


def build_meta(base_date=None, field_map_version=None, periods=None, extra=None):
    """组装面板元信息。

    Args:
        base_date: 复权基准日（YYYYMMDD）。价格面板用于冻结复权口径（H1）。
        field_map_version: 字段映射版本号。
        periods: 已纳入面板的报告期列表。
        extra: 其它需要记录的键值对（如 rows/cols/stocks）。

    Returns:
        dict: 元信息字典。
    """
    try:
        meta = {
            "meta_version": PANEL_META_VERSION,
            "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "base_date": base_date,
            "tdx_version": tdx_data_version(),
            "field_map_version": field_map_version,
            "periods": sorted(periods or []),
            "period_count": len(periods or []),
            "tdx_root": config.TDX_ROOT,
        }
        if extra:
            meta.update(extra)
        return meta
    except Exception as exc:
        LOG.error("[meta] 组装元信息异常: %s\n%s", exc, traceback.format_exc())
        return {"meta_version": PANEL_META_VERSION, "error": str(exc)}


def _atomic_write_json(obj, path):
    """原子写 JSON（先写 .tmp 再 rename），避免写一半损坏。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def save_meta(meta, path=None):
    """落盘面板元信息。

    Returns:
        str: 实际写入路径。
    """
    path = path or config.PANEL_META_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _atomic_write_json(meta, path)
        LOG.info("[meta] 已写入 %s (base_date=%s tdx_version=%s)",
                 path, meta.get("base_date"), meta.get("tdx_version"))
        return path
    except Exception as exc:
        LOG.error("[meta] 写入元信息异常 %s: %s\n%s", path, exc, traceback.format_exc())
        return path


def load_meta(path=None):
    """读取面板元信息。

    Returns:
        dict | None: 元信息；不存在或损坏返回 None。
    """
    path = path or config.PANEL_META_FILE
    try:
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        LOG.error("[meta] 读取元信息异常 %s: %s\n%s", path, exc, traceback.format_exc())
        return None


def save_field_map(fields=None, version=None, path=None):
    """把字段映射落盘（带版本），供代码读取而非硬编码（H13）。

    Args:
        fields: ``{内部名: gpcw 列名}``；缺省取 ``config.FUND_FIELDS``。
        version: 映射版本号；缺省用日期。
        path: 落盘路径。

    Returns:
        str: 实际写入路径。
    """
    path = path or config.FIELD_MAP_FILE
    fields = fields or config.FUND_FIELDS
    payload = {
        "version": version or datetime.now().strftime("%Y-%m"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(fields),
        "fields": dict(fields),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _atomic_write_json(payload, path)
        LOG.info("[meta] 字段映射已落盘 %s (%d 个字段, ver=%s)",
                 path, payload["count"], payload["version"])
        return path
    except Exception as exc:
        LOG.error("[meta] 写入字段映射异常 %s: %s\n%s", path, exc, traceback.format_exc())
        return path


def load_field_map(path=None):
    """读取字段映射；缺失或损坏时回退 ``config.FUND_FIELDS``。

    Returns:
        tuple[dict, str]: ``(字段映射, 版本号)``。
    """
    path = path or config.FIELD_MAP_FILE
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
            fields = payload.get("fields") or {}
            if fields:
                return fields, payload.get("version") or "unknown"
    except Exception as exc:
        LOG.error("[meta] 读取字段映射异常，回退 config: %s\n%s", exc, traceback.format_exc())
    return dict(config.FUND_FIELDS), "config"


def assert_fields(columns, fields=None):
    """列名存在性断言：缺列立即抛错，**禁止静默降级**（H13）。

    若 gpcw 升级导致列名变化而代码静默取到 NaN，会让质量门剔除全市场、
    买池变空且无任何报错 —— 这是最危险的失败模式，故此处强校验。

    Args:
        columns: 实际列名集合（list / Index）。
        fields: 期望字段映射；缺省取 config.FUND_FIELDS。

    Raises:
        KeyError: 存在缺失列时。
    """
    fields = fields or config.FUND_FIELDS
    col_set = {str(c) for c in columns}
    missing = [k for k, v in fields.items() if v not in col_set]
    if missing:
        detail = ", ".join("%s→%s" % (k, fields[k]) for k in missing[:10])
        LOG.error("[meta] 字段缺失 %d 个（共 %d）: %s", len(missing), len(fields), detail)
        raise KeyError("gpcw 字段缺失 %d 个（前 10）: %s；请核对 config.FUND_FIELDS" % (len(missing), detail))
    LOG.debug("[meta] 字段校验通过，共 %d 个字段", len(fields))
    return True


def check_panel_reproducible(meta=None):
    """校验面板是否仍与当前通达信数据一致，用于提示"回测结果不可直接对比"(H1)。

    Returns:
        dict: ``{"ok": bool, "reason": str, "stored": int|None, "current": int|None}``
    """
    meta = meta if meta is not None else load_meta()
    if not meta:
        return {"ok": False, "reason": "面板未构建（meta.json 缺失）", "stored": None, "current": None}
    stored = meta.get("tdx_version")
    current = tdx_data_version()
    if stored is None or current is None:
        return {"ok": False, "reason": "无法判定数据版本", "stored": stored, "current": current}
    if int(stored) != int(current):
        msg = "通达信数据已更新（面板 %s → 当前 %s），回测结果不可直接对比，请重建面板" % (stored, current)
        LOG.warning("[meta] %s", msg)
        return {"ok": False, "reason": msg, "stored": stored, "current": current}
    return {"ok": True, "reason": "面板与当前数据一致", "stored": stored, "current": current}

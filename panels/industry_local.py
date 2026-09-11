# -*- coding: utf-8 -*-
"""本地行业分类解析（**零网络，离线主源**）。

**背景**：抓行业曾走东财 clist 接口（`panels/industry.py`），但东财会限流、
且只有 5223 只。实测发现通达信本地**自带完整行业分类**，覆盖更好且无需联网。

**数据来源（均在通达信安装目录）**

| 文件 | 内容 | 实测 |
|---|---|---|
| `T0002/hq_cache/tdxhy.cfg` | `市场\\|代码\\|通达信行业代码\\|\\|\\|申万行业代码` | **5657 行**（含北交所） |
| `incon.dat` → `#TDXNHY` 段 | 行业代码 → 名称（层级树 `T01\\|能源`、`T0101\\|煤炭`） | 21 段中第 1 段 |

**样例**

```
tdxhy.cfg :  0|000001|T1001|||X500102
             0|000002|T110201|||X530101
incon.dat :  #TDXNHY
             T01|能源
             T0101|煤炭
             T010101|煤炭开采
```

**层级归一化**：通达信行业为三级（`T01` 一级 / `T0101` 二级 / `T010101` 三级），
`tdxhy.cfg` 中给的是二级或三级混合。本模块统一**截取到二级**（如 `T110201` → `T1102`），
得到约 90 个行业，粒度适合做"单行业 ≤N 只"的组合约束。
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config                                          # noqa: E402

LOG = logging.getLogger(__name__)

_TDXHY_REL = ("T0002", "hq_cache", "tdxhy.cfg")
_INCON_REL = ("incon.dat",)
_SECTION_TDXNHY = "#TDXNHY"
_SECTION_MARK_RE = ("#",)
_SPLIT_CHAR = "|"
_LEVEL2_LEN = 5         # "T1102" 长度（T + 4 位）
_ENC = "gbk"


def _read_text(path):
    """读取 GBK 文本（通达信配置文件编码）。

    Returns:
        str | None
    """
    try:
        if not os.path.exists(path):
            LOG.warning("[industry_local] 文件不存在: %s", path)
            return None
        with open(path, "rb") as fh:
            return fh.read().decode(_ENC, errors="replace")
    except Exception as exc:
        LOG.error("[industry_local] 读取失败 %s: %s\n%s", path, exc, traceback.format_exc())
        return None


def _to_level2(tdx_code):
    """通达信行业代码归一化到二级（``T110201`` → ``T1102``）。

    Args:
        tdx_code: 原始行业代码，如 ``"T110201"`` / ``"T1001"``。

    Returns:
        str: 二级代码；非法输入原样返回。
    """
    code = str(tdx_code or "").strip().upper()
    if not code.startswith("T"):
        return code
    return code[:_LEVEL2_LEN] if len(code) > _LEVEL2_LEN else code


def parse_incon(path=None):
    """解析 ``incon.dat`` 的 ``#TDXNHY`` 段：行业代码 → 名称。

    Args:
        path: 文件路径；缺省 ``TDX_ROOT/incon.dat``。

    Returns:
        dict: ``{行业代码: 名称}``，含一级/二级/三级全部层级。
    """
    path = path or os.path.join(config.TDX_HOME, *_INCON_REL)
    text = _read_text(path)
    if not text:
        return {}
    out = {}
    try:
        lines = text.splitlines()
        in_section = False
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                # 段标记行；进入 TDXNHY 段后，遇到下一个 # 开头段即结束
                if line.startswith(_SECTION_TDXNHY):
                    in_section = True
                    continue
                if in_section:
                    break
                continue
            if not in_section:
                continue
            parts = line.split(_SPLIT_CHAR)
            if len(parts) >= 2 and parts[0].strip():
                out[parts[0].strip().upper()] = parts[1].strip()
        LOG.info("[industry_local] incon.dat 解析: #TDXNHY 段 %d 个行业条目", len(out))
    except Exception as exc:
        LOG.error("[industry_local] 解析 incon.dat 异常: %s\n%s", exc, traceback.format_exc())
    return out


def parse_tdxhy(path=None):
    """解析 ``tdxhy.cfg``：股票代码 → 通达信行业代码（归一化到二级）。

    Args:
        path: 文件路径；缺省 ``TDX_ROOT/T0002/hq_cache/tdxhy.cfg``。

    Returns:
        tuple[dict, dict]: ``(股票→二级行业代码, 统计信息)``
    """
    path = path or os.path.join(config.TDX_HOME, *_TDXHY_REL)
    text = _read_text(path)
    mapping = {}
    stats = {"lines": 0, "skipped": 0}
    if not text:
        return mapping, stats
    try:
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            stats["lines"] += 1
            parts = line.split(_SPLIT_CHAR)
            if len(parts) < 3:
                stats["skipped"] += 1
                continue
            code = parts[1].strip()
            tdx = parts[2].strip()
            if not code or not tdx:
                stats["skipped"] += 1
                continue
            mapping[code.zfill(6)] = _to_level2(tdx)
        LOG.info("[industry_local] tdxhy.cfg 解析: %d 只股票（%d 行，跳过 %d）",
                 len(mapping), stats["lines"], stats["skipped"])
    except Exception as exc:
        LOG.error("[industry_local] 解析 tdxhy.cfg 异常: %s\n%s", exc, traceback.format_exc())
    return mapping, stats


def build_industry_map():
    """构建 ``{6 位代码: 行业名称}``（本地，零网络）。

    Returns:
        tuple[dict, dict]: ``(映射, 统计)``
    """
    names = parse_incon()
    codes, stats = parse_tdxhy()
    out = {}
    unknown = 0
    for code, tdx in codes.items():
        name = names.get(tdx) or names.get(_to_level2(tdx))
        if name:
            out[code] = name
        else:
            unknown += 1
    stats.update({
        "mapped": len(out),
        "unknown_industry_code": unknown,
        "n_industry_level2": len({_to_level2(v) for v in codes.values()}),
    })
    cover = 100.0 * len(out) / max(1, len(codes))
    LOG.info("[industry_local] 本地行业映射: %d 只 / %d 二级行业（解析率 %.1f%%，%d 条行业代码无名称）",
             len(out), stats["n_industry_level2"], cover, unknown)
    return out, stats


def save_industry_local(mapping, stats=None, path=None):
    """落盘本地行业映射（原子写）。

    Returns:
        str: 实际写入路径。
    """
    path = path or config.INDUSTRY_LOCAL_FILE
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(mapping),
        "source": "tdx_local_tdxhy_cfg+incon_dat",
        "stats": stats or {},
        "items": dict(mapping),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, path)
        LOG.info("[industry_local] 已落盘 %s（%d 条）", path, len(mapping))
    except Exception as exc:
        LOG.error("[industry_local] 落盘异常 %s: %s\n%s", path, exc, traceback.format_exc())
    return path


def load_industry_local(path=None):
    """读取本地行业映射。

    Returns:
        dict: ``{6 位代码: 行业名}``；缺失或损坏返回空 dict。
    """
    path = path or config.INDUSTRY_LOCAL_FILE
    try:
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload.get("items") or {}
    except Exception as exc:
        LOG.error("[industry_local] 读取异常 %s: %s\n%s", path, exc, traceback.format_exc())
        return {}


def main():
    """构建并落盘。

    Returns:
        dict: 统计信息。
    """
    mapping, stats = build_industry_map()
    if mapping:
        save_industry_local(mapping, stats)
    return {"count": len(mapping), **stats}


if __name__ == "__main__":      # pragma: no cover - 手动执行入口
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="[%(asctime)s.%(msecs)03d] %(levelname)-5s %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    print(json.dumps(main(), ensure_ascii=False, indent=1))

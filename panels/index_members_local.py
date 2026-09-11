# -*- coding: utf-8 -*-
"""本地指数成分解析（**零网络**）。

**背景**：抓指数成分曾尝试东财接口（`push2.eastmoney.com`、`datacenter-web`），
均实测失败（空响应 / 字段名不存在）。**改用通达信本地文件，完全离线**。

**数据来源（两个文件互补）**

| 文件 | 格式样例 | 实测覆盖 |
|---|---|---|
| `T0002/hq_cache/infoharbor_block.dat`（738KB） | ``#ZS_沪深300,300,,20050408,,,`` 换行后 ``0#000001,0#000002,...`` | **117 个 ``ZS_`` 指数**：沪深300=300 ✓、上证50=50 ✓、中证800=800 ✓、创业板指=100 ✓、科创50=50 ✓、北证50=50 ✓ |
| `T0002/hq_cache/spblock.dat`（316KB） | ``#中证500`` 换行后 ``0000009``（7 位 = 1 位市场 + 6 位代码） | **35 个板块**：中证500=500 ✓、中证1000=1000 ✓、中证2000=2000 ✓、中证A500=500 ✓ |

> 数量与指数公布值**精确吻合**，确认是真实成分股（非概念标签）。

**实测验证价值**：`fundamentals_broad.json` 的**前 300 只与本地 ``ZS_沪深300`` 重合率 100%**
→ 证实该文件"前 300 只 = 沪深300 成分"，即 **E5 实验发现的"指数成分前视偏差"成立**
（见 [docs/10 §6.9](../docs/10-改造方案自审与优化建议.md)）。

⚠️ **重要限制**：本模块只提供**当前快照**（随通达信更新，实测为 2026-09-09 前后），
**不含历史成分变更记录** → **无法用于消除回测的前视偏差**。
用途限于：① 实盘选池（离线、比东财接口稳定）；② 核对回测宇宙构成；
③ 后续"滚动定池"（R0a）的**终点校验**。
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

_HQ_CACHE = ("T0002", "hq_cache")
_ZF = "_ZF_"          # 每个板块记录中的字段分隔符（形如 ``#ZS_沪深300,300,,20050408,,,``）
_Z = "ZS_"            # infoharbor 中指数成分板块的前缀
_ENC = "gbk"
_CODE_LEN = 6


def _read_text(name):
    """读取 ``T0002/hq_cache/<name>`` 的 GBK 文本。

    Returns:
        str | None
    """
    path = os.path.join(config.TDX_HOME, *_HQ_CACHE, name)
    try:
        if not os.path.exists(path):
            LOG.warning("[idx_local] 文件不存在: %s", path)
            return None
        with open(path, "rb") as fh:
            return fh.read().decode(_ENC, errors="replace")
    except Exception as exc:
        LOG.error("[idx_local] 读取失败 %s: %s\n%s", path, exc, traceback.format_exc())
        return None


def _pure(code):
    """``"0#000001"`` / ``"0000001"`` → ``"000001"``（取末 6 位）。"""
    s = str(code or "").strip()
    if not s:
        return ""
    s = s.split("#")[-1]
    return s.zfill(_CODE_LEN)[-_CODE_LEN:]


def _parse_block_file(name, keep_prefix=None):
    """解析 ``#板块名`` + 成分股列表 结构的文件。

    Args:
        name: ``hq_cache`` 下的文件名。
        keep_prefix: 仅保留以此前缀开头的板块（如 ``"ZS_"``）；``None`` 表示全部。

    Returns:
        dict: ``{板块名: [6 位代码, ...]}``（已去重、保序）
    """
    text = _read_text(name)
    out = {}
    if not text:
        return out
    try:
        cur = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                head = line[1:].split(",")[0].strip()
                if not head:
                    cur = None
                    continue
                cur = head
                if cur not in out:
                    out[cur] = []
            elif cur:
                for tok in line.split(","):
                    c = _pure(tok)
                    if c and c.isdigit():
                        out[cur].append(c)
        if keep_prefix:
            out = {k: sorted(set(v)) for k, v in out.items() if k.startswith(keep_prefix)}
        else:
            out = {k: sorted(set(v)) for k, v in out.items()}
        LOG.info("[idx_local] %s 解析: %d 个板块", name, len(out))
    except Exception as exc:
        LOG.error("[idx_local] 解析 %s 异常: %s\n%s", name, exc, traceback.format_exc())
    return out


def build_index_members(include_other_blocks=True):
    """合并两个本地文件，构建指数成分映射。

    Args:
        include_other_blocks: 是否同时保留 ``spblock.dat`` 中的非指指数板块
            （融资融券 / 专精特新 / 沪港通 等，亦可用于选池）。

    Returns:
        tuple[dict, dict]: ``({板块名: [代码]}, 统计信息)``
    """
    zs = _parse_block_file("infoharbor_block.dat", keep_prefix=_Z)
    sp = _parse_block_file("spblock.dat")
    members = dict(zs)
    # spblock 中的中证系列（中证500/1000/2000/A500）与 ZS_ 互补
    for k, v in sp.items():
        if k not in members or not members[k]:
            if include_other_blocks or k.startswith("中证") or k.startswith("国证"):
                members["ZS_" + k if not k.startswith("ZS_") else k] = v
    all_codes = set()
    for v in members.values():
        all_codes |= set(v)
    stats = {
        "n_blocks": len(members),
        "n_from_infoharbor": len(zs),
        "n_from_spblock": len(sp),
        "n_codes_union": len(all_codes),
        "empty_blocks": sorted([k for k, v in members.items() if not v]),
        "key_blocks": {k: len(members[k]) for k in
                       ("ZS_沪深300", "ZS_中证500", "ZS_中证800", "ZS_上证50",
                        "ZS_中证1000", "ZS_中证2000", "ZS_中证A500", "ZS_创业板指",
                        "ZS_科创50", "ZS_北证50") if k in members},
    }
    LOG.info("[idx_local] 合并: %d 个板块 / %d 只成分（关键指数: %s）",
             stats["n_blocks"], stats["n_codes_union"], stats["key_blocks"])
    return members, stats


def save_index_members(members, stats=None, path=None):
    """落盘（原子写）。

    Returns:
        str: 实际写入路径。
    """
    path = path or config.INDEX_MEMBERS_FILE
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "tdx_local infoharbor_block.dat + spblock.dat",
        "n_blocks": len(members),
        "stats": stats or {},
        "members": members,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, path)
        LOG.info("[idx_local] 已落盘 %s（%d 个板块）", path, len(members))
    except Exception as exc:
        LOG.error("[idx_local] 落盘异常 %s: %s\n%s", path, exc, traceback.format_exc())
    return path


def load_index_members(path=None):
    """读取本地指数成分。

    Returns:
        dict: ``{板块名: [代码]}``；缺失或损坏返回空 dict。
    """
    path = path or config.INDEX_MEMBERS_FILE
    try:
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload.get("members") or {}
    except Exception as exc:
        LOG.error("[idx_local] 读取异常 %s: %s\n%s", path, exc, traceback.format_exc())
        return {}


def verify_against_universe(fundamentals_file=None):
    """核对本地成分与 ``fundamentals_broad.json`` 顺序的关系（H-A / E5 验证）。

    Returns:
        dict: 各关键区间的重合率。
    """
    try:
        ff = fundamentals_file or os.path.join(_ROOT, "modules", "strategy",
                                               "fundamentals_broad.json")
        with open(ff, encoding="utf-8") as fh:
            raw = json.load(fh)
        ks = [str(k).zfill(_CODE_LEN) for k in raw.keys()]
        members = load_index_members() or build_index_members()[0]
        out = {"n_file_codes": len(ks)}
        for blk, rng in (("ZS_沪深300", 300), ("ZS_中证800", 800), ("ZS_上证50", 50)):
            local = set(members.get(blk, []))
            pref = set(ks[:rng])
            hit = len(local & pref)
            out[blk] = {
                "local": len(local), "prefix": len(pref), "intersect": hit,
                "prefix_cover": round(100.0 * hit / max(1, len(pref)), 1),
                "local_cover": round(100.0 * hit / max(1, len(local)), 1),
            }
        LOG.info("[idx_local] 与宇宙顺序核对: %s", json.dumps(out, ensure_ascii=False))
        return out
    except Exception as exc:
        LOG.error("[idx_local] 核对异常: %s\n%s", exc, traceback.format_exc())
        return {}


def main():
    """构建 + 落盘 + 核对。

    Returns:
        dict: 统计信息。
    """
    members, stats = build_index_members()
    if members:
        save_index_members(members, stats)
    stats["verify"] = verify_against_universe()
    return stats


if __name__ == "__main__":      # pragma: no cover - 手动执行入口
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="[%(asctime)s.%(msecs)03d] %(levelname)-5s %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    print(json.dumps(main(), ensure_ascii=False, indent=1))

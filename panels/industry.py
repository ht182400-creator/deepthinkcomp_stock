# -*- coding: utf-8 -*-
"""行业分类获取（东财批量接口）。

**为什么需要**

- ``gpcw`` 585 列**不含行业**（已实测）；
- 通达信 ``incon.dat`` 只有行业名称树、**无成分股映射**（已实测）；
- ``fundamentals_broad.json`` 仅覆盖 **1771 只**。

宇宙扩容到 5561 只后，行业会大面积缺失，直接导致：

1. ``is_financial()`` 金融股过滤失效（银行 / 券商 / 保险漏入候选池）；
2. 行业上限（``ind_cap``）失效，组合行业集中度不受控。

**方案**：东财 ``clist`` 接口的 ``f100`` 字段返回全市场行业名称（实测 5912 只），
落盘 ``data/panel/industry.json`` 供离线复用。

**两个已踩的坑（勿重犯）**

1. ``pz`` 单页上限为 **100**，超过会返回空列表；
2. 东财对缺少 **Referer** 的请求会**直接断开连接**
   （``Remote end closed connection without response``），故复用
   ``sources/base.http_get``（项目既有、带限流与统一 Referer）。
"""
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config                                          # noqa: E402
from sources.base import http_get                      # noqa: E402  (带限流的请求封装)

LOG = logging.getLogger(__name__)

_FIELDS = "f12,f14,f100"        # f12=代码 / f14=名称 / f100=所属行业
# 东财必须带 Referer，否则直接断连；复用项目既有的东财请求头（见 sources/eastmoney.py）
_HEADERS = {"Referer": "https://data.eastmoney.com/", "User-Agent": config.USER_AGENT}
_INTER_PAGE_SLEEP = 0.15        # 页间轻微限流


def _fetch_page(page, page_size):
    """抓取东财 clist 单页数据（多节点轮换）。

    Args:
        page: 页码（从 1 开始）。
        page_size: 单页条数（**不得超过 100**）。

    Returns:
        tuple[list[dict], int]: ``(diff 列表, total)``；失败返回 ``([], 0)``。

    实现要点（两个已踩的坑）：

    1. **节点**：``push2`` 常被限流并直接断连，``push2delay`` 才是稳定节点
       （项目 ``services/stock_list.py`` 一直使用它）→ 故按 ``config.INDUSTRY_URLS`` 轮换；
    2. **排序字段**：用 ``fid=f12``（按代码升序）而非 ``f3``（涨跌幅），
       避免翻页期间排序变化导致漏股 / 重复。
    """
    # fs 参数含 ":" 与 "+"，用 params= 会被 requests 编码，故显式拼接完整 URL
    # 并令 requests 不再二次编码（params=None）。
    last_err = None
    for base in getattr(config, "INDUSTRY_URLS", [config.INDUSTRY_URL]):
        url = ("%s?pn=%d&pz=%d&po=1&np=1&fltt=2&invt=2&fid=f12&fs=%s&fields=%s"
               % (base, page, page_size, config.INDUSTRY_FS, _FIELDS))
        for attempt in range(config.INDUSTRY_RETRY):
            try:
                resp = http_get(url, _HEADERS, limiter_name="eastmoney",
                                rate=config.RATE_LIMIT_EM)
                data = resp.json().get("data") or {}
                return (data.get("diff") or []), int(data.get("total") or 0)
            except Exception as exc:
                last_err = exc
                wait = config.INDUSTRY_BACKOFF[min(attempt, len(config.INDUSTRY_BACKOFF) - 1)]
                LOG.warning("[industry] %s 第 %d 页第 %d 次失败: %s（%.0fs 后重试）",
                            base.split("//")[-1].split("/")[0], page, attempt + 1, exc, wait)
                time.sleep(wait)
    LOG.error("[industry] 第 %d 页全部节点失败: %s", page, last_err)
    return [], 0


def fetch_industry(page_size=None, max_pages=None):
    """抓取全市场 ``代码 → 行业`` 映射。

    Args:
        page_size: 单页条数；缺省 ``config.INDUSTRY_PAGE_SIZE``（100）。
        max_pages: 最大页数（防御性上限）。

    Returns:
        dict: ``{6 位代码: 行业名}``；失败返回已获取的部分。
    """
    page_size = min(page_size or config.INDUSTRY_PAGE_SIZE, config.INDUSTRY_PAGE_SIZE)
    max_pages = max_pages or config.INDUSTRY_MAX_PAGES
    mapping = {}
    total = None
    try:
        for page in range(1, max_pages + 1):
            rows, total = _fetch_page(page, page_size)
            if not rows:
                LOG.warning("[industry] 第 %d 页返回空，停止翻页", page)
                break
            for row in rows:
                code = str(row.get("f12") or "").strip()
                ind = (row.get("f100") or "").strip()
                if code and ind and ind != "-":
                    mapping[code] = ind
            if page % 10 == 0 or page == 1:
                LOG.info("[industry] 第 %d 页: 累计 %d / 共 %s", page, len(mapping), total)
            if total and len(mapping) >= total:
                break
            time.sleep(_INTER_PAGE_SLEEP)
    except Exception as exc:
        LOG.error("[industry] 抓取异常: %s\n%s", exc, traceback.format_exc())
    LOG.info("[industry] 抓取完成: %d 只股票有行业（总 %s）", len(mapping), total)
    return mapping


def save_industry(mapping, path=None):
    """落盘行业映射（原子写）。

    Returns:
        str: 实际写入路径。
    """
    path = path or config.INDUSTRY_FILE
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(mapping),
        "source": "eastmoney_clist_f100",
        "items": dict(mapping),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, path)
        LOG.info("[industry] 已落盘 %s（%d 条）", path, len(mapping))
    except Exception as exc:
        LOG.error("[industry] 落盘异常 %s: %s\n%s", path, exc, traceback.format_exc())
    return path


def _load_eastmoney(path=None):
    """读取东财行业映射文件。

    Returns:
        dict: ``{6 位代码: 行业名}``；缺失或损坏返回空 dict。
    """
    path = path or config.INDUSTRY_FILE
    try:
        if not os.path.exists(path):
            LOG.warning("[industry] 东财行业映射不存在: %s（可运行 python -m panels.industry）", path)
            return {}
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        items = payload.get("items") or {}
        LOG.debug("[industry] 载入东财行业 %d 条（更新于 %s）", len(items), payload.get("updated_at"))
        return items
    except Exception as exc:
        LOG.error("[industry] 读取东财映射异常 %s: %s\n%s", path, exc, traceback.format_exc())
        return {}


def load_industry(path=None, prefer_local=True):
    """读取行业映射：**通达信本地为主（离线、无 5223 只上限），东财为补充**。

    主源理由：本地 ``tdxhy.cfg`` 实测覆盖 **5575 只 / 57 个二级行业**（东财 5223 只），
    且零网络、分类标准稳定；东财仅用于补本地缺失的标的。

    Args:
        path: 东财映射文件路径（兼容旧签名）。
        prefer_local: ``True`` 时以本地为准（冲突时本地覆盖东财）。

    Returns:
        dict: ``{6 位代码: 行业名}``
    """
    try:
        from panels import industry_local as iloc
        local = iloc.load_industry_local()
    except Exception as exc:
        LOG.error("[industry] 载入本地行业失败: %s", exc)
        local = {}
    em = _load_eastmoney(path=path)

    if local and prefer_local:
        merged = dict(em)
        merged.update(local)                  # 本地覆盖
        src = "本地 tdxhy.cfg 为主 + 东财补充"
    elif local:
        merged = dict(local)
        merged.update(em)                     # 东财覆盖
        src = "东财为主 + 本地补充"
    else:
        merged = dict(em)
        src = "仅东财"
    LOG.info("[industry] 行业映射合并: %d 条（本地 %d / 东财 %d，来源=%s）",
             len(merged), len(local), len(em), src)
    return merged


def main():
    """抓取并落盘。

    Returns:
        dict: ``{"count": int, "path": str|None}``
    """
    mapping = fetch_industry()
    path = save_industry(mapping) if mapping else None
    return {"count": len(mapping), "path": path}


if __name__ == "__main__":      # pragma: no cover - 手动执行入口
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="[%(asctime)s.%(msecs)03d] %(levelname)-5s %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    print(json.dumps(main(), ensure_ascii=False, indent=1))

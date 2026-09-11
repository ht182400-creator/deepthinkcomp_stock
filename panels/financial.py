# -*- coding: utf-8 -*-
"""财务面板构建（R1）。

流程::

    mootdx 读 cw/gpcw<报告期>.dat（本地，0.4s/期）
      → 列名存在性断言（H13，缺列立即报错）
      → 抽取 config.FUND_FIELDS（51 个字段，填充率均 ≥94%）
      → 拼接为长表面板（period × code）
      → 落盘 Parquet：fund_history.parquet（回测用）
      → 派生 fund_latest.parquet（实盘用，**每股回溯**最近有数据的报告期，H4）

关键设计：

- **每股回溯**（H4）：不使用"全市场统一最新期"。季报披露期内该期文件逐步填充，
  统一取最新期会让大批股票因缺数据被误剔除，买池骤减。
- **不要自己算 TTM**：``gpcw`` 自带 ``营业总收入TTM(万元)`` 与"近一年"系列（docs/08 §6.6.3）。
- **时点对齐**：``gpcw`` 自带 ``财报公告日期``（FN314，YYMMDD），无需法定披露日兜底。
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))      # .../panels
_ROOT = os.path.dirname(_HERE)                          # 项目根
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config                                          # noqa: E402
from panels import meta as panel_meta                  # noqa: E402
from panels import universe as uni                     # noqa: E402

LOG = logging.getLogger(__name__)

# 判定"该股该期数据有效"的最小字段集（任一为空即视为无效行）
_VALID_KEYS = ["ROE", "NP_PARENT", "NOTICE_DATE"]
_YY_THRESHOLD = 70          # 两位年份 <70 视作 20xx，否则 19xx
_YEAR_BASE_20 = 2000
_YEAR_BASE_19 = 1900
_PERIOD_DIGITS = 8


def _reader():
    """惰性创建 mootdx 的 FinancialReader（避免导入期即加载重依赖）。"""
    from mootdx.financial.financial import FinancialReader
    return FinancialReader()


def read_period(period, gpcw_dir=None, reader=None):
    """读取单个报告期的全市场财务数据。

    Args:
        period: 报告期，如 ``"20260630"``。
        gpcw_dir: 财务数据目录；缺省 ``config.GPCW_DIR``。
        reader: 复用的 ``FinancialReader`` 实例（批量时传入以避免重复构造）。

    Returns:
        pandas.DataFrame | None: 索引为 6 位代码；文件缺失 / 空文件 / 解析失败返回 None。
    """
    gpcw_dir = gpcw_dir or config.GPCW_DIR
    path = os.path.join(gpcw_dir, "gpcw%s.dat" % period)
    try:
        if not os.path.exists(path):
            LOG.debug("[financial] 报告期文件不存在: %s", path)
            return None
        if os.path.getsize(path) == 0:
            # 未到披露日的未来期，通达信会预建 0 行占位文件 —— 属正常，非错误（H4）
            LOG.debug("[financial] 报告期 %s 为空占位文件，跳过", period)
            return None
        reader = reader or _reader()
        df = reader.to_data(path)
        if df is None or len(df) == 0:
            LOG.debug("[financial] 报告期 %s 解析结果为空", period)
            return None
        return df
    except Exception as exc:
        LOG.error("[financial] 读取报告期 %s 异常: %s\n%s", period, exc, traceback.format_exc())
        return None


def normalize_notice_date(series):
    """把 ``gpcw`` 的"财报公告日期"（YYMMDD 数字，如 260815）归一化为 YYYYMMDD。

    Args:
        series: 原始序列（float / int / 空值）。

    Returns:
        pandas.Series: Int64 类型的 YYYYMMDD；无法解析处为 ``pd.NA``。
    """
    num = pd.to_numeric(series, errors="coerce")
    out = pd.Series(pd.NA, index=series.index, dtype="Int64")
    valid = num.notna() & (num > 0)
    if not valid.any():
        return out
    n = num[valid].astype("int64")
    yy = n // 10000
    year = (yy + _YEAR_BASE_20).where(yy < _YY_THRESHOLD, yy + _YEAR_BASE_19)
    out[valid] = (year * 10000 + (n % 10000)).astype("Int64")
    return out


def extract_period(df, period):
    """从单期 DataFrame 抽取 ``config.FUND_FIELDS`` 并规范化。

    Args:
        df: ``read_period`` 返回的原始 DataFrame。
        period: 报告期字符串。

    Returns:
        pandas.DataFrame: 列 = 内部字段名 + ``code`` / ``period`` / ``notice_date``。

    Raises:
        KeyError: 存在缺失列时（H13 强校验，禁止静默降级）。
    """
    panel_meta.assert_fields(df.columns)        # 缺列立即抛错
    data = {}
    for key, col in config.FUND_FIELDS.items():
        sub = df[col]
        if isinstance(sub, pd.DataFrame):
            # 列名重复时 pandas 返回 DataFrame，取第一列（docs/08 §6.2-④ 坑 4）
            sub = sub.iloc[:, 0]
        data[key] = pd.to_numeric(sub, errors="coerce")
    out = pd.DataFrame(data)
    out.index = [str(x).strip().zfill(6) for x in out.index]
    out.index.name = "code"
    out = out.reset_index()
    out["period"] = str(period)
    out["notice_date"] = normalize_notice_date(out["NOTICE_DATE"])
    return out


def period_deadline(period):
    """返回某报告期的法定披露截止日（YYYYMMDD）。

    规则：一季报/年报截止 4/30、半年报 8/31、三季报 10/31；
    年报（1231）的截止日在**次年** 4/30。
    """
    year = int(str(period)[:4])
    suffix = str(period)[4:]
    md = config.FUND_DEADLINE.get(suffix)
    if md is None:
        return None
    end_year = year + 1 if suffix == "1231" else year
    return end_year * 10000 + md


def is_period_overdue(period, today=None):
    """判断某报告期是否已过法定披露截止日（H4）。

    只有"已过截止日仍无数据"才应怀疑数据缺失；
    未到期的空占位文件属正常，不得触发备源或告警。
    """
    deadline = period_deadline(period)
    if deadline is None:
        return False
    today = today or int(datetime.now().strftime("%Y%m%d"))
    return today > deadline


def build_history(periods=None, save=True, verbose=True):
    """构建财务历史面板并落盘 Parquet。

    Args:
        periods: 指定报告期；缺省按 ``config.GPCW_MIN_PERIOD`` 自动列举。
        save: 是否落盘。
        verbose: 是否打印进度日志。

    Returns:
        pandas.DataFrame | None: 长表面板；无数据返回 None。
    """
    periods = periods or uni.list_gpcw_periods()
    frames = []
    skipped = []
    try:
        reader = _reader()
    except Exception as exc:
        LOG.error("[financial] 初始化 mootdx 失败: %s\n%s", exc, traceback.format_exc())
        return None

    for i, period in enumerate(periods, 1):
        df = read_period(period, reader=reader)
        if df is None:
            skipped.append(period)
            continue
        try:
            frames.append(extract_period(df, period))
        except KeyError as exc:
            # 列名缺失是致命错误：中断并明确指出是哪一期（防止静默产出空面板）
            LOG.error("[financial] 报告期 %s 字段缺失，构建中断: %s", period, exc)
            raise
        if verbose and (i % 10 == 0 or i == len(periods)):
            LOG.info("[financial] 已解析 %d/%d 期（累计 %d 只股票行）",
                     i, len(periods), sum(len(f) for f in frames))

    if not frames:
        LOG.error("[financial] 无任何可用报告期数据")
        return None

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["period", "code"]).reset_index(drop=True)
    LOG.info("[financial] 面板构建完成: %d 行 × %d 列 | 报告期 %d 个（跳过 %d 个空期）",
             len(panel), panel.shape[1], len(frames), len(skipped))

    if save:
        try:
            os.makedirs(os.path.dirname(config.FUND_PANEL_FILE), exist_ok=True)
            panel.to_parquet(config.FUND_PANEL_FILE, index=False, compression="zstd")
            LOG.info("[financial] 已落盘 %s", config.FUND_PANEL_FILE)
        except Exception as exc:
            LOG.error("[financial] 落盘面板异常: %s\n%s", exc, traceback.format_exc())
    return panel


def effective_base_period(panel):
    """返回"已过披露截止日的最大报告期"，作为 stale 判定基准（H4）。

    Args:
        panel: 长表面板。

    Returns:
        str | None
    """
    if panel is None or panel.empty:
        return None
    periods = sorted(set(str(p) for p in panel["period"].unique()))
    overdue = [p for p in periods if is_period_overdue(p)]
    return (overdue or periods)[-1]


def build_latest(panel, save=True):
    """派生最新快照：**每股回溯其最近一个有数据的报告期**（H4）。

    Args:
        panel: 由 ``build_history`` 产出的长表面板。
        save: 是否落盘 Parquet + 轻量 JSON。

    Returns:
        pandas.DataFrame | None: 每股一行，附加 ``stale_periods`` / ``is_stale`` / ``full``。
    """
    if panel is None or panel.empty:
        LOG.warning("[financial] 面板为空，无法派生最新快照")
        return None
    try:
        valid = panel.dropna(subset=[k for k in _VALID_KEYS if k in panel.columns])
        if valid.empty:
            LOG.error("[financial] 面板中无任何有效行（关键字段全空）")
            return None
        # 每股取 period 最大的一行（回溯，而非全市场统一最新期）
        latest = valid.sort_values("period").groupby("code", as_index=False).tail(1).copy()

        periods = sorted(set(str(p) for p in panel["period"].unique()))
        pos = {p: i for i, p in enumerate(periods)}
        base = effective_base_period(panel)
        base_pos = pos.get(base, len(periods) - 1)
        latest["stale_periods"] = latest["period"].map(lambda p: base_pos - pos.get(str(p), base_pos))
        latest["is_stale"] = latest["stale_periods"] >= config.FUND_STALE_PERIODS
        latest["full"] = latest["code"].map(uni.pure_to_full)
        latest["board"] = latest["full"].map(uni.board_of)
        latest = latest.sort_values("code").reset_index(drop=True)

        stale_cnt = int(latest["is_stale"].sum())
        LOG.info("[financial] 最新快照: %d 只 | 基准期=%s | 财报陈旧(stale) %d 只(%.1f%%)",
                 len(latest), base, stale_cnt, 100.0 * stale_cnt / max(1, len(latest)))

        if save:
            try:
                latest.to_parquet(config.FUND_LATEST_FILE, index=False, compression="zstd")
                # 轻量 JSON：供后端快速加载 / 前端展示（只保留关键列，控制体积）
                cols = ["code", "full", "board", "period", "notice_date", "stale_periods", "is_stale",
                        "ROE", "ROE_WEIGHTED", "NP_PARENT", "NP_DEDUCT", "BVPS", "DEBT_RATIO",
                        "OCF", "CAPEX", "TOTAL_SHARE", "FLOAT_A", "FREE_FLOAT", "HOLDERS",
                        "REV_TTM", "REV_TTM_RECENT", "GP_MARGIN", "NP_MARGIN",
                        "REV_YOY", "NP_YOY", "NP_DEDUCT_YOY", "OCF_TO_NP"]
                keep = [c for c in cols if c in latest.columns]
                payload = {
                    "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "base_period": base,
                    "count": len(latest),
                    "items": latest[keep].where(pd.notna(latest[keep]), None).to_dict(orient="records"),
                }
                with open(config.FUND_DAILY_LATEST_FILE, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, ensure_ascii=False)
                LOG.info("[financial] 已落盘 %s 与 %s",
                         config.FUND_LATEST_FILE, config.FUND_DAILY_LATEST_FILE)
            except Exception as exc:
                LOG.error("[financial] 落盘最新快照异常: %s\n%s", exc, traceback.format_exc())
        return latest
    except Exception as exc:
        LOG.error("[financial] 派生最新快照异常: %s\n%s", exc, traceback.format_exc())
        return None


def main(periods=None, save=True):
    """构建入口：财务历史面板 + 最新快照 + 字段映射 + 元信息。

    Returns:
        dict: ``{"panel_rows": int, "latest_rows": int, "stocks": int, "periods": int}``
    """
    result = {"panel_rows": 0, "latest_rows": 0, "stocks": 0, "periods": 0}
    try:
        panel_meta.save_field_map()                       # 字段映射带版本落盘（H13）
        panel = build_history(periods=periods, save=save)
        if panel is None:
            LOG.error("[financial] 构建失败：面板为空")
            return result
        latest = build_latest(panel, save=save)
        result["panel_rows"] = len(panel)
        result["latest_rows"] = 0 if latest is None else len(latest)
        result["stocks"] = int(panel["code"].nunique())
        result["periods"] = int(panel["period"].nunique())

        if save:
            # ⚠️ 财务面板本身无复权概念，但 meta.json 是**价格/财务共用**的同一个文件：
            # 若这里直接写 base_date=None，会把 `panels/price.py` 冻结的复权基准抹掉，
            # 破坏 H1（"前复权口径冻结 → 回测可复现"）且**无任何报错**。
            # 故此处必须**沿用已有 base_date**，不得覆盖。
            _prev_base = (panel_meta.load_meta() or {}).get("base_date")
            meta = panel_meta.build_meta(
                base_date=_prev_base,
                field_map_version=panel_meta.load_field_map()[1],
                periods=sorted(set(str(p) for p in panel["period"].unique())),
                extra={
                    "panel_rows": result["panel_rows"],
                    "stocks": result["stocks"],
                    "latest_rows": result["latest_rows"],
                    "latest_base_period": effective_base_period(panel),
                    "source": "tdx_gpcw_mootdx",
                },
            )
            panel_meta.save_meta(meta)
        LOG.info("[financial] 完成: %s", result)
        return result
    except Exception as exc:
        LOG.error("[financial] 构建异常: %s\n%s", exc, traceback.format_exc())
        return result


if __name__ == "__main__":      # pragma: no cover - 手动执行入口
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="[%(asctime)s.%(msecs)03d] %(levelname)-5s %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    print(json.dumps(main(), ensure_ascii=False, indent=1))

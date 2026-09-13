# -*- coding: utf-8 -*-
"""生成"本周 vs 上周"信号对比 JSON (data/live_compare.json)，供 build_dashboard 渲染对比段。
同时落盘 data/live_buy_list_<信号日>.txt（与 live B 文本一致）。

原理：current_candidates 支持 today= 指定任意历史周信号日；本周取全局周轴末根，
上周取倒数第二根。进程内宇宙缓存(_get_universe)使两次计算只构建一次宇宙。

重要（数据同源）：看板 build_dashboard 从项目根 data/ 读取 txt 与 live_compare.json。
若二者不是同一次运行生成，看板会出现"①③ 用本周、② 用旧周"的张冠李戴。
因此分析流程 (analysis._persist_dashboard) 会复用已算好的本周 res 调用 write_compare()
同步刷新本 JSON，保证三处数据同源。

用法: python live_compare.py [cash] [N] [scheme]
"""
import os, sys, json

# 同目录导入 regime 引擎；用模块属性方式访问，便于单测打桩（patch R.current_candidates）
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import regime_layer2_backtest as R

# 产物统一写到项目 data/（build_dashboard 的读取位置）
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "data"))


def _slim(res):
    """把 current_candidates 的完整结果裁剪成看板需要的精简结构。"""
    if res is None:
        return None
    return dict(
        signal_date=res['signal_date'],
        regime_up=res['regime_up'],
        n_stocks=res['n_stocks'],
        selected=[dict(code=r['code'], name=r.get('name', r['code']), price=r['price'],
                       lots=r.get('lots', 0), capital=r.get('capital', 0),
                       mom=r['mom'], roe=r['roe'], sind=r.get('sind', ''))
                  for r in res['selected']],
        # 合格池带 score，供看板 ③ 按评分降序完整列出
        pool=[dict(code=r['code'], name=r.get('name', r['code']), price=r['price'],
                   mom=r['mom'], roe=r['roe'], sind=r.get('sind', ''),
                   score=r.get('score', 0))
              for r in res['buy']],
    )


def _build(cur, prev, cash, N, scheme, prev_date):
    return dict(scheme=scheme, cash=cash, N=N,
                current=_slim(cur), prev=_slim(prev),
                prev_signal_date=prev_date,
                same_data=(prev is not None and prev['signal_date'] == cur['signal_date']))


def write_compare(cur, cash=None, N=None, scheme=None):
    """用已算好的本周结果 cur 生成 data/live_compare.json（只重算上周，避免重复算本周）。

    参数 cur 为 current_candidates 的返回值；cash/N/scheme 缺省时从 cur 中取。
    返回写出的 dict。分析流程复用以保证看板 ①②③ 数据同源。
    """
    scheme = scheme or cur.get('scheme', 'B')
    cash = cur.get('cash') if cash is None else cash
    N = cur.get('n_target') if N is None else N

    # 上周 = 全局周轴上、本周信号日的前一根
    _, global_dates, _, _ = R._get_universe(include_bj=True)
    prev, prev_date = None, None
    cur_date = cur['signal_date']
    idx = global_dates.index(cur_date) if cur_date in global_dates else len(global_dates) - 1
    if idx >= 1:
        prev_date = global_dates[idx - 1]
        prev = R.current_candidates(scheme=scheme, cash=cash, N=N, today=prev_date)

    out = _build(cur, prev, cash, N, scheme, prev_date)
    os.makedirs(DATA, exist_ok=True)
    json_path = os.path.join(DATA, "live_compare.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def main():
    cash = float(sys.argv[1]) if len(sys.argv) > 1 else 50000.0
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    scheme = sys.argv[3] if len(sys.argv) > 3 else 'B'

    # 本周：today=None → 全局周轴末根(最新信号)
    cur = R.current_candidates(scheme=scheme, cash=cash, N=N)
    txt = R.format_live_report(cur)
    os.makedirs(DATA, exist_ok=True)
    txt_path = os.path.join(DATA, f"live_buy_list_{cur['signal_date']}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt + "\n")

    # 上周对比（只重算上周）
    out = write_compare(cur, cash=cash, N=N, scheme=scheme)
    prev = out.get("prev")

    # ---------- 控制台摘要 ----------
    print(f"[live_compare] 本周信号={cur['signal_date']} regime_up={cur['regime_up']} "
          f"建仓{len(cur['selected'])}只 合格池{len(cur['buy'])}只")
    if prev:
        cur_sel = {r['code'] for r in cur['selected']}
        prev_sel = {r['code'] for r in prev['selected']}
        cur_pool = {r['code'] for r in cur['buy']}
        prev_pool = {r['code'] for r in prev['pool']}
        print(f"              上周信号={prev['signal_date']} regime_up={prev['regime_up']} "
              f"建仓{len(prev['selected'])}只 合格池{len(prev['pool'])}只")
        print(f"              建仓变化: 新进{len(cur_sel - prev_sel)} "
              f"退出{len(prev_sel - cur_sel)} 维持{len(cur_sel & prev_sel)}")
        print(f"              合格池变化: 进入{len(cur_pool - prev_pool)} "
              f"退出{len(prev_pool - cur_pool)}")
    else:
        print("              无上周数据(全局周轴<2周)，跳过对比")
    print(f"              已写 -> {txt_path}")
    print(f"              已写 -> {os.path.join(DATA, 'live_compare.json')}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""把 live_buy_list_*.txt + results_layer2_fresh.json 渲染成自包含 HTML 看盘面板。"""
import re, json, os, glob, math
from datetime import date

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(BASE, "data")
files = sorted(glob.glob(os.path.join(BASE, "live_buy_list_*.txt")))
live_path = files[-1] if files else None
if live_path is None:
    raise SystemExit("找不到 live_buy_list_*.txt")
res_path = os.path.join(BASE, "results_layer2_fresh.json")

with open(live_path, encoding="utf-8") as f:
    txt = f.read()
with open(res_path, encoding="utf-8") as f:
    res = json.load(f)

curves_path = os.path.join(BASE, "results_layer2_curves.json")
curves = json.load(open(curves_path, encoding="utf-8")) if os.path.exists(curves_path) else {}

# ---------- 加载上周对比 ----------
cmp_path = os.path.join(BASE, "live_compare.json")
cmp = json.load(open(cmp_path, encoding="utf-8")) if os.path.exists(cmp_path) else None

# ---------- 解析头部 ----------
m = re.search(r"signal=(\d+)  scheme=(\w+).*?段/全局regime_up=(\w+)", txt)
signal, scheme, regime = m.group(1), m.group(2), m.group(3)
m2 = re.search(r"账户=([\d.]+)元\s*目标仓数N=(\d+)\s*暴露=([\d.]+)\s*可投=([\d.]+)\s*单仓预算=([\d.]+)\s*宇宙=([\d.]+)", txt)
account, N, expo, invest, per, universe = (m2.group(i) for i in range(1, 7))
segm = re.search(r"段指数: (\{.*?\})", txt).group(1)
# 段状态 / 合格池板块分布 / 板块约束（用于解释"为何候选集中在某板块"）
_m_seg = re.search(r"段状态\(56周均线\): (.+)", txt)
SEG_STATE = _m_seg.group(1).strip() if _m_seg else ""
_m_bd = re.search(r"合格池板块分布: (.+)", txt)
BOARD_DIST = _m_bd.group(1).strip() if _m_bd else ""
_m_bc = re.search(r"板块约束: (.+)", txt)
BOARD_CAP_TXT = _m_bc.group(1).strip() if _m_bc else ""

def mkt(code):
    if code.startswith("920") or code.startswith("8") or code.startswith("4"):
        return "bj"
    if code.startswith("60") or code.startswith("68") or code.startswith("90"):
        return "sh"
    return "sz"

MKT_CN = {"sh": "沪市", "sz": "深市", "bj": "北交所"}
MKT_COLOR = {"sh": "#4aa3ff", "sz": "#2ecc71", "bj": "#ff9f43"}

# ---------- 解析实际建仓 ----------
actual = []
for line in txt.splitlines():
    p = line.split()
    if len(p) == 9 and re.match(r"^\d{6}$", p[0]) and re.match(r"^\d", p[3]):
        name = p[1] if not (p[1] == p[0] or p[1].isdigit()) else ""
        actual.append(dict(code=p[0], name=name, industry=p[2], price=float(p[3]),
                           roe=float(p[4]), fcf=float(p[5]), mom=float(p[6]),
                           lots=int(p[7]), amt=int(p[8])))

# ---------- 解析合格买仓池 ----------
pool = []
for line in txt.splitlines():
    star = "★" in line
    mm = re.search(r"(\d{6})\s+(\S+)\s+(\S+?)\s+价\s*([\d.]+)\s+ROE\s*([\d.]+)%\s+FCF/N\s*([\d.]+)\s+MOM\s*([\d.]+)%\s+分([\d.]+)\s+\[(.*?)\](UP|DOWN)", line)
    if mm:
        name = mm.group(2).replace("★", "")
        if name == mm.group(1) or name.isdigit():
            name = ""
        pool.append(dict(code=mm.group(1), name=name, industry=mm.group(3),
                         price=float(mm.group(4)), roe=float(mm.group(5)), fcf=float(mm.group(6)),
                         mom=float(mm.group(7)), pct=float(mm.group(8)), seg=mm.group(9),
                         up=mm.group(10) == "UP", star=star))

# ---------- 解析观察池 ----------
watch = []
for line in txt.splitlines():
    mm = re.search(r"(\d{6})(?:\s+\d{6})?\s+(.+?)\s+ROE=([\d.]+)%\s+未过:(.+)", line)
    if mm:
        watch.append(dict(code=mm.group(1), industry=mm.group(2), roe=float(mm.group(3)), reason=mm.group(4).strip()))

# ---------- SVG 柱状图 ----------
def bar_svg(data, height=300, pct=True, color_pos="#2ecc71", color_neg="#e74c3c"):
    width = 760
    pad = 50
    base = height - 45
    barmax = base - 30
    n = len(data)
    gap = (width - pad * 2) / n
    bw = gap * 0.62
    maxv = max(abs(v) for _, v in data) or 1
    s = [f'<svg viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="xMidYMid meet" style="max-width:760px">']
    s.append(f'<line x1="{pad}" y1="{base}" x2="{width-pad}" y2="{base}" stroke="#33415c" stroke-width="1"/>')
    for i, (lab, val) in enumerate(data):
        x = pad + gap * i + (gap - bw) / 2
        h = (abs(val) / maxv) * barmax
        y = base - h
        col = color_pos if val >= 0 else color_neg
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3" fill="{col}"/>')
        labtxt = f"{val*100:.1f}%" if pct else f"{val:.2f}"
        s.append(f'<text x="{x+bw/2:.1f}" y="{y-6:.1f}" text-anchor="middle" fill="#e6edf3" font-size="13" font-weight="600">{labtxt}</text>')
        s.append(f'<text x="{x+bw/2:.1f}" y="{base+18:.1f}" text-anchor="middle" fill="#9aa7b8" font-size="11">{lab}</text>')
    s.append("</svg>")
    return "".join(s)

def netvalue_svg(curves, width=760, height=360):
    bk = curves.get("B_全样本1996+")
    ck = curves.get("current_全样本1996+")
    if not bk:
        return '<p class="note">净值曲线数据未生成（请先运行 dump_curves.py）。</p>'
    dates, beq = bk["dates"], bk["equity"]
    ceq = ck["equity"] if ck else None
    n = len(beq)
    allv = list(beq) + (list(ceq) if ceq else [])
    lmin = math.log10(min(allv)); lmax = math.log10(max(allv))
    pad_l, pad_r, pad_t, pad_b = 52, 18, 22, 38

    def X(i):
        return pad_l + (width - pad_l - pad_r) * (i / (n - 1) if n > 1 else 0)

    def Y(v):
        return height - pad_b - (height - pad_t - pad_b) * (math.log10(v) - lmin) / (lmax - lmin)

    s = [f'<svg viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="xMidYMid meet" style="max-width:760px;background:#0d1117">']
    for g in range(0, 6):
        yy = pad_t + (height - pad_t - pad_b) * g / 5.0
        val = 10 ** (lmax - (lmax - lmin) * g / 5.0)
        s.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width-pad_r}" y2="{yy:.1f}" stroke="#21262d"/>')
        s.append(f'<text x="4" y="{yy+3:.1f}" fill="#8b98a9" font-size="10">{val:.1f}x</text>')
    # 回撤阴影（B 相对历史峰值）
    pk = beq[0]; peak = []
    for v in beq:
        pk = max(pk, v); peak.append(pk)
    pts = [(X(i), Y(beq[i])) for i in range(n)] + [(X(i), Y(peak[i])) for i in range(n - 1, -1, -1)]
    s.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + '" fill="rgba(231,76,60,0.13)"/>')
    if ceq:
        cp = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(ceq[:n]))
        s.append(f'<polyline points="{cp}" fill="none" stroke="#4aa3ff" stroke-width="1.2" opacity="0.85"/>')
    bp = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(beq))
    s.append(f'<polyline points="{bp}" fill="none" stroke="#2ecc71" stroke-width="2.2"/>')
    last_year = None
    for i, d in enumerate(dates):
        yr = d // 10000
        if yr != last_year:
            last_year = yr
            s.append(f'<line x1="{X(i):.1f}" y1="{pad_t}" x2="{X(i):.1f}" y2="{height-pad_b}" stroke="#1b212b"/>')
            s.append(f'<text x="{X(i):.1f}" y="{height-10:.1f}" fill="#6b7686" font-size="10">{yr}</text>')
    s.append(f'<text x="{pad_l}" y="14" fill="#2ecc71" font-size="11" font-weight="700">■ B 方案(分市场段)</text>')
    if ceq:
        s.append(f'<text x="{pad_l+150}" y="14" fill="#4aa3ff" font-size="11" font-weight="700">■ current(上证)</text>')
    s.append("</svg>")
    ann = bk["annualized"] * 100; mdd = bk["max_drawdown"] * 100
    ck_ann = ck["annualized"] * 100 if ck else None
    note = (f'<div class="note">红色阴影=净值相对历史峰值的回撤（水下区域）。B(修复后) 全样本净值 {beq[-1]:.1f}x，'
            f'年化 {ann:.1f}%，最大回撤 {mdd:.0f}%，末根 {dates[-1]}。'
            + (f'current(上证) 全样本净值更高（年化 {ck_ann:.1f}%），但差距已很小——修复段指数缺失退化为放行后，B 与上证单指数门控长期基本重合，印证"分市场段门控"原意图成立；'
               if ck_ann is not None else '')
            + '两线在 2014 年后仍有一定分化（深市个股由深证成指而非上证门控）。实时买仓用 B（当前市场健康）。</div>')
    return "".join(s) + note

def diff_section(cmp, cur_signal=None):
    """本周 vs 上周信号对比段。cmp = live_compare.json 内容(可能 None)。
    cur_signal = 本周 txt 的信号日，用于校验对比数据是否同源（防"本周清单配上周变化"）。"""
    if cmp is None:
        return ('<div class="section"><h2>② 信号 vs 上周变化</h2>'
                '<div class="note">尚未生成对比数据（先运行 <code>python live_compare.py</code>）。'
                '运行一次后即可显示本周相对上周的建仓与合格池变化。</div></div>')
    cur = cmp.get("current")
    prev = cmp.get("prev")
    if cur is None:
        return ('<div class="section"><h2>② 信号 vs 上周变化</h2>'
                '<div class="note">本周信号数据缺失。</div></div>')
    # 同源校验：对比数据的最新信号日必须等于本周 txt 的信号日，否则隐藏（避免张冠李戴）
    if cur_signal is not None and str(cur.get("signal_date")) != str(cur_signal):
        return ('<div class="section"><h2>② 信号 vs 上周变化</h2>'
                f'<div class="warn">⚠️ 对比数据滞后：本条对比来自 <b>{cur.get("signal_date")}</b>，'
                f'与本周信号 <b>{cur_signal}</b> 不一致。为避免"本周清单配旧周变化"，此处暂不展示。<br>'
                '请在 [保存并分析] 完成后刷新本页，或运行 <code>python live_compare.py</code> 刷新对比数据。</div></div>')
    if prev is None:
        return (f'<div class="section"><h2>② 信号 vs 上周变化</h2>'
                f'<div class="note">本周信号 {cur["signal_date"]} 为首次信号（全局周轴不足 2 周），'
                f'暂无上周对比。下周运行后即可看到变化。</div></div>')

    def reg_label(up):
        return "全段 UP → 建议建仓" if up else "存在下跌段 → 空仓观望"

    rc = (cur["regime_up"] != prev["regime_up"])
    if rc:
        banner_col, banner_txt = ("#e74c3c",
            f"⚠️ 信号状态变化：上周【{reg_label(prev['regime_up'])}】→ 本周【{reg_label(cur['regime_up'])}】")
    elif cur["regime_up"]:
        banner_col, banner_txt = ("#2ecc71",
            f"✅ 信号状态维持：连续两周【{reg_label(cur['regime_up'])}】（{prev['signal_date']} → {cur['signal_date']}）")
    else:
        banner_col, banner_txt = ("#e67e22",
            f"⏸ 信号状态维持：连续两周【{reg_label(cur['regime_up'])}】（{prev['signal_date']} → {cur['signal_date']}）")

    cur_sel = {r["code"]: r for r in cur["selected"]}
    prev_sel = {r["code"]: r for r in prev["selected"]}
    new_codes = [c for c in cur_sel if c not in prev_sel]
    exit_codes = [c for c in prev_sel if c not in cur_sel]
    hold_codes = [c for c in cur_sel if c in prev_sel]
    cur_pool = {r["code"] for r in cur["pool"]}
    prev_pool = {r["code"] for r in prev["pool"]}
    enter_pool = sorted(c for c in cur_pool if c not in prev_pool)
    leave_pool = sorted(c for c in prev_pool if c not in cur_pool)
    # 代码 -> 中文名称映射（cur/prev 的 pool 条目均已带 name 字段）
    pool_name = {}
    for _p in (cur["pool"], prev["pool"]):
        for r in _p:
            pool_name.setdefault(r["code"], r.get("name") or r["code"])

    def cell(r):
        mk = mkt(r["code"])
        tag = f"<span class='mkt' style='background:{MKT_COLOR[mk]}'>{MKT_CN[mk]}</span>"
        return (f"<tr><td class='col-code'><b>{r['code']}</b></td>"
                f"<td class='col-name'>{r.get('name') or '—'}</td>"
                f"<td class='col-mkt'>{tag}</td>"
                f"<td class='col-price num'>{r['price']:.2f}</td>"
                f"<td class='col-mom num' style='color:#2ecc71'>+{r['mom']*100:.0f}%</td>"
                f"<td class='col-lots num'>{r.get('lots',0)}</td>"
                f"<td class='col-amt num'>{r.get('capital',0):,.0f}</td></tr>")

    def mini(title, rows_codes, src, color):
        if not rows_codes:
            body = "<tr><td colspan='7' class='note' style='text-align:center'>— 无 —</td></tr>"
        else:
            body = "".join(cell(src[c]) for c in rows_codes)
        return (f"<div class='diffcol'><div class='difftitle' style='color:{color}'>{title}（{len(rows_codes)}）</div>"
                f"<table class='diff-table'><tr>"
                f"<th class='col-code'>代码</th><th class='col-name'>名称</th><th class='col-mkt'>市场</th>"
                f"<th class='col-price num'>现价</th><th class='col-mom num'>动量</th>"
                f"<th class='col-lots num'>手</th><th class='col-amt num'>金额</th></tr>"
                f"{body}</table></div>")

    new_html = mini("🟢 新进建仓", new_codes, cur_sel, "#2ecc71")
    exit_html = mini("🔴 退出建仓", exit_codes, prev_sel, "#e74c3c")
    hold_html = mini("⚪ 维持建仓", hold_codes, cur_sel, "#9aa7b8")

    def pool_cell(r):
        mk = mkt(r["code"])
        tag = f"<span class='mkt' style='background:{MKT_COLOR[mk]}'>{MKT_CN[mk]}</span>"
        return (f"<tr><td class='col-code'><b>{r['code']}</b></td>"
                f"<td class='col-name'>{r.get('name') or '—'}</td>"
                f"<td class='col-mkt'>{tag}</td>"
                f"<td class='col-price num'>{r['price']:.2f}</td>"
                f"<td class='col-mom num' style='color:#2ecc71'>+{r['mom']*100:.0f}%</td></tr>")

    def pool_mini(title, rows_codes, src, color):
        if not rows_codes:
            body = "<tr><td colspan='5' class='note' style='text-align:center'>— 无 —</td></tr>"
        else:
            body = "".join(pool_cell(src[c]) for c in rows_codes)
        return (f"<div class='diffcol'><div class='difftitle' style='color:{color}'>{title}（{len(rows_codes)}）</div>"
                f"<table class='diff-table pool-diff-table'><tr>"
                f"<th class='col-code'>代码</th><th class='col-name'>名称</th><th class='col-mkt'>市场</th>"
                f"<th class='col-price num'>现价</th><th class='col-mom num'>动量</th></tr>"
                f"{body}</table></div>")

    cur_pool_map = {r["code"]: r for r in cur["pool"]}
    prev_pool_map = {r["code"]: r for r in prev["pool"]}

    enter_html = pool_mini("🟢 进入合格池", enter_pool, cur_pool_map, "#2ecc71")
    leave_html = pool_mini("🔴 退出合格池", leave_pool, prev_pool_map, "#e74c3c")

    pool_html = (f"<div class='pooldiff'>"
                 f"<div class='summary'>合格买仓池：上周 <b>{len(prev_pool)}</b> 只 → 本周 <b>{len(cur_pool)}</b> 只"
                 f"（<span style='color:#2ecc71'>进入 {len(enter_pool)}</span> / "
                 f"<span style='color:#e74c3c'>退出 {len(leave_pool)}</span>）</div>"
                 f"<div class='grid2'>{enter_html}{leave_html}</div>"
                 f"</div>")

    return (f'<div class="section"><h2>② 信号 vs 上周变化（{prev["signal_date"]} → {cur["signal_date"]}）</h2>'
            f'<div class="banner" style="border-color:{banner_col};color:{banner_col}">{banner_txt}</div>'
            f'<div class="diff-stack">{new_html}{exit_html}{hold_html}</div>'
            f'{pool_html}'
            f'<div class="note">说明：建仓以"实际下单参考"为准（受价格×100≤单仓预算的整手约束）；'
            f'合格池为所有通过质量+动量+站线+段 regime 的候选。若两周间无变化，说明模型信号稳定，'
            f'通常发生于趋势市；若出现退出/新进，多为价格越过 56 周线、动量转负或段 regime 翻转所致。</div>'
            f'</div>')

schemes_show = [("current(上证)", "current_全样本1996+"),
                ("A(全指)", "A_全样本1996+"),
                ("B(分市场段)", "B_全样本1996+"),
                ("C(内生)", "C_全样本1996+"),
                ("E(尾部)", "E_全样本1996+")]
ann = [(lab, res[key]["annualized"]) for lab, key in schemes_show]
shp = [(lab, res[key]["sharpe"]) for lab, key in schemes_show]
svg_ann = bar_svg(ann, pct=True)
svg_shp = bar_svg(shp, pct=False)
nv_svg = netvalue_svg(curves)

# 回测表
bt_rows = ""
for lab, key in [("current 上证56w", "current_全样本1996+"), ("B 分市场段56w (实时用)", "B_全样本1996+"),
                 ("C 内生无regime", "C_全样本1996+"), ("A 全指56w", "A_全样本1996+"),
                 ("E 上证200w尾部", "E_全样本1996+")]:
    r = res[key]
    win = "📈 历史最优(基准)" if key == "current_全样本1996+" else ("✅ 修复后≈基准" if key == "B_全样本1996+" else "")
    bt_rows += (f"<tr><td>{lab}{('<span class=win>'+win+'</span>') if win else ''}</td>"
                f"<td>{r['annualized']*100:.1f}%</td><td>{r['sharpe']:.2f}</td>"
                f"<td style='color:#ff6b6b'>{r['max_drawdown']*100:.0f}%</td>"
                f"<td>{r['empty_frac']*100:.0f}%</td><td>{r['avg_turnover']*100:.0f}%</td></tr>")

# ---------- 表格行 ----------
def score_color(score, lo, hi):
    """评分 → 颜色：**同批内评分越高越红**（色相 210° 蓝 → 0° 红，线性插值）。

    返回 (文字色, 背景色)。`lo == hi`（同批同分）时取中间色。
    文字用高饱和色、背景用同色相低透明度，形成"热力"观感，便于从高到低扫读。
    """
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "#8b98a9", "transparent"
    t = 0.5 if hi <= lo else (s - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    hue = 210.0 - 210.0 * t                      # 210(蓝) → 0(红)
    return f"hsl({hue:.0f}, 85%, 64%)", f"hsla({hue:.0f}, 85%, 45%, {0.10 + 0.22 * t:.2f})"


def pos_rows(items, show_star=False, score_range=None):
    out = ""
    for it in items:
        mk = mkt(it["code"])
        tag = f"<span class='mkt' style='background:{MKT_COLOR[mk]}'>{MKT_CN[mk]}</span>"
        star = "<span class='star'>★建仓</span>" if (show_star and it.get("star")) else ""
        pct = it.get("pct", 0.0) or 0.0
        if score_range:
            _fg, _bg = score_color(pct, score_range[0], score_range[1])
            score_td = (f"<td class='num' style='color:{_fg};background:{_bg};"
                        f"font-weight:700'>{pct:.2f}</td>")
        else:
            score_td = f"<td class='num'>{pct:.2f}</td>"
        out += (f"<tr><td><b>{it['code']}</b></td><td>{it.get('name') or '—'}</td>"
                f"<td>{it.get('industry','—')}</td><td>{tag}</td>"
                f"<td class='num'>{it['price']:.2f}</td>"
                f"<td class='num'>{it.get('roe',0):.1f}%</td>"
                f"<td class='num'>{it.get('fcf',0):.2f}</td>"
                f"<td class='num' style='color:#2ecc71'>+{it['mom']:.0f}%</td>"
                f"{score_td}<td>{star}</td>")
        if "lots" in it:
            out += f"<td class='num'>{it['lots']}</td><td class='num'>{it['amt']:,}</td>"
        out += "</tr>"
    return out

# ---------- ① 我的实际持仓（来自左侧「当前持仓」录入 holdings.json） ----------
_HOLD_PATH = os.path.join(BASE, "holdings.json")
try:
    holdings = json.load(open(_HOLD_PATH, encoding="utf-8")) if os.path.exists(_HOLD_PATH) else []
except Exception:
    holdings = []

_actual_codes = {a["code"] for a in actual}
_pool_by_code = {p["code"]: p for p in pool}
_watch_by_code = {}
for _w in watch:
    _watch_by_code.setdefault(_w["code"], _w)


def hold_status(code):
    """给每只持仓标注模型本周信号。返回 (文案, 颜色)。"""
    if code in _actual_codes:
        return "★ 本轮建仓", "#2ecc71"
    if code in _pool_by_code:
        return "合格池", "#4aa3ff"
    if code in _watch_by_code:
        return "观察：" + _watch_by_code[code]["reason"], "#e67e22"
    return "未在模型名单", "#8b98a9"


def holdings_rows(items):
    """① 表体：真实持仓 + 本周信号；空则显示占位提示。"""
    if not items:
        return ("<tr><td colspan='8' class='note' style='text-align:center;padding:16px'>"
                "暂无持仓（在左侧「当前持仓」录入后，本表自动同步）</td></tr>")
    out = ""
    for h in items:
        code = h.get("code", "")
        mk = mkt(code)
        tag = f"<span class='mkt' style='background:{MKT_COLOR[mk]}'>{MKT_CN[mk]}</span>"
        st, col = hold_status(code)
        amt = h.get("amount", 0) or 0
        ding = "<span class='ding'>定投</span>" if h.get("dingtou") else "—"
        out += (f"<tr><td><b>{code}</b></td><td>{h.get('name') or '—'}</td>"
                f"<td>{h.get('industry') or '—'}</td><td>{tag}</td>"
                f"<td class='num'>{amt:,.0f}</td><td>{ding}</td>"
                f"<td>{h.get('date') or '—'}</td>"
                f"<td style='color:{col}'>{st}</td></tr>")
    return out


holdings_html = holdings_rows(holdings)
hold_total = sum((h.get("amount", 0) or 0) for h in holdings)

# ③ 合格池按模型评分降序完整列出（不再截断）；评分列按**同批相对**渐变着色（越高越红）
pool.sort(key=lambda r: -r.get("pct", 0.0))
_pool_scores = [p.get("pct", 0.0) or 0.0 for p in pool]
_score_lo, _score_hi = (min(_pool_scores), max(_pool_scores)) if _pool_scores else (0.0, 1.0)
pool_html = pos_rows(pool, show_star=True, score_range=(_score_lo, _score_hi))
SCORE_LEGEND = ('评分列颜色 = 同批相对（<span style="color:hsl(210,85%,64%)">低</span>'
                ' → <span style="color:hsl(0,85%,64%)">高</span>，越红分越高；本批 '
                f'{_score_lo:.2f}~{_score_hi:.2f}）')
watch_html = "".join(
    f"<tr><td><b>{w['code']}</b></td><td>{w['industry']}</td><td class='num'>{w['roe']:.1f}%</td><td>{w['reason']}</td></tr>"
    for w in watch)

diff_html = diff_section(cmp, signal)

# B 方案是"分市场段"各自裁决，res['regime_up'] 恒为 True；
# 直接显示"全部上涨 → 建议建仓"会误导（实际本周可能只有 1 个段 UP）→ 按段状态概括
_SEG_UP, _SEG_DOWN = [], []
for _it in SEG_STATE.split():
    if "=" not in _it:
        continue
    _n, _v = _it.split("=", 1)
    (_SEG_UP if _v.strip().upper() == "UP" else _SEG_DOWN).append(_n)

SEG_SUMMARY = ""
if scheme.upper() == "B" and (_SEG_UP or _SEG_DOWN):
    SEG_SUMMARY = (f"{'、'.join(_SEG_UP)} UP" if _SEG_UP else "无段 UP")
    if _SEG_DOWN:
        SEG_SUMMARY += f" · {len(_SEG_DOWN)} 段 DOWN"
    if not _SEG_DOWN:
        regime_cn, regime_color = f"5 段全 UP → 建议建仓（{SEG_SUMMARY}）", "#2ecc71"
    elif _SEG_UP:
        regime_cn, regime_color = f"仅 {SEG_SUMMARY} → 仅该板块可买", "#e67e22"
    else:
        regime_cn, regime_color = f"5 段全 DOWN → 空仓观望", "#e74c3c"
else:
    regime_cn = "全部上涨 → 建议建仓" if regime == "True" else "存在下跌段 → 空仓观望"
    regime_color = "#2ecc71" if regime == "True" else "#e74c3c"

# 顶部卡片：市场段摘要（仅 B 方案；全球方案沿用"市场状态"卡片）
SEG_CARD = (f'<div class="card"><div class="k">市场段(56周MA)</div>'
            f'<div class="v small" style="color:{regime_color}">{SEG_SUMMARY}</div></div>'
            ) if SEG_SUMMARY else ""

# ③ 的"为什么全是同一板块"说明（段状态 + 板块分布 + 板块约束是否放宽）
_dim = []
if SEG_STATE:
    _dim.append(f"本周 5 个市场段（56 周均线）：<b>{SEG_STATE}</b>")
if BOARD_DIST:
    _dim.append(f"合格候选板块分布：<b>{BOARD_DIST}</b>")
if BOARD_CAP_TXT:
    _dim.append(f"组合约束：{BOARD_CAP_TXT}")
POOL_DIM_NOTE = f'<div class="note">{"；".join(_dim)}。</div>' if _dim else ""

_bd_items = [x for x in BOARD_DIST.split() if "=" in x]
if len(_bd_items) == 1 and "已放宽板块=是" in BOARD_CAP_TXT:
    _only = _bd_items[0].split("=")[0]
    POOL_DIM_NOTE += (
        f'<div class="warn">⚠️ 本周合格候选<b>全部集中在「{_only}」</b>：B 方案按市场段过滤，'
        f'本周只有「{_SEG_UP[0] if _SEG_UP else "该段"}」站上 56 周均线，其余段 DOWN 的个股即使质量达标也不入选。<br>'
        f'因此"单板块最多 {_bd_items[0].split("=")[1]} 只"的上限已被<b>自动放宽</b>'
        f'（<b>保留单行业上限</b>），以避免"仓位被迫减半、单票风险翻倍"。'
        f'如果你更希望严格限板块（宁可持仓变少/仓位变小），可调低 <code>BOARD_CAP</code> 或关闭该放宽逻辑。</div>')

CSS = """
* { box-sizing: border-box; margin:0; padding:0; }
body { background:#0d1117; color:#e6edf3; font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif; padding:24px; line-height:1.5; }
h1 { font-size:22px; margin-bottom:4px; }
.sub { color:#8b98a9; font-size:13px; margin-bottom:20px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-bottom:26px; }
.card { background:#161b22; border:1px solid #21262d; border-radius:10px; padding:16px; }
.card .k { color:#8b98a9; font-size:12px; }
.card .v { font-size:22px; font-weight:700; margin-top:6px; }
.card .v.small { font-size:16px; }
.section { background:#161b22; border:1px solid #21262d; border-radius:10px; padding:18px; margin-bottom:22px; }
.section h2 { font-size:16px; margin-bottom:14px; border-left:3px solid #2ecc71; padding-left:10px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid #21262d; }
th { color:#8b98a9; font-weight:600; background:#0f141b; position:sticky; top:0; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.mkt { color:#0d1117; font-size:11px; padding:2px 7px; border-radius:4px; font-weight:700; }
.star { color:#ffd166; font-size:11px; font-weight:700; }
.ding { color:#2ecc71; font-size:11px; font-weight:700; }
tr:hover { background:#1c2230; }
.win { color:#2ecc71; font-size:11px; margin-left:6px; }
.note { color:#8b98a9; font-size:12px; margin-top:10px; }
.warn { background:#2d1b1b; border:1px solid #5c2b2b; color:#ffb3b3; padding:12px 14px; border-radius:8px; font-size:13px; margin-bottom:22px; }
footer { color:#6b7686; font-size:12px; margin-top:30px; border-top:1px solid #21262d; padding-top:14px; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }
@media(max-width:760px){ .grid2{grid-template-columns:1fr;} }
.banner { border:1px solid; border-radius:8px; padding:10px 14px; font-size:13px; font-weight:600; margin-bottom:14px; background:#0f141b; }
.diffcol { background:#0f141b; border:1px solid #21262d; border-radius:8px; padding:10px; }
.diff-stack { display:flex; flex-direction:column; gap:14px; margin-bottom:16px; }
.difftitle { font-size:13px; font-weight:700; margin-bottom:8px; }
.pooldiff { font-size:13px; color:#c9d3df; background:#0f141b; border:1px solid #21262d; border-radius:8px; padding:10px 12px; }
.pooldiff .summary { margin-bottom:8px; }
.diff-table { table-layout:fixed; width:100%; border-collapse:collapse; font-size:12px; }
.diff-table th, .diff-table td { text-align:left; padding:6px 8px; border-bottom:1px solid #21262d; vertical-align:middle; }
.diff-table th { color:#8b98a9; font-weight:600; background:#0f141b; white-space:nowrap; }
.diff-table td.num { text-align:right; font-variant-numeric:tabular-nums; }
.diff-table .col-code { width:13%; }
.diff-table .col-name { width:17%; }
.diff-table .col-mkt { width:10%; }
.diff-table .col-price { width:14%; }
.diff-table .col-mom { width:14%; }
.diff-table .col-lots { width:10%; }
.diff-table .col-amt { width:22%; }
.pool-diff-table .col-code { width:16%; }
.pool-diff-table .col-name { width:24%; }
.pool-diff-table .col-mkt { width:14%; }
.pool-diff-table .col-price { width:23%; }
.pool-diff-table .col-mom { width:23%; }
"""

body = f"""
<h1>周频量化策略 · 实时看盘面板</h1>
<div class="sub">信号日 {signal} · 方案 {scheme} · 生成于 {date.today().isoformat()} · 数据来源：通达信本地行情 + 东方财富基本面</div>

<div class="warn">⚠️ 本面板为策略研究展示，所有标的均为量化模型输出，<b>不构成投资建议</b>。请结合自身风险承受能力独立决策。</div>

<div class="cards">
  <div class="card"><div class="k">当前方案</div><div class="v small">B · 分市场段指数 56 周 MA</div></div>
  <div class="card"><div class="k">市场状态</div><div class="v small" style="color:{regime_color}">{regime_cn}</div></div>
  <div class="card"><div class="k">账户 / 目标仓数</div><div class="v small">{account} 元 / {N} 仓</div></div>
  <div class="card"><div class="k">我的持仓</div><div class="v">{len(holdings)} 只<span style="font-size:13px;color:#8b98a9"> · {hold_total:,.0f} 元</span></div></div>
  {SEG_CARD}
</div>

<div class="section">
  <h2>① 我的实际持仓（来自左侧「当前持仓」录入）</h2>
  <table>
    <tr><th>代码</th><th>名称</th><th>行业</th><th>市场</th><th class="num">金额(元)</th><th>定投</th><th>买入日期</th><th>本周信号</th></tr>
    {holdings_html}
  </table>
  <div class="note">本表 = 你在左侧「当前持仓」录入的真实持仓，金额以你的录入为准；持仓为空时显示"暂无"。末列「本周信号」为模型建议：★本轮建仓 = 已选入模型建仓；合格池 = 通过质量+动量+站线+段 regime；观察：&lt;原因&gt; = 质量过关但未触发买点；未在模型名单 = 不在本周候选。<b>模型建议不构成投资建议。</b></div>
</div>

{diff_html}

<div class="section">
  <h2>③ 合格买仓池（质量+动量+站线+段 regime，{len(pool)} 只 · 按评分降序全量）</h2>
  <table>
    <tr><th>代码</th><th>名称</th><th>行业</th><th>市场</th><th class="num">现价</th><th class="num">ROE</th><th class="num">FCF/N</th><th class="num">52w动量</th><th class="num">评分</th><th>状态</th></tr>
    {pool_html}
  </table>
  <div class="note">本表<b>按模型评分从高到低完整列出本周全部合格候选（共 {len(pool)} 只）</b>。★建仓 = 本轮已选入实际建仓；其余为同批合格但受"单仓预算/整手"约束未入选的候选。颜色区分沪市/深市/北交所；{SCORE_LEGEND}。</div>
  {POOL_DIM_NOTE}
</div>

<div class="section">
  <h2>④ 为什么信这套？回测对比（全样本 1996+，周频）</h2>
  <div class="grid2">
    <div><div class="note" style="margin:0 0 6px">年化收益率</div>{svg_ann}</div>
    <div><div class="note" style="margin:0 0 6px">夏普比率</div>{svg_shp}</div>
  </div>
  <table style="margin-top:14px">
    <tr><th>方案</th><th class="num">年化</th><th class="num">夏普</th><th class="num">最大回撤</th><th class="num">空仓占比</th><th class="num">换手</th></tr>
    {bt_rows}
  </table>
  <div class="note">结论（基于本机最新同快照重算、<b>修复 B 段指数缺失/未成熟时退化为"无脑放行"的缺陷后</b>，1687 只含北交所、周线 1990+）：年化排序 current(上证)≈11.4% ≈ <b>B(分市场段, 修复后)≈10.8%</b> &gt; C(内生)9.2% &gt; A(全指)6.7% &gt; E(尾部)1.7%。修复前 B 因早期段指数缺失直接放行、回撤高达 -68%（与无 regime 的 C 同）；修复为"回退父指数(上证)门控"后，B 回撤收敛到 -56%、2014+ 年化从 0.6% 回升到 7.2%，长期表现已与上证单指数门控<b>基本持平</b>（残差来自深市个股改由深证成指而非上证门控——"更精细"但方向不必然更优）。由此确认 B 的"分市场段门控"原意图成立，<b>可作为 live 默认 gate</b>；E（尾部降仓）经多参数验证仍被否定（全样本 1.7%、2014+ -3.5%）。</div>
</div>

<div class="section">
  <h2>⑤ 策略长期净值曲线（全样本 1996+，对数轴）</h2>
  {nv_svg}
</div>

<div class="section">
  <h2>⑥ 观察池（质量过关但未触发买点，前 {len(watch)} 只）</h2>
  <table>
    <tr><th>代码</th><th>行业</th><th class="num">ROE</th><th>未入选原因</th></tr>
    {watch_html}
  </table>
  <div class="note">"未站线"=未站上 56 周均线；"段 regime DOWN"=所属板块指数在 56 周线下方；"动量负"=近 52 周收益为负。这些是有潜力、等信号回暖的备胎。</div>
</div>

<div class="section">
  <h2>⑦ 怎么用 / 风控规则</h2>
  <ul style="font-size:13px;color:#c9d3df;line-height:1.9;padding-left:18px">
    <li><b>仓位</b>：5 万元账户、目标 3–4 仓、暴露 0.9（即约 90% 资金可投）；单只按"价格×100 ≤ 单仓预算"取整手，预算不够则自动集中到更少仓位。</li>
    <li><b>买入条件</b>：基本面质量门（ROE≥10% & 自由现金流转正 & ≥3 年财报）+ 52 周动量为正 + 站上 56 周均线 + 所属板块指数站上 56 周均线（B 方案 gate）。</li>
    <li><b>双退出</b>（非价格止损）：① 估值泡沫信号；② 基本面恶化（ROE/FCF 转差）。亏损 -10% 不作为机械止损线。</li>
    <li><b>空仓规则</b>：任一关键段指数跌破 56 周均线即该段清仓；全盘普跌时整体空仓（回测空仓占比见上表）。</li>
    <li><b>刷新</b>：行情更新后运行 <code>python regime_layer2_backtest.py live B</code> 重新生成买仓清单。</li>
  </ul>
</div>

<footer>本报告仅供参考，不构成个人投资建议。数据来源：通达信本地 .day 行情、东方财富基本面数据、自研量化回测框架。模型历史表现不代表未来收益。</footer>
"""

html = ("<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>周频量化策略看盘面板 {signal}</title><style>" + CSS + "</style></head><body>"
        + body + "</body></html>")

out_name = f"dashboard_{signal}.html"
out = os.path.join(BASE, out_name)
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
# 删除旧的未带日期的 dashboard.html（若存在且不是刚写的），避免混淆
old = os.path.join(BASE, "dashboard.html")
if os.path.exists(old) and os.path.abspath(old) != os.path.abspath(out):
    try:
        os.remove(old)
    except OSError:
        pass
print("OK ->", out)
print("holdings:", len(holdings), "pool:", len(pool), "watch:", len(watch), "hold_total:", hold_total)

# -*- coding: utf-8 -*-
"""
股票搜索服务：基于 services/stock_list.py 本地全 A 股清单（5549+ 条，含拼音首字母）。
启动时后台预热，首屏同步可降级到 120+ 预置池。
"""
from services.stock_list import search as _list_search  # 全 A 股搜索（含拼音首字母）
# 沪深 300 + 创业板 + 科创板主要成分 + ETF（约 120 只）
_STOCK_POOL = [
    ("sh600519", "贵州茅台", "白酒"), ("sh600036", "招商银行", "银行"), ("sh601318", "中国平安", "保险"),
    ("sh601398", "工商银行", "银行"), ("sh601939", "建设银行", "银行"), ("sh600276", "恒瑞医药", "医药"),
    ("sh600887", "伊利股份", "消费"), ("sh600030", "中信证券", "券商"), ("sh601012", "隆基绿能", "光伏"),
    ("sh601166", "兴业银行", "银行"), ("sh600000", "浦发银行", "银行"), ("sh600028", "中国石化", "石化"),
    ("sh601288", "农业银行", "银行"), ("sh600585", "海螺水泥", "建材"), ("sh600690", "海尔智家", "家电"),
    ("sh601888", "中国中免", "消费"), ("sh603259", "药明康德", "医药"), ("sh600196", "复星医药", "医药"),
    ("sh601628", "中国人寿", "保险"), ("sh600104", "上汽集团", "汽车"), ("sh600050", "中国联通", "通信"),
    ("sh600837", "海通证券", "券商"), ("sh601138", "工业富联", "电子"), ("sh600111", "北方稀土", "稀土"),
    ("sh601995", "中金公司", "券商"), ("sh600048", "保利发展", "地产"), ("sh601066", "中信建投", "券商"),
    ("sh601633", "长城汽车", "汽车"), ("sh600438", "通威股份", "光伏"), ("sh601728", "中国电信", "通信"),
    ("sh601800", "中国交建", "基建"), ("sh601857", "中国石油", "石油"), ("sh600547", "山东黄金", "黄金"),
    ("sh600010", "包钢股份", "钢铁"), ("sh601668", "中国建筑", "基建"), ("sh600025", "华能水电", "电力"),
    ("sh600019", "宝钢股份", "钢铁"), ("sh601877", "正泰电器", "电气"), ("sh601658", "邮储银行", "银行"),
    ("sh600926", "杭州银行", "银行"), ("sh600029", "南方航空", "航空"), ("sh601111", "中国国航", "航空"),
    ("sh601169", "北京银行", "银行"), ("sh600795", "国电电力", "电力"),
    ("sz000858", "五粮液", "白酒"), ("sz000333", "美的集团", "家电"), ("sz000651", "格力电器", "家电"),
    ("sz000002", "万科A", "地产"), ("sz000725", "京东方A", "面板"), ("sz000063", "中兴通讯", "通信"),
    ("sz000568", "泸州老窖", "白酒"), ("sz000001", "平安银行", "银行"), ("sz000661", "长春高新", "医药"),
    ("sz000776", "广发证券", "券商"), ("sz002594", "比亚迪", "汽车"), ("sz300750", "宁德时代", "电池"),
    ("sz300059", "东方财富", "券商"), ("sz000625", "长安汽车", "汽车"), ("sz000538", "云南白药", "医药"),
    ("sz000963", "华东医药", "医药"), ("sz002415", "海康威视", "安防"), ("sz000166", "申万宏源", "券商"),
    ("sz000768", "中航西飞", "军工"), ("sz002714", "牧原股份", "养殖"), ("sz000876", "新希望", "养殖"),
    ("sz000895", "双汇发展", "消费"), ("sz000423", "东阿阿胶", "医药"), ("sz002230", "科大讯飞", "AI"),
    ("sz300760", "迈瑞医疗", "医药"), ("sz300015", "爱尔眼科", "医药"), ("sz002475", "立讯精密", "电子"),
    ("sz300124", "汇川技术", "电气"), ("sz002241", "歌尔股份", "电子"), ("sz000792", "盐湖股份", "化工"),
    ("sz300122", "智飞生物", "医药"), ("sz002460", "赣锋锂业", "锂电"), ("sz002371", "北方华创", "半导体"),
    ("sz300347", "泰格医药", "医药"), ("sz300142", "沃森生物", "医药"), ("sz002049", "紫光国微", "芯片"),
    ("sz300782", "卓胜微", "芯片"), ("sz002812", "恩捷股份", "锂电"), ("sz300316", "晶盛机电", "半导体"),
    ("sz300661", "圣邦股份", "芯片"), ("sz300496", "中科创达", "软件"), ("sz300454", "深信服", "软件"),
    ("sz300144", "宋城演艺", "旅游"), ("sz300033", "同花顺", "金融"), ("sz300628", "亿联网络", "通信"),
    ("sz002555", "三七互娱", "游戏"), ("sz300251", "光线传媒", "传媒"), ("sz002558", "巨人网络", "游戏"),
    ("sz300253", "卫宁健康", "医疗IT"), ("sz002410", "广联达", "软件"), ("sz002405", "四维图新", "地图"),
    ("sz300383", "光环新网", "IDC"), ("sz002335", "科华数据", "IDC"), ("sz300364", "中文在线", "传媒"),
    ("sh688981", "中芯国际", "芯片"), ("sh688012", "中微公司", "半导体"), ("sh688599", "天合光能", "光伏"),
    ("sh688111", "金山办公", "软件"), ("sh688256", "寒武纪", "AI芯片"), ("sh688271", "联影医疗", "医疗"),
    ("sh688005", "容百科技", "电池"), ("sh688009", "中国通号", "通信"), ("sh688036", "传音控股", "消费电子"),
    ("sh688008", "澜起科技", "芯片"), ("sh688082", "华熙生物", "医美"),
    ("sh510300", "沪深300ETF", "ETF"), ("sh510500", "中证500ETF", "ETF"), ("sh510050", "上证50ETF", "ETF"),
    ("sz159915", "创业板ETF", "ETF"), ("sh588000", "科创50ETF", "ETF"), ("sz159338", "中证A500ETF", "ETF"),
]

_HOT = [("sh600519", "贵州茅台", "白酒"), ("sz000858", "五粮液", "白酒"), ("sz000333", "美的集团", "家电"),
        ("sz300750", "宁德时代", "电池"), ("sh601318", "中国平安", "保险"), ("sz002594", "比亚迪", "汽车"),
        ("sh510300", "沪深300ETF", "ETF"), ("sh510500", "中证500ETF", "ETF"), ("sh510050", "上证50ETF", "ETF")]


def _cat_of(code: str) -> str:
    """由代码前缀推导市场/品种标签，统一搜索结果结构（避免前端渲染 undefined）。"""
    code = (code or "").lower()
    if code.startswith("bj"):
        return "北交"
    if code.startswith("sh"):
        return "沪基" if code[2] in ("5", "0", "4") else "沪A"
    if code.startswith("sz"):
        return "深基" if code[2] in ("1", "5", "6", "8") else "深A"
    return ""


def search_stocks(keyword: str, limit: int = 20) -> list:
    """全 A 股搜索：code / name / 拼音首字母。空关键词返回前 limit 条。
    返回结构统一含 code/name/cat/display，避免命中项缺 cat 字段。"""
    out = _list_search(keyword, limit)
    # 兜底：空关键词或本地未加载 → 用 _HOT
    if not out and not keyword.strip():
        return [{"code": c, "name": n, "cat": t, "display": f"{c.upper()} {n} · {t}"}
                for c, n, t in _HOT]
    return [{"code": r["code"], "name": r["name"], "cat": _cat_of(r["code"]),
             "display": f"{r['code'].upper()} {r['name']}"} for r in out]


def _guess_prefix(code6: str) -> str | None:
    """纯 6 位数字按首位猜市场前缀：0/3→sz, 6/9/5→sh, 4/8→bj, 其他→None。"""
    if not code6.isdigit() or len(code6) != 6:
        return None
    head = code6[0]
    if head in ("0", "3"):
        return "sz"
    if head in ("6", "9", "5"):
        return "sh"
    if head in ("4", "8"):
        return "bj"
    return None


def _probe_name(code: str):
    """轻量试探：从腾讯 qt.gtimg.cn 拉真实中文名（1.5s 超时，失败返回 None）。"""
    import requests
    try:
        r = requests.get(f"https://qt.gtimg.cn/q={code}",
                         headers={"Referer": "https://gu.qq.com/",
                                  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                         timeout=1.5)
        r.encoding = "gbk"
        body = r.text.strip()
        if "=" not in body:
            return None
        fields = body.split("=", 1)[1].strip('"').split("~")
        return fields[1] if len(fields) >= 2 else None
    except Exception:
        return None


def search_stocks_with_guess(keyword: str, limit: int = 20) -> list:
    """在 search_stocks 基础上，对纯数字关键词追加"前缀试探项"：同步探一次真实中文名。"""
    base = search_stocks(keyword, limit)
    if base:
        return base
    kw = keyword.strip().replace(" ", "")
    prefix = _guess_prefix(kw)
    if prefix:
        full = f"{prefix}{kw}"
        name = _probe_name(full) or "未确认"
        return [{"code": full, "name": name, "cat": "?",
                "display": f"{full.upper()} {name}" if name != "未确认" else f"{full.upper()} 未匹配，点击试探拉取报价"}]
    return []


# code → 中文名 快速映射（用于 watchlist 下拉显示）
_NAME_BY_CODE = {c: n for c, n, _ in _STOCK_POOL}
_NAME_BY_CODE.update({c: n for c, n, _ in _HOT})


def all_pool_items() -> list:
    """返回全部预置池 [(code, name), ...]（去重）；供 watchlist datalist 渲染"""
    out = []
    seen = set()
    for c, n, _ in _HOT:
        if c not in seen:
            out.append((c, n)); seen.add(c)
    for c, n, _ in _STOCK_POOL:
        if c not in seen:
            out.append((c, n)); seen.add(c)
    return out


def get_code_name(code: str) -> str:
    """从预置池查中文名；不在池返回原 code（前端降级显示）。"""
    return _NAME_BY_CODE.get(code, code)

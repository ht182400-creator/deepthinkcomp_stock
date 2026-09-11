# -*- coding: utf-8 -*-
"""
全局配置：数据源优先级链 / 超时 / 熔断 / 限流 / TTL / 路径
所有可调参数集中于此，改配置不改代码。
"""
import os

# ---------- 路径 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
KLINE_CACHE_DIR = os.path.join(DATA_DIR, "kline_cache")
SQLITE_PATH = os.path.join(DATA_DIR, "market.db")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

# 通达信本地数据根目录（历史日/周/月 K 权威源）
# 可用环境变量 TDX_ROOT 覆盖，方便换机器/部署（不再硬编码 Windows 绝对路径）
TDX_ROOT = os.environ.get("TDX_ROOT", r"D:\new_tdx64\vipdoc")

for _d in (DATA_DIR, LOG_DIR, KLINE_CACHE_DIR):
    os.makedirs(_d, exist_ok=True)

# ---------- HTTP ----------
HTTP_TIMEOUT = 5          # 单请求超时（s）
HTTP_TOTAL_TIMEOUT = 12   # 单标的整体拉取上限
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ---------- 数据源优先级链（with_fallback 依次尝试） ----------
# 报价/分时
QUOTE_SOURCES = ["tencent", "eastmoney"]
# 主力资金（东财内部多节点轮换）
FUND_HOSTS = ["push2.eastmoney.com", "push2delay.eastmoney.com"]
# 日/周/月 K：通达信本地 → npx
# 注：东财 K线 HTTP 接口不稳定（调研曾返回 null），暂未接入降级链；实现后加回 "eastmoney"
KLINE_DAY_SOURCES = ["tdx", "npx"]
# 分钟 K：通达信本地优先（全量历史，m5/m15/m30/m60 由 1 分钟线聚合）；无本地数据回退 npx（当日）
KLINE_MIN_SOURCES = ["tdx", "npx"]

# ---------- 稳定性 ----------
CIRCUIT_FAILS = 5        # 连续失败 N 次 → 熔断
CIRCUIT_RESET_S = 60     # 熔断恢复时间（s）
CIRCUIT_HALF_OPEN = 1    # 半开态放行请求数
RATE_LIMIT_EM = 2.0      # 东财限流（req/s）
RATE_LIMIT_TX = 5.0      # 腾讯限流（req/s）
RETRY_MAX = 3            # 重试次数
RETRY_BACKOFF = (1, 2, 4)  # 指数退避（s）

# ---------- 缓存 TTL（s） ----------
TTL_QUOTE = 10           # 报价
TTL_MINUTE = 30          # 分时
TTL_FUND = 60            # 主力资金
TTL_KLINE = 3600 * 24    # K线缓存
TTL_STATIC = 600         # 低频/静态数据（公司财务、股东、融资融券、龙虎榜等，10min）

# ---------- 并发 ----------
POOL_MAX_WORKERS = 8     # 批量聚合并发上限
MAX_CODES = 50           # /api/many 单次批量上限（防滥用/雪崩）

# ---------- 自选默认 ----------
DEFAULT_WATCHLIST = ["sh600519", "sz000858", "sz300750", "sh601318"]

# =====================================================================
# 数据面板（R1a / R1）
# 目的：把"价格 + 财务"落盘为"带版本的面板"，使回测可复现（docs/10 隐患 H1/H3/H13）
# =====================================================================

# ---------- 路径 ----------
PANEL_DIR = os.path.join(DATA_DIR, "panel")                       # 面板落盘目录
GPCW_DIR = os.path.join(TDX_ROOT, "cw")                           # 通达信财务数据目录
# 通达信**安装根目录**（TDX_ROOT 指向其中的 vipdoc 数据子目录）
# 行业分类等配置在根目录下：T0002/hq_cache/tdxhy.cfg、incon.dat
TDX_HOME = os.path.dirname(os.path.normpath(TDX_ROOT))
PRICE_PANEL_FILE = os.path.join(PANEL_DIR, "price_weekly.parquet")  # 前复权周线面板
FUND_PANEL_FILE = os.path.join(PANEL_DIR, "fund_history.parquet")   # 财务历史面板（回测）
FUND_LATEST_FILE = os.path.join(PANEL_DIR, "fund_latest.parquet")   # 财务最新快照（实盘）
FUND_DAILY_LATEST_FILE = os.path.join(PANEL_DIR, "fund_daily_latest.json")  # 实盘用轻量 JSON
FIELD_MAP_FILE = os.path.join(PANEL_DIR, "field_map.json")        # 字段映射（带版本）
PANEL_META_FILE = os.path.join(PANEL_DIR, "meta.json")            # 面板元信息
INDUSTRY_FILE = os.path.join(PANEL_DIR, "industry.json")          # 行业分类（东财批量）
INDUSTRY_LOCAL_FILE = os.path.join(PANEL_DIR, "industry_local.json")  # 行业分类（通达信本地，离线）
BACKTEST_YEARLY_FILE = os.path.join(DATA_DIR, "baseline_yearly.json")  # 分年收益归因（H-B 检验）
INDEX_MEMBERS_FILE = os.path.join(PANEL_DIR, "index_members.json")     # 指数成分（通达信本地，离线）
PORTFOLIO_STATE_FILE = os.path.join(DATA_DIR, "portfolio_state.json")  # 组合风控状态（峰值/回撤/暴露）
os.makedirs(PANEL_DIR, exist_ok=True)

# ---------- 行业分类获取（东财批量接口） ----------
# 背景：gpcw 585 列不含行业；通达信 incon.dat 只有行业名称树、无成分股；
#       fundamentals_broad.json 仅覆盖 1771 只。宇宙扩容到 5561 只后行业缺失，
#       会导致 is_financial 过滤与行业上限失效（金融股漏入候选池）。
# 方案：东财 clist 的 f100 字段一次返回全市场行业（约 5900 只 / 2 页）。
# ⚠️ 节点选择是关键：`push2` 常被限流并直接断连（Remote end closed without response），
#    项目既有 `services/stock_list.py` 一直使用 `push2delay` 且稳定可用 —— 故以它为主、push2 为备。
INDUSTRY_URLS = [
    "https://push2delay.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
]
INDUSTRY_URL = INDUSTRY_URLS[0]     # 兼容旧引用
INDUSTRY_PAGE_SIZE = 100        # 单页条数（东财 clist 上限 100，超过会返回空）
INDUSTRY_MAX_PAGES = 80         # 最大翻页数（约 5900 只 / 100 = 59 页）
# 与 services/stock_list.py 已验证可用的过滤串保持一致（含 t:13 / t:14 段）
INDUSTRY_FS = "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23,m:1+t:14"
INDUSTRY_TIMEOUT = 20           # 单请求超时（秒）
INDUSTRY_RETRY = 3              # 重试次数
INDUSTRY_BACKOFF = (1, 2, 4)    # 退避秒数

# ---------- 回测适配（R1 验证：旧引擎 vs 新面板） ----------
BACKTEST_BASELINE_FILE = os.path.join(DATA_DIR, "baseline_panel_compare.json")   # 对比结果

# ---------- 面板参数 ----------
GPCW_MIN_PERIOD = "20100101"    # 财务面板起始报告期（控制体积；更早数据质量差）
GPCW_PERIOD_SUFFIX = ("0331", "0630", "0930", "1231")   # 合法报告期后缀
MIN_FILL_RATE = 0.90            # 字段最低填充率，低于此值不纳入面板
FUND_STALE_PERIODS = 2          # 财报超期 N 期以上 → 标记 stale 并在评分中降权（docs/10 H4）
PRICE_MIN_BARS = 60             # 周线最少根数，不足则该股不入面板
PRICE_PANEL_FIELDS = ["open", "high", "low", "close", "volume", "amount"]

# 法定最晚披露日（用于判断"某报告期是否已过披露截止"，docs/10 H4）
FUND_DEADLINE = {"0331": 430, "0630": 831, "0930": 1031, "1231": 430}  # 月日；1231 指次年

# ---------- 财务字段映射 ----------
# key = 内部字段名（策略代码引用），value = gpcw 精确列名。
# ⚠️ 所有列名均已实测（gpcw20260630，填充率 ≥94%），列名改动必须同步 tests/test_panels.py。
FUND_FIELDS = {
    # ---- 每股指标 ----
    "EPS": "基本每股收益",
    "EPS_DEDUCT": "扣除非经常性损益每股收益",
    "BVPS": "每股净资产",
    "OCF_PS": "每股经营现金流量",
    "CF_PS": "每股现金流量净额(元)",
    # ---- 质量：盈利 ----
    "ROE": "净资产收益率",
    "ROE_WEIGHTED": "加权净资产收益率(每股指标)",
    "NP_PARENT": "归属于母公司所有者的净利润",
    "NP_DEDUCT": "扣除非经常性损益后的净利润",
    "GP_MARGIN": "销售毛利率(%)(非金融类指标)",
    "NP_MARGIN": "销售净利率(%)",
    "OP_MARGIN": "营业利润率(非金融类指标)",
    "EBITDA_MARGIN": "EBITDA/营业总收入(%)(非金融类指标)",
    # ---- 质量：现金流 ----
    "OCF": "经营活动产生的现金流量净额",
    "CAPEX": "购建固定资产、无形资产和其他长期资产支付的现金",
    "CASH_TO_REV": "营业收入现金含量(%)(非金融类指标)",
    "OCF_TO_NP": "经营活动现金净流量与净利润比率",
    "CASH_RECOVERY": "全部资产现金回收率",
    "OCF_TO_REV": "经营活动产生的现金流量净额/营业收入",
    "SALES_CASH_TO_REV": "销售商品提供劳务收到的现金/营业收入(%)",
    "OCF_TO_DEBT": "经营活动产生的现金流量净额/负债合计(%)(非金融类指标)",
    # ---- 安全 / 效率 ----
    "DEBT_RATIO": "资产负债率(%)",
    "EQUITY_MULT": "权益乘数(%)",
    "CURRENT_RATIO": "流动比率(非金融类指标)",
    "QUICK_RATIO": "速动比率(非金融类指标)",
    "AR_TURNOVER": "应收帐款周转率(非金融类指标)",
    "INV_TURNOVER": "存货周转率(非金融类指标)",
    "ASSET_TURNOVER": "总资产周转率(非金融类指标)",
    "FA_TURNOVER": "固定资产周转率(非金融类指标)",
    "CA_TURNOVER": "流动资产周转率(非金融类指标)",
    "EQUITY_TURNOVER": "股东权益周转率(非金融类指标)",
    "WC_TURNOVER": "运营资金周转率(非金融类指标)",
    # ---- 成长 ----
    "REV_YOY": "营业收入增长率(%)",
    "NP_YOY": "净利润增长率(%)",
    "EQUITY_YOY": "净资产增长率(%)",
    "ASSET_YOY": "总资产增长率(%)",
    "FA_YOY": "固定资产增长率(%)",
    "OP_YOY": "营业利润增长率(%)",
    "INVEST_YOY": "投资收益增长率(%)",
    "NP_DEDUCT_YOY": "扣非净利润同比(%)",
    "EPS_DEDUCT_YOY": "扣非每股收益同比(%)",
    # ---- TTM 口径（⚠️ 关键：质量门必须用 TTM，不得用"年初至今累计值"） ----
    # 季报的净利/现金流是"年初至今累计"，一季报仅为全年 1/4，
    # 直接用于 ROE≥10% 之类的门槛会在季报期误杀大批股票（实测均池 96→41）。
    "NP_TTM": "近一年归母净利润（万元）",
    "NP_DEDUCT_TTM": "近一年扣非净利润（万元）",
    "OCF_TTM": "近一年经营活动现金流净额",
    # ---- 资产负债（绝对量：旧引擎财务门需要 ta/tl/te，R6 规模维度也需要） ----
    "TOTAL_ASSETS": "资产总计",
    "TOTAL_LIAB": "负债合计",
    "TOTAL_EQUITY": "所有者权益（或股东权益）合计",
    "CA_TOTAL": "流动资产合计",
    "NCA_TOTAL": "非流动资产合计",
    "CL_TOTAL": "流动负债合计",
    "NCL_TOTAL": "非流动负债合计",
    "PAID_CAPITAL": "实收资本（或股本）",
    # ---- 规模 / 收入 ----
    "REV": "营业收入",
    "REV_TOTAL": "营业总收入(万元)",
    "REV_TTM": "营业总收入TTM(万元)",
    "REV_TTM_RECENT": "最近一年营业收入（万元）",
    "REV_Q": "营业总收入(单季度)(万元)",
    # ---- 股本 / 筹码 ----
    "TOTAL_SHARE": "总股本",
    "FLOAT_A": "已上市流通A股",
    "FREE_FLOAT": "自由流通股(股)",
    "HOLDERS": "股东人数(户)",
    # ---- 时点 ----
    "NOTICE_DATE": "财报公告日期",
}

# ---------- 交易成本（人工操作场景，docs/10 隐患 H9） ----------
SLIPPAGE = 0.002            # 滑点（人工下单，单边 0.2%）
COMMISSION_RATE = 0.00025   # 佣金费率（单边）
MIN_COMMISSION = 5.0        # 最低佣金（元）
STAMP_TAX = 0.0005          # 印花税（仅卖出）

# ---------- 组合约束（docs/10 隐患 H5/H11） ----------
MAX_PER_INDUSTRY = 2        # 单行业上限（软约束优先，此处为硬上限）
MAX_PER_BOARD = 2           # 单板块上限（硬）
INDUSTRY_PENALTY = 0.85     # 同行业重复入选时的分数惩罚系数（软约束）
MAX_TURNOVER_PER_WEEK = 0.5 # 单周换手上限（优先保留已有持仓）

# ---------- 风控（docs/10 隐患 H10） ----------
STOP_LOSS_HALF = -0.15      # 单票浮亏达此值 → 减半
STOP_LOSS_CLEAR = -0.25     # 单票浮亏达此值 → 清仓
TRAILING_STOP = -0.12       # 自持仓期最高点回撤达此值 → 触发
PORTFOLIO_DD_HALF = -0.15   # 组合自高点回撤达此值 → 暂停建仓/半仓
PORTFOLIO_DD_CLEAR = -0.25  # 组合自高点回撤达此值 → 清仓观察

# ---------- 策略健康度监控（docs/10 隐患 H12） ----------
HEALTH_IC_WINDOW = 26           # 滚动 IC 窗口（周）
HEALTH_IC_FLOOR = 0.01          # 滚动 IC 警戒下限
HEALTH_SHARPE_WINDOW = 52       # 滚动夏普窗口（周）
HEALTH_WINRATE_WINDOW = 30      # 买入后胜率统计笔数
HEALTH_WINRATE_FLOOR = 0.45     # 胜率警戒下限
HEALTH_POOL_FLOOR = 3           # 买池规模警戒下限（只）

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

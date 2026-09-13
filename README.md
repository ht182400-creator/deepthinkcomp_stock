# DeepThinkCompStock · 持仓管理 · 客户工具

一站式 A 股工具：策略持仓管理 + 推荐选股 + **个股详情（100% 移植 deepthinkSingle 完整前端）**。

## 快速开始

```bash
# 依赖（4.6.x 已含 fastapi/uvicorn）
python -m pip install -r requirements.txt

# 启动（默认 8899）
python -m uvicorn server:app --host 127.0.0.1 --port 8899

# 浏览器打开
http://127.0.0.1:8899/
```

## 页面结构

- **侧栏**：持仓录入 / 当前 / 预算（client 客户工具）
- **Tab 路由**：拆解卡 · 本周推荐 · 个股详情 · 历史回测 …
- **本周推荐 → 个股详情**：点击推荐行代码，`#/stock/<code>?from=rec` 进入完整个股详情

### 功能截图

**① 本周推荐**（Tab 3）：左侧客户信息 + 选股规则；右侧滚动收益排行榜，含评级（市值/估值/PEG）/ROE/扣非增速/资产负债率等关键指标，命中字段红色高亮。

![本周推荐](docs/screenshots/01-recommend-list.png)

**② 个股详情**（完整移植 deepthinkSingle）：左列分时 + 副图（VOLFS 成交量、资金博弈主力净额+散户黄线）+ 近 5 日主力净流入；中列深色盘口（5 档卖/大字现价 58.47/5 档买/ob-stats 8 行×2 列实时数据）+ 逐笔成交；右列 13 个 mp-section（行情/估值/财务/年度净利/主力多空/融资融券/股东户数/龙虎榜/北向资金/公司/盈利预测/最新公告）。

![个股详情](docs/screenshots/02-stock-detail.png)

**③ 历史回测**（Tab 4）：策略分区 5 段 + 实时净值曲线（含 50/150 日均线）+ 标准差/夏普/最大回撤 + 退换手/当前仓位/成交股票数 + 同期上证指数对照图。

![历史回测](docs/screenshots/03-backtest.png)

**④ HTML 报告**：策略分组 + 净值/胜率柱状图 + 板块配比横向柱图 + 五只重点持仓股票详情表（代码/名称/板块/现价/涨跌/量比/扣非增速/ROE/资产负债率/PE/换手率/市场容量）+ 综合 KPI 解释与策略结论。

![HTML 报告](docs/screenshots/04-html-report.png)

## 个股详情（deepthinkSingle 1:1 完整移植）

`static/js/modules/stock.js` 是薄壳：渲染 `single-template.js` 的完整 DOM，由 `single-app.js`（原 deepthinkSingle app.js）驱动。功能清单见 `docs/05-接口规范.md §6.4`，包括：

- 顶部状态栏 + 自选管理 + 搜索联想 + +/- 自选
- 分钟视图：分时 + 可配置副图（最多 5 个）、盘口（5档+大字现价+ob-stats 8行×2列）、逐笔成交（↑/↓ 切换）
- K线视图：7 周期（日/周/月/60/30/15/5）+ MA5/10/20 + 成交量 + dataZoom + K线副图（MACD/KDJ/BOLL/RSI）
- 历史分时小图（双击 K 线 / Enter）、分钟资金流明细、复盘记录、副图配置、右键菜单、导出 CSV、公告 modal
- 30s 自动刷新；A股红涨绿跌

### 财务分析（个股）· 本地量价指标

个股详情页「财务分析」第 10 个标签 **本地量价**，基于本地周线价量数据（`panels/volume_price.py` → `/api/stock/finance_full` → `panels/fund_local.py`）：

- **经典量价图**：上方收盘价折线 + 下方成交量(亿股)柱，双 grid 共享 X 轴联动
- **量价形态判读**：量价齐升 / 价升量缩 / 放量下跌 / 量价背离 等，并给出「最新判读」结论横幅
- **指标卡片**：放量倍数、量能趋势、量价背离、成交额、周涨跌幅等
- 数据源零网络依赖（本地通达信周线），详见 `static/js/modules/single-finance.js` 与 `docs/05-接口规范.md`

## 数据源（四级免费降级）

腾讯行情 → 东方财富（资金/基本面）→ 通达信本地 → npx 兜底。含熔断/限流/退避/缓存。

## 后端 API（与 deepthinkSingle 契约一致）

`/api/quote`（聚合）、`/api/kline`、`/api/minute`、`/api/watchlist`、`/api/many`、`/api/search`、`/api/announcement`、`/api/analysis`（复盘）、`/api/stock/full`、`/api/stock/north`、`/api/stock/kline` 等。详见 `docs/05-接口规范.md`。

## 测试

```bash
# 前端 63 用例（5 个文件，node:test + jsdom）
npm run test:frontend

# 后端 258 用例
python -m unittest discover tests -p "test_*.py"
```

## 文档

`docs/`：01-PRD / 02-架构设计 / 03-UI设计规范 / 04-测试方案 / 05-接口规范 / 06-项目计划 / 07-决策问答记录 / **08-策略与架构评审报告** / **09-改造实施方案** / **10-改造方案自审与优化建议** / **11-组合风控实盘落地指南** / **12-开发问题FAQ**
`docs/screenshots/`：4 张功能截图（推荐/个股详情/历史回测/HTML 报告）

> **08-策略与架构评审报告**（v2.0）：策略引擎与架构全面评审。含瓶颈诊断（质量因子滞后 16 个月 / 回撤 -56% / 实盘无行业上限 / 回测与实盘口径不一致）、评分体系升级方案、**数据源实测结论**、模型选型矩阵与常见疑问答疑（为何不建议 LSTM/Transformer/RL/因子挖掘、GBDT 含义、退市股数据意义）。**新开发展请先读此文。**
>
> **09-改造实施方案**（v1.8）：基于 08 的可执行计划。含改造范围（R0~R12）、优先级矩阵、进度表与里程碑、验收门禁（DoD）、风险与回退、**明确不做清单**。
>
> **10-改造方案自审与优化建议**（**v1.8**）：对 09 的**批判性自审 + 全部验证实验结果**。核心结论：
> **① 原回测基线 12.73% 因"指数成分前视偏差"作废**（含前视 14.59% vs 无前视 **8.30%**，偏差 **6.3pp**）；
> ② 新基线 **`R300_dyn`**（半年度滚动定池，无前视）= 年化 **8.30%** / 夏普 0.287 / 回撤 **-51.83%** / Calmar 0.16；
> ③ **单票止损与均线择时双双无效**，**组合回撤 -15% 降半有效**（回撤 → **-35.29%**，Calmar +16%）。
> **做任何回测或改造前必读。**
>
> **11-组合风控实盘落地指南**（v1.0）：把 10 的 §6.12 结论落成**可执行操作规程**。含规则精确表述、数据准备、**每周 5 步操作**、减半的执行示例（含整手取整）、注意事项与局限、分档降仓预留方案。工具：`python -m panels.portfolio_guard`。

**项目定位**：面向 **10~15 万本金 · 人工下单 · 持仓 2~4 只 · 单人维护** 的场景。系统定位是**初筛器**（1689 → 7 只），由人做终审（7 → 2~4 只）；不追求全自动量化建模。

## 排错 / 运维

- **外部行情（腾讯/东财）报 `Could not find a suitable TLS CA certificate bundle, invalid path: ...certifi\cacert.pem`**
  根因：托管解释器 `versions\3.13.12` 的 site-packages 被运行时清理、certifi 被删；若服务是清理前启动的旧进程，会缓存失效的 CA 路径，导致外部 HTTPS 抓取失败（本地接口不受影响）。
  修复：双击 **`check_env.bat`** 自检并补装依赖（`pip install -r requirements.txt`），随后**手动重启服务**（`server.py` 无 auto-reload）：结束占用 8899 的进程后 `python server.py --port 8899`。重启后 `certifi.where()` 指向真实存在的 `cacert.pem`，外部抓取即恢复。
- **启动报 `ModuleNotFoundError: No module named 'fastapi'` 等**
  同样跑 `check_env.bat` 补装依赖即可；或重跑 `start.bat`（其依赖检查会自动 `pip install`）。
- 服务无热重载，改 `server.py` / `sources/*.py` 后必须重启。

---

## 版本与发布

- 当前版本：**v0.5.0**（应用内版本号见 `static/index.html`，形如 `V0.5.0 · 2026-09-13`）
- 发布标签：`v0.5.0`
- 本次更新：
  - 分时均价归一化收口到 service 层唯一入口（`services/quote_service.normalize_minute_avg`），修复 `/api/quote` 漏归一化导致单股页分时图均价小 100 倍（详见 `docs/12-开发问题FAQ.md` Q9）
  - 策略报告 ③ 明示各市场段 56 周均线状态、合格池板块分布与板块约束；候选集中于单一板块时给橙色警示（Q8）
  - 合格池「评分」列按分数同批相对渐变着色（越高越红）
  - 顺带修复：★建仓 脱出表格、命令行清单输出路径错（写 `data/`）、B 方案顶部"市场状态"误显示"全部上涨"
- 双远程同步：`github`（git@github.com:ht182400-creator/deepthinkcomp_stock.git）与 `forgejo`（本地 http://localhost:3000）

> 本工具仅供研究参考，不构成个人投资建议。

# DeepThinkCompStock · 产品需求文档（PRD）

| 字段 | 值 |
|------|---|
| 文档版本 | v2.0（评审后修订） |
| 编写日期 | 2026-08-16 |
| 文档状态 | **待评审** |
| 项目代号 | **deepthinkcomp_stock** |
| 项目路径 | `E:\AI_Studio\deepthinkcomp_stock` |
| 上游系统 | `deepthinkstock`（周频量化+持仓管理）<br/>`deepthinkSingle`（个股主力追踪，Sprint 1-4 已交付，132+15 测试） |
| 需求方法 | EARS（Easy Approach to Requirements Syntax） |

---

## 〇、核心决策（评审决议记录）

| # | 决策点 | 决议 | 依据 |
|---|--------|------|------|
| D1 | **项目命名** | `deepthinkcomp_stock` | 用户指定 |
| D2 | **行情数据源主链** | **腾讯→东财→通达信本地→npx 免费四级链**（沿用 deepthinkSingle） | **通达信官方 MCP 为积分制收费**（新用户仅送 1 万积分≈1 个月，之后按量购买）；用户要求"收费则以 deepthinkSingle 方式为主，其他为备选" |
| D3 | 通达信 MCP 角色 | **最后备选**（第 5 级，默认关闭；仅在 1 万积分耗尽前的必要时刻、且免费四级链全挂时启用） | 用户确认：积分仅 1 万，作最后兜底 |
| D4 | 前端技术栈 | **原生 ES Modules + ECharts + Chart.js**（无构建链）——**已定案** | 用户确认采纳推荐方案；deepthinkSingle 已验证（128 测试通过） |
| D5 | 本期范围 | 全量：策略+持仓+推荐+个股详情(8卡)+回测+报告+日志 | 用户未要求裁剪 |
| D6 | 行情刷新频率 | 价格/盘口 5s；资金/订单流 10s；财务 10min 缓存；新闻 30min | 折中实时与限流风险 |
| D7 | 个股详情页范围 | **8 卡片全量**（行情概况/分时/盘口/VOLFS/主力资金/资金博弈/财务/股东+新闻） | deepthinkSingle 8 卡全部已验证可用，迁移成本≈0；真正新增仅"跳转衔接" |

---

## 一、项目概述

### 1.1 背景
用户日常操作涉及两个独立工具：
- **deepthinkstock**：**决策层**——周频量化策略、持仓录入、自动调仓、回测报告（`localhost:8899`）
- **deepthinkSingle**：**行情层**——单股分时/VOLFS/主力资金/资金博弈/盘口/K线（`localhost:5000`，Sprint 1-4 已完成）

**核心痛点**：在"看策略 → 决定买 → 看行情 → 下单"的完整链路中，两个系统互相割裂——**无法从"本周最值得买入"一键跳到该股实时行情**，而这个衔接正是真实交易决策的命门。

### 1.2 目标
在 `E:\AI_Studio\deepthinkcomp_stock` 构建一站式平台：
1. 策略决策（质量+动量+Regime 门控，来自 deepthinkstock）
2. 持仓管理（录入/分析/调仓）
3. **个股行情详情（继承 deepthinkSingle 全部能力）**
4. **核心衔接：持仓/推荐代码点击 → 一键跳转个股详情**

### 1.3 非目标（本期）
- 不做真实下单（仅"建议买入"标记）
- 不做多用户/多账户/登录
- 不做移动端 APP（仅响应式 Web）
- 不做 Level-2 逐笔推送（订单流用腾讯/东财公开数据近似）

---

## 二、用户角色

| 角色 | 描述 | 诉求 |
|------|------|------|
| **本人（持仓决策者）** | 唯一用户，A 股个人投资者 | 一站式完成"选股→持仓→看行情→下单" |

---

## 三、功能需求（EARS 格式）

### 3.1 Ubiquitous（系统始终满足）

- **R-U1** The system shall 提供单页 Web 界面，包含 8 个主 Tab（持仓操作卡/本周推荐/个股详情/自动调仓/历史回测/HTML报告/MD报告/日志）。
- **R-U2** The system shall 以**免费四级数据链**获取行情：腾讯（首选）→ 东财（兜底）→ 通达信本地 .day（历史 K）→ npx westock（离线补全）。
- **R-U3** The system shall 在任一 Tab 的股票代码单元格渲染为可点击链接，点击跳转到该股详情页。
- **R-U4** The system shall 将所有运行日志写入 `web/data/logs/analyze.log`（UTF-8，带 `[时间] 级别 消息` 格式）。
- **R-U5** The system shall 在页面顶部固定显示免责声明："仅供研究参考，不构成投资建议"。

### 3.2 Event-driven（事件驱动）

- **R-E1** When 用户点击"本周推荐"或"持仓操作卡"中的股票代码，then the system shall 切换 hash 路由到 `#/stock/<code>` 并渲染个股详情页。
- **R-E2** When 个股详情页加载完成，then the system shall 并发拉取 8 类数据（行情概况/分时/盘口/订单流/资金博弈/财务/股东/新闻）并渲染卡片。
- **R-E3** When 用户在个股详情页点击"← 返回"，then the system shall 根据 URL `?from=` 参数回到来源 Tab。
- **R-E4** When 用户点击"保存并分析"，then the system shall 后台线程运行策略分析（≤5 分钟）并推送进度（SSE）。
- **R-E5** When 分析完成，then the system shall 自动落盘 `live_buy_list_<信号日>.txt` 并生成 `dashboard_<信号日>.html`。
- **R-E6** When 用户修改持仓/设置，then the system shall 原子写 JSON（先写 .tmp 再 rename）并立即反馈。

### 3.3 State-driven（状态驱动）

- **R-S1** While 个股详情页处于打开状态，the system shall 每 5 秒刷新价格/盘口，每 10 秒刷新资金/订单流。
- **R-S2** While 非交易时段，the system shall 展示最近收盘数据并标注"休市中"。
- **R-S3** While 请求日/周/月 K 线，the system shall 优先从通达信本地 .day 读取（0.01s），无数据时降级 npx。
- **R-S4** While 请求分钟 K 线，the system shall 优先读取本地 JSON 缓存（24h），未命中时 npx 拉取并写缓存。
- **R-S5** While analyze 后台任务运行中，the system shall 拒绝重复提交并提示"任务进行中"。

### 3.4 Unwanted（异常处理）

- **R-U6** If 腾讯数据源失败，then the system shall 自动降级东财并记录日志，不中断页面。
- **R-U7** If 某数据源连续失败 ≥5 次，then the system shall 熔断该源 60s（直接走备用源），半开后试探恢复。
- **R-U8** If 返回数据为空/格式异常，then the system shall 显示"数据获取失败"占位并保留上次数据。
- **R-U9** If 东财被限流（4xx/5xx/超时），then the system shall 切换 push2delay 节点并指数退避重试（1s/2s/4s，最多 3 次）。
- **R-U10** If 通达信本地 .day 缺失/损坏，then the system shall 静默降级 npx/东财，不影响页面。
- **R-U11** If 前端图表渲染异常，then the system shall try/catch 隔离并显示占位，不影响其他面板。
- **R-U12** If analyze 后台任务异常，then the system shall 记录 ERROR 级日志并在 UI 明示（不静默失败）。

### 3.5 Optional（可选）

- **R-O1** Where 用户已连接通达信 MCP，the system shall 提供"MCP 实时行情"开关作为第 5 级数据源（默认关闭）。
- **R-O2** Where 需要，the system shall 提供近 5 日主力净流入柱状对比（f178）。
- **R-O3** Where 需要，the system shall 导出分时/资金/K 线为 CSV。

---

## 四、功能模块分解

### 模块 A：周频策略（来自 deepthinkstock）

| 编号 | 需求 | 对应代码/文件 |
|------|------|--------------|
| A1 | 实时买仓清单（4 只⭐精选 + 12 只📋更多候选） | `modules/strategy/candidates.py` |
| A2 | 持仓管理（录入/删除/金额/定投） | `modules/holdings/store.py` |
| A3 | 持仓操作卡（评分/建议/本周操作/说明） | `modules/holdings/cards.py` |
| A4 | 本周推荐（selected 置顶 + 超预算标注） | `modules/holdings/recommend.py` |
| A5 | 历史回测对比（5 方案×2 窗口+净值曲线） | `modules/strategy/backtest.py` |
| A6 | 自动调仓记录 + HTML/MD 报告 + 日志 | `modules/analysis/report.py` |
| A7 | **代码列可点击 → 跳转个股详情（核心新增）** | 前端 `router.js` + `modules/recommend.js` |

### 模块 B：标的池与基本面（来自 deepthinkstock）

| 编号 | 需求 |
|------|------|
| B1 | 1771 只沪深+北交所标的池（代码/名称/行业/市场），分类筛选+搜索 |
| B2 | 质量门：ROE≥10% + FCF/N>0 + ≥3年财报 |
| B3 | 基本面季度刷新（东财 DMSK 三表） |

### 模块 C：个股行情详情（**继承 deepthinkSingle**）

| 编号 | 需求 | 数据源（免费链） |
|------|------|-----------------|
| C1 | 行情概况（现价/涨跌/换手/PE/PB/市值/量比等 16+ 指标） | 腾讯 qt.gtimg.cn → 东财 |
| C2 | 五档盘口（买1-5/卖1-5/委比/量比） | 腾讯 → 东财 |
| C3 | 分时走势（现价白线+均价黄线，240 根分钟线） | 腾讯 ifzq → 东财 trends2 |
| C4 | VOLFS 成交量（每分钟柱，红涨绿跌） | 腾讯 → 东财 |
| C5 | 主力资金追踪（主力净流入累计曲线） | 东财 push2 → push2delay |
| C6 | 资金博弈副图（主力/散户/大单/特大单） | 东财 → 计算 |
| C7 | 订单流（逐笔成交近似） | 腾讯 → 新浪 |
| C8 | 财务摘要（5 年营收/净利/ROE/负债） | 东财 datacenter-web |
| C9 | 股东户数/户均持股 | 东财 emweb f10 |
| C10 | 新闻/公告（最近 10 条） | 东财公告接口 |
| C11 | 历史 K 线（日/周/月/60/30/15/5 分，MA+VOL） | 通达信本地 .day/.lc1 → npx → 东财 |
| C12 | 股票搜索（全 A 股 5549+，代码/名称/拼音模糊） | 本地 JSON + 东财 clist |

### 模块 D：导航与全局（整合新增）

| 编号 | 需求 |
|------|------|
| D1 | 8 个主 Tab + hash 路由（`#/stock/<code>`） |
| D2 | 顶部 fixed header（标题/版本/时钟/环境信息） |
| D3 | 工具栏（强制刷新/自动跟踪/保存并分析/进度条） |
| D4 | 浅色主题 + 响应式（≥1024px 双栏，<1024px 单栏） |
| D5 | 免责声明横幅 + 版本徽章 |

---

## 五、非功能需求（NFR）

### 5.1 性能
| 编号 | 指标 | 目标 |
|------|------|------|
| NFR-P1 | 首屏加载 | < 1.5s（localhost，无外部 CDN 阻塞） |
| NFR-P2 | 表格渲染（1000 行） | < 500ms |
| NFR-P3 | 个股详情 8 卡片 | 并发加载 < 3s |
| NFR-P4 | analyze 后台任务 | ≤ 5 分钟 |
| NFR-P5 | 单次行情请求 P95 | ≤ 500ms（本地 K 线 ≤100ms） |

### 5.2 可靠性
| 编号 | 指标 | 目标 |
|------|------|------|
| NFR-R1 | 页面可用性（数据源正常） | ≥ 99.5% |
| NFR-R2 | 双源全挂 | 显示最近缓存 + "数据源异常"提示，不崩溃 |
| NFR-R3 | 主源恢复后自动切回 | ≤ 60s |
| NFR-R4 | 配置/持仓 JSON 原子写 | 100% |

### 5.3 可维护性
| 编号 | 指标 | 目标 |
|------|------|------|
| NFR-M1 | 后端 API | /docs 自动生成 Swagger |
| NFR-M2 | 代码注释 | 关键函数中文注释 + docstring |
| NFR-M3 | 前端模块化 | 按 Tab 分文件（holdings/cards/recommend/stock/bt/html/md/log/router） |
| NFR-M4 | 日志级别 | INFO/WARN/ERROR/SUCCESS 四档 |

### 5.4 安全
| 编号 | 指标 | 目标 |
|------|------|------|
| NFR-S1 | 外部请求 | 仅 HTTPS，全部接口走 UA 伪装 |
| NFR-S2 | 仓库安全 | 不提交任何 token/key（.gitignore 排除） |
| NFR-S3 | XSS | 前端所有用户输入 escapeHtml |

### 5.5 可移植性
| 编号 | 指标 | 目标 |
|------|------|------|
| NFR-X1 | 通达信路径 | `TDX_ROOT` 环境变量可覆盖（默认 `D:\new_tdx64\vipdoc`） |
| NFR-X2 | 单入口 | `web/start.bat`（先杀旧进程再启动） |
| NFR-X3 | 依赖最少 | requirements.txt 仅 FastAPI/uvicorn + 必要库 |

---

## 六、验收标准

### 6.1 功能验收
- ✅ 录入持仓 → 保存并分析 → 持仓卡/本周推荐/自动调仓记录 全部真实数据
- ✅ **本周推荐/持仓卡代码点击 → 跳转个股详情 → 8 卡片全部渲染**
- ✅ 个股详情"← 返回"回到来源 Tab
- ✅ analyze 完成后自动落盘 txt + html
- ✅ 行情四级降级：断网腾讯 → 东财正常；断网东财 → 通达信本地 K 线仍可看

### 6.2 质量验收
- ✅ 后端 `python -m py_compile` 全过
- ✅ 前端 `node --check` 全过（每次改完必验）
- ✅ 后端单测 ≥ 100 例（继承 deepthinkSingle 132 例的 core/sources/services 部分）
- ✅ 前端 `node --test` ≥ 15 例（指标算法 + DOM 冒烟）
- ✅ analyze 异常有 ERROR 级日志 + UI 明示

### 6.3 性能验收
- ✅ 800 只持仓 × 4 周 → analyze < 5 分钟
- ✅ 个股详情 8 卡片 < 3s 全部展示

---

## 七、风险与对策

| 风险 | 等级 | 对策 |
|------|------|------|
| 东财接口限流/封 IP | 高 | 多节点轮换 + 令牌桶（2 req/s）+ 指数退避 + 熔断（deepthinkSingle 已验证） |
| 通达信官方 MCP 收费 | 中 | **默认不用 MCP**；免费四级链为主；MCP 作可选第 5 级（用户已有积分才开） |
| 腾讯接口字段变动 | 中 | 字段映射集中封装 + 单测守护（deepthinkSingle 已有 10 类修复经验） |
| 浏览器缓存旧 JS | 低 | Ctrl+F5 提示 + 生产环境文件名加 hash |
| daily_broad.json 133MB | 低 | .gitignore 排除 + README 说明 |
| 实盘风险 | 中 | 所有页面顶部 Disclaimer |

---

## 八、项目目录（计划）

```
E:\AI_Studio\deepthinkcomp_stock\
├── docs/                        # 文档（项目审批）
│   ├── 01-需求文档(PRD).md      # 本文档
│   ├── 02-架构设计.md
│   ├── 03-UI设计规范.md
│   ├── 04-测试方案.md
│   ├── 05-接口规范.md
│   └── 06-项目计划(PM).md
├── server.py                    # FastAPI 主入口
├── config.py                    # 数据源链/熔断/限流/TTL/路径
├── start.bat                    # 一键启动
├── requirements.txt
├── core/                        # 稳定性核心（来自 deepthinkSingle）
│   ├── circuit_breaker.py
│   ├── rate_limiter.py
│   ├── fallback.py
│   └── cache.py
├── sources/                     # 数据源适配器（来自 deepthinkSingle）
│   ├── tencent.py / eastmoney.py / tdx.py / npx.py / company.py
├── services/                    # 服务层
├── modules/                     # 业务模块
│   ├── strategy/                # 策略内核（来自 deepthinkstock）
│   ├── holdings/                # 持仓管理
│   ├── analysis/                # 分析管线
│   └── market/                  # 行情聚合（组合 sources）
├── static/
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js               # 主入口
│       ├── modules/             # 按 Tab 分模块
│       │   ├── holdings.js / cards.js / recommend.js / stock.js
│       │   ├── bt.js / html.js / md.js / log.js / router.js
│       └── charts/              # ECharts 封装（来自 deepthinkSingle）
├── data/                        # 运行时数据（不提交）
└── tests/                       # 单元 + 集成 + 前端测试
```

---

## 九、开发阶段（待审批后启动）

| 阶段 | 内容 | 交付物 | 估时 |
|------|------|--------|------|
| **P0 文档阶段** | PRD/架构/UI/测试/接口/计划 | docs/01-06 | 2 天 |
| **P1 骨架阶段** | 项目初始化 + 数据源层（sources+core）迁移 | 可跑通行情四级降级 | 3 天 |
| **P2 策略整合** | 策略+持仓+分析模块迁入 + 单页路由 | 持仓/推荐/回测可用 | 3 天 |
| **P3 详情集成** | 个股详情页（8 卡片 + 跳转衔接） | 核心目标达成 | 4 天 |
| **P4 打磨阶段** | 主题/响应式/性能/SSE | 验收标准 | 2 天 |
| **P5 测试发布** | 全量测试 + 上线文档 + README | 测试报告 + 发布 | 2 天 |

**总估时：约 16 个工作日**（P1 可复用 deepthinkSingle 已验证代码，实际更快）

---

## 十、评审意见（专家团队）

### 项目经理（PM）意见
- 阶段划分合理，P1 复用 deepthinkSingle 已验证代码（132+15 测试）可显著压缩风险
- **建议**：P2 与 P3 并行风险低，可合并里程碑 M2（策略+详情一体）验收
- 风险预案充分；唯一需用户确认的是行情刷新频率（D6 已折中 5s/10s）

### 评审专家意见
- 需求用 EARS 格式清晰；R-U1~R-U12 覆盖主要异常路径
- **一处需澄清**：C7"订单流"用腾讯/新浪公开数据是**近似逐笔**（非 Level-2 真实逐笔），已在非目标声明，符合实际
- 验收标准 6.2 前端测试 15 例需在 P3 完成时翻倍（详情页交互）

---

## 十一、待用户确认（本轮）

1. ✅ 命名 `deepthinkcomp_stock`（已确认）
2. ✅ 行情免费链为主、**MCP 作最后备选**（已确认，仅 1 万积分）
3. ✅ 前端 **原生 JS + ECharts**（已确认，采纳推荐方案）
4. ⏳ **个股详情页范围**：**推荐 8 卡片全量**（deepthinkSingle 已验证、迁移≈0）；若只要"概况+分时+盘口"3 卡请明示
5. ✅ 行情刷新频率 5s/10s（已确认无异议）

---

*本 PRD 基于 deepthinkstock（策略/持仓）与 deepthinkSingle（行情/稳定性）两个已交付系统的实测能力编写，无编造功能。数据源决策依据公开信息：通达信官方 MCP 为积分制收费。*
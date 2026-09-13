# 12 · 开发问题 FAQ

> 记录开发/使用过程中**已定位并修复**的问题（现象 → 根因 → 修复 → 验证），供后续排查复用。
> 新增条目请追加在文末，保持"编号 + 标题"格式；本文件超过 4000 行时另起 `13-开发问题FAQ_更新02.md`。

## 锚点
- [Q1 蓝特光电为何同时出现在「退出建仓」与「合格买仓池」？](#q1)
- [Q2 ② 显示"本周 75 只"、③ 却只有 8 只，哪个对？](#q2)
- [Q3 报告 ①「实际建仓清单」与我的「当前持仓」对不上](#q3)
- [Q4 从「财务分析」切回 K线/分时 后图表被压缩](#q4)
- [Q5 财务分析里的数据为什么有白的、有红的、有绿的？](#q5)
- [Q6 「资产负债」能不能看同期对比（负债变化 / 偿债恢复能力）？](#q6)
- [Q7 分时图均价显示成 2.17（现价 219）、涨跌幅一长串小数](#q7)
- [Q8 合格买仓池为什么全是沪市（科创板）？不是"同一市场最多 2 只"吗？](#q8)
- [Q9 分时图涨跌幅对了，但均价还是不对（均价 1.77 / 现价 176.31）](#q9)

---

<a id="q1"></a>
## Q1 蓝特光电（688127）为何同时出现在「退出建仓」和「合格买仓池（★建仓）」？

**现象**：报告 ②「退出建仓」列出 688127；同时 ③「合格买仓池」里 688127 带 ★建仓 标记。

**根因（数据不同源）**：报告 ①②③ 由不同数据文件驱动——
- ①③ 读最新的 `data/live_buy_list_<信号日>.txt`（当周）；
- ② 读 `data/live_compare.json`（本周 vs 上周对比）。

Web 端 [保存并分析] 只写 txt 并重建 HTML，**从不刷新 `live_compare.json`**；该文件只在命令行 `python live_compare.py` 时才更新。本次 `live_compare.json` 停留在 **20260828**，而 txt 是 **20260911** → ② 用的是 8 月的对比：8/21→8/28 那周 688127 确实"退出建仓"，但 9/11 它已重新入选 ★建仓。两段来自不同周，才显得自相矛盾。

**修复**：
1. `modules/strategy/live_compare.py` 抽出 `write_compare(cur, ...)`：复用已算好的本周结果、仅重算上周，写 `live_compare.json`。
2. `modules/analysis/analysis.py` 的 `_persist_dashboard` 写完 txt 后调用 `write_compare(res)`，保证 **txt 与对比同源**。
3. `modules/strategy/build_dashboard.py` 的 `diff_section()` 增加**同源校验**：对比信号日 ≠ 本周 txt 信号日时，隐藏 ② 并提示"对比数据滞后"，杜绝张冠李戴。

**验证**：`tests/test_strategy.py::TestLiveCompare`；另将 `dashboard_20260911.html` 重新生成，② 正确显示"对比数据滞后（20260828 ≠ 20260911）"。下次 [保存并分析] 后 ② 即恢复为本周对比。

---

<a id="q2"></a>
## Q2 ② 显示"合格买仓池 上周 76 → 本周 75"，而 ③ 只有 8 只，哪个对？

**根因**：同上，"75" 来自**过期的** `live_compare.json`（20260828 的池规模），并非本周。经核对各周 txt：
`20260814=75 只 / 20260828=75 只 / 20260904=7 只 / 20260910=8 只 / 20260911=8 只`。
9 月初池规模从 75 骤降到 7~8，是段 regime 判定变化所致。**本周（20260911）真实池规模 = 8 只**。

**修复**：`format_live_report` 的合格池输出去掉 `[:30]` 截断，**全量按评分降序**列出；看板 ③ 标题与说明标注"按评分降序全量（共 N 只）"。

**验证**：`tests/test_strategy.py::TestLiveReport`（35 只候选全部出现 + 评分降序）。

---

<a id="q3"></a>
## Q3 报告 ①「实际建仓清单」显示 4 只，但我的「当前持仓」是空的，怎么对不上？

**根因**：原 ① 展示的是**模型建仓建议**（`live_buy_list` 的"实际建仓"段），与用户在左侧「当前持仓」录入的真实持仓（`data/holdings.json`）是两回事，空持仓时自然"对不上"。

**修复（按用户选择：① 跟随真实持仓）**：
- `modules/strategy/build_dashboard.py`：① 改为读取 `data/holdings.json` 渲染"我的实际持仓"，空则显示"暂无持仓"；末列「本周信号」用模型名单标注（★本轮建仓 / 合格池 / 观察：原因 / 未在模型名单）。
- `modules/holdings/holdings.py` 新增 `clear_holdings()`；`server.py` 新增 `POST /api/holdings/clear`，并在持仓增/删/清空后调用 `_rebuild_dashboard()` 重建看板。
- 前端 `static/index.html` 左侧新增「清空全部持仓」按钮；`static/js/app.js` 新增 `clearAllHoldings()`，并在持仓变更后刷新报告 iframe。

**验证**：`tests/test_strategy.py::TestHoldings.test_clear_holdings`；`tests/frontend/sidebar.test.js` 3 个清空用例；临时写入样例持仓重建报告，① 正确显示 呈和科技/蓝特光学（★本轮建仓）与 贵州茅台（未在模型名单）。

---

<a id="q4"></a>
## Q4 从「财务分析」切回 K线/分时 后，图表被压缩成一条

**现象**：进入个股详情的「财务」视图后，点「返回图表」或顶栏「K线」，回来看分时/K线图被压扁（X 轴挤在左侧、刻度重叠）。

**根因**：`stock.js` 的 `openFinance()` 把 `minuteView / klineView / watchlistView` 加了 `.hidden`（display:none），但 `closeFinance()` 只把视图重新显示，**从未通知 ECharts 重算尺寸**。ECharts 在 `display:none` 容器上 resize/setOption 只能拿到 0×0；而 single-app 的图表只挂在 `window.resize` 上，切视图不会触发它，于是回来仍是 0 尺寸 → 被压成一条。

**修复**（**不改 `single-app.js`**，符合架构铁律）：
- `static/js/modules/stock.js` 新增 `notifyViewResize()`：用 **window 自身的 Event 构造器**派发一次 `resize`（下一帧 + 100ms 双保险），触发 single-app 已有的 `window.resize` 处理器，按当前视图 resize 对应图表。
- `closeFinance()` 返回时触发 resize，并**还原进入财务前的视图**（`_prevViewId` 记录：分时/K线/自选），不再一律回分时。
- 顶栏「K线 / 自选 / 返回」点击时同步隐藏财务视图并触发 resize。
- `single-template.js` 返回按钮文案「返回K线」→「返回图表」（与实际行为一致）。

**根治（图表生命周期治理，`single-finance.js`）**：原实现"每张图各注册一个 `window.resize` 监听、且重渲染不释放旧实例"，长会话会持续累积（监听 + ECharts 实例/画布）。现改为：
- 模块级**图表注册表** `_liveCharts` + `trackChart()`：**全局只注册 1 个 resize 监听**；
- `disposeFinance()`：**每次重渲染前 dispose 上一批实例**，并在个股页重建（`stock.js:loadAll`）/离开（`cleanTimers`）时调用；
- 监听回调里对 **`isDisposed()`** 与**容器不可见（`offsetParent === null`）**双判空 → 隐藏时不再把尺寸算成 0×0。

**验证**：`tests/frontend/stock.test.js` 新增 3 用例（① 返回时派发 resize 并还原原视图；② 点顶栏 K线 隐藏财务视图；③ 重渲染不新增 resize 监听且 dispose 旧实例）。前端 **57 通过**。

---

<a id="q5"></a>
## Q5 财务分析里的数据为什么有白的、有红的、有绿的？

**旧规则（易误导）**：财务指标表只给 `kind === "pct"`（百分数）单元格加 `up/down` 类，而 `static/css/style.css` 有一条**全局** `.up{color:红}` / `.down{color:绿}` → **任何百分数只要为正就变红**。于是 ROE、毛利率、净利率、甚至「资产负债率」全被标红（负债率高本该是警示），而金额 / 每股 / 倍数类保持白色——看起来就是"颜色很随意"。

**新规则（语义化，已统一到全模块）**：

| 颜色 / 箭头 | 含义 | 适用指标 |
|---|---|---|
| 🔴 `↑` 红 `up` | **增长**（同比 / 环比为正） | 营收 / 净利 / 扣非净利同比、营收/净利 TTM 同比、单季营收/净利环比、周涨跌、量能趋势、变动说明的环比 |
| 🟢 `↓` 绿 `down` | **负向**（下降 / 数值为负） | 同上，数值为负时；**以及表格 / 卡片中的任何负值**（如自由现金流 FCF、每股现金流、净资产为负） |
| ⚪ `→` 白 `flat` | **持平**（\|变化\| < 0.1 个百分点） | 同上，变化极小时 |
| 🟠 橙 `warn` | 偏离常态警示（触发阈值） | 资产负债率 > 70%、流动 / 速动比率 < 1、经营现金流/净利 < 60% |
| ⚪ 白 | 中性（**正值 / 零**，无正负好坏之分） | 金额、每股、倍数、比率、ROE / 毛利率 / 净利率、周转率、股东户数 |

> 持平需要容差：几乎不会有变化"正好等于 0"，因此以 `FLAT_EPS = 0.1`（个百分点）为界，`|变化| < 0.1` 视为持平并显示 `→`（白色）。
> 箭头用 `<span class="arw">` 单独放大（1.35em、加粗）并带**同色浅底**（`.up/.down/.flat` 各配 18% 透明的红/绿/白底），比纯文字更醒目。

**实现**：
- `single-finance.js` 新增指标字典 `IND_META`（每项含口径说明 `desc`、配色语义 `color: sign|warn|plain`、阈值谓词 `warn`）与 `indClass()`；
- 变化值统一走 `chg(v, {pct, digits})` → `{cls, html}`（`↑ +21.2%` / `↓ -5.0%` / `→ +0.0%`）与 `chgCard()`；持平容差 `FLAT_EPS = 0.1`；
- **负值标绿**：`valCls(v)`（`v < 0 → down`）+ `finCls(key, v)`（先按 `IND_META` 规则，否则负值标绿）；已覆盖所有多期科目表（`periodTable`）、杜邦表、指标表、财务诊断卡片与 `valCard`；
- 每个标签顶部统一渲染 `finLegend()` 配色图例；
- 财务指标表行标签带 `title` 悬浮说明，表尾新增可展开的「指标说明与配色」逐项清单；
- `.fin-table td.up/.down/.warn` 写入模块自身的 `FIN_CSS`（**自包含**，不再依赖全局 `.up/.down`）；
- 财务诊断关键指标卡、杜邦 ROE、成长趋势 ROE、现金流含金量等同步改用同一语义。

**验证**：`tests/frontend/stock.test.js` 新增 2 用例（配色语义 + 图例 + 指标说明；所有标签均有图例）。前端 **59 通过**。

---

<a id="q6"></a>
## Q6 「资产负债」能不能看同期对比（负债变化 / 偿债恢复能力）？

**诉求**：只看最新一期的负债率，看不出企业在**去杠杆**还是**加杠杆**。需要与**上年同季**对比。

**实现**：
- 后端 `panels/fund_local.py:get_balance` 新增 `ratio_series`（各期比率序列，与 `periods` 等长）：`debt_ratio` / `current_ratio` / `quick_ratio` / `current_assets_pct` / `current_liab_pct`。
- 前端「资产负债」新增 **「同期对比（最新期 vs 上年同季）」** 分组：总资产同比 / 总负债同比 / 净资产同比 / 资产负债率变化（百分点）/ 流动比率变化 / 速动比率变化，全部用醒目箭头 + 红绿白配色。
- **同期定位精确**：用「报告期 − 10000」（如 20260630 → 20250630）在 `periods` 里精确查找，不依赖"往前数 4 期"（避免报告期缺失时错位）。
- 页面内给出解读提示：总负债同比**降** = 去杠杆；流动 / 速动比率同比**升** = 短期偿债能力在恢复；资产负债率变化单位为**百分点**。
- **健壮性（兜底）**：若后端 `ratio_series` 缺失（典型情况：`server.py` 无热重载、**服务未重启**），前端会用多期科目**现场推算** 资产负债率 / 流动比率 / 流动资产占比 / 流动负债占比，保证同期对比仍可用；**速动比率**需存货字段、无法推算 → 显示 `--`。
- **`--` 通用解释**：解释行在出现 `--` 时自动追加一句说明（缺少上年同季 / 缺对应字段 / 服务未重启导致 `ratio_series` 未生效），并列出受影响项，避免用户误以为是数据错误。

**示例（sh688019 安集科技，20260630 vs 20250630）**：资产负债率 31.28% → 17.16%（**↓ -14.12 个百分点**），总负债同比明显下降 → 显著去杠杆。

**验证**：`tests/test_panels.py::TestBalanceRatioSeries` 3 用例（序列存在且对齐 / 与 `ratios` 一致 / 上年同季可定位）；`tests/frontend/stock.test.js` 新增同期对比渲染用例。后端 **242**、前端 **60** 通过。

---

<a id="q7"></a>
## Q7 分时图均价显示成 2.17（现价 219）、涨跌幅一长串小数

**现象**：分时 tooltip 里 现价 218.89、均价却 2.17（差约 100 倍）；涨跌幅显示 `-1.6578308922634672`。

**根因（两个独立问题）**：
1. **均价量纲偏差**：`sources/tencent.py` 按「手」口径 `cum_amt / (cum_vol × 100)` 算均价，但个别标的实际 `cum_vol` 是「股」→ 均价小 100 倍。而 `server._normalize_minute_avg` 的旧判据是 `avg < 1 才 ×100`，**高价股（2.17 > 1）漏掉了**。
2. **tooltip 未格式化**：`single-app.js` 的分时 tooltip 用 ECharts 默认格式，把 `(p−pre)/pre×100` 的原始浮点直接打印。

**修复**：
1. `server.py:_normalize_minute_avg` 改为**自校准**：以**同一分钟的价格**为基准，若 `|avg×100 − price| < |avg − price|` 则判定漏乘 100（对高价股有效，对低价股与正常值同样成立）；应用到 `/api/quote`、`/api/minute`、`/api/stock/tick`。`sources/tencent.py` 公式**保持不变**（其单测以「手」为单位），由上述归一化统一兜底。
2. **tooltip 桥接**（`stock.js`，**不改 single-app.js**）：包装 `echarts.init → setOption`，仅当图表含「涨跌幅」系列时注入 formatter —— **涨跌幅保留 4 位小数、价格保留 2 位**；其它图表（如回测净值曲线）不受影响。

**验证**：`tests/test_api.py::TestMinuteAvgNormalize` 5 用例（×100 还原 / 正确值不动 / 低价股仍正确 / 缺字段安全 / 不就地改入参）；`tests/frontend/stock.test.js` 新增 tooltip 桥接用例（`-1.6578%`、非分时图不注入）。后端 **247**、前端 **62** 通过。

---

<a id="q8"></a>
## Q8 合格买仓池为什么全是沪市（科创板）？不是"同一市场最多 2 只"吗？

**现象**：③ 合格买仓池 8 只全是 `688xxx`（沪市科创板），★建仓 4 只也全是科创板。

**结论：不是 bug，是 B 方案「分市场段」过滤 + 板块上限"有意放宽"的结果。**

### ① 为什么只有科创板

B 方案按**个股所属市场段**裁决（每段指数各自判断 56 周均线），映射见 `seg_index_for()`：

| 段指数 | 覆盖 | 本周(20260911) |
|---|---|---|
| `sh000688` 科创50 | 科创板 | **UP ✅** |
| `sh000001` 上证 | 沪市主板 | DOWN ❌ |
| `sz399001` 深证成指 | 深市主板 | DOWN ❌ |
| `sz399006` 创业板指 | 创业板 | DOWN ❌ |
| `bj899050` 北证50 | 北交所 | DOWN ❌ |

**只有科创50 站上 56 周均线** → 其余 4 段的个股即使质量达标也被 `段regime DOWN` 拦下进观察池（本周因此排除 88 只：沪主板 37 / 深主板 29 / 创业板 21 / 北证 1）。所以 ③ 只剩科创板。

### ② "同市场最多 2 只"确实存在，但被**有意放宽**

`BOARD_CAP = 0.50` → `N=4` 时 `board_cap_n = 2`（单板块上限 2 只），它**先生效**；但候选全在同一板块时硬限只能选出 2 只 → 5 万账户 4 个仓位只占 2 个，**单票预算翻倍、风险反而更集中**。故代码中有明确注明的放宽分支：

```python
if len(pick) < N and _bd_cap_n:
    # 候选集中在少数板块时（例如 8 只全是科创板），硬限板块会把持仓压到 2 只，
    # 反而使单票仓位翻倍、风险更集中 → 放宽板块约束回填，
    # **但保留行业约束**（行业才是真正的同涨同跌来源）。
    _alt = _apply(_ind_cap_n, None)
```

本周实测 `已放宽板块=是`，且**保留单行业上限 1 只**（4 只精选分属化学制品 / 光学光电子 / 通用设备 / 电子化学品）。

### ③ 现在报告里会明示（本次新增）

- 顶部新增卡片「市场段(56周MA)」：`科创50 UP · 4 段 DOWN`；「市场状态」对 B 方案改为 `仅 … UP → 仅该板块可买`（此前恒显示"全部上涨 → 建议建仓"，属**误导**）。
- ③ 表下新增说明：**5 段状态 + 合格池板块分布 + 板块约束（是否放宽）**；候选集中在单一板块时给橙色警示。
- **评分列按「同批相对」渐变着色：越高越红**（色相 210° 蓝 → 0° 红），分值仍以数字展示；背景为同色相低透明度（高分更实），便于从高到低扫读。实现见 `build_dashboard.score_color()`，表下有图例说明；回归用例 `TestDashboardHtml::test_pool_score_gradient` 校验"最高分必须比最低分更红"。

### ④ 顺带修掉两个真实缺陷

- **`live_report` 输出路径**：原先写 `WORK`（= `modules/strategy/`），而看板读 `data/` → 命令行生成的清单"看不见"，还留下 stray 文件；现统一 `OUT = <repo>/data`（与 `live_compare` / `build_dashboard` / `analysis` 一致）。
- **★建仓 脱出表格**：`pos_rows` 里 `<span class='star'>` 未包 `<td>` → 浏览器将其甩到表格格子外（表现为表格上方单独一行"★建仓 ★建仓 …"）；已修正为 `<td>{star}</td>`。

### ⑤ 决策（2026-09-13）：本项目选择 **A —— 保留放宽**

用户决定**维持现状**：候选集中在单一板块时，宁可"同板块但跨行业"的 4 仓，也不接受"压成 2 仓、单票预算翻倍"。

理由：行业（而非板块）才是真正同涨同跌的来源，而**单行业上限 `ind_cap_n=1` 始终保留**，已避免"4 只实质 1 只"的伪分散。

**若日后改主意**：调低 `BOARD_CAP`（如 `0.25` → `board_cap_n=1`），或移除 `current_candidates` 中的放宽分支。代价是席位更少 / 更集中。

**验证**：`tests/test_strategy.py::TestDashboardHtml` 3 用例（★建仓 在 `<td>` 内 / ③ 评分降序 / 段状态说明存在）。后端 **250**、前端 **63** 通过。

---

<a id="q9"></a>
## Q9 分时图涨跌幅对了，但均价还是不对（均价 1.77 / 现价 176.31）

**现象**：单股页分时图 tooltip 显示 现价 176.31、**均价 1.77**（差 100 倍）；涨跌幅已正常。

**根因：均价归一化漏了一个接口。**

Q7 修"均价小 100 倍"时，把自校准 `_normalize_minute_avg` 加到了 `/api/minute`、`/api/stock/tick`、`/api/stock/full`，**但 `/api/quote` 漏了**；而单股页分时图的**唯一数据源正是 `/api/quote`**（`single-app.js: loadQuote()` → `latestData.minute` → `avgs = m.map(x => x.avg)`），所以均价一直没被修正。

涨跌幅是由价格**前端现算**的（`(p - pre) / pre * 100`），与 `avg` 无关 —— 这正是"涨跌幅对了、均价不对"的原因。

实测真实数据（修复前）：

| 代码 | 同分钟 现价 | 均价 | 比值 |
|---|---|---|---|
| `sh688300` 联瑞新材 | 179.02 | **1.79** | 100.0 ❌ |
| `sh600519` 贵州茅台 | 1285.15 | 1285.15 | 1.00 ✅ |

即**同一接口内不同股票量纲不同**：降级链命中的源不同（腾讯 ifzq 的 `cum_vol` 是"股"，再按"手"除 100 就小 100 倍）。

### 修复：收口到 service 层唯一入口 + 端点兜底

1. `services/quote_service.normalize_minute_avg()`：原先只是 `server.py` 的私有函数，改为放在 **service 层**，并在 **`get_minute()`（含历史分时 `get_minute_with_meta`）返回前统一调用** → `/api/quote`、`/api/many`、`/api/stock/full`、`/api/minute`、`/api/stock/tick` 全部自动覆盖，不再"漏一个接口"。
2. `server.py` 的 `_normalize_minute_avg` 保留为**对 service 实现的引用**（兼容原调用点与既有单测），并在 `/api/quote` 加**端点级兜底**（幂等，不会二次放大）。
3. 判据不变：**×100 后更接近 price 才判定漏乘**；且**幂等**（重复调用结果不变）。

### 验证

修复后 `/api/quote` 真实数据：`sh688300` 首根 `(179.02, 179.0)`、末根 `(178.69, 177.3)`；`sh600519` 保持 `(1285.15, 1285.15)` 不变。

回归测试（`tests/test_api.py`）：
- `TestQuoteMinuteAvgNormalized`：/api/quote 归一化 / 正确值不放大 / 缺 `avg` 安全返回
- `TestGetMinuteNormalizesAvg`：service 层归一化 / 正确值保持 / **幂等** / 不修改入参

> **教训**：同一类校正要放在**所有消费方共用的唯一入口**，而不是逐个接口补 —— "在哪归一化"比"归一化逻辑本身"更容易出错。
> **注意**：后端改动需**重启服务**才生效；前端无需改动。

---

## 附：本次改动文件清单

| 文件 | 改动 |
|---|---|
| `modules/strategy/live_compare.py` | 新增可复用 `write_compare()`；池数据带 `score`；改模块属性调用便于打桩 |
| `modules/analysis/analysis.py` | `_persist_dashboard` 同步刷新 `live_compare.json` |
| `modules/strategy/regime_layer2_backtest.py` | 合格池输出去掉 `[:30]` 截断，全量按评分降序 |
| `modules/strategy/build_dashboard.py` | ② 同源校验；① 改真实持仓；③ 全量评分降序；表头"分位"→"评分" |
| `modules/holdings/holdings.py` | 新增 `clear_holdings()` |
| `server.py` | 新增 `/api/holdings/clear`；`_rebuild_dashboard()` 持仓变更后同步看板 |
| `static/index.html` / `static/js/app.js` | 新增「清空全部持仓」按钮与处理、报告 iframe 刷新 |
| `tests/test_strategy.py` / `tests/frontend/sidebar.test.js` | 新增回归用例 |

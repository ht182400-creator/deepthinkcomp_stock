// 由 deepthinkSingle/templates/index.html 的 <body> 提取（完整功能 DOM：topbar/自选/K线/副图/复盘/资金流/右键菜单/全部 modal）
export const SINGLE_HTML = `
  <!-- 顶部状态栏 -->
  <header class="topbar">
    <div class="stock-info">
      <span class="name" id="stName">--</span>
      <span class="code" id="stCode">--</span>
      <span class="price" id="stPrice">--</span>
      <span class="chg" id="stChg">--</span>
      <span class="tag" id="stSource"></span>
    </div>
    <div class="controls">
      <select id="watchSel" hidden></select>
      <input id="watchInput" list="watchOptions" placeholder="自选/搜索 股票 (sh600519/茅台)">
      <datalist id="watchOptions"></datalist>
      <div class="search-wrap">
        <input id="searchInput" placeholder="搜股票 sh600519/茅台/白酒" autocomplete="off">
        <div id="searchResults" class="search-results"></div>
      </div>
      <button id="addBtn" title="把当前标的加入自选">+</button>
      <button id="delBtn" title="把当前标的移出自选">−</button>
      <button id="refreshBtn" title="立即刷新行情">刷新</button>
      <button id="klineBtn" title="切换 K线/分时视图">K线</button>
      <button id="watchlistBtn" title="自选批量表格">自选</button>
      <button id="analysisBtn" title="复盘/分析记录">复盘</button>
      <span class="muted" id="updateTime"></span>
    </div>
  </header>

  <!-- 自选批量表格视图 -->
  <div id="watchlistView" class="hidden">
    <section class="panel">
      <div class="phead row-flex">
        <span>自选批量监控（点击行切换到分时）</span>
        <button id="wlRefreshBtn" class="ghost">刷新</button>
      </div>
      <table id="watchlistTable" class="wl-table">
        <thead><tr><th>代码</th><th>名称</th><th>现价</th><th>涨跌幅</th><th>涨跌额</th><th>成交额</th><th>换手</th></tr></thead>
        <tbody></tbody>
      </table>
    </section>
  </div>

  <!-- 分钟视图 -->
  <div id="minuteView">
    <div class="minute-row">
      <div class="minute-left">
        <section class="panel" id="p1">
          <div class="phead">分时走势 (双击/回车查看 K线) · 右键点空白区配置副图</div>
          <div id="ch1" class="chart"></div>
          <div id="p1Empty" class="empty-overlay hidden">暂无分时数据</div>
        </section>
        <div id="subCharts"></div>
      </div>
      <div class="minute-mid">
        <div id="orderBook" class="orderbook"></div>
        <div id="minuteDetail" class="minute-detail"></div>
      </div>
      <div class="minute-right">
        <div id="marketPanel" class="market-panel"></div>
        <div id="marketPanelRight" class="market-panel"></div>
      </div>
    </div>
  </div>

  <!-- K线视图 -->
  <div id="klineView" class="hidden">
    <section class="panel">
      <div class="phead row-flex">
        <span id="klineTitle">K线图</span>
        <div class="muted gap">
          <button class="kperiod active" data-p="day">日K</button>
          <button class="kperiod" data-p="week">周K</button>
          <button class="kperiod" data-p="month">月K</button>
          <button class="kperiod" data-p="m60">60分</button>
          <button class="kperiod" data-p="m30">30分</button>
          <button class="kperiod" data-p="m15">15分</button>
          <button class="kperiod" data-p="m5">5分</button>
          <button id="backBtn">返回分时</button>
        </div>
      </div>
      <div id="ch4" class="chart tall"></div>
    </section>
    <div id="klineSubs"></div>
    <section class="panel" id="klineMarket">
      <div class="phead">市场综合（参考示例图：行情/估值/财务/净利/多空/两融/股东/龙虎榜/公司/预测/公告）</div>
      <div id="klineMarketPanel" class="market-panel kline-mp"></div>
    </section>
  </div>

  <footer class="muted">每 30 秒自动刷新 · 数据源：腾讯自选股（主力资金来自东方财富） · K 线首次加载需 5-10s（下载 westock-data-skillhub 包）</footer>
</div>

<!-- 历史分时小图模态（K 线双击/回车弹出） -->
<div id="histModal" class="modal hidden">
  <div class="modal-body">
    <div class="modal-head">
      <span id="histTitle" class="muted">历史分时</span>
      <button id="histClose" class="ghost">关闭</button>
    </div>
    <div id="histChart" class="chart-mini"></div>
    <div id="histMsg" class="muted small"></div>
  </div>
</div>

<!-- 公告正文模态（点击公告行弹出） -->
<div id="annModal" class="modal hidden">
  <div class="modal-body ann-modal-body">
    <div class="modal-head">
      <span id="annTitle" class="muted">公告</span>
      <button id="annPdf" class="ghost hidden">查看PDF</button>
      <button id="annClose" class="ghost">关闭</button>
    </div>
    <div id="annContent" class="ann-content"></div>
    <div id="annMsg" class="muted small"></div>
  </div>
</div>

<!-- 分钟资金流明细 modal（US-015 Sprint 3） -->
<div id="fundFlowModal" class="modal hidden">
  <div class="modal-body fund-flow-body">
    <div class="modal-head">
      <span id="fundFlowTitle" class="muted">分钟资金流明细</span>
      <button id="fundFlowClose" class="ghost">关闭</button>
    </div>
    <table class="wl-table fund-flow-table">
      <thead><tr><th>时间</th><th>主力净额</th><th>超大单</th><th>大单</th><th>中单</th><th>小单</th></tr></thead>
      <tbody id="fundFlowBody"></tbody>
    </table>
  </div>
</div>

<!-- K线副图配置 modal -->
<div id="klineSubConfigModal" class="modal hidden">
  <div class="modal-body sub-config-body">
    <div class="modal-head">
      <span class="muted">K线副图配置（技术指标）</span>
      <button id="klineSubConfigClose" class="ghost">关闭</button>
    </div>
    <div id="klineSubConfigRows" class="sub-config-rows"></div>
    <div class="sub-config-actions">
      <button id="klineSubConfigReset" class="ghost">恢复默认</button>
      <button id="klineSubConfigSave" class="primary">保存</button>
    </div>
  </div>
</div>

<!-- 副图配置 modal（右键空白区弹出） -->
<div id="subConfigModal" class="modal hidden">
  <div class="modal-body sub-config-body">
    <div class="modal-head">
      <span class="muted">副图窗口配置</span>
      <button id="subConfigClose" class="ghost">关闭</button>
    </div>
    <div class="sub-config-row">
      <label>副图个数</label>
      <select id="subConfigCount"></select>
      <span class="muted small">最多 5 个</span>
    </div>
    <div id="subConfigRows"></div>
    <div class="sub-config-actions">
      <button id="subConfigReset" class="ghost">恢复默认</button>
      <button id="subConfigSave" class="primary">保存</button>
    </div>
  </div>
</div>

<!-- 复盘/分析记录 modal（US-017） -->
<div id="analysisModal" class="modal hidden">
  <div class="modal-body analysis-body">
    <div class="modal-head">
      <span id="analysisTitle" class="muted">复盘记录</span>
      <button id="analysisClose" class="ghost">关闭</button>
    </div>
    <textarea id="analysisInput" class="analysis-input" placeholder="记录对当前标的的分析判断（如：放量突破、主力连续流入…）"></textarea>
    <div class="analysis-actions">
      <button id="analysisSave" class="primary">保存</button>
    </div>
    <div id="analysisList" class="analysis-list"></div>
  </div>
</div>

<!-- 右键菜单 -->
<div id="contextMenu" class="ctx-menu hidden">
  <div class="ctx-item" id="ctxConfigSub">⚙ 副图配置</div>
  <div class="ctx-item" id="ctxConfigKlineSub" style="display:none">📊 K线副图配置</div>
  <div class="ctx-item" id="ctxFundFlow">💧 资金流明细</div>
  <div class="ctx-item" id="ctxExportCsv">📥 导出 CSV</div>
  <div class="ctx-item" id="ctxRefresh">🔄 立即刷新</div>
  <div class="ctx-sep"></div>
  <div class="ctx-item ctx-hint muted small">提示：右键空白区 / 分时图 均可</div>
`;

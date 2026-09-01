// 真实浏览器端到端测试：用系统 Chrome（puppeteer-core）加载页面，
// 模拟"搜索切换股票 + 切 30 分 K 线"，校验图表真有数据（不再走 npx/熔断）。
// 注：headless 下 puppeteer 的 waitForFunction/waitForSelector 对本页（持续行情轮询）不稳定，
// 故全程用 page.evaluate + element.click() + sleep 轮询驱动。
const puppeteer = require("puppeteer-core");

const BASE = "http://127.0.0.1:5000";
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const CODES = [
  ["sh600519", "茅台"],
  ["sh600048", "保利发展"],
  ["sh601398", "工商银行"],
  ["sz300750", "宁德时代"],
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(...a);

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage();
  page.on("pageerror", (e) => log("  [pageerror]", e.message));

  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
  // 等搜索框出现
  for (let i = 0; i < 40; i++) {
    if (await page.evaluate(() => !!document.getElementById("klineBtn"))) break;
    await sleep(150);
  }
  // 切到 K 线视图
  await page.evaluate(() => document.getElementById("klineBtn").click());
  await sleep(600);

  const results = [];
  for (const [code, name] of CODES) {
    // 触发搜索
    await page.evaluate((c) => {
      const inp = document.getElementById("searchInput");
      inp.value = c;
      inp.dispatchEvent(new Event("input", { bubbles: true }));
    }, code);
    // 轮询等搜索结果（且第一项 data-code 匹配当前股票，避免上一轮残留 .item 误点）
    let items = 0;
    for (let i = 0; i < 20; i++) {
      await sleep(150);
      items = await page.evaluate(
        (c) => {
          const el = document.querySelector("#searchResults .item");
          return el && el.dataset.code && el.dataset.code.toLowerCase() === c ? 1 : 0;
        },
        code
      );
      if (items > 0) break;
    }
    if (items === 0) {
      const h = await page.evaluate(() => document.getElementById("searchResults").innerHTML);
      log(`  FAIL ${code} ${name} | 搜索无结果: ${h.slice(0, 80)}`);
      results.push({ code, name, pass: false, maxLen: 0, title: "搜索无结果" });
      continue;
    }
    // 点击第一项切换股票
    await page.evaluate(() => document.querySelector("#searchResults .item").click());
    // 选 30 分（确保周期；不依赖实时行情源 loadQuote，只验证本地 tdx 的分钟 K 渲染）
    await page.evaluate(() => document.querySelector('.kperiod[data-p="m30"]').click());
    // 轮询等标题含本股票代码 +「30分」且无失败/空（K 线标题由本地 tdx loadKline 更新）
    let title = "";
    let titleOk = false;
    for (let i = 0; i < 40; i++) {
      await sleep(250);
      title = await page.evaluate(() => document.getElementById("klineTitle").textContent);
      if (
        title.toUpperCase().includes(code.toUpperCase()) &&
        title.includes("30分") &&
        !title.includes("失败") &&
        !title.includes("空") &&
        !title.includes("加载中")
      ) {
        titleOk = true;
        break;
      }
    }
    if (!titleOk) {
      log(`  FAIL ${code} ${name} | 标题异常: ${title}`);
      results.push({ code, name, pass: false, maxLen: 0, title });
      continue;
    }
    await sleep(300);
    // 校验 echarts 实例真有数据
    const info = await page.evaluate(() => {
      const inst = window.echarts.getInstanceByDom(document.getElementById("ch4"));
      const opt = inst && inst.getOption();
      const series = (opt && opt.series) || [];
      let maxLen = 0;
      series.forEach((s) => {
        if (Array.isArray(s.data)) maxLen = Math.max(maxLen, s.data.length);
      });
      return { title: document.getElementById("klineTitle").textContent, maxLen };
    });
    const pass = info.maxLen > 0;
    results.push({ code, name, ...info, pass });
    log(`  ${pass ? "PASS" : "FAIL"} ${code} ${name} | ${info.title} | 图表数据点=${info.maxLen}`);
  }

  const fails = results.filter((r) => !r.pass);
  log("\n==== E2E 结果 ====");
  log(fails.length ? "FAIL: " + fails.map((f) => f.code).join(",") : "ALL PASS ✅");
  await browser.close();
  process.exit(fails.length ? 1 : 0);
})().catch((e) => {
  log("E2E ERROR:", e.message);
  process.exit(2);
});

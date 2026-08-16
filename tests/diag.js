const puppeteer = require("puppeteer-core");
const BASE = "http://127.0.0.1:5000";
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
(async () => {
  const b = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox","--disable-gpu","--disable-dev-shm-usage"] });
  const p = await b.newPage();
  p.on("pageerror", e => console.log("PAGEERR:", e.message));
  p.on("console", m => { if (m.type()==="error") console.log("CONSOLE.ERR:", m.text()); });
  await p.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
  await new Promise(r => setTimeout(r, 2000));
  const before = await p.evaluate(() => ({
    kline: document.getElementById("klineView").className,
    echarts: typeof window.echarts,
    ch4: document.getElementById("ch4") ? document.getElementById("ch4").clientWidth + "x" + document.getElementById("ch4").clientHeight : "no-ch4",
  }));
  console.log("BEFORE:", JSON.stringify(before));
  await p.evaluate(() => { const x=document.getElementById("klineBtn"); console.log("clicking klineBtn", !!x); x && x.click(); });
  await new Promise(r => setTimeout(r, 500));
  const after = await p.evaluate(() => ({ kline: document.getElementById("klineView").className, minute: document.getElementById("minuteView").className }));
  console.log("AFTER:", JSON.stringify(after));
  await b.close();
})().catch(e => { console.log("DIAG ERR:", e.message); process.exit(1); });

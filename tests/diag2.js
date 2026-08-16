const puppeteer = require("puppeteer-core");
const BASE = "http://127.0.0.1:5000";
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox","--disable-gpu","--disable-dev-shm-usage"] });
  const p = await b.newPage();
  p.on("pageerror", e => console.log("PAGEERR:", e.message));
  p.on("console", m => { if (m.type()==="error") console.log("CONSOLE.ERR:", m.text()); });
  await p.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
  await sleep(1500);
  await p.evaluate(() => { const inp = document.getElementById("searchInput"); inp.value = "sh600519"; inp.dispatchEvent(new Event("input", { bubbles: true })); });
  await sleep(1000);
  const r2 = await p.evaluate(() => {
    const box = document.getElementById("searchResults");
    return { items: document.querySelectorAll("#searchResults .item").length, html: box.innerHTML.slice(0, 300) };
  });
  console.log("R2:", JSON.stringify(r2));
  // 直接测试 fetch 是否可用
  const r3 = await p.evaluate(async () => {
    try {
      const resp = await fetch("/api/search?q=sh600519");
      const j = await resp.json();
      return { ok: resp.ok, len: j.length, sample: j[0] };
    } catch (e) { return { err: e.message }; }
  });
  console.log("FETCH:", JSON.stringify(r3));
  await b.close();
})().catch(e => { console.log("DIAG2 ERR:", e.message); process.exit(1); });

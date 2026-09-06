#!/usr/bin/env node
/**
 * Mobile-friendliness scanner for AppVerse.
 * Renders every app at Pixel-7 size and MEASURES; does not grep for viewport tags
 * (364/366 apps have one, so that tag proves nothing).
 *
 * Serves the files itself on 8766 so the live server's _access.log and the `opened`
 * signal stay clean -- `opened` is genuine human usage the menu revamp depends on.
 */
const APPS = __dirname;
const { chromium, devices } = require("playwright");
const fs = require("fs"), path = require("path"), http = require("http");

const OUT = path.join(__dirname, "test_reports", "mobile_scan");
const SHOTS = path.join(OUT, "shots");
fs.mkdirSync(SHOTS, { recursive: true });
const PORT = 8766, WORKERS = 4;

function discover() {
  const out = [];
  (function walk(dir, rel) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, e.name), rp = rel ? path.join(rel, e.name) : e.name;
      if (e.isDirectory()) {
        if (!["test_reports", "node_modules", ".git", "screenshots"].includes(e.name)) walk(full, rp);
      } else if (e.name.endsWith(".html")) {
        out.push(rp.split(path.sep).join("/"));
      }
    }
  })(APPS, "");
  return out;
}

function serve() {
  return new Promise(r => {
    const s = http.createServer((req, res) => {
      const fp = path.join(APPS, decodeURIComponent(req.url.split("?")[0]));
      if (!fs.existsSync(fp) || fs.statSync(fp).isDirectory()) { res.writeHead(404); return res.end(); }
      const t = { ".html": "text/html", ".js": "application/javascript", ".css": "text/css",
                  ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".json": "application/json" };
      res.writeHead(200, { "Content-Type": t[path.extname(fp).toLowerCase()] || "application/octet-stream" });
      fs.createReadStream(fp).pipe(res);
    });
    s.listen(PORT, "127.0.0.1", () => r(s));
  });
}

// Static red flag: arrow/WASD keyboard control with no touch or pointer handler.
// A phone has no arrow keys, so this is a hard NO however well it renders.
function hasTouch(rel) {
  const t = fs.readFileSync(path.join(APPS, rel.split("/").join(path.sep)), "utf8").toLowerCase();
  return /(touchstart|touchmove|pointerdown|ontouchstart)/.test(t);
}

function keyboardOnly(rel) {
  const t = fs.readFileSync(path.join(APPS, rel.split("/").join(path.sep)), "utf8").toLowerCase();
  const keys = /key(down|up)/.test(t) && /(arrowup|arrowdown|arrowleft|arrowright|keycode\s*===?\s*3[7-9]|keycode\s*===?\s*40)/.test(t);
  const touch = /(touchstart|touchend|pointerdown|ontouchstart)/.test(t);
  return keys && !touch;
}

async function measure(page) {
  return await page.evaluate(() => {
    const de = document.documentElement;
    const vw = window.innerWidth;
    const sw = Math.max(de.scrollWidth, document.body ? document.body.scrollWidth : 0);
    let wideCanvas = 0;
    for (const c of document.querySelectorAll("canvas")) {
      const b = c.getBoundingClientRect();
      if (b.width - vw > 4) wideCanvas = Math.max(wideCanvas, Math.round(b.width));
    }
    // Interactive controls too small to hit with a thumb.
    let tiny = 0, total = 0;
    for (const el of document.querySelectorAll("button,[role=button],a,input,select,textarea,[onclick]")) {
      const b = el.getBoundingClientRect();
      if (b.width === 0 || b.height === 0) continue;
      total++;
      if (b.height < 30 || b.width < 30) tiny++;
    }
    return { overflow: Math.round(sw - vw), wideCanvas, tiny, total };
  });
}

async function run(rel, ctx) {
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(String(e.message).slice(0, 200)));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text().slice(0, 200)); });
  const r = { app: rel, ok: false, reasons: [], errors: [] };
  try {
    await page.goto("http://127.0.0.1:" + PORT + "/" + encodeURI(rel), { timeout: 15000, waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1600);
    const m1 = await measure(page);

    // Start screens hide the real layout, so press the biggest visible button and re-measure.
    try {
      const h = await page.evaluateHandle(() => {
        let best = null, area = 0;
        for (const b of document.querySelectorAll("button,[role=button],.btn")) {
          const q = b.getBoundingClientRect();
          if (q.width > 0 && q.top < window.innerHeight && q.width * q.height > area) { area = q.width * q.height; best = b; }
        }
        return best;
      });
      const el = h.asElement();
      if (el) { await el.click({ timeout: 1500 }); await page.waitForTimeout(1200); }
    } catch (e) { /* not clickable; first measurement still stands */ }
    const m2 = await measure(page);

    const overflow = Math.max(m1.overflow, m2.overflow);
    const wideCanvas = Math.max(m1.wideCanvas, m2.wideCanvas);
    const tiny = Math.max(m1.tiny, m2.tiny), total = Math.max(m1.total, m2.total);

    if (overflow > 8) r.reasons.push("h-scroll +" + overflow + "px");
    if (wideCanvas) r.reasons.push("canvas " + wideCanvas + "px wider than screen");
    if (keyboardOnly(rel)) r.reasons.push("keyboard-only controls");
    const fatal = errors.filter(e => !/favicon|net::ERR_FILE|Failed to load resource/i.test(e));
    if (fatal.length) r.reasons.push("js error: " + fatal[0].slice(0, 60));
    // "No DOM buttons" is not the same as "not interactive": a canvas game is
    // driven by touch handlers on the canvas itself, and those are exactly the
    // games worth showing off. Flagging them cost 14 action games on the first
    // pass before this exemption was added.
    if (total === 0 && !hasTouch(rel)) r.reasons.push("no interactive controls found");
    else if (tiny > 3 && tiny / total > 0.5) r.reasons.push(tiny + "/" + total + " tap targets under 30px");

    r.metrics = { overflow, wideCanvas, tiny, total };
    r.errors = fatal.slice(0, 3);
    r.ok = r.reasons.length === 0;
    await page.screenshot({ path: path.join(SHOTS, rel.split("/").join("__") + ".jpg"), type: "jpeg", quality: 55 });
  } catch (e) {
    r.reasons.push("load failed: " + String(e.message).split("\n")[0].slice(0, 80));
  }
  await page.close();
  return r;
}

(async () => {
  let apps = discover();
  console.log("apps: " + apps.length);
  const server = await serve();
  const browser = await chromium.launch();
  const results = [];
  let i = 0;
  await Promise.all(Array.from({ length: WORKERS }, async () => {
    const ctx = await browser.newContext({
      ...devices["Pixel 7"],
      userAgent: devices["Pixel 7"].userAgent + " AppVerse-MobileScan/1",
    });
    while (true) {
      const n = i++;
      if (n >= apps.length) break;
      results.push(await run(apps[n], ctx));
      if (results.length % 25 === 0) console.log("  " + results.length + "/" + apps.length);
    }
    await ctx.close();
  }));
  await browser.close(); server.close();
  results.sort((a, b) => a.app.localeCompare(b.app));
  fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(results, null, 1));
  const pass = results.filter(r => r.ok);
  console.log("\nPASS " + pass.length + " / " + results.length);
  const why = {};
  for (const r of results) for (const x of r.reasons) {
    const k = x.split(":")[0].replace(/\d+/g, "N");
    why[k] = (why[k] || 0) + 1;
  }
  console.log(JSON.stringify(why, null, 1));
})();

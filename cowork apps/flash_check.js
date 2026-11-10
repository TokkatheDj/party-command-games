#!/usr/bin/env node
/**
 * flash_check.js - does an app flash a large part of the screen more than 3 times a second? (10 Nov 2026)
 *
 * The 10 Nov code review found Light Jockey strobing the whole screen 8-9 times a second and Phosphor Lock
 * at 4. Reading code catches that one app at a time; this MEASURES it. Each app is opened (muted), its
 * Start-like button pressed, and it is played for a few seconds (taps, Space, arrows; any STROBE / FLASH
 * control is held down). Every frame the browser draws is captured (Chrome screencast, small), split into
 * a 12x12 grid, and compared with the frame before:
 *   - a cell "brightens" / "darkens" when its luminance changes by >= 0.1 (0-1 scale), the darker side
 *     being below 0.8 (WCAG's general-flash definition, simplified);
 *   - a frame is a big transition when >= 11% of the cells moved the same way (WCAG's 341x256 px at 1024x768);
 *   - a FLASH is a brighten followed by a darken (or the other way round);
 *   - the app FAILS if any 1-second window holds more than 3 flashes.
 * Simplified on purpose (no red-flash rule, cells not pixels): it is a screen, not a certificate.
 *
 *   node flash_check.js kids_apps/a.html party_apps/b.html     ->  JSON {apps:[{app, ok, maxPerSec, ...}]}
 *   node flash_check.js --seconds 10 --port 8768 FILES...
 */
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), http = require("http");

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(name); if (i < 0) return dflt; const v = args[i + 1]; args.splice(i, 2); return v; };
const SECONDS = +opt("--seconds", 8), PORT = +opt("--port", 8768);
// WCAG measures flash AREA in absolute terms: about 341x256 px on a 1024x768 screen (25% of a 10-degree
// field of view), so the check runs at 1024x768 and a big transition is >= 341*256/(1024*768) = 11% of it.
// The first version used 25% of a phone screen and missed Light Jockey's 8-9 Hz stage (25% of the phone).
const ROOT = __dirname, GRID = 16, DELTA = 0.1, AREA = (341 * 256) / (1024 * 768), LIMIT = 3, VIEW = { width: 1024, height: 768 };
const START = /^\s*(start|play|begin|go|let'?s go|new game|start game|play now|tap to start|ready)\b/i;
const FLASHY = [/strobe/i, /lightning|thunder/i, /flash|blink/i];   // tried in this order
// Never hold a SAFETY control: on 10 Nov the first version held "SAFE FLASH", which switched safe mode back on.
const NOT_FLASHY = /safe|steady|reduc|calm|mute|sound|music|setting|help|off/i;

function serve() {
  const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml" };
  return new Promise(res => {
    const s = http.createServer((q, r) => {
      const p = path.join(ROOT, decodeURIComponent(q.url.split("?")[0]));
      if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { r.writeHead(404); return r.end(); }
      r.writeHead(200, { "Content-Type": types[path.extname(p)] || "application/octet-stream" }); fs.createReadStream(p).pipe(r);
    }).listen(PORT, "127.0.0.1", () => res(s));
  });
}

// Decode a JPEG frame into GRID x GRID mean relative luminance, inside a helper page (no npm image library).
async function makeDecoder(browser) {
  const p = await browser.newPage();
  await p.setContent("<canvas id=c></canvas>");
  return async (b64) => p.evaluate(async ([b64, G]) => {
    const img = new Image(); img.src = "data:image/jpeg;base64," + b64; await img.decode();
    const c = document.getElementById("c"); c.width = G * 4; c.height = G * 4;
    const x = c.getContext("2d"); x.drawImage(img, 0, 0, c.width, c.height);
    const d = x.getImageData(0, 0, c.width, c.height).data, out = new Array(G * G).fill(0);
    const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    for (let y = 0; y < c.height; y++) for (let xx = 0; xx < c.width; xx++) {
      const i = (y * c.width + xx) * 4, L = 0.2126 * lin(d[i]) + 0.7152 * lin(d[i + 1]) + 0.0722 * lin(d[i + 2]);
      out[Math.floor(y / 4) * G + Math.floor(xx / 4)] += L / 16;
    }
    return out;
  }, [b64, GRID]);
}

function analyse(frames) {   // frames: [{t (s), L: [cells]}]
  const trans = [];          // {t, dir: +1 brighten / -1 darken}
  for (let i = 1; i < frames.length; i++) {
    const a = frames[i - 1].L, b = frames[i].L; let up = 0, down = 0;
    for (let k = 0; k < a.length; k++) {
      const d = b[k] - a[k];
      if (d >= DELTA && Math.min(a[k], b[k]) < 0.8) up++;
      else if (d <= -DELTA && Math.min(a[k], b[k]) < 0.8) down++;
    }
    const n = a.length;
    if (up / n >= AREA) trans.push({ t: frames[i].t, dir: 1 });
    else if (down / n >= AREA) trans.push({ t: frames[i].t, dir: -1 });
  }
  const flashes = [];        // a flash = a transition followed by the opposite one
  for (let i = 1; i < trans.length; i++) if (trans[i].dir !== trans[i - 1].dir) { flashes.push(trans[i].t); i++; }
  let maxPerSec = 0;
  for (let i = 0; i < flashes.length; i++) {
    let j = i; while (j < flashes.length && flashes[j] - flashes[i] < 1) j++;
    maxPerSec = Math.max(maxPerSec, j - i);
  }
  return { transitions: trans.length, flashes: flashes.length, maxPerSec };
}

async function checkOne(browser, decode, rel) {
  const ctx = await browser.newContext({ viewport: VIEW, hasTouch: true });
  const page = await ctx.newPage(); const errs = [];
  page.on("pageerror", e => errs.push(String(e.message || e).slice(0, 100)));
  page.on("dialog", d => d.dismiss().catch(() => {}));
  const cdp = await ctx.newCDPSession(page); const raw = [];
  cdp.on("Page.screencastFrame", f => { raw.push({ t: f.metadata.timestamp, data: f.data }); cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {}); });
  const url = `http://127.0.0.1:${PORT}/${rel.split("/").map(encodeURIComponent).join("/")}`;
  try { await page.goto(url, { waitUntil: "load", timeout: 20000 }); } catch (e) { errs.push("LOAD " + e.message.slice(0, 80)); }
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 40, maxWidth: 128, maxHeight: 96, everyNthFrame: 1 });
  await page.waitForTimeout(400);
  // press the most Start-like visible button
  try {
    const btn = await page.evaluateHandle(re => Array.from(document.querySelectorAll("button,[role=button],a"))
      .find(b => b.getBoundingClientRect().width > 0 && new RegExp(re, "i").test((b.textContent || "").trim())), START.source);
    if (btn && (await btn.evaluate(b => !!b))) await btn.click({ timeout: 1500 }).catch(() => {});
  } catch (e) {}
  // hold any strobe / flash control for 2.5 s, then play generically
  const end = Date.now() + SECONDS * 1000;
  try {
    const fl = await page.evaluateHandle(([res, bad]) => {
      const bs = Array.from(document.querySelectorAll("button,[role=button]")).filter(b => b.getBoundingClientRect().width > 0);
      const label = b => (b.textContent || "") + " " + (b.getAttribute("aria-label") || "");
      for (const re of res) { const m = bs.find(b => new RegExp(re, "i").test(label(b)) && !new RegExp(bad, "i").test(label(b))); if (m) return m; }
      return null;
    }, [FLASHY.map(r => r.source), NOT_FLASHY.source]);
    if (fl && (await fl.evaluate(b => !!b))) {
      const r = await fl.evaluate(b => { const q = b.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 }; });
      await page.mouse.move(r.x, r.y); await page.mouse.down(); await page.waitForTimeout(2500); await page.mouse.up();
    }
  } catch (e) {}
  const keys = ["Space", "ArrowUp", "ArrowLeft", "ArrowRight", "ArrowDown"]; let k = 0;
  while (Date.now() < end) {
    try {
      if (k % 3 === 0) await page.mouse.click(300 + (k * 53) % 420, 200 + (k * 97) % 380);
      else await page.keyboard.press(keys[k % keys.length]);
    } catch (e) {}
    k++; await page.waitForTimeout(150);
  }
  await cdp.send("Page.stopScreencast").catch(() => {});
  const frames = [];
  for (const f of raw) { try { frames.push({ t: f.t, L: await decode(f.data) }); } catch (e) {} }
  await ctx.close();
  const a = analyse(frames);
  return { app: rel, ok: a.maxPerSec <= LIMIT, maxPerSec: a.maxPerSec, flashes: a.flashes, frames: frames.length, errors: errs.slice(0, 2) };
}

if (require.main === module) {
  (async () => {
    const server = await serve();
    const browser = await chromium.launch({ args: ["--mute-audio"] });
    const decode = await makeDecoder(browser);
    const out = { checked_at: new Date().toISOString(), limit: LIMIT, apps: [] };
    for (const rel of args) { out.apps.push(await checkOne(browser, decode, rel)); }
    await browser.close(); server.close();
    process.stdout.write(JSON.stringify(out, null, 1) + "\n");
  })();
}
module.exports = { analyse };

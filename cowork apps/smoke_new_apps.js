#!/usr/bin/env node
/**
 * smoke_new_apps.js - PLAY each new app a little, not just load it (13 Oct 2026).
 *
 * test_apps.js proves a page loads without errors. That passed all five apps of
 * 9-10 Oct, and two of them were still broken in ways only playing showed:
 *   - Ricochet Arena started on load: with nobody touching it, GAME OVER at 11.5 s.
 *   - Backronym Bash printed the word "null" on every writing screen.
 * So for each app, on a phone and a tablet viewport, this:
 *   1. loads it and records errors (console, uncaught, failed requests);
 *   2. waits IDLE_S seconds with no input, and flags a "game over"-type message
 *      that appeared on its own;
 *   3. presses the most Start-like button (by touch on the phone) and plays for a
 *      few seconds - taps and arrow keys - recording any errors it causes;
 *   4. flags "null" / "undefined" / "NaN" left showing as text.
 *
 *   node smoke_new_apps.js kids_apps/2026-10-11-foo.html party_apps/bar.html
 * Prints one JSON object: { checked_at, apps: [{ app, title, ok, problems: [...] }] }.
 * Run nightly by new_app_check.py, which picks the apps (new or changed since the
 * last commit) and reports the result.
 */
const { chromium } = require("playwright");
const fs = require("fs");
const http = require("http");
const path = require("path");

const ROOT = __dirname;
const PORT = 8766;
const IDLE_S = 15;
const PLAY_S = 5;
const VIEWPORTS = [
  { name: "phone", width: 390, height: 844, isMobile: true, hasTouch: true },
  { name: "tablet", width: 1024, height: 1366, isMobile: false, hasTouch: true },
];
const OVER = /\b(game over|you lose|you lost|you died|time'?s up|out of lives|no lives left)\b/i;
const START = /^\W*(start|play|let'?s|begin|go\b|tap to (start|play)|new game|ready)/i;
const SKIP = /sound|mute|music|volume|settings|help|how to|rules|about|back|quit|menu|reset/i;
const JUNK = /(^|[\s:(=])(null|undefined|NaN)(?=[\s.,!?)]|$)/;

function serve() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const file = path.join(ROOT, decodeURIComponent(req.url.split("?")[0]));
      if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404); res.end(); return;
      }
      res.writeHead(200, { "Content-Type": file.endsWith(".html") ? "text/html; charset=utf-8" : "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    }).listen(PORT, "127.0.0.1", () => resolve(server));
  });
}

async function checkOne(browser, rel, vp) {
  const problems = [];
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, isMobile: vp.isMobile, hasTouch: vp.hasTouch });
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", e => errors.push("uncaught: " + e.message));
  page.on("requestfailed", r => { if (!r.url().startsWith("data:")) errors.push("failed request: " + r.url()); });
  const add = (what) => problems.push(`${vp.name}: ${what}`);
  const text = () => page.evaluate(() => document.body ? document.body.innerText : "").catch(() => "");
  let title = rel;
  try {
    await page.goto(`http://127.0.0.1:${PORT}/${rel.split("/").map(encodeURIComponent).join("/")}`, { waitUntil: "load", timeout: 15000 });
    title = (await page.title()) || rel;
    await page.waitForTimeout(1500);
    const atLoad = await text();
    if (errors.length) add("errors while loading: " + errors.splice(0).slice(0, 3).join(" | "));

    // 2. nobody touches it
    await page.waitForTimeout(IDLE_S * 1000);
    const idle = await text();
    const m = idle.match(OVER);
    if (m && !OVER.test(atLoad)) add(`"${m[0]}" appeared after ${IDLE_S} s with no input - does it start before you tap?`);
    if (errors.length) add("errors while idle: " + errors.splice(0).slice(0, 3).join(" | "));

    // 3. press Start and play a little
    const candidates = page.locator("button, [role=button], a, input[type=button], input[type=submit]");
    const n = Math.min(await candidates.count(), 60);
    let pressed = null;
    for (let i = 0; i < n; i++) {
      const el = candidates.nth(i);
      if (!(await el.isVisible().catch(() => false))) continue;
      const label = ((await el.innerText().catch(() => "")) || (await el.getAttribute("aria-label")) || (await el.getAttribute("value")) || "").trim();
      if (START.test(label) && !SKIP.test(label)) { pressed = { el, label }; break; }
    }
    if (pressed) {
      if (vp.hasTouch && vp.isMobile) await pressed.el.tap({ timeout: 3000 }).catch(() => pressed.el.click({ timeout: 3000 }).catch(() => {}));
      else await pressed.el.click({ timeout: 3000 }).catch(() => {});
      const t0 = Date.now(), cx = vp.width / 2, cy = vp.height / 2;
      while (Date.now() - t0 < PLAY_S * 1000) {
        const x = cx + (Math.random() - 0.5) * vp.width * 0.6, y = cy + (Math.random() - 0.5) * vp.height * 0.5;
        if (vp.isMobile) await page.touchscreen.tap(x, y).catch(() => {}); else await page.mouse.click(x, y).catch(() => {});
        await page.keyboard.press(["ArrowLeft", "ArrowRight", "ArrowUp", "Space"][Math.floor(Math.random() * 4)]).catch(() => {});
        await page.waitForTimeout(250);
      }
      if (errors.length) add(`errors after pressing "${pressed.label.slice(0, 30)}": ` + errors.splice(0).slice(0, 3).join(" | "));
    }

    // 4. leftovers showing as words
    const after = await text();
    for (const [when, t] of [["at load", atLoad], ["while playing", after]]) {
      const j = t.match(JUNK);
      if (j) { add(`the word "${j[2]}" is showing ${when}: …${t.slice(Math.max(0, j.index - 30), j.index + 30).replace(/\s+/g, " ")}…`); break; }
    }
  } catch (e) {
    add("could not run: " + e.message.split("\n")[0]);
  }
  await ctx.close();
  return { title, problems };
}

(async () => {
  const apps = process.argv.slice(2);
  const server = await serve();
  const browser = await chromium.launch();
  const out = { checked_at: new Date().toISOString(), apps: [] };
  for (const rel of apps) {
    const problems = []; let title = rel;
    for (const vp of VIEWPORTS) {
      const r = await checkOne(browser, rel, vp);
      title = r.title; problems.push(...r.problems);
    }
    out.apps.push({ app: rel, title, ok: problems.length === 0, problems });
  }
  await browser.close(); server.close();
  process.stdout.write(JSON.stringify(out, null, 1) + "\n");
})();

#!/usr/bin/env node
/**
 * arcade_play_check.js - play EVERY tile of the public Games Arcade (13 Oct 2026).
 *
 * smoke_new_apps.js plays a file. But the Arcade's 64 tiles come from 35 files: the 19
 * party games are screens of one file, the 8 carnival games one canvas build picked by
 * #game=..., the maths tiles one worksheet file with different settings. Playing the
 * files only ever saw their first screen. This opens each tile THROUGH the catalog
 * (index.html#play/<id>), on a phone and a tablet viewport, and like smoke_new_apps.js:
 *   1. records errors while it opens (console, uncaught, failed requests);
 *   2. waits IDLE_S with no input, flags "game over"-type text that appears on its own;
 *   3. presses the most Start-like button in the game, then plays PLAY_S seconds -
 *      taps inside the game and arrow keys - recording errors;
 *   4. flags "null" / "undefined" / "NaN" left showing as text.
 * Canvas games (the carnival) have no buttons to read: they get the taps and keys only.
 *
 *   node arcade_play_check.js [repo root] [tile-id regex]
 * Prints { checked_at, tiles: [{ id, name, ok, problems }] }. Run weekly by
 * arcade_weekly.py. 13 Oct: 64 tiles, 0 broken after SongBox Studio's fixes (6f129cc).
 */
const { chromium } = require("playwright");
const http = require("http"), fs = require("fs"), path = require("path");

const ROOT = path.resolve(process.argv[2] || path.join(__dirname, ".."));
const ONLY = process.argv[3] ? new RegExp(process.argv[3]) : null;
const PORT = 8772, IDLE_S = 15, PLAY_S = 5;
const VIEWPORTS = [{ name: "phone", width: 390, height: 844, mobile: true }, { name: "tablet", width: 1024, height: 1366, mobile: false }];
const OVER = /\b(game over|you lose|you lost|you died|time'?s up|out of lives|no lives left)\b/i;
const START = /^\W*(start|play|let'?s|begin|go\b|tap to (start|play)|new (game|word|item)|ready|spin|roll|deal|flip|shuffle|pick|next|truth)/i;
const SKIP = /sound|mute|music|volume|settings|help|how to|rules|about|back|quit|menu|reset|all games/i;
const JUNK = /(^|[\s:(=])(null|undefined|NaN)(?=[\s.,!?)]|$)/;
// "UNDEFINED" IS ALSO A MATHS WORD (25 Nov 2026). The Algebra tile says "Vertical line: slope is undefined." - correct,
// and it was reported as a value leaking onto the page. The word is let through only when a maths term sits within
// 60 characters of it; "Score: undefined" and "Hello undefined" are still caught, and so are null and NaN anywhere.
const MATHS_NEAR = /\b(slope|gradient|divid\w*|division|by zero|denominator|fraction|tangent|limit|logarithm|square root|expression|vertical line|asymptote)\b/i;
function junkIn(t) {   // -> the first [match, index] that is a leaked value, or null
  const re = new RegExp(JUNK.source, "g"); let m;
  while ((m = re.exec(t))) {
    const at = m.index + m[1].length;
    if (m[2] === "undefined" && MATHS_NEAR.test(t.slice(Math.max(0, at - 60), at + 60 + m[2].length))) continue;
    return [m, m.index];
  }
  return null;
}
// Errors that come from the TEST browser, not the app (13 Oct 2026): headless Chromium has no
// speech voices (speechSynthesis errors) and no microphone, so a recording is empty and
// playing its blob: URL fails with ERR_REQUEST_RANGE_NOT_SATISFIABLE. Real devices have both.
const IGNORE = /SpeechSynthesisErrorEvent|Speech synthesis error|ERR_REQUEST_RANGE_NOT_SATISFIABLE|failed request: blob:/;
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".png": "image/png",
  ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".json": "application/json", ".mp3": "audio/mpeg", ".wav": "audio/wav" };

function serve() {
  return new Promise(res => {
    const s = http.createServer((q, r) => {
      const f = path.join(ROOT, decodeURIComponent(q.url.split("?")[0].split("#")[0]));
      if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { r.writeHead(404); return r.end(); }
      r.writeHead(200, { "Content-Type": TYPES[path.extname(f).toLowerCase()] || "application/octet-stream" });
      fs.createReadStream(f).pipe(r);
    }).listen(PORT, "127.0.0.1", () => res(s));
  });
}

async function playTile(p, vp, id, errs) {
  const probs = [], add = w => probs.push(`${vp.name}: ${w}`), flush = () => [...new Set(errs.splice(0))].slice(0, 3).join(" | ");
  await p.goto("about:blank");                 // a full reload: a hash-only change can catch the player mid-switch
  await p.goto(`http://127.0.0.1:${PORT}/index.html#play/${id}`);
  await p.waitForTimeout(3000);
  const fr = p.frames().find(f => f !== p.mainFrame() && f.url() !== "about:blank");
  if (!fr) { add("the game didn't open"); errs.splice(0); return probs; }
  const text = () => fr.evaluate(() => document.body ? document.body.innerText : "").catch(() => "");
  const t0 = await text();
  if (errs.length) add("errors while opening: " + flush());
  await p.waitForTimeout(IDLE_S * 1000);
  const m = (await text()).match(OVER);
  if (m && !OVER.test(t0)) add(`"${m[0]}" appeared after ${IDLE_S} s with no input`);
  if (errs.length) add("errors while idle: " + flush());
  const cands = fr.locator("button:visible, [role=button]:visible, a:visible, input[type=button]:visible");
  const n = Math.min(await cands.count().catch(() => 0), 80);
  let pressed = "";
  for (let i = 0; i < n; i++) {
    const el = cands.nth(i);
    const label = ((await el.innerText().catch(() => "")) || (await el.getAttribute("aria-label").catch(() => "")) || "").trim();
    if (START.test(label) && !SKIP.test(label)) {
      pressed = label.replace(/\s+/g, " ").slice(0, 24);
      await (vp.mobile ? el.tap({ timeout: 2000 }) : el.click({ timeout: 2000 })).catch(() => {});
      break;
    }
  }
  const box = await p.locator("#player-frame").boundingBox();
  const t9 = Date.now();
  while (box && Date.now() - t9 < PLAY_S * 1000) {
    const x = box.x + box.width * (0.2 + Math.random() * 0.6), y = box.y + box.height * (0.25 + Math.random() * 0.6);
    await (vp.mobile ? p.touchscreen.tap(x, y) : p.mouse.click(x, y)).catch(() => {});
    await p.keyboard.press(["ArrowLeft", "ArrowRight", "ArrowUp", "Space"][Math.floor(Math.random() * 4)]).catch(() => {});
    await p.waitForTimeout(250);
  }
  if (errs.length) add(`errors after pressing "${pressed || "(no Start button - taps only)"}": ` + flush());
  const t2 = await text();
  for (const [w, t] of [["on open", t0], ["while playing", t2]]) {
    const hit = junkIn(t), j = hit && hit[0];
    if (j) { add(`the word "${j[2]}" is showing ${w}: …${t.slice(Math.max(0, j.index - 30), j.index + 30).replace(/\s+/g, " ")}…`); break; }
  }
  return probs;
}

if (process.argv.includes("--self-test")) {
  const cases = [
    ["a leaked value is caught", "Score: undefined", true],
    ["a greeting with a leaked name is caught", "Hello undefined, ready to play?", true],
    ["null and NaN are caught even beside maths words", "The slope is NaN", true],
    ["the maths sense is let through", "m = 0. Vertical line: slope is undefined. Positive slope rises", false],
    ["dividing by zero is let through", "You cannot divide by zero: the answer is undefined.", false],
    ["a leak AFTER a maths sentence is still caught", "The slope is undefined for a vertical line. " + "x".repeat(80) + " Your score: undefined", true],
    ["ordinary text is quiet", "Tap a card to flip it", false],
  ];
  let bad = 0;
  for (const [name, text, want] of cases) { const got = !!junkIn(text); console.log((got === want ? "ok   " : "FAIL ") + name); if (got !== want) bad++; }
  process.exit(bad ? 1 : 0);
}

(async () => {
  const server = await serve();
  const browser = await chromium.launch({ args: ["--mute-audio"] });   // never play through the speakers (25 Nov 2026: the weekly run played every Arcade game aloud)
  const tiles = {};
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, isMobile: vp.mobile, hasTouch: true });
    const p = await ctx.newPage();
    const errs = [];
    p.on("pageerror", e => { const t = "uncaught: " + e.message.split("\n")[0].slice(0, 160); if (!IGNORE.test(t)) errs.push(t); });
    p.on("console", m => { if (m.type() === "error" && !IGNORE.test(m.text())) errs.push(m.text().split("\n")[0].slice(0, 160)); });
    p.on("requestfailed", r => { if (!r.url().startsWith("data:") && !r.url().startsWith("blob:")) errs.push("failed request: " + r.url().slice(-80)); });
    await p.goto(`http://127.0.0.1:${PORT}/index.html`); await p.waitForTimeout(800);
    const list = await p.evaluate(() => Object.keys(REGISTRY).filter(i => !/^https?:/.test(REGISTRY[i].src || ""))
      .map(i => ({ id: i, name: REGISTRY[i].name })));
    errs.splice(0);
    for (const t of list.filter(t => !ONLY || ONLY.test(t.id))) {
      let probs;
      try { probs = await playTile(p, vp, t.id, errs); } catch (e) { probs = [`${vp.name}: could not run: ${e.message.split("\n")[0]}`]; }
      (tiles[t.id] = tiles[t.id] || { id: t.id, name: t.name, problems: [] }).problems.push(...probs);
    }
    await ctx.close();
  }
  await browser.close(); server.close();
  const out = { checked_at: new Date().toISOString(), tiles: Object.values(tiles).map(t => ({ ...t, ok: t.problems.length === 0 })) };
  process.stdout.write(JSON.stringify(out, null, 1) + "\n");
})();

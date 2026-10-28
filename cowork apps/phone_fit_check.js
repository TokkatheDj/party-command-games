#!/usr/bin/env node
/**
 * phone_fit_check.js - does every Arcade game fit a REAL phone screen? (28 Oct 2026)
 *
 * On a phone, the browser's address bar and toolbar take part of the screen, but CSS "100vh"
 * is measured as if they weren't there (Safari, and Chrome while its bar is showing). Amigo's
 * Candy Math sized itself with 100vh and its bottom row sat half off a real iPhone - while every
 * test passed, because a test browser has no bars and its vh is the visible height.
 *
 * This imitates the phone: the visible screen is the smaller height, and every "vh" in the page
 * the phone opens is measured against the taller full screen (the same thing Safari does). Inside
 * an iframe vh is the frame's own height, so pages loaded in a frame are left alone. Each game is
 * opened both ways a child opens it - as an Arcade tile (index.html#play/<id>) and as a direct
 * link to its file - Start is pressed, and it FAILS if a button, canvas, input or link ends below
 * the visible screen and the page can't be scrolled to reach it.
 *
 *   node phone_fit_check.js [repo root] [id-or-file regex]
 * Prints { checked_at, results: [{ what, how, ok, problems }] }.
 */
const { chromium } = require("playwright");
const http = require("http"), fs = require("fs"), path = require("path");

const ROOT = path.resolve(process.argv[2] || path.join(__dirname, ".."));
const ONLY = process.argv[3] ? new RegExp(process.argv[3]) : null;
const PORT = 8773;
// visible size with the browser bars showing, and the full height the phone's vh is measured on
const PHONES = [{ name: "iPhone 14", width: 390, height: 664, full: 844 },
                { name: "iPhone SE", width: 375, height: 553, full: 667 }];
const START = /^\W*(start|play|let'?s|begin|go\b|tap to (start|play)|new (game|word|item)|ready|spin|roll|deal|flip|shuffle|pick|next|truth)/i;
const SKIP = /sound|mute|music|volume|settings|help|how to|rules|about|back|quit|menu|reset|all games/i;
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

// What a child can't reach: things ending below the visible screen, where nothing scrolls to them.
// Runs inside a frame; offsetTop is where that frame sits on the screen, bottom the screen's height.
function unreachable({ offsetTop, bottom }) {
  // Can a FINGER scroll the page? (Code can scroll an overflow:hidden page, a finger can't.)
  // The page scrolls by <html>'s overflow, or <body>'s when <html> leaves it "visible".
  const se = document.scrollingElement || document.documentElement;
  const ho = getComputedStyle(document.documentElement).overflowY, bo = document.body ? getComputedStyle(document.body).overflowY : "visible";
  const pageOverflow = ho !== "visible" ? ho : bo;
  if (pageOverflow !== "hidden" && pageOverflow !== "clip" && se.scrollHeight > innerHeight + 2) return [];
  // ...or a box it sits in, <body> included: a body with height:100% and overflow:auto scrolls
  // itself while the page reports nothing to scroll (four false alarms on 28 Oct)
  const scrollsInside = el => { for (let a = el.parentElement; a && a !== document.documentElement; a = a.parentElement) {
    const o = getComputedStyle(a).overflowY; if ((o === "auto" || o === "scroll") && a.scrollHeight > a.clientHeight + 2) return true; }
    return false; };
  const out = [];
  for (const el of document.querySelectorAll("button, canvas, input, select, textarea, a[href], [role=button]")) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) continue;
    if (r.top + offsetTop >= bottom + 400) continue;            // parked far off-screen on purpose (slide-in panels)
    const over = Math.round(r.bottom + offsetTop - bottom);
    if (over > 4 && !scrollsInside(el)) {
      const label = (el.innerText || el.getAttribute("aria-label") || el.id || el.tagName).replace(/\s+/g, " ").trim().slice(0, 24);
      out.push(`${el.tagName.toLowerCase()} "${label}" ${over}px below the screen`);
    }
  }
  return out;
}

// A real Start/Play first: a "Shuffle" earlier in the page, under the title card, isn't it
const FIRST = /^\W*(start|play|let'?s play|begin|tap to (start|play))/i;
async function pressStart(fr) {
  const cands = fr.locator("button:visible, [role=button]:visible, a:visible, input[type=button]:visible");
  const n = Math.min(await cands.count().catch(() => 0), 80), labels = [];
  for (let i = 0; i < n; i++)
    labels.push(((await cands.nth(i).innerText().catch(() => "")) || (await cands.nth(i).getAttribute("aria-label").catch(() => "")) || "").trim());
  for (const re of [FIRST, START])
    for (let i = 0; i < n; i++)
      if (re.test(labels[i]) && !SKIP.test(labels[i])) {
        await cands.nth(i).tap({ timeout: 2000 }).catch(() => {});
        return labels[i].replace(/\s+/g, " ").slice(0, 20);
      }
  return "";
}

async function check(p, phone, url, inFrame) {
  await p.goto("about:blank");
  await p.goto(url);
  await p.waitForTimeout(inFrame ? 2500 : 1200);
  const fr = inFrame ? p.frames().find(f => f !== p.mainFrame() && f.url() !== "about:blank") : p.mainFrame();
  if (!fr) return ["the game didn't open"];
  const offset = inFrame ? (await (await fr.frameElement()).boundingBox() || { y: 0 }).y : 0;
  const probs = [];
  const look = async when => {
    for (const w of await fr.evaluate(unreachable, { offsetTop: offset, bottom: phone.height }).catch(e => ["could not measure: " + e.message.slice(0, 60)]))
      probs.push(`${phone.name}, ${when}: ${w}`);
  };
  await look("on open");
  const pressed = await pressStart(fr);
  if (pressed) { await p.waitForTimeout(1200); await look(`after "${pressed}"`); }
  return [...new Set(probs)].slice(0, 6);
}

// Make a browser context behave like the phone with its bars showing: "vh" in the page the phone
// opens is measured on the FULL height; pages inside frames are untouched.
async function imitateBars(ctx, phone) {
  const scale = phone.full / 100;
  await ctx.route(/\.html(\?|#|$)/, async (route, req) => {
    const resp = await route.fetch();
    let body = await resp.text();
    if (req.frame() && req.frame().parentFrame() === null)
      body = body.replace(/(\d*\.?\d+)vh\b/g, (m, n) => `${(parseFloat(n) * scale).toFixed(2)}px`);
    await route.fulfill({ response: resp, body });
  });
}

// One page opened directly, on every phone: the problems found (smoke_new_apps.js uses this nightly)
async function fitProblems(browser, url) {
  const out = [];
  for (const phone of PHONES) {
    const ctx = await browser.newContext({ viewport: { width: phone.width, height: phone.height }, isMobile: true, hasTouch: true });
    try { await imitateBars(ctx, phone); out.push(...await check(await ctx.newPage(), phone, url, false)); }
    catch (e) { out.push(`${phone.name}: could not check the fit: ${e.message.split("\n")[0]}`); }
    finally { await ctx.close(); }
  }
  return out;
}
module.exports = { PHONES, imitateBars, check, fitProblems };

if (require.main === module) (async () => {
  const server = await serve();
  const browser = await chromium.launch();
  const results = {};
  for (const phone of PHONES) {
    const ctx = await browser.newContext({ viewport: { width: phone.width, height: phone.height }, isMobile: true, hasTouch: true });
    await imitateBars(ctx, phone);
    const p = await ctx.newPage();
    await p.goto(`http://127.0.0.1:${PORT}/index.html`); await p.waitForTimeout(800);
    const tiles = await p.evaluate(() => Object.keys(REGISTRY).filter(i => !/^https?:/.test(REGISTRY[i].src || ""))
      .map(i => ({ id: i, name: REGISTRY[i].name, src: REGISTRY[i].src })));
    const base = await p.evaluate(() => typeof GAMES_BASE === "string" ? GAMES_BASE : "");
    const files = [...new Set(tiles.map(t => (t.src || "").split("#")[0]).filter(Boolean))];
    const jobs = [...tiles.map(t => ({ what: `${t.name} (${t.id})`, how: "Arcade tile", url: `http://127.0.0.1:${PORT}/index.html#play/${t.id}`, frame: true })),
                  ...files.map(f => ({ what: decodeURIComponent(f), how: "direct link", url: `http://127.0.0.1:${PORT}/${base}${f}`.replace(/ /g, "%20"), frame: false }))];
    for (const j of jobs.filter(j => !ONLY || ONLY.test(j.what))) {
      let probs;
      try { probs = await check(p, phone, j.url, j.frame); } catch (e) { probs = [`${phone.name}: could not run: ${e.message.split("\n")[0]}`]; }
      const k = j.how + "|" + j.what;
      (results[k] = results[k] || { what: j.what, how: j.how, problems: [] }).problems.push(...probs);
    }
    await ctx.close();
  }
  await browser.close(); server.close();
  const out = { checked_at: new Date().toISOString(), results: Object.values(results).map(r => ({ ...r, ok: r.problems.length === 0 })) };
  process.stdout.write(JSON.stringify(out, null, 1) + "\n");
})();

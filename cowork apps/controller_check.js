#!/usr/bin/env node
/**
 * controller_check.js - do game controllers still work on the live arcades? (19 Nov 2026)
 *
 * pad.js (18 Nov) turns an Xbox / PlayStation / Switch controller into the keys and clicks a game
 * understands. It went live on the Games Arcade (129 games), the Amigo Arcade and the AppVerse with
 * nothing watching it: an edit to a game, to an arcade page or to one copy of pad.js could break
 * controllers silently. This drives the LIVE sites with a simulated controller:
 *   - Games Arcade: the D-pad reaches a card, A opens it, the menu stays still while a game is
 *     open, View goes back; then every tile gets pad.js and receives the stick and A (or reads
 *     controllers itself, which is fine);
 *   - Amigo Arcade: front page, the built-in games, and one student game through play.html's
 *     locked frame;
 *   - drift: every copy of pad.js matches the master (cowork apps/pad.js);
 *   - Lance's own setup (added 19 Nov 2026, after the buttons flipped three times in one day): an
 *     iPad in Chrome with a "Pro Controller Extended Gamepad", which reports its bottom button as
 *     B (raw 1). The bottom button must still be A (confirm) everywhere, the D-pad must move a
 *     highlight through game menus, Candy Math must fill the Games Arcade frame, and Squad Leader
 *     and Frontier must fire the laser with A.
 *
 *   node controller_check.js            prints JSON, exit 1 if anything needs a look
 * Run weekly by arcade_weekly.py. Muted browser; no clicks outside the simulated controller.
 */
const { chromium } = require("playwright");
const crypto = require("crypto"), fs = require("fs"), path = require("path");

const GAMES = "https://tokkathedj.github.io/party-command-games/index.html";
const AMIGO = "https://amigo-arcade.vercel.app";
const COPIES = {
  "Games Arcade": "https://tokkathedj.github.io/party-command-games/cowork%20apps/pad.js",
  "Amigo Arcade": AMIGO + "/pad.js",
};
const MASTER = path.join(__dirname, "pad.js");
const sha = s => crypto.createHash("sha1").update(String(s).replace(/\r\n/g, "\n")).digest("hex").slice(0, 12);

// the simulated controller: each frame (the arcade page and each game) reads its own copy, so the
// helpers below press in every frame at once, like a real controller does
const FAKE = () => {
  window.__pad = { buttons: new Array(17).fill(0), axes: [0, 0, 0, 0] };
  navigator.getGamepads = () => [{ index: 0, id: "controller_check (simulated)", connected: true, mapping: "standard",
    timestamp: performance.now(), buttons: __pad.buttons.map(v => ({ pressed: v > 0.5, touched: v > 0, value: v })), axes: __pad.axes.slice() }];
  try { speechSynthesis.speak = () => {}; } catch (e) {}
  try { HTMLMediaElement.prototype.play = function () { return Promise.resolve(); }; } catch (e) {}
};
const LOG = () => { window.__log = []; for (const t of ["keydown", "pointerdown", "click"]) addEventListener(t, e => __log.push(t + ":" + (e.key || (e.target && e.target.tagName) || "")), true); };
const every = (pg, fn, arg) => Promise.all(pg.frames().map(f => f.evaluate(fn, arg).catch(() => {})));
async function press(pg, i) { await every(pg, i => { if (window.__pad) __pad.buttons[i] = 1; }, i); await pg.waitForTimeout(140); await every(pg, i => { if (window.__pad) __pad.buttons[i] = 0; }, i); await pg.waitForTimeout(90); }
async function stick(pg, a) { await every(pg, a => { if (window.__pad) __pad.axes = a; }, a); await pg.waitForTimeout(160); await every(pg, () => { if (window.__pad) __pad.axes = [0, 0, 0, 0]; }); await pg.waitForTimeout(90); }

async function gamesArcade(ctx, out) {
  const pg = await ctx.newPage();
  pg.on("dialog", d => d.dismiss().catch(() => {}));
  const check = (name, ok, detail) => out.checks.push({ site: "Games Arcade", name, ok, detail: detail || "" });
  await pg.goto(GAMES + "?v=" + Date.now(), { waitUntil: "load", timeout: 60000 });
  await pg.waitForTimeout(1500);
  await press(pg, 13); await press(pg, 13);
  const card = await pg.evaluate(() => document.activeElement.classList.contains("card") ? document.activeElement.dataset.id : "");
  check("D-pad reaches a game card", !!card, card);
  await press(pg, 0); await pg.waitForTimeout(2500);
  check("A opens the focused game", await pg.evaluate(id => document.getElementById("player").classList.contains("open") && location.hash.includes(id), card));
  const before = await pg.evaluate(() => document.activeElement.dataset.id || document.activeElement.tagName);
  await press(pg, 15);
  const after = await pg.evaluate(() => document.activeElement.dataset.id || document.activeElement.tagName);
  // the D-pad may move a highlight INSIDE the open game (its own menu, 19 Nov); the arcade's cards must not move
  check("menu stays still while a game is open", after === before || after === "IFRAME", before + " -> " + after);
  await press(pg, 8); await pg.waitForTimeout(600);
  check("View goes back to All Games", await pg.evaluate(() => !document.getElementById("player").classList.contains("open")));

  const ids = await pg.evaluate(() => Object.keys(REGISTRY));
  for (const id of ids) {
    const errs = [];
    const onErr = e => errs.push(e.message);
    pg.on("pageerror", onErr);
    await pg.evaluate(id => { location.hash = "play/" + id; }, id);
    // wait for the game to load and get pad.js (the 1 MB worksheet pages take several seconds)
    let state = "no";
    for (let t = 0; t < 40 && state === "no"; t++) {
      await pg.waitForTimeout(300);
      state = await pg.evaluate(() => { try { const w = document.getElementById("player-frame").contentWindow; return w.AmigoPad ? "yes" : "no"; } catch (e) { return "other-site"; } });
    }
    const tile = { id, ok: true, problem: "" };
    if (state === "other-site") tile.problem = "game is on another site, so pad.js can't be added (fine)";
    else if (state !== "yes") { tile.ok = false; tile.problem = "pad.js never loaded into the game"; }
    else {
      const fr = pg.frames().find(f => f.parentFrame() === pg.mainFrame());
      await fr.evaluate(LOG).catch(() => {});
      await stick(pg, [-1, 0, 0, 0]); await press(pg, 0);
      const got = await fr.evaluate(() => (window.__log || []).join(" ")).catch(() => "(page changed)");
      // on 18 Nov every tile took the simulated keys; a game that reads controllers itself would show up here
      if (!got) { tile.ok = false; tile.problem = "no key or click reached the game (or it now reads controllers itself: then this is fine)"; }
    }
    if (errs.length) { tile.ok = false; tile.problem = (tile.problem ? tile.problem + "; " : "") + "page error: " + errs[0].slice(0, 120); }
    pg.off("pageerror", onErr);
    out.tiles.push(tile);
    await pg.evaluate(() => { location.hash = ""; }); await pg.waitForTimeout(250);
  }
  await pg.close();
}

async function amigoArcade(ctx, out) {
  const check = (name, ok, detail) => out.checks.push({ site: "Amigo Arcade", name, ok, detail: detail || "" });
  let pg = await ctx.newPage();
  await pg.goto(AMIGO + "/?v=" + Date.now(), { waitUntil: "load", timeout: 60000 }); await pg.waitForTimeout(1200);
  await press(pg, 15);
  check("D-pad reaches a game card", await pg.evaluate(() => document.activeElement.classList.contains("card")));
  await pg.close();
  for (const [name, file, act] of [["Oops 3D", "games/oops-c.html", "start"], ["Click Click", "games/click-click.html", "start"], ["Amigo's Candy Math", "games/amigos-candy-math.html", "pointer"]]) {
    pg = await ctx.newPage();
    await pg.goto(AMIGO + "/" + file, { waitUntil: "load", timeout: 60000 }); await pg.waitForTimeout(4000);
    const loaded = await pg.evaluate(() => !!window.AmigoPad);
    await pg.evaluate(LOG);
    if (act === "pointer") {
      await every(pg, () => { __pad.axes = [0, 0, 0.8, 0.6]; }); await pg.waitForTimeout(400); await every(pg, () => { __pad.axes = [0, 0, 0, 0]; });
      await press(pg, 0);
    } else { await press(pg, 0); await stick(pg, [-1, 0, 0, 0]); }
    const got = await pg.evaluate(() => __log.join(" "));
    check(name + ": controller works", loaded && !!got, loaded ? got.slice(0, 80) : "pad.js not loaded");
    await pg.close();
  }
  pg = await ctx.newPage();
  await pg.goto(AMIGO + "/", { waitUntil: "load" }); await pg.waitForTimeout(2500);
  const slug = await pg.evaluate(() => { const a = [...document.querySelectorAll("a.card")].find(a => a.href.includes("play.html?g=")); return a ? a.href : ""; });
  if (!slug) check("a student game through the locked frame", false, "no student game listed");
  else {
    await pg.goto(slug, { waitUntil: "load" }); await pg.waitForTimeout(3500);
    const fr = pg.frames().find(f => f !== pg.mainFrame());
    const sandbox = await pg.evaluate(() => { const f = document.querySelector("#stage iframe"); return f ? f.getAttribute("sandbox") : ""; });
    if (fr) await fr.evaluate(LOG).catch(() => {});
    await press(pg, 14); await press(pg, 0);
    const got = fr ? await fr.evaluate(() => (window.__log || []).join(" ")).catch(() => "") : "";
    check("a student game through the locked frame", sandbox === "allow-scripts" && /keydown:ArrowLeft/.test(got), slug.split("g=")[1] + " | " + got.slice(0, 60));
  }
  await pg.close();
}

// ---- Lance's iPad + Nintendo-layout controller (19 Nov 2026) ----
const IPAD_UA = "Mozilla/5.0 (iPad; CPU OS 27_2_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/156.0.8078.54 Mobile/15E148 Safari/604.1";
const PRO_ID = "Pro Controller Extended Gamepad";
const BOTTOM = 1;   // on this controller the bottom button arrives as raw button 1 (it is printed B)
const FAKE_PRO = id => {
  Object.defineProperty(navigator, "maxTouchPoints", { get: () => 5 });
  window.__pad = { buttons: new Array(17).fill(0), axes: [0, 0, 0, 0] };
  navigator.getGamepads = () => [{ index: 0, id, connected: true, mapping: "standard", timestamp: performance.now(),
    buttons: __pad.buttons.map(v => ({ pressed: v > 0.5, touched: v > 0, value: v })), axes: __pad.axes.slice() }];
  try { speechSynthesis.speak = () => {}; } catch (e) {}
  try { HTMLMediaElement.prototype.play = function () { return Promise.resolve(); }; } catch (e) {}
  // the iPad fault Candy Math tripped over: inside a frame, visualViewport can report 0
  if (window.self !== window.top && window.visualViewport) try { Object.defineProperty(visualViewport, "height", { get: () => 0 }); } catch (e) {}
};
const highlight = f => f.evaluate(() => { const h = document.querySelector(".amigo-pad-focus"); return h ? (h.innerText || h.getAttribute("aria-label") || h.tagName).trim().slice(0, 24) : ""; });

async function ipadPro(browser, out) {
  const check = (name, ok, detail) => out.checks.push({ site: "iPad + Pro Controller", name, ok, detail: detail || "" });
  const ctx = await browser.newContext({ viewport: { width: 820, height: 1180 }, userAgent: IPAD_UA, hasTouch: true });
  await ctx.addInitScript(FAKE_PRO, PRO_ID);
  try {
    // 1. Oops 3D: the bottom button is A and presses START
    let pg = await ctx.newPage();
    await pg.goto(AMIGO + "/games/oops-c.html?v=" + Date.now(), { waitUntil: "load", timeout: 60000 }); await pg.waitForTimeout(3500);
    await pg.evaluate(LOG); await press(pg, BOTTOM); await pg.waitForTimeout(600);
    const oops = await pg.evaluate(() => __log.join(" "));
    check("Oops 3D: bottom button = A presses START", /click:BUTTON/.test(oops), oops.slice(0, 80));
    await pg.close();

    // 2. Candy Math (Amigo Arcade): the D-pad moves a highlight through the title menu
    pg = await ctx.newPage();
    await pg.goto(AMIGO + "/games/amigos-candy-math.html?v=" + Date.now(), { waitUntil: "load", timeout: 60000 }); await pg.waitForTimeout(5000);
    await press(pg, 13); const h1 = await highlight(pg);
    await press(pg, 13); const h2 = await highlight(pg);
    check("Candy Math: the D-pad moves the menu highlight", !!h1 && !!h2 && h1 !== h2, (h1 + " -> " + h2).replace(/\s+/g, " "));
    await pg.close();

    // 3. a student game in play.html's locked frame: D-pad highlights, the bottom button presses it
    pg = await ctx.newPage();
    await pg.goto(AMIGO + "/play.html?g=brick-dash-fd47&v=" + Date.now(), { waitUntil: "load", timeout: 60000 }); await pg.waitForTimeout(5000);
    const fr = pg.frames().find(f => f !== pg.mainFrame());
    if (!fr) check("Brick Dash (locked frame): D-pad + A work the menu", false, "no game frame");
    else {
      await press(pg, 13); const hb = await highlight(fr);
      await fr.evaluate(() => { window.__clk = 0; addEventListener("click", () => __clk++, true); });
      await press(pg, BOTTOM);
      const clk = await fr.evaluate(() => window.__clk);
      check("Brick Dash (locked frame): D-pad + A work the menu", !!hb && clk >= 1, "highlight " + (hb || "none").replace(/\s+/g, " ") + " | clicks " + clk);
    }
    await pg.close();

    // 4. Candy Math inside the Games Arcade frame keeps a full-size board (iPad visualViewport fault)
    pg = await ctx.newPage();
    await pg.goto(GAMES.replace("index.html", "cowork%20apps/all-games-hub.html") + "?v=" + Date.now() + "#play/kids-amigoscandym", { waitUntil: "load", timeout: 60000 });
    await pg.waitForTimeout(7000);
    const board = await pg.evaluate(() => { try { const d = document.getElementById("player-frame").contentDocument;
      const c = d.querySelector("#wrap canvas"); if (!c) return -2; const r = c.getBoundingClientRect(); return Math.min(r.width, r.height); } catch (e) { return -1; } });
    check("Candy Math fills the Games Arcade frame", board >= 200, "board side " + Math.round(board) + "px");
    await pg.close();
  } finally { await ctx.close(); }

  // 5. Squad Leader + Frontier read the controller themselves: run their live padByPos as this
  //    iPad + controller, and check the laser is on A
  for (const [name, url] of [["Squad Leader", "https://tokkathedj.github.io/party-command-games/amigo-arcade-games/squad-leader.html"],
                             ["Squad Leader Frontier", "https://tokkathedj.github.io/party-command-games/amigo-arcade-games/squad-leader-frontier.html"]]) {
    let src = "";
    try { const r = await fetch(url + "?v=" + Date.now()); if (r.ok) src = await r.text(); } catch (e) {}
    const m = src.match(/function padByPos\(q\)\{[\s\S]*?\n\}/);
    let mapped = "padByPos not found";
    if (m) try {
      const vm = require("vm"), sb = { navigator: { userAgent: IPAD_UA, maxTouchPoints: 5 }, localStorage: { getItem: () => null } };
      vm.runInNewContext(m[0] + ";this.f=padByPos;", sb);
      const raw = [0, 1, 2, 3].map(i => ({ pressed: i === BOTTOM, value: i === BOTTOM ? 1 : 0 }));
      mapped = sb.f({ id: PRO_ID, buttons: raw.concat(new Array(13).fill({ pressed: false, value: 0 })), axes: [] }).buttons[0].pressed ? "bottom -> A" : "bottom -> not A";
    } catch (e) { mapped = "error: " + e.message; }
    const laserOnA = /edge\(0\)\)fireLaser\(\)/.test(src);
    check(name + ": bottom button is A and A fires the laser", mapped === "bottom -> A" && laserOnA, mapped + " | laser on A: " + laserOnA);
  }
}

async function drift(out) {
  const master = sha(fs.readFileSync(MASTER, "utf8"));
  out.drift.push({ copy: "master (cowork apps/pad.js)", sha: master, ok: true });
  for (const [name, url] of Object.entries(COPIES)) {
    let s = "unreachable", body = "";
    try { const r = await fetch(url + "?v=" + Date.now()); if (r.ok) { body = await r.text(); s = sha(body); } } catch (e) {}
    // the Amigo Arcade serves a forwarder (19 Nov 2026) that loads the shared Games Arcade copy
    const fwd = name === "Amigo Arcade" && s !== "unreachable" && /party-command-games\/cowork%20apps\/pad\.js/.test(body);
    out.drift.push({ copy: name + (fwd ? " (forwarder to the shared copy)" : ""), sha: s, ok: s === master || fwd });
  }
}

(async () => {
  const out = { checked_at: new Date().toISOString(), checks: [], tiles: [], drift: [] };
  const browser = await chromium.launch({ args: ["--mute-audio"] });   // never play through the speakers
  const ctx = await browser.newContext({ viewport: { width: 1024, height: 768 } });
  await ctx.addInitScript(FAKE);
  try { await gamesArcade(ctx, out); } catch (e) { out.checks.push({ site: "Games Arcade", name: "the check itself", ok: false, detail: String(e.message).slice(0, 200) }); }
  try { await amigoArcade(ctx, out); } catch (e) { out.checks.push({ site: "Amigo Arcade", name: "the check itself", ok: false, detail: String(e.message).slice(0, 200) }); }
  try { await ipadPro(browser, out); } catch (e) { out.checks.push({ site: "iPad + Pro Controller", name: "the check itself", ok: false, detail: String(e.message).slice(0, 200) }); }
  await browser.close();
  await drift(out);
  out.ok = out.checks.every(c => c.ok) && out.tiles.every(t => t.ok) && out.drift.every(d => d.ok);
  console.log(JSON.stringify(out, null, 1));
  // not process.exit(): on Windows, Node 24 can abort while fetch's sockets close (see 4a16d18)
  process.exitCode = out.ok ? 0 : 1;
})();

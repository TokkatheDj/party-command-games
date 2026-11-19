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
 *   - drift: every copy of pad.js matches the master (cowork apps/pad.js).
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
  await browser.close();
  await drift(out);
  out.ok = out.checks.every(c => c.ok) && out.tiles.every(t => t.ok) && out.drift.every(d => d.ok);
  console.log(JSON.stringify(out, null, 1));
  // not process.exit(): on Windows, Node 24 can abort while fetch's sockets close (see 4a16d18)
  process.exitCode = out.ok ? 0 : 1;
})();

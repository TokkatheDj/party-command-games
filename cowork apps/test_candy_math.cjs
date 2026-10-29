#!/usr/bin/env node
/**
 * test_candy_math.cjs - the tests that checked every change to Amigo's Candy Math (28 Oct 2026).
 *
 * Each round of changes that day was checked by its own scratch script; they are kept here as
 * one suite so the next change is checked the same way. Sections:
 *   play     - every theme, phone and tablet: a chain scores, Amigo stays hidden until a
 *              question, the question waits for an answer (the board is blocked), a wrong
 *              answer says try again, a right one gives the bonus, every line Amigo says comes
 *              from his recorded voice (never the device's), no sideways scroll, no errors
 *   modes    - one colour per number in every theme; Relax mixes a stuck board with no game
 *              over; Race's clock waits during a question and ends with "Time's up" in his
 *              voice; each mode keeps its own best score
 *   effects  - a small merge gets a small effect and no shower; a big one a much bigger effect,
 *              a shower over the screen and a flash; it all clears; no errors
 *   mathoff  - Relax's Math off switch: no sums, no questions, remembered; Classic still asks
 *   fit      - the board fits a phone with its browser bars showing (phone_fit_check.js)
 *   a11y     - axe (serious + critical) on the title, play and game-over screens, every theme
 *
 *   node test_candy_math.cjs            all sections (a few minutes)
 *   node test_candy_math.cjs modes fit  just those
 *   CANDY_FILE=other.html node ...      test another copy
 * Exits 1 if anything fails.
 */
const path = require("path"), fs = require("fs"), http = require("http");
const { chromium } = require("playwright");

// CANDY_FILE=<path> tests another copy instead (e.g. a deliberately broken one, to check the checks)
const GAME = process.env.CANDY_FILE || path.join(__dirname, "kids_apps", "2026-10-27-amigos-candy-math.html");
const URL = "file:///" + GAME.split(path.sep).join("/");
const AXE = "D:/Documents/Claude Local/canopy-hr/node_modules/axe-core/axe.min.js";
const THEMES = ["sweet", "spooky", "ocean", "volcano", "forest", "space"];
const PHONE = { width: 390, height: 844 }, TABLET = { width: 820, height: 1180 };

let fails = 0;
function ok(cond, what) { if (!cond) fails++; console.log((cond ? "  ok    " : "  FAIL  ") + what); }

async function open(b, vp, theme) {
  const p = await b.newPage({ viewport: vp, isMobile: vp === PHONE, hasTouch: true });
  p.errs = [];
  p.on("pageerror", e => p.errs.push(e.message));
  p.on("console", m => { if (m.type() === "error") p.errs.push(m.text()); });
  await p.goto(URL); await p.waitForTimeout(300);
  if (theme) await p.evaluate(t => setTheme(t), theme);
  return p;
}
async function board(p) {
  const r = await p.$eval("#cv", c => { const q = c.getBoundingClientRect(); return { x: q.x, y: q.y, w: q.width, h: q.height }; });
  return (c, row) => [r.x + (c + .5) * r.w / 5, r.y + (row + .5) * r.h / 6];
}
// a 10-candy chain along the top two rows into a 64
async function bigChain(p) {
  await p.evaluate(() => { const v = [[2, 2, 2, 2, 2], [16, 8, 4, 2, 2]]; for (let r = 0; r < 2; r++) for (let c = 0; c < 5; c++) grid[r][c].v = v[r][c]; });
  const at = await board(p);
  await p.mouse.move(...at(0, 0)); await p.mouse.down();
  for (const [c, r] of [[1, 0], [2, 0], [3, 0], [4, 0], [4, 1], [3, 1], [2, 1], [1, 1], [0, 1]]) await p.mouse.move(...at(c, r), { steps: 5 });
  await p.mouse.up();
}
async function pair(p, row = 5) {
  await p.evaluate(r => { grid[r][0].v = 2; grid[r][1].v = 2; }, row);
  const at = await board(p);
  await p.mouse.move(...at(0, row)); await p.mouse.down(); await p.mouse.move(...at(1, row), { steps: 5 }); await p.mouse.up();
}
const answerOf = q => { const m = q.match(/(\d+) ([+−]) (\d+)/); return m[2] === "+" ? +m[1] + +m[3] : +m[1] - +m[3]; };

const SECTIONS = {
  async play(b) {
    for (const vp of [PHONE, TABLET]) for (const th of THEMES) {
      const tag = `${th}, ${vp === PHONE ? "phone" : "tablet"}:`;
      const p = await open(b, vp, th);
      await p.evaluate(() => startGame()); await p.waitForTimeout(1500);
      await p.evaluate(() => { window.__said = []; window.__dev = 0; const sc = sayClips;
        sayClips = async k => { const r = await sc(k); __said.push([k.join("|"), r]); return r; }; sayDevice = () => { __dev++; }; });
      await bigChain(p); await p.waitForTimeout(700);
      const s = await p.evaluate(() => ({ score, top: document.getElementById("sTopN").textContent }));
      ok(s.score === 64 && s.top === "64", `${tag} a 10-candy chain scores 64`);
      const up = () => p.evaluate(() => getComputedStyle(document.getElementById("amigoBox")).visibility === "visible");
      const cornerFree = () => p.evaluate(() => { const c = document.getElementById("cv").getBoundingClientRect();
        return document.elementFromPoint(c.left + c.width / 10, c.bottom - c.height / 12) === document.getElementById("cv"); });
      ok(!(await up()) && await cornerFree(), `${tag} Amigo hidden while playing, bottom-left tile free`);
      await p.waitForTimeout(3000);
      await p.evaluate(() => askCoach()); await p.waitForTimeout(900);
      const q = await p.evaluate(() => ({ open: coachOpen, q: document.querySelector("#bubble p").textContent, n: document.querySelectorAll("#bubble .choices button").length }));
      const ans = answerOf(q.q);
      ok(q.open && q.n === 3 && ans >= 0 && ans <= 10 && await up(), `${tag} Amigo pops up with a counting question`);
      const before = await p.evaluate(() => moves);
      await pair(p); ok(await p.evaluate(() => moves) === before, `${tag} the board waits during the question`);
      const wrong = await p.evaluate(a => [...document.querySelectorAll("#bubble .choices button")].map(x => +x.dataset.v).find(v => v !== a), ans);
      await p.click(`#bubble .choices button[data-v="${wrong}"]`); await p.waitForTimeout(500);
      ok(await p.evaluate(() => coachOpen && document.querySelector("#bubble .qhint").textContent.length > 3), `${tag} a wrong answer says try again`);
      const sc0 = await p.evaluate(() => score);
      await p.click(`#bubble .choices button[data-v="${ans}"]`); await p.waitForTimeout(1500);
      ok(await p.evaluate(() => score) === sc0 + 20, `${tag} the right answer gives the bonus`);
      await p.waitForTimeout(3000);
      ok(!(await up()) && await cornerFree(), `${tag} Amigo goes again after the answer`);
      const v = await p.evaluate(() => ({ said: __said, dev: __dev }));
      ok(v.dev === 0 && v.said.length >= 3 && v.said.every(x => x[1] === true), `${tag} every line in Amigo's recorded voice (${v.said.length} lines)`);
      ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${tag} no sideways scroll`);
      ok(p.errs.length === 0, `${tag} no errors ${p.errs.join(" | ")}`);
      await p.close();
    }
  },

  async modes(b) {
    const p = await open(b, PHONE);
    const cols = await p.evaluate(() => THEME_ORDER.map(t => THEMES[t].colors.slice(0, 8).join()));
    ok(new Set(cols).size === 1, "every theme gives each number the same colour");
    ok(await p.locator(".modes button").count() === 3, "three mode buttons on the title card");
    await p.evaluate(() => { setMode("relax"); startGame(); }); await p.waitForTimeout(1500);
    await p.evaluate(() => { window.__said = []; const sc = sayClips; sayClips = async k => { const r = await sc(k); __said.push([k.join("|"), r]); return r; }; });
    await p.evaluate(() => { shuffles = 0; grid.forEach((row, r) => row.forEach((t, c) => t.v = Math.pow(2, 1 + ((r * 2 + c * 3) % 9)))); checkOver = true; settling = true; });
    await p.waitForTimeout(1500);
    const rx = await p.evaluate(() => ({ state, hm: hasMove(), btn: document.getElementById("btnShuffle").disabled }));
    ok(rx.state === "play" && rx.hm && !rx.btn, "Relax: a stuck board mixes itself, no game over, Shuffle still usable");
    await p.evaluate(() => { hush(); setMode("race"); startGame(); }); await p.waitForTimeout(500);
    ok(/^⏱ (2:00|1:5)/.test(await p.textContent("#clock")), "Race: the clock shows two minutes");
    await p.evaluate(() => { raceEnd = performance.now() + 5000; askCoach(); }); await p.waitForTimeout(3000);
    ok(await p.evaluate(() => state === "play" && (raceEnd - performance.now()) / 1000 > 4), "Race: the clock waits while Amigo asks");
    await p.evaluate(() => { closeCoach(); raceEnd = performance.now() + 1500; score = 777; best = Math.max(best, score); saveBest(); });
    await p.waitForTimeout(3500);
    ok(await p.evaluate(() => state === "over" && raceDone && /TIME'S\s*UP/i.test(document.getElementById("card").innerText)), "Race: ends with Time's up");
    ok((await p.evaluate(() => __said)).some(x => /^Time's up/.test(x[0]) && x[1] === true), "Race: \"Time's up\" in Amigo's recorded voice");
    const bests = await p.evaluate(() => { const r = {}; for (const m of MODE_ORDER) { setMode(m); r[m] = best; } setMode("classic"); return r; });
    ok(bests.race === 777 && bests.classic !== 777, "each mode keeps its own best score");
    ok(p.errs.length === 0, "no errors " + p.errs.join(" | "));
    await p.close();
  },

  async effects(b) {
    for (const th of THEMES) {
      const p = await open(b, PHONE, th);
      await p.evaluate(() => startGame()); await p.waitForTimeout(1500);
      await pair(p); await p.waitForTimeout(60);
      const small = await p.evaluate(() => ({ fx: fxParts.length, shower: showers.length }));
      await p.waitForTimeout(2500);
      await bigChain(p); await p.waitForTimeout(60);
      const big = await p.evaluate(() => ({ fx: fxParts.length, shower: showers.length, flash: document.getElementById("flash").style.background !== "" }));
      await p.waitForTimeout(4500);
      const after = await p.evaluate(() => fxParts.length + showers.length);
      ok(small.fx > 5 && small.shower === 0, `${th}: a pair of 2s - a small effect (${small.fx}), no shower`);
      ok(big.fx > small.fx * 3 && big.shower > 40 && big.flash, `${th}: 10 candies into 64 - ${big.fx} pieces, a ${big.shower}-piece shower, a flash`);
      ok(after === 0, `${th}: everything clears away`);
      ok(p.errs.length === 0, `${th}: no errors ${p.errs.join(" | ")}`);
      await p.close();
    }
  },

  async mathoff(b) {
    const p = await open(b, PHONE);
    ok(await p.locator("#mathBtn").count() === 0, "no Math switch while Classic is picked");
    await p.evaluate(() => { setMode("relax"); showOverlay("title"); }); await p.waitForTimeout(200);
    ok(await p.getAttribute("#mathBtn", "aria-pressed") === "true", "Relax shows the switch, Math on");
    await p.click("#mathBtn", { force: true }); await p.waitForTimeout(200);
    ok(await p.getAttribute("#mathBtn", "aria-pressed") === "false", "the switch turns Math off");
    await p.click("#ovBtn", { force: true }); await p.waitForTimeout(1500);
    await p.evaluate(() => { moves = 4; score = 195; grid[5][2].v = 4; });
    const at = await board(p);
    await p.evaluate(() => { grid[5][0].v = 2; grid[5][1].v = 2; });
    await p.mouse.move(...at(0, 5)); await p.mouse.down(); await p.mouse.move(...at(1, 5), { steps: 5 }); await p.mouse.move(...at(2, 5), { steps: 5 }); await p.mouse.up();
    await p.waitForTimeout(400);
    const r = await p.evaluate(() => ({ eq: document.getElementById("eq").classList.contains("show"), prev: document.getElementById("preview").textContent, level }));
    ok(!r.eq && /in a row/.test(r.prev) && !/\+/.test(r.prev), "Math off: no sum shown, the panel says \"in a row\"");
    await p.waitForTimeout(4000);
    ok(!(await p.evaluate(() => coachOpen)) && r.level === 2, "Math off: no question after the 5th move or the level-up");
    await p.reload(); await p.waitForTimeout(500);
    ok(await p.getAttribute("#mathBtn", "aria-pressed") === "false", "Math off is remembered");
    await p.evaluate(() => { setMode("classic"); startGame(); }); await p.waitForTimeout(1500);
    await p.evaluate(() => askCoach()); await p.waitForTimeout(300);
    ok(await p.evaluate(() => coachOpen), "Classic still asks questions");
    ok(p.errs.length === 0, "no errors " + p.errs.join(" | "));
    await p.close();
  },

  async fit(b) {
    const fit = require("./phone_fit_check");
    const srv = await new Promise(res => { const s = http.createServer((q, r) => {
      r.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); fs.createReadStream(GAME).pipe(r); }).listen(8781, () => res(s)); });
    const probs = await fit.fitProblems(b, "http://127.0.0.1:8781/candy.html");
    srv.close();
    ok(probs.length === 0, "fits a phone with its browser bars showing (two phones) " + probs.slice(0, 2).join(" | "));
  },

  async a11y(b) {
    if (!fs.existsSync(AXE)) { ok(false, "axe-core not found at " + AXE); return; }
    const axe = fs.readFileSync(AXE, "utf8");
    for (const th of THEMES) for (const st of ["title", "play", "over"]) {
      const p = await open(b, PHONE, th);
      if (st === "title") await p.evaluate(() => showOverlay("title"));
      if (st !== "title") { await p.evaluate(() => startGame()); await p.waitForTimeout(1500); await p.evaluate(() => askCoach()); }
      if (st === "over") await p.evaluate(() => { state = "over"; showOverlay("over"); });
      await p.waitForTimeout(1300);
      await p.addScriptTag({ content: axe });
      const v = await p.evaluate(async () => (await axe.run(document, { resultTypes: ["violations"] })).violations
        .filter(x => x.impact === "serious" || x.impact === "critical").map(x => x.id + " x" + x.nodes.length));
      ok(v.length === 0, `${th}, ${st}${st === "play" ? " (question open)" : ""}: no serious accessibility problems ${v.join(", ")}`);
      await p.close();
    }
  },
};

(async () => {
  const want = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SECTIONS);
  const unknown = want.filter(w => !SECTIONS[w]);
  if (unknown.length) { console.log("unknown section(s): " + unknown.join(", ") + " - try: " + Object.keys(SECTIONS).join(" ")); process.exit(2); }
  const b = await chromium.launch({ args: ["--autoplay-policy=no-user-gesture-required"] });
  for (const w of want) { console.log("\n" + w); await SECTIONS[w](b); }
  await b.close();
  console.log(fails ? `\n${fails} FAILED` : "\nALL PASS");
  process.exit(fails ? 1 : 0);
})();

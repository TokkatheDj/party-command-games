#!/usr/bin/env node
/**
 * double_tap_check.js - does a double-tap press a button on the NEXT screen? (27 Nov 2026)
 *
 * When a button changes the screen, whatever button the new screen puts under the same finger gets the
 * second tap of a double-tap. On 26-27 Nov thirteen Arcade games were played from first tap to last screen
 * and every one of the ten made by the app factory did this somewhere: it skipped the hand-over to the next
 * writer (The Folded Page), showed the referee's answer (Clue Ladder), banked a round unseen (Alphabet
 * Scene), wiped the final scores (Line 'Em Up, Slow Focus) and answered question 1 wrong (Deep Sea Dive
 * Quiz). A two-tap "tap again to confirm" with no pause confirmed itself and wiped every badge (Pepper's
 * Fire Pup Station). All of it was found by hand, because nothing here tested for it. The prompts now carry
 * the rule (=== PLAYS RIGHT ===); this is the check behind it.
 *
 * HOW: the page is opened on a phone and walked forward, one button at a time, by REAL double-taps: two
 * touches 90 ms apart on the same spot. Every click the browser delivers is logged before any page code
 * runs, and again after it has passed through the page, so a click the page's own guard swallowed is seen
 * as swallowed. It FAILS a page when
 *   - the second tap was delivered to a DIFFERENT button, the first button had left the screen, and the
 *     page let that click through; or
 *   - the second tap landed on the SAME button after its label changed to a "tap again / are you sure"
 *     confirmation, and the button did not stay on that label (a confirm needs a pause, or a double-tap
 *     confirms itself).
 * Buttons inside an element marked data-rapid are not tested: that is how a game says "tapping neighbouring
 * buttons fast is the game here" (bubble pop, drum pads), and the same mark switches the page's guard off.
 * Sound / mute / help / quit / reset style buttons are not pressed, so the walk keeps moving forward.
 *
 * It walks at most MAX_PRESSES buttons deep and fills empty text boxes with names so a setup screen can be
 * passed. It does not find a double-tap bug it never walks to; it is a net, not a proof.
 *
 *   node double_tap_check.js kids_apps/a.html party_apps/b.html     paths under this folder, or absolute
 *   node double_tap_check.js --self-test                            prove it fails bad pages and passes guarded ones
 * Prints { checked_at, results: [{ file, ok, problems, pressed }] }; exit 1 if any page fails.
 * smoke_new_apps.js runs doubleTapProblems() on every new app, so new_app_check.py reports it nightly.
 */
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), url = require("url");

const MAX_PRESSES = 18, GAP_MS = 90, SETTLE_MS = 650;
const START = /^\W*(start|play|let'?s|begin|go\b|tap to (start|play)|new (game|word|item)|ready|next|continue|deal|reveal|done|ok\b|got it|pass|show|open)/i;
const SKIP = /sound|mute|music|volume|settings|help|how to|rules|about|back|quit|exit|menu|home|reset|clear|delete|remove|start over|all games|share|print|full ?screen|install|^\W*[x×✕✖]\W*$/i;
const CONFIRM = /again|sure|confirm|really|tap to (clear|quit|delete|reset)/i;
const ADD = /^\W*(\+|add\b)/i;   // "Add player": pressed up to 4 times, a name typed before each, so a 3-player setup can be passed

// Runs in the page before any of its code: log every click as the browser delivers it (window, capture)
// and again if it comes out the other side (window, bubble) without being cancelled.
function instrument() {
  const ids = new WeakMap(); let n = 0;
  const label = b => ((b.getAttribute("aria-label") || b.innerText || b.textContent || "").replace(/\s+/g, " ").trim() || "(no text)").slice(0, 40);
  const idOf = b => { if (!ids.has(b)) ids.set(b, ++n); return ids.get(b); };
  const shown = b => !!(b && b.isConnected && b.getClientRects().length);
  window.__dtap = { log: [], last: null, lastNow: () => { const l = window.__dtap.last; return l ? { shown: shown(l.el), label: label(l.el) } : null; } };
  window.addEventListener("click", e => {
    if (!e.isTrusted) return;
    const b = e.target && e.target.closest ? e.target.closest("button, [role=button], a[href], input[type=button], input[type=submit]") : null;
    const prev = window.__dtap.last;
    const rec = { t: performance.now(), id: b ? idOf(b) : 0, label: b ? label(b) : "", rapid: !!(b && b.closest("[data-rapid]")),
      prevShown: prev ? shown(prev.el) : null, through: false };
    e.__dtap = rec; window.__dtap.log.push(rec); if (b) window.__dtap.last = { el: b };
  }, true);
  window.addEventListener("click", e => { if (e.__dtap && !e.defaultPrevented) e.__dtap.through = true; }, false);
}

// Enabled buttons the page is showing right now (on screen or a scroll away), each tagged so it can be found again.
const listButtons = page => page.evaluate(() => {
  const out = []; let k = 0;
  for (const b of document.querySelectorAll("button, [role=button], input[type=button], input[type=submit]")) {
    b.removeAttribute("data-dtap");
    if (b.disabled || b.getAttribute("aria-disabled") === "true" || b.closest("[data-rapid]")) continue;
    const r = b.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    const st = getComputedStyle(b); if (st.visibility === "hidden" || st.pointerEvents === "none") continue;
    b.setAttribute("data-dtap", String(++k));
    out.push({ k, label: ((b.getAttribute("aria-label") || b.innerText || b.textContent || "").replace(/\s+/g, " ").trim() || "(no text)").slice(0, 40) });
  }
  return out;
});
// Scroll a tagged button into view and say where its middle is - or null if something covers it.
const aim = async (page, k) => {
  await page.locator(`[data-dtap="${k}"]`).first().scrollIntoViewIfNeeded({ timeout: 1500 }).catch(() => {});
  return page.evaluate(k => {
    const b = document.querySelector(`[data-dtap="${k}"]`); if (!b) return null;
    const r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return null;
    const top = document.elementFromPoint(x, y);
    return top && (top === b || b.contains(top)) ? { x, y } : null;
  }, k);
};

/** Problems (strings) for one page address. Empty = no double-tap fell through on the path walked. */
async function doubleTapProblems(browser, address, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  page.on("dialog", d => d.dismiss().catch(() => {}));
  await page.addInitScript(instrument);
  await page.addInitScript(() => { try { speechSynthesis.speak = () => {}; } catch (e) {} });
  const problems = [], pressed = [], tried = new Map();
  try {
    await page.goto(address, { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(900);
    for (let step = 0; step < (opts.maxPresses || MAX_PRESSES); step++) {
      // names for a setup screen, so "Start" is allowed to start
      const boxes = page.locator('input[type=text]:visible, input:not([type]):visible');
      const nb = Math.min(await boxes.count().catch(() => 0), 12);
      for (let i = 0; i < nb; i++) { const el = boxes.nth(i); if (!(await el.inputValue().catch(() => "x"))) await el.fill(["Ana", "Ben", "Cy", "Dee", "Eli", "Fay", "Gus", "Hal", "Ivy", "Jo", "Kit", "Lu"][i]).catch(() => {}); }
      // forward first (Start / Next / Continue: may repeat), then "Add player" (up to 4), then anything not pressed yet
      const cap = b => START.test(b.label) ? 8 : ADD.test(b.label) ? 4 : 1;
      let pick = null, at = null;
      for (let wait = 0; wait < 3 && !pick; wait++) {                 // a reveal or a count-in may still be running
        const fresh = (await listButtons(page)).filter(b => !SKIP.test(b.label) && (tried.get(b.label) || 0) < cap(b));
        for (const c of [...fresh.filter(b => START.test(b.label)), ...fresh.filter(b => ADD.test(b.label)), ...fresh.filter(b => !START.test(b.label) && !ADD.test(b.label))]) {
          at = await aim(page, c.k);
          if (at) { pick = c; break; }
          tried.set(c.label, 99);                                     // covered or unreachable: don't keep trying it
        }
        if (!pick) await page.waitForTimeout(1300);
      }
      if (!pick) break;
      pick.x = at.x; pick.y = at.y;
      tried.set(pick.label, (tried.get(pick.label) || 0) + 1); pressed.push(pick.label);
      const before = await page.evaluate(() => window.__dtap.log.length);
      await page.touchscreen.tap(pick.x, pick.y);
      await page.waitForTimeout(GAP_MS);
      await page.touchscreen.tap(pick.x, pick.y);
      await page.waitForTimeout(SETTLE_MS);
      const log = (await page.evaluate(n => window.__dtap.log.slice(n), before)).filter(c => c.id);
      if (log.length < 2) continue;                                   // the second tap hit no button at all
      const [a, b] = log;
      if (a.rapid || b.rapid || !b.through) continue;                 // a fast-tap area, or the page swallowed it
      if (b.id !== a.id && b.prevShown === false)
        problems.push(`a double-tap on "${a.label}" also pressed "${b.label}" on the next screen`);
      else if (b.id === a.id && b.label !== a.label && CONFIRM.test(b.label)) {
        // The click reaches the page either way; what matters is whether the page ACTED on it. A confirm
        // that waited is still showing its "tap again" label; one that went through has moved on.
        const now = await page.evaluate(() => window.__dtap.lastNow());
        if (!now || !now.shown || now.label !== b.label)
          problems.push(`a double-tap on "${a.label}" confirmed itself: the button changed to "${b.label}" and the second tap went straight through`);
      }
      if (problems.length >= 3) break;
    }
  } catch (e) {
    problems.push("could not walk the page with double-taps: " + String(e.message).slice(0, 120));
  }
  await ctx.close();
  const uniq = [...new Set(problems)];
  return opts.withPath ? { problems: uniq, pressed } : uniq;
}

const GUARD = `(function () { let t0 = 0, el = null, x0 = 0, y0 = 0;
  document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('button');
    if (!b || b.closest('[data-rapid]') || (!e.detail && !e.clientX && !e.clientY)) return;
    const now = performance.now(), gone = el && !(el.isConnected && el.getClientRects().length);
    if (now - t0 < 400 && b !== el && gone && Math.hypot(e.clientX - x0, e.clientY - y0) < 56) { e.stopPropagation(); e.preventDefault(); return; }
    t0 = now; el = b; x0 = e.clientX; y0 = e.clientY; }, true); })();`;
const css = `<style>button{position:absolute;left:40px;top:200px;width:300px;height:80px;font-size:20px}</style>`;
const twoScreens = guard => `<!doctype html><title>t</title>${css}<div id="a"><button id="s">Start</button></div><div id="b" hidden><button id="q">D. Whale shark</button></div>
<script>s.onclick = () => { a.hidden = true; b.hidden = false; }; q.onclick = () => { document.title = "answered"; };${guard}</script>`;
const confirm = pause => `<!doctype html><title>t</title>${css}<button id="r">Next</button>
<script>let armed = 0; r.onclick = () => { if (!armed) { armed = performance.now(); r.textContent = "Tap again to confirm"; return; } if (performance.now() - armed < ${pause}) return; document.title = "wiped"; r.textContent = "Done"; };</script>`;
const rapid = `<!doctype html><title>t</title>${css}<div data-rapid><button id="s">Start</button></div><div id="b" hidden data-rapid><button id="q">Pop</button></div>
<script>s.onclick = () => { s.parentNode.hidden = true; b.hidden = false; }; q.onclick = () => {};</script>`;
const oneScreen = `<!doctype html><title>t</title>${css}<button id="s">Play</button><script>let n = 0; s.onclick = () => { s.textContent = "Play (" + (++n) + ")"; };</script>`;

module.exports = { doubleTapProblems };

if (require.main === module) (async () => {
  const args = process.argv.slice(2);
  const browser = await chromium.launch({ args: ["--mute-audio"] });
  let bad = false;
  if (args[0] === "--self-test") {
    const cases = [
      ["a page whose next screen puts a button under the finger FAILS", twoScreens(""), true],
      ["the same page with the guard PASSES", twoScreens(GUARD), false],
      ["a two-tap confirm with no pause FAILS", confirm(0), true],
      ["a two-tap confirm that waits 700 ms PASSES", confirm(700), false],
      ["a fast-tap area marked data-rapid PASSES", rapid, false],
      ["a button that stays put and is tapped twice PASSES", oneScreen, false]];
    for (const [name, html, shouldFail] of cases) {
      const p = await doubleTapProblems(browser, "data:text/html;charset=utf-8," + encodeURIComponent(html));
      const failed = p.length > 0, ok = failed === shouldFail && !p.some(x => /could not walk/.test(x));
      if (!ok) bad = true;
      console.log(`${ok ? "ok  " : "FAIL"} ${name}${p.length ? "  [" + p[0].slice(0, 110) + "]" : ""}`);
    }
  } else if (!args.length) {
    console.error("usage: node double_tap_check.js <file.html>... | --self-test");
    process.exitCode = 2; await browser.close(); return;
  } else {
    const results = [];
    for (const a of args) {
      const file = path.isAbsolute(a) ? a : path.join(__dirname, a);
      const r = await doubleTapProblems(browser, url.pathToFileURL(file).href, { withPath: true });
      if (r.problems.length) bad = true;
      results.push({ file: a, ok: r.problems.length === 0, problems: r.problems, pressed: r.pressed });
    }
    console.log(JSON.stringify({ checked_at: new Date().toISOString(), results }, null, 1));
  }
  await browser.close();
  process.exitCode = bad ? 1 : 0;   // not process.exit(): see predeploy_check.js (19 Nov 2026)
})();

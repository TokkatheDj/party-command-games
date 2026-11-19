#!/usr/bin/env node
/**
 * storage_block_check.js - does a game still start when the browser blocks saved data? (19 Nov 2026)
 *
 * A browser can refuse localStorage and sessionStorage outright: some privacy settings, and any page
 * shown in a sandboxed frame. The refusal is thrown the moment the page so much as READS
 * window.localStorage - not only when it writes. A game that reads a saved setting at start-up with
 * nothing to catch that stops right there: on 18 Nov, 14 of the 90 game files on the Games Arcade did
 * (Goldilocks Dream Cards and Shake On It showed nothing at all), and so did Carnival Games, Card Match
 * and Party Commands on Netlify. Three more arrived that week (Human Remote, Rule Pile, Common Ground),
 * each found by hand, because nothing here tested for it.
 *
 * HOW: the page's HTML is put in a sandboxed frame WITHOUT "allow-same-origin". There the browser
 * itself throws SecurityError on localStorage / sessionStorage - nothing is imitated. Two earlier ways
 * of faking the refusal were thrown away on 18 Nov: one could not be undone by a page's own guard, the
 * other did not block at all and passed the broken originals. A check that the broken files pass is
 * not a check, so `--self-test` proves this one bites before you trust it.
 *
 * It FAILS a page only for an uncaught error that names localStorage or sessionStorage. Other things a
 * sandboxed frame refuses (cookies, IndexedDB, service workers) are not this check's business.
 *
 *   node storage_block_check.js kids_apps/a.html party_apps/b.html     paths under this folder, or absolute
 *   node storage_block_check.js --self-test                            prove it fails a bad page and passes a guarded one
 * Prints { checked_at, results: [{ file, ok, problems }] }; exit 1 if any page fails.
 * smoke_new_apps.js runs storageProblems() on every new app, so new_app_check.py reports it nightly.
 */
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");

const STORAGE = /\b(localStorage|sessionStorage)\b/;
const esc = s => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;");

/** Problems (strings) for one page's HTML. Empty = it starts with saved data refused. */
async function storageProblemsForHtml(browser, html) {
  const ctx = await browser.newContext({ viewport: { width: 1024, height: 768 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(String(e.message || e)));
  page.on("dialog", d => d.dismiss().catch(() => {}));
  let refused = null;
  try {
    await page.setContent(
      `<!doctype html><body style="margin:0"><iframe sandbox="allow-scripts" style="border:0;width:1024px;height:768px" srcdoc="${esc(html)}"></iframe></body>`,
      { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(1500);
    // Is storage really refused in there? A raw read through a fresh, untouched window answers that even
    // when the page has swapped in its own stand-in (which is the fix working, not the block failing).
    const frame = page.frames().find(f => f !== page.mainFrame());
    refused = frame ? await frame.evaluate(() => {
      try {
        const f = document.createElement("iframe"); f.style.display = "none"; document.documentElement.appendChild(f);
        try { void f.contentWindow.localStorage; return false; } catch (e) { return true; } finally { f.remove(); }
      } catch (e) { return null; }
    }).catch(() => null) : null;
  } catch (e) {
    await ctx.close();
    return ["could not load the page to test saved data being blocked: " + String(e.message).slice(0, 120)];
  }
  await ctx.close();
  const problems = [];
  if (refused === false) problems.push("the test did not block saved data, so this result means nothing (storage_block_check.js needs a look)");
  const hit = errors.filter(e => STORAGE.test(e));
  if (hit.length) problems.push("stops when the browser blocks saved data - reads localStorage or sessionStorage with nothing to catch the refusal: " + hit[0].slice(0, 140));
  return problems;
}

async function storageProblems(browser, file) {
  let html;
  try { html = fs.readFileSync(file, "utf8"); } catch (e) { return []; }   // unreadable: the load check reports it
  return storageProblemsForHtml(browser, html);
}

const BAD = `<!doctype html><title>bad</title><button id="b">Start</button><script>var muted = localStorage.getItem("m") === "1"; document.getElementById("b").textContent = "Ready";</script>`;
const GOOD = `<!doctype html><title>good</title><button id="b">Start</button><script>var muted = false; try { muted = localStorage.getItem("m") === "1"; } catch (e) {} document.getElementById("b").textContent = "Ready";</script>`;
const NONE = `<!doctype html><title>none</title><button>Start</button><script>document.title = "no storage";</script>`;

module.exports = { storageProblems, storageProblemsForHtml };

if (require.main === module) (async () => {
  const args = process.argv.slice(2);
  const browser = await chromium.launch({ args: ["--mute-audio"] });
  let bad = false;
  if (args[0] === "--self-test") {
    const cases = [["a page that reads localStorage unguarded FAILS", BAD, true], ["a page that guards it PASSES", GOOD, false], ["a page that never touches it PASSES", NONE, false]];
    for (const [name, html, shouldFail] of cases) {
      const p = await storageProblemsForHtml(browser, html);
      const failed = p.length > 0, ok = failed === shouldFail && !p.some(x => /did not block/.test(x));
      if (!ok) bad = true;
      console.log(`${ok ? "ok  " : "FAIL"} ${name}${p.length ? "  [" + p[0].slice(0, 90) + "]" : ""}`);
    }
  } else if (!args.length) {
    console.error("usage: node storage_block_check.js <file.html>... | --self-test");
    process.exitCode = 2; await browser.close(); return;
  } else {
    const results = [];
    for (const a of args) {
      const file = path.isAbsolute(a) ? a : path.join(__dirname, a);
      const problems = await storageProblems(browser, file);
      if (problems.length) bad = true;
      results.push({ file: a, ok: problems.length === 0, problems });
    }
    console.log(JSON.stringify({ checked_at: new Date().toISOString(), results }, null, 1));
  }
  await browser.close();
  process.exitCode = bad ? 1 : 0;   // not process.exit(): see predeploy_check.js (19 Nov 2026)
})();

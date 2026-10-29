#!/usr/bin/env node
/**
 * worksheet_a11y_check.js - the worksheet apps pass the accessibility scan the Arcade holds apps to
 * (axe-core, serious and critical WCAG 2 A/AA issues), in every subject and grade band (29 Oct 2026).
 *
 * The nightly check scans an app once, on its opening screen. The worksheets are one page each with
 * many subjects behind tabs, so a problem on a later tab never showed: on 29 Oct the subject
 * worksheets' grade-band names failed colour contrast only once a band row was open. This opens
 * every subject (and every grade band, where the app has them) at phone and desktop width, in
 * student mode, and scans each.
 *
 *   node worksheet_a11y_check.js [page URL or file ...]
 * Default: the live Arcade Math Worksheets and Subject Worksheets. Prints JSON; exit 1 on any issue
 * (or a page that wouldn't run).
 */
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");

const LIVE = "https://tokkathedj.github.io/party-command-games/cowork%20apps/Educational%20Apps/educational_apps/";
const PAGES = process.argv.slice(2).length ? process.argv.slice(2)
  : [LIVE + "2026-06-26-guided-math-worksheets.html", LIVE + "2026-10-29-guided-subject-worksheets.html"];
const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
// A11Y_WIDTHS=390 scans one width - a lighter run when the machine is short of memory
const WIDTHS = process.env.A11Y_WIDTHS ? process.env.A11Y_WIDTHS.split(",").map(Number) : [390, 1280];

function toUrl(p) {
  return /^(https?|file):/.test(p) ? p : "file:///" + path.resolve(p).replace(/\\/g, "/").replace(/ /g, "%20");
}

async function scan(page) {
  await page.addScriptTag({ content: AXE });
  return page.evaluate(async () => (await axe.run(document, { runOnly: ["wcag2a", "wcag2aa"] })).violations
    .filter(v => v.impact === "serious" || v.impact === "critical")
    .map(v => `${v.id} x${v.nodes.length} (e.g. ${v.nodes[0].target.join(" ")})`));
}

(async () => {
  const b = await chromium.launch();
  const pages = [];
  for (const p of PAGES) {
    const url = toUrl(p), issues = new Set(), errors = [];
    let views = 0;
    // A11Y_SUBJECTS=algebra1,trig scans just those subjects (another way to split a long run)
    const only = process.env.A11Y_SUBJECTS ? process.env.A11Y_SUBJECTS.split(",") : null;
    async function open(w) {
      const page = await b.newPage({ viewport: { width: w, height: 900 } });
      page.on("pageerror", e => errors.push(e.message.slice(0, 200)));
      await page.goto(url + (url.includes("?") ? "&" : "?") + "v=" + Date.now(), { waitUntil: "load", timeout: 60000 });
      await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
      await page.reload({ waitUntil: "load" }); await page.waitForTimeout(800);
      return page;
    }
    for (const w of WIDTHS) {
      let subjects = [];
      try { const pg = await open(w); subjects = (await pg.evaluate(() => Object.keys(SUBJECTS))).filter(s => !only || only.includes(s)); await pg.close(); }
      catch (e) { errors.push(`@${w}px: ` + String(e.message || e).slice(0, 300)); continue; }
      // a fresh tab for each subject: one tab through all 134 math worksheets ran the headless
      // browser out of memory on the Surface (29 Oct), and a crash then lost every later subject
      for (const s of subjects) {
        let page = null;
        try {
          page = await open(w);
          await page.evaluate(s => {
            switchSubject(s);
            if (!document.body.classList.contains("student-mode") && typeof toggleStudentMode === "function") toggleStudentMode();
          }, s);
          await page.waitForTimeout(150);
          // subject worksheets: each grade band of the subject is its own row of topics
          const bands = await page.evaluate(() => [...document.querySelectorAll("#subject-subbar .band-btn")].filter(x => x.offsetParent).map(x => x.dataset.band));
          for (const band of bands.length ? bands : [null]) {
            if (band) { await page.evaluate(bd => switchBand(bd), band); await page.waitForTimeout(150); }
            // every worksheet behind the tab, not just the first: a scan only sees what is showing
            const topics = await page.evaluate(() => [...document.querySelectorAll("#topic-bar .topic-btn")].map((b, i) => i));
            for (const ti of topics.length ? topics : [null]) {
              if (ti !== null) {
                await page.evaluate(i => {
                  document.querySelectorAll("#topic-bar .topic-btn")[i].click();
                  if (typeof activateInteractive === "function" && document.body.classList.contains("student-mode")) activateInteractive();
                }, ti);
                await page.waitForTimeout(80);
              }
              const where = await page.evaluate(() => { const m = document.querySelector(".module.active"); return m ? m.id.replace("mod-", "") : "?"; });
              for (const v of await scan(page)) issues.add(`${s}${band ? "/" + band : ""}/${where} @${w}px: ${v}`);
              views++;
            }
          }
        } catch (e) { errors.push(`${s} @${w}px: ` + String(e.message || e).slice(0, 200)); }
        if (page) await page.close().catch(() => {});
      }
    }
    pages.push({ url, views, issues: [...issues], errors, ok: views > 0 && !issues.size && !errors.length });
  }
  await b.close();
  console.log(JSON.stringify({ checked_at: new Date().toISOString(), pages }, null, 1));
  process.exit(pages.every(p => p.ok) ? 0 : 1);
})();

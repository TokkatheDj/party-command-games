#!/usr/bin/env node
/**
 * worksheet_blanks_check.js - every fill-in spot on the maths worksheets takes typing (28 Oct 2026).
 *
 * Student mode only turned class="blank" into a text box, so the Box Method grid (.box-blank),
 * its like-term lines (.lt-blank), the division boxes (.fill-blank) and the "write a sentence"
 * lines (empty .blank-line) showed as shapes nobody could type in - a student found the Box
 * Method one. This opens every subject and worksheet in student mode and lists any spot with
 * "blank" in its class that has no box in it. Table labels (.g6-blank: the "a", "b", "?" the
 * steps ask for) and answer-key text (.solution-box) are not fill-in spots.
 *
 *   node worksheet_blanks_check.js [page URL or file ...]
 * Default: the live Arcade worksheets and the live Kids Math Play
 * (kids-math-play.netlify.app, hand-deployed from Google Drive). Prints JSON; exit 1 if any
 * spot can't be typed in (or a page wouldn't run). Run weekly by arcade_weekly.py.
 */
const { chromium } = require("playwright");
const path = require("path");

const PAGES = process.argv.slice(2).length ? process.argv.slice(2) : [
  "https://tokkathedj.github.io/party-command-games/cowork%20apps/Educational%20Apps/educational_apps/2026-06-26-guided-math-worksheets.html",
  "https://kids-math-play.netlify.app/",
];
const NOT_SPOTS = ["blank-line", "blank-text", "g6-blank"];

function toUrl(p) {
  return /^(https?|file):/.test(p) ? p : "file:///" + path.resolve(p).replace(/\\/g, "/").replace(/ /g, "%20");
}

async function checkPage(browser, url) {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(url + (url.includes("?") ? "&" : "?") + "v=" + Date.now(), { waitUntil: "load", timeout: 60000 });
  await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
  await page.reload({ waitUntil: "load" });
  await page.waitForTimeout(800);
  const r = await page.evaluate(async (NOT_SPOTS) => {
    const out = { worksheets: 0, problems: 0, boxes: 0, untypeable: [] };
    const seen = new Set();
    for (const subj of Object.keys(SUBJECTS)) {
      switchSubject(subj);
      for (const m of SUBJECTS[subj]) {
        if (seen.has(m.id)) continue;
        seen.add(m.id);
        const mod = document.getElementById("mod-" + m.id);
        if (!mod) continue;
        switchModule(m.id);
        if (!document.body.classList.contains("student-mode")) toggleStudentMode(); else activateInteractive();
        await new Promise(res => setTimeout(res, 20));
        out.worksheets++;
        const missed = {};
        mod.querySelectorAll(".worksheet .problem").forEach(p => {
          out.problems++;
          p.querySelectorAll("[class*=blank]").forEach(el => {
            if (el.closest(".solution-box")) return;
            const empty = el.classList.contains("blank-line") && !el.children.length;
            const c = empty ? "blank-line (empty write-in line)"
              : [...el.classList].find(c => /blank/.test(c) && !NOT_SPOTS.includes(c));
            if (!c) return;
            if (el.querySelector("input, textarea, select")) { out.boxes++; return; }
            missed[c] = (missed[c] || 0) + 1;
          });
        });
        for (const [c, n] of Object.entries(missed)) out.untypeable.push(`${subj}/${m.id} (${m.label}): ${n} x ${c}`);
      }
    }
    return out;
  }, NOT_SPOTS);
  await page.close();
  return { url, ...r, errors: errors.slice(0, 5), ok: !r.untypeable.length && !errors.length && r.worksheets > 0 };
}

(async () => {
  const browser = await chromium.launch();
  const pages = [];
  for (const p of PAGES) {
    const url = toUrl(p);
    try { pages.push(await checkPage(browser, url)); }
    catch (e) { pages.push({ url, ok: false, errors: [String(e.message || e).slice(0, 300)] }); }
  }
  await browser.close();
  console.log(JSON.stringify({ checked_at: new Date().toISOString(), pages }, null, 1));
  process.exit(pages.every(p => p.ok) ? 0 : 1);
})();

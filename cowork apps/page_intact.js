#!/usr/bin/env node
/**
 * page_intact.js - is a single-file app whole? (18 Nov 2026)
 *
 * On 28 Oct the AppVerse copy of Kids Math Play was cut off part-way: its <style> block ran
 * straight into the middle of a graphing function, and the page crashed on load. The live site
 * is hand-deployed from a Google Drive folder with `netlify deploy --prod --dir=.`, which sends
 * whatever is there - a cut-off index.html would go live without any warning.
 *
 * This checks a page's text (no browser, about a second):
 *   - it ends with </html>
 *   - every inline <script> parses
 *   - with --against <url>: it is not more than 10% smaller than that page (the live site)
 *
 *   node page_intact.js "G:\My Drive\Netlify Apps\guided-math-worksheets\index.html" --against https://kids-math-play.netlify.app/
 * Exit 1 on any problem. worksheet_blanks_check.js uses intactProblems() on the live pages weekly.
 */
const fs = require("fs");
const vm = require("vm");

const RUNS_AS_SCRIPT = /^(|text\/javascript|application\/javascript|module)$/i;

function intactProblems(html) {
  const out = [];
  if (!/<\/html>\s*$/i.test(html)) out.push("doesn't end with </html> - the file looks cut off");
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m, n = 0;
  while ((m = re.exec(html))) {
    n++;
    const attrs = m[1];
    if (/\bsrc\s*=/i.test(attrs)) continue;
    const type = ((attrs.match(/\btype\s*=\s*["']?([^"'\s>]+)/i) || [])[1] || "").trim();
    if (!RUNS_AS_SCRIPT.test(type)) continue;            // JSON data, templates
    if (/^module$/i.test(type)) continue;                // import/export won't parse as a classic script
    try { new vm.Script(m[2], { filename: `inline script ${n}` }); }
    catch (e) { out.push(`inline script ${n} doesn't parse: ${String(e.message).split("\n")[0]}`); }
  }
  // a <script> opened but never closed (the 28 Oct cut-off left one)
  const opens = (html.match(/<script\b/gi) || []).length, closes = (html.match(/<\/script>/gi) || []).length;
  if (opens > closes) out.push(`${opens - closes} <script> tag(s) never closed`);
  return out;
}

function sizeProblem(bytes, refBytes, label) {
  if (!refBytes) return null;
  return bytes < refBytes * 0.9
    ? `${bytes.toLocaleString()} bytes is ${Math.round(100 - (100 * bytes) / refBytes)}% smaller than ${label} (${refBytes.toLocaleString()}) - check nothing was cut off before deploying`
    : null;
}

module.exports = { intactProblems, sizeProblem };

if (require.main === module) (async () => {
  const args = process.argv.slice(2);
  const ai = args.indexOf("--against");
  const against = ai >= 0 ? args.splice(ai, 2)[1] : null;
  const file = args[0];
  if (!file) { console.error("usage: node page_intact.js <index.html> [--against <live url>]"); process.exit(2); }
  const html = fs.readFileSync(file, "utf8");
  const bytes = Buffer.byteLength(html);
  const problems = intactProblems(html);
  if (against) {
    try {
      const r = await fetch(against + (against.includes("?") ? "&" : "?") + "v=" + Date.now());
      const live = Buffer.byteLength(await r.text());
      const p = sizeProblem(bytes, live, "the live page"); if (p) problems.push(p);
    } catch (e) { problems.push("couldn't fetch the live page to compare sizes: " + e.message); }
  }
  if (problems.length) { console.log("NOT SAFE TO DEPLOY - " + file + "\n  - " + problems.join("\n  - ")); process.exit(1); }
  console.log(`ok - ${file} is whole (${bytes.toLocaleString()} bytes${against ? ", not smaller than live" : ""})`);
})();

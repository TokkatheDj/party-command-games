#!/usr/bin/env node
/**
 * predeploy_check.js - is a hand-deployed Netlify folder safe to send? (18 Nov 2026)
 *
 * The kids' sites in G:\My Drive\Netlify Apps\<folder> go live with `netlify deploy --prod`,
 * which sends whatever the folder holds. Two ways that goes wrong:
 *   - a cut-off file (28 Oct: a Kids Math Play copy ended mid-script and crashed on load);
 *   - a ROLLBACK: on 18 Nov the Drive copies of Carnival Games (24 Jun build) and Splashy Bubbles
 *     (3 Jul build) were older than what was live (deployed 17 Oct from elsewhere). Deploying
 *     either from Drive would have put a four-month-old version back.
 *
 * For each folder it reads the publish folder (netlify.toml `publish`, else the folder itself),
 * checks every .html is whole and every .js parses, asks Netlify (the logged-in CLI, read-only)
 * for the live address and when it was last deployed, and compares the front page with live:
 *   SAME AS LIVE   - nothing new to deploy
 *   NEW CHANGES    - differs from live and is newer: fine to deploy
 *   ROLLBACK       - differs from live but every file is older than the live deploy: STOP
 *   NOT WHOLE      - a page is cut off or a script doesn't parse: STOP
 *
 *   node predeploy_check.js "G:\My Drive\Netlify Apps\carnival-games"
 *   node predeploy_check.js --all "G:\My Drive\Netlify Apps"
 * Exit 1 if any folder is ROLLBACK or NOT WHOLE.
 */
const fs = require("fs"), path = require("path"), os = require("os"), crypto = require("crypto");
const { execFileSync, execSync } = require("child_process");
const { intactProblems } = require("./page_intact");

const SKIP_DIRS = new Set(["node_modules", ".git", ".netlify", "src", "_backups"]);
const sha = b => crypto.createHash("sha256").update(b).digest("hex");
const day = t => new Date(t).toISOString().slice(0, 16).replace("T", " ") + " UTC";

function publishDir(folder) {
  const toml = path.join(folder, "netlify.toml");
  const m = fs.existsSync(toml) && fs.readFileSync(toml, "utf8").match(/^\s*publish\s*=\s*"([^"]*)"/m);
  return path.resolve(folder, m ? m[1] : ".");
}

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith(".") || SKIP_DIRS.has(e.name)) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out); else out.push(p);
  }
  return out;
}

function jsParses(file) {
  // built bundles are ES modules, service workers are classic scripts: either is fine
  for (const ext of [".mjs", ".cjs"]) {
    const tmp = path.join(os.tmpdir(), `predeploy-${process.pid}-${Date.now()}${ext}`);
    fs.copyFileSync(file, tmp);
    try { execFileSync(process.execPath, ["--check", tmp], { stdio: "pipe" }); return true; }
    catch (e) { /* try the other kind */ }
    finally { fs.rmSync(tmp, { force: true }); }
  }
  return false;
}

function liveSite(folder) {
  const st = path.join(folder, ".netlify", "state.json");
  if (!fs.existsSync(st)) return { err: "no .netlify/state.json - this folder isn't linked to a Netlify site" };
  const id = JSON.parse(fs.readFileSync(st, "utf8")).siteId;
  try {
    const j = JSON.parse(execSync(`netlify api getSite --data "{\\"site_id\\":\\"${id}\\"}"`, { stdio: ["ignore", "pipe", "pipe"], encoding: "utf8" }));
    return { id, url: (j.ssl_url || j.url).replace(/\/?$/, "/"), deployedAt: j.published_deploy && j.published_deploy.published_at };
  } catch (e) { return { id, err: "couldn't ask Netlify about the site (is the netlify CLI installed and logged in?)" }; }
}

async function checkFolder(folder) {
  const name = path.basename(folder);
  const pub = publishDir(folder);
  const problems = [];
  if (!fs.existsSync(path.join(pub, "index.html"))) return { name, status: "NOT WHOLE", problems: [`no index.html in ${path.relative(folder, pub) || "."}`] };
  const files = walk(pub);
  let newest = 0;
  for (const f of files) {
    newest = Math.max(newest, fs.statSync(f).mtimeMs);
    const rel = path.relative(folder, f);
    if (/\.html$/i.test(f)) for (const p of intactProblems(fs.readFileSync(f, "utf8"))) problems.push(`${rel}: ${p}`);
    else if (/\.m?js$/i.test(f) && !jsParses(f)) problems.push(`${rel}: doesn't parse as a script`);
  }
  const site = liveSite(folder);
  if (site.err) return { name, status: "UNKNOWN", problems: [...problems, site.err] };
  if (problems.length) return { name, url: site.url, status: "NOT WHOLE", problems };

  const local = fs.readFileSync(path.join(pub, "index.html"));
  let live;
  try { live = Buffer.from(await (await fetch(site.url + "?v=" + Date.now())).arrayBuffer()); }
  catch (e) { return { name, url: site.url, status: "UNKNOWN", problems: ["couldn't fetch the live page: " + e.message] }; }
  // a Vite page names its bundles: the same names mean the same build, whatever else changed
  const bundles = b => [...b.toString().matchAll(/(?:src|href)="\.?\/?(assets\/[^"]+)"/g)].map(m => m[1]).sort().join(" ");
  const same = sha(local) === sha(live) || (bundles(local) && bundles(local) === bundles(live));
  if (same) return { name, url: site.url, status: "SAME AS LIVE", problems: [] };
  const liveT = site.deployedAt ? Date.parse(site.deployedAt) : 0;
  if (liveT && newest < liveT) return { name, url: site.url, status: "ROLLBACK", problems: [
    `live (deployed ${day(liveT)}) is newer than every file here (newest ${day(newest)}) and differs from it - deploying this folder would put an older version back. Find the newer source first.`] };
  return { name, url: site.url, status: "NEW CHANGES", problems: [] };
}

(async () => {
  const args = process.argv.slice(2);
  const asJson = args.includes("--json");            // arcade_weekly.py reads this
  if (asJson) args.splice(args.indexOf("--json"), 1);
  let folders;
  if (args[0] === "--all") {
    const root = args[1];
    if (!root) { console.error('usage: node predeploy_check.js --all "G:\\My Drive\\Netlify Apps"'); process.exit(2); }
    folders = fs.readdirSync(root, { withFileTypes: true }).filter(e => e.isDirectory() && fs.existsSync(path.join(root, e.name, ".netlify", "state.json"))).map(e => path.join(root, e.name));
  } else if (args[0]) folders = [path.resolve(args[0])];
  else { console.error('usage: node predeploy_check.js <site folder> | --all <Netlify Apps folder>'); process.exit(2); }
  let bad = false;
  const results = [];
  for (const f of folders) {
    const r = await checkFolder(f);
    results.push(r);
    if (r.status === "ROLLBACK" || r.status === "NOT WHOLE") bad = true;
    if (asJson) continue;
    console.log(`${r.status.padEnd(12)} ${r.name}${r.url ? "  " + r.url : ""}`);
    for (const p of r.problems) console.log("             - " + p);
  }
  if (asJson) console.log(JSON.stringify({ checked_at: new Date().toISOString(), sites: results }, null, 1));
  else if (bad) console.log("\nNOT SAFE TO DEPLOY the folders marked ROLLBACK or NOT WHOLE.");
  // Not process.exit(): on Windows, Node 24 aborts with "Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)"
  // when exit() lands while fetch's sockets are still closing, and SHIP IT read that crash as a failed check
  // (19 Nov 2026, right after a correct NEW CHANGES). Setting the code lets Node end by itself.
  process.exitCode = bad ? 1 : 0;
})();

#!/usr/bin/env node
/**
 * Mobile Test Agent for Cowork Apps
 * Tests all HTML apps for bugs using Playwright with mobile/tablet viewports.
 *
 * Usage:
 *   node test_apps.js                  # Test all apps
 *   node test_apps.js --category kids  # Test one category
 *   node test_apps.js --app "star"     # Test apps matching name
 *   node test_apps.js --url http://192.168.0.248:8080  # Test against running server
 *
 * First run: npx playwright install chromium
 */

const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const http = require("http");

// ── Config ────────────────────────────────────────────────────────────────────

const APPS_DIR = __dirname;
const REPORT_DIR = path.join(__dirname, "test_reports");
const PORT = 8765; // internal test server port

const VIEWPORTS = [
  { name: "iPhone 14",  width: 390,  height: 844,  isMobile: true,  hasTouch: true },
  { name: "iPad Pro",   width: 1024, height: 1366, isMobile: false, hasTouch: true },
];

// How long to wait for a page to settle (ms)
const LOAD_TIMEOUT   = 8000;
const SETTLE_TIMEOUT = 2000;

// ── Args ──────────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const getArg = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null; };
const filterCategory = getArg("--category");
const filterApp      = getArg("--app");
const remoteUrl      = getArg("--url");

// ── Discover apps ─────────────────────────────────────────────────────────────

function discoverApps() {
  const apps = [];
  function walk(dir, rel) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const relPath = rel ? path.join(rel, entry.name) : entry.name;
      if (entry.isDirectory()) {
        if (!["test_reports", "node_modules", ".git"].includes(entry.name)) {
          walk(full, relPath);
        }
      } else if (entry.name.endsWith(".html")) {
        const category = relPath.includes(path.sep)
          ? relPath.split(path.sep)[0].replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
          : "Other";
        const stem = entry.name.replace(/\.html$/, "");
        const name = stem.replace(/^\d{4}-\d{2}-\d{2}-/, "").replace(/[-_]/g, " ")
          .replace(/\b\w/g, c => c.toUpperCase());
        apps.push({ name, category, file: full, relPath: relPath.replace(/\\/g, "/") });
      }
    }
  }
  walk(APPS_DIR, "");
  return apps;
}

// ── Minimal file server for local HTML files ──────────────────────────────────

function startFileServer(appsDir) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let filePath = path.join(appsDir, decodeURIComponent(req.url.split("?")[0]));
      if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
        res.writeHead(404); res.end("Not found"); return;
      }
      const ext = path.extname(filePath).toLowerCase();
      const types = { ".html": "text/html", ".js": "application/javascript",
        ".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/json" };
      res.writeHead(200, { "Content-Type": types[ext] || "application/octet-stream" });
      fs.createReadStream(filePath).pipe(res);
    });
    server.listen(PORT, "127.0.0.1", () => resolve(server));
  });
}

// ── Test a single app ─────────────────────────────────────────────────────────

async function testApp(page, url, appName, viewport) {
  const errors = [];
  const warnings = [];
  const networkFailures = [];

  page.on("console", msg => {
    const text = msg.text();
    if (msg.type() === "error") errors.push(text);
    else if (msg.type() === "warning") warnings.push(text);
  });

  page.on("pageerror", err => errors.push(`UNCAUGHT: ${err.message}`));

  page.on("requestfailed", req => {
    const url = req.url();
    if (!url.startsWith("data:")) networkFailures.push(`${req.failure()?.errorText} — ${url}`);
  });

  let loaded = false;
  try {
    await page.goto(url, { timeout: LOAD_TIMEOUT, waitUntil: "domcontentloaded" });
    await page.waitForTimeout(SETTLE_TIMEOUT);
    loaded = true;
  } catch (e) {
    return { loaded: false, errors: [`Load failed: ${e.message}`], warnings, networkFailures, screenshot: null, interactions: [] };
  }

  // Screenshot
  const screenshotPath = path.join(
    REPORT_DIR, "screenshots",
    `${appName.replace(/\s+/g, "_")}_${viewport.name.replace(/\s+/g, "_")}.png`
  );
  await page.screenshot({ path: screenshotPath, fullPage: false });

  // Basic interaction tests
  const interactions = [];

  // Check for buttons/interactive elements
  const buttons = await page.$$("button, [role=button], input[type=button], input[type=submit]");
  if (buttons.length > 0) {
    try {
      await buttons[0].click({ timeout: 2000 });
      await page.waitForTimeout(500);
      interactions.push({ action: "click first button", result: "ok" });
    } catch (e) {
      interactions.push({ action: "click first button", result: `failed: ${e.message}` });
    }
  }

  // Check for canvas elements (many apps use canvas)
  const canvases = await page.$$("canvas");
  if (canvases.length > 0) {
    try {
      const box = await canvases[0].boundingBox();
      if (box) {
        await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        await page.waitForTimeout(300);
        interactions.push({ action: "click canvas center", result: "ok" });
      }
    } catch (e) {
      interactions.push({ action: "click canvas", result: `failed: ${e.message}` });
    }
  }

  // Scroll test
  try {
    await page.evaluate(() => window.scrollBy(0, 200));
    interactions.push({ action: "scroll down", result: "ok" });
  } catch (e) {
    interactions.push({ action: "scroll", result: `failed: ${e.message}` });
  }

  return { loaded, errors, warnings, networkFailures, screenshotPath, interactions };
}

// ── HTML Report ───────────────────────────────────────────────────────────────

function statusBadge(result) {
  if (!result.loaded) return '<span class="badge fail">LOAD FAIL</span>';
  if (result.errors.length > 0) return '<span class="badge error">ERRORS</span>';
  if (result.warnings.length > 0) return '<span class="badge warn">WARNINGS</span>';
  return '<span class="badge pass">PASS</span>';
}

function generateReport(results, elapsed) {
  const pass = results.filter(r => r.results.every(vr => vr.loaded && vr.errors.length === 0)).length;
  const fail = results.length - pass;

  const rows = results.map(({ app, results: vrs }) => {
    const viewportSections = vrs.map(vr => {
      const imgRel = vr.screenshotPath ? path.relative(REPORT_DIR, vr.screenshotPath).replace(/\\/g, "/") : null;
      const errHtml = vr.errors.length
        ? `<ul class="err-list">${vr.errors.map(e => `<li>${escHtml(e)}</li>`).join("")}</ul>` : "";
      const warnHtml = vr.warnings.length
        ? `<ul class="warn-list">${vr.warnings.map(w => `<li>${escHtml(w)}</li>`).join("")}</ul>` : "";
      const netHtml = vr.networkFailures.length
        ? `<ul class="net-list">${vr.networkFailures.slice(0, 5).map(n => `<li>${escHtml(n)}</li>`).join("")}</ul>` : "";
      const imgHtml = imgRel ? `<img src="${imgRel}" loading="lazy" style="max-width:220px;border-radius:8px;border:1px solid #333;margin-top:6px;">` : "";
      return `<div class="vp-section"><strong>${vr.viewport}</strong> ${statusBadge(vr)}${imgHtml}${errHtml}${warnHtml}${netHtml}</div>`;
    }).join("");

    const overallPass = vrs.every(vr => vr.loaded && vr.errors.length === 0);
    return `<tr class="${overallPass ? "pass-row" : "fail-row"}">
      <td><a href="${escHtml(app.relPath)}">${escHtml(app.name)}</a><br><small>${escHtml(app.category)}</small></td>
      <td>${viewportSections}</td>
    </tr>`;
  }).join("\n");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>App Test Report</title>
<style>
  body { font-family: -apple-system, sans-serif; background: #111; color: #ddd; margin: 0; padding: 1rem; }
  h1 { color: #aaf; margin-bottom: 0.3rem; }
  .summary { background: #1a1a2a; border-radius: 10px; padding: 1rem; margin-bottom: 1.5rem; display: flex; gap: 2rem; }
  .stat { text-align: center; }
  .stat-n { font-size: 2rem; font-weight: 700; }
  .stat-l { font-size: 0.8rem; color: #888; }
  .pass-n { color: #4f4; }
  .fail-n { color: #f44; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 0.5rem; border-bottom: 2px solid #333; color: #aaa; }
  td { padding: 0.7rem 0.5rem; vertical-align: top; border-bottom: 1px solid #222; }
  .pass-row td:first-child { border-left: 3px solid #4f4; }
  .fail-row td:first-child { border-left: 3px solid #f44; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; margin-left: 6px; }
  .pass { background: #1a3a1a; color: #4f4; }
  .error, .fail { background: #3a1a1a; color: #f44; }
  .warn { background: #3a2a00; color: #fa0; }
  .err-list, .warn-list, .net-list { margin: 4px 0 0 0; padding-left: 1.2rem; font-size: 0.78rem; }
  .err-list { color: #f88; }
  .warn-list { color: #faa; }
  .net-list { color: #88f; }
  .vp-section { margin-bottom: 0.8rem; }
  a { color: #88aaff; }
  footer { margin-top: 2rem; color: #555; font-size: 0.8rem; }
</style>
</head>
<body>
<h1>Cowork Apps — Test Report</h1>
<div class="summary">
  <div class="stat"><div class="stat-n">${results.length}</div><div class="stat-l">Total Apps</div></div>
  <div class="stat"><div class="stat-n pass-n">${pass}</div><div class="stat-l">Passed</div></div>
  <div class="stat"><div class="stat-n fail-n">${fail}</div><div class="stat-l">Issues</div></div>
  <div class="stat"><div class="stat-n">${Math.round(elapsed / 1000)}s</div><div class="stat-l">Duration</div></div>
</div>
<table>
<thead><tr><th>App</th><th>Results</th></tr></thead>
<tbody>${rows}</tbody>
</table>
<footer>Generated ${new Date().toLocaleString()}</footer>
</body>
</html>`;
}

function escHtml(str) {
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  let apps = discoverApps();

  if (filterCategory) {
    apps = apps.filter(a => a.category.toLowerCase().includes(filterCategory.toLowerCase()));
  }
  if (filterApp) {
    apps = apps.filter(a => a.name.toLowerCase().includes(filterApp.toLowerCase()));
  }

  if (apps.length === 0) {
    console.error("No apps found matching filters.");
    process.exit(1);
  }

  fs.mkdirSync(path.join(REPORT_DIR, "screenshots"), { recursive: true });

  console.log(`\n🧪 Cowork Apps Test Agent`);
  console.log(`   Testing ${apps.length} apps × ${VIEWPORTS.length} viewports\n`);

  let server = null;
  let baseUrl;

  if (remoteUrl) {
    baseUrl = remoteUrl.replace(/\/$/, "");
    console.log(`   Using remote server: ${baseUrl}\n`);
  } else {
    server = await startFileServer(APPS_DIR);
    baseUrl = `http://127.0.0.1:${PORT}`;
    console.log(`   Started local test server on port ${PORT}\n`);
  }

  const browser = await chromium.launch({ headless: true });
  const startTime = Date.now();
  const allResults = [];

  for (const app of apps) {
    const url = `${baseUrl}/${app.relPath}`;
    const appResults = [];
    process.stdout.write(`  ${app.name.padEnd(45)}`);

    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        isMobile: vp.isMobile,
        hasTouch: vp.hasTouch,
        userAgent: vp.isMobile
          ? "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
          : "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
      });
      const page = await context.newPage();
      const result = await testApp(page, url, app.name, vp);
      result.viewport = vp.name;
      appResults.push(result);
      await context.close();
    }

    const hasErrors = appResults.some(r => !r.loaded || r.errors.length > 0);
    console.log(hasErrors ? "✗ ISSUES" : "✓ OK");
    if (hasErrors) {
      for (const r of appResults) {
        if (r.errors.length > 0) {
          console.log(`    [${r.viewport}] ${r.errors[0].slice(0, 100)}`);
        }
      }
    }

    allResults.push({ app, results: appResults });
  }

  await browser.close();
  if (server) server.close();

  const elapsed = Date.now() - startTime;
  const reportPath = path.join(REPORT_DIR, "index.html");
  fs.writeFileSync(reportPath, generateReport(allResults, elapsed));

  const pass = allResults.filter(r => r.results.every(vr => vr.loaded && vr.errors.length === 0)).length;
  const fail = allResults.length - pass;

  console.log(`\n  ✅ ${pass} passed   ❌ ${fail} issues   ⏱ ${Math.round(elapsed / 1000)}s`);
  console.log(`  Report: ${reportPath}\n`);
}

main().catch(err => { console.error(err); process.exit(1); });

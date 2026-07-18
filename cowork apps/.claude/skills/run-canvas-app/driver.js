#!/usr/bin/env node
/**
 * Driver for a single self-contained HTML canvas app in the cowork-apps ecosystem
 * (canvas + Web Audio + inline JS), e.g. music_apps/2026-06-25-gravity-bells.html.
 *
 *   node driver.js <path-to.html> [--wait <ms>] [--shots <dir>]
 *
 * Launches LOCAL headless Chromium (the repo's bundled Playwright), loads the file
 * over file://, reports <title> + document.hidden + the control list + canvas count
 * + any console/page errors, and screenshots the app. If an app-specific driver
 * exists at ./drivers/<basename>.js it is invoked to actually DRIVE the canvas
 * (draw, click, drop, wait, screenshot); otherwise the app is just launched and
 * shot once (plus a second shot after --wait ms).
 *
 * WHY local headless — not the claude-in-chrome / playwright MCP wrappers:
 *   - A backgrounded/remote tab has document.hidden === true, so Chrome PAUSES
 *     requestAnimationFrame and the canvas FREEZES: time-based behavior (settling,
 *     dissolving, decay, generative motion) never advances. A local headless page
 *     is "visible" (hidden === false) so rAF runs and physics actually moves.
 *   - file:// is blocked by both MCP browser wrappers; local Playwright loads it.
 *   - Canvas getImageData from an extension's isolated world returns all-zero
 *     pixels — use screenshots, never a pixel probe.
 *
 * Screenshots land in <dir> (default ./screenshots next to this file).
 */
const path = require("path");
const fs = require("fs");
const { pathToFileURL } = require("url");
const { chromium } = require("playwright"); // resolves via repo node_modules (this file lives under cowork apps/)

function arg(flag) {
  const i = process.argv.indexOf(flag);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

(async () => {
  const file = process.argv.slice(2).find((a) => !a.startsWith("--"));
  if (!file) {
    console.error("Usage: node driver.js <path-to.html> [--wait <ms>] [--shots <dir>]");
    process.exit(1);
  }
  const waitMs = Number(arg("--wait") || 0);
  const shotDir = arg("--shots") || path.join(__dirname, "screenshots");
  fs.mkdirSync(shotDir, { recursive: true });

  const abs = path.resolve(file);
  if (!fs.existsSync(abs)) {
    console.error("No such file: " + abs);
    process.exit(1);
  }
  const base = path.basename(abs).replace(/\.html?$/i, "");
  const url = pathToFileURL(abs).href;

  const errors = [];
  const shots = [];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1200, height: 700 } });
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push("PAGEERROR: " + e.message));

  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(400);

  const report = await page.evaluate(() => ({
    title: document.title,
    hidden: document.hidden, // MUST be false, else rAF is paused and the canvas is frozen
    canvases: document.querySelectorAll("canvas").length,
    controls: [...document.querySelectorAll("select,button,input")]
      .slice(0, 50)
      .map((el) => el.id || (el.textContent || "").trim().slice(0, 18) || el.type)
      .filter(Boolean),
  }));

  const shot = async (label) => {
    const p = path.join(shotDir, `${base}-${label}.png`);
    await page.screenshot({ path: p });
    shots.push(p);
  };
  const wait = (ms) => page.waitForTimeout(ms);

  await shot("load");

  // canvas rect for driving
  const box = await page.$eval("canvas", (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  }).catch(() => null);

  // app-specific driver, if present
  const appDriver = path.join(__dirname, "drivers", base + ".js");
  if (fs.existsSync(appDriver)) {
    try {
      await require(appDriver).drive(page, box, { shot, wait, page });
    } catch (e) {
      errors.push("DRIVER: " + e.message);
    }
  } else if (waitMs > 0) {
    await wait(waitMs);
    await shot("after");
  }

  await browser.close();
  report.consoleErrors = errors;
  report.screenshots = shots;
  console.log(JSON.stringify(report, null, 2));
  console.log(`\nScreenshots: ${shotDir}`);
  if (errors.length) {
    console.log(`\n${errors.length} console/page/driver error(s) — see above.`);
    process.exitCode = 1;
  }
})().catch((e) => {
  console.error("FATAL " + e.message);
  process.exit(1);
});

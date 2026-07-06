#!/usr/bin/env node
/**
 * Driver for the AppVerse local hub server (serve_apps.py).
 * Commands:
 *   node driver.js start   — launch the server in the background (idempotent)
 *   node driver.js stop    — stop the server this driver started
 *   node driver.js status  — report whether port 8080 is listening
 *   node driver.js smoke   — start (if needed), drive the UI with Playwright,
 *                            screenshot light+dark+/build, report console errors
 *
 * Screenshots land in ./screenshots/ next to this file.
 */
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const http = require("http");
const fs = require("fs");
const path = require("path");

const APPS_DIR = path.resolve(__dirname, "..", "..", "..");
const SKILL_DIR = __dirname;
const PORT = 8080;
const BASE_URL = `http://localhost:${PORT}`;
const PID_FILE = path.join(SKILL_DIR, ".server.pid");
const SHOT_DIR = path.join(SKILL_DIR, "screenshots");

function isUp() {
  return new Promise((resolve) => {
    const req = http.get(BASE_URL + "/", { timeout: 1500 }, (res) => {
      res.resume();
      resolve(true);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

async function waitUp(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isUp()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

async function start() {
  if (await isUp()) {
    console.log(`Already running at ${BASE_URL}`);
    return;
  }
  const child = spawn("python", ["serve_apps.py"], {
    cwd: APPS_DIR,
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  });
  child.unref();
  fs.writeFileSync(PID_FILE, String(child.pid));
  const ok = await waitUp(15000);
  if (!ok) {
    console.error("Server did not come up within 15s — check `python serve_apps.py` manually for errors.");
    process.exit(1);
  }
  console.log(`Started (pid ${child.pid}) at ${BASE_URL}`);
}

function stop() {
  if (!fs.existsSync(PID_FILE)) {
    console.log("No pidfile — nothing to stop (server may have been started outside this driver).");
    return;
  }
  const pid = fs.readFileSync(PID_FILE, "utf8").trim();
  try {
    execSync(`taskkill /PID ${pid} /T /F`, { stdio: "ignore" });
    console.log(`Stopped pid ${pid}`);
  } catch {
    console.log(`Process ${pid} was not running.`);
  }
  fs.unlinkSync(PID_FILE);
}

async function status() {
  console.log((await isUp()) ? `UP at ${BASE_URL}` : "DOWN");
}

async function smoke() {
  await start();
  fs.mkdirSync(SHOT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 420, height: 900 } });
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  const report = {};

  // 1. Main hub, light mode (default)
  await page.goto(BASE_URL + "/", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("header h1");
  report.title = await page.title();
  report.h1 = await page.textContent("header h1");
  report.lightHeaderBg = await page.evaluate(() =>
    getComputedStyle(document.querySelector("header")).backgroundColor
  );
  report.dataThemeDefault = await page.evaluate(() =>
    document.documentElement.getAttribute("data-theme")
  );
  await page.screenshot({ path: path.join(SHOT_DIR, "01-light.png") });

  // 2. Toggle to dark, confirm header+panel go purple
  await page.click("#theme-toggle-btn");
  await page.waitForTimeout(150);
  report.darkHeaderBg = await page.evaluate(() =>
    getComputedStyle(document.querySelector("header")).backgroundColor
  );
  report.dataThemeAfterToggle = await page.evaluate(() =>
    document.documentElement.getAttribute("data-theme")
  );
  await page.screenshot({ path: path.join(SHOT_DIR, "02-dark.png") });

  // reset back to light so repeated runs start from the default state
  await page.click("#theme-toggle-btn");

  // 3. Standalone /build page renders and shares the same theme wiring
  await page.goto(BASE_URL + "/build", { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".builder-form");
  report.buildTitle = await page.title();
  await page.screenshot({ path: path.join(SHOT_DIR, "03-build.png") });

  await browser.close();

  report.consoleErrors = consoleErrors;
  console.log(JSON.stringify(report, null, 2));
  console.log(`\nScreenshots: ${SHOT_DIR}`);
  if (consoleErrors.length) {
    console.log(`\n${consoleErrors.length} console error(s) — see above.`);
    process.exitCode = 1;
  }
}

const cmd = process.argv[2];
(async () => {
  if (cmd === "start") await start();
  else if (cmd === "stop") stop();
  else if (cmd === "status") await status();
  else if (cmd === "smoke") await smoke();
  else {
    console.log("Usage: node driver.js <start|stop|status|smoke>");
    process.exit(1);
  }
})();

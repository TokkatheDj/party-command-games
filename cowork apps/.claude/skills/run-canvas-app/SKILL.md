---
name: run-canvas-app
description: Launch and drive a single self-contained HTML canvas app from the cowork-apps ecosystem (music_apps, action_games, dj_music_apps, party_apps, etc.) in a local headless Chromium — load it over file://, drive its canvas with real mouse events, and screenshot before/after to verify it renders, responds, and animates with no console errors. Use for one app file; for the AppVerse hub server (serve_apps.py) use run-appverse instead.
---

# Run a single cowork HTML canvas app

These apps are one self-contained `.html` file each (HTML5 canvas + Web Audio +
inline JS/CSS), e.g. `music_apps/2026-06-25-gravity-bells.html`. This skill
launches one **as a user would** and drives it — it does not run a test suite.

## Launch + drive

From anywhere:

```bash
node "C:/Users/tokka/Claude Local/cowork apps/.claude/skills/run-canvas-app/driver.js" \
  "C:/Users/tokka/Claude Local/cowork apps/music_apps/2026-06-25-gravity-bells.html"
```

The driver prints `<title>`, **`hidden`** (must be `false`), the control list, the
canvas count, and any console/page errors, and writes screenshots to
`run-canvas-app/screenshots/<name>-*.png`.

- If an app-specific driver exists at `drivers/<basename>.js`, it is invoked to
  actually drive the canvas (draw / click / drop / wait / screenshot).
- Otherwise the app is launched and shot once; add `--wait <ms>` for a second shot
  after a delay (to see time-based behavior).

**Open the screenshots and look at them.** A blank frame is a failed launch, not a
pass. The gravity-bells reference shots in `screenshots/` show the expected flow:
`-rest` = 10 marbles resting, `-after` = all dissolved (empty field).

## Why local headless Chromium — NOT the claude-in-chrome / playwright MCP wrappers

These traps each cost real time; the driver sidesteps all of them:

- **rAF is paused in a backgrounded/remote tab.** The claude-in-chrome extension
  drives a remote Chrome whose tab is usually `document.hidden === true`, so Chrome
  pauses `requestAnimationFrame` and the canvas **freezes** — physics/animations
  never advance, so time-based behavior (settling, dissolving, decay, generative
  motion) never happens and the app looks "stuck." A local headless page is
  "visible" (`hidden === false`), so rAF runs and the sim actually moves. Always
  check `hidden` is `false` in the report.
- **`file://` is blocked** by both MCP browser wrappers. Local Playwright loads
  `file://` directly — no dev server needed for a single self-contained file.
- **Canvas pixel readback returns zeros** from an extension's isolated world
  (`getImageData` → all-0 bytes). Verify visually via screenshots, never a pixel
  probe.
- The playwright MCP also tries to `mkdir .playwright-mcp` in the cwd, which fails
  under read-only dirs (e.g. `C:\Program Files\...`). The local driver writes only
  to its own `screenshots/`.

## Driving the canvas (for a new app driver)

The apps attach `mousedown` to the `<canvas>` and `mousemove`/`mouseup` to `window`.
Drive with real Playwright mouse events at coordinates from the canvas rect. Copy
`drivers/2026-06-25-gravity-bells.js` as a template — export
`async drive(page, box, { shot, wait })`, where `box` is the canvas
`{x,y,w,h}`, `shot(label)` screenshots `<name>-<label>.png`, and `wait(ms)` delays:

```js
exports.drive = async (page, box, { shot, wait }) => {
  const px = f => box.x + box.w * f, py = f => box.y + box.h * f;
  await page.mouse.move(px(0.3), py(0.8)); await page.mouse.down();
  await page.mouse.move(px(0.7), py(0.8), { steps: 8 }); await page.mouse.up(); // draw / drag
  await page.click('#someToolButton');                                          // pick a mode
  await page.mouse.click(px(0.5), py(0.75));                                     // tap / act
  await wait(1000); await shot('state-a');
  await wait(4500); await shot('state-b');   // let rAF advance for time-based behavior
};
```

Verified on gravity-bells: theme switch (`--bg` changes), the SOUND picker (replaced
the old scale/key selects), and the stuck-marble dissolve (10 → 0 after ~2.5 s).

## Requirements

- Node + the repo's bundled Playwright (`cowork apps/node_modules/playwright`) with
  Chromium already installed. **No `npm install` needed.** `require('playwright')`
  from the driver resolves via the repo's `node_modules` (the skill lives under
  `cowork apps/`).

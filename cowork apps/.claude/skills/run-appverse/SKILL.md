---
name: run-appverse
description: Build, run, and drive AppVerse (formerly "Cowork Apps"), the local family HTML-app hub server (serve_apps.py). Use when asked to start AppVerse, run/restart the server, take a screenshot of its UI, drive the Build/Apps/Reviews/Notes/Lists tabs, or check the light/dark theme.
---

AppVerse is a single-file Python 3 HTTP server (`serve_apps.py`, stdlib only —
no pip install needed) that serves a hand-rolled SPA at `/` and a standalone
`/build` page. Drive it with the Node/Playwright script at
`.claude/skills/run-appverse/driver.js` (Playwright is already a
`devDependency` in the repo's `package.json` and Chromium is already
downloaded — no `npx playwright install` needed if `node_modules/` is present).

All paths below are relative to `cowork apps/` (the repo root is one level up,
`D:\Documents\Claude Local`, and contains other unrelated projects).

## Prerequisites

Windows host, Python 3 on `PATH`, Node on `PATH`, and `node_modules/`
installed (`npm install` — installs `playwright` only). Verified with
Python 3.14 and Node 24; Chromium launches headless with no extra
`apt-get`/system packages needed on this machine.

## Build

No build step. `serve_apps.py` runs directly.

## Run (agent path)

```bash
cd "cowork apps/.claude/skills/run-appverse"
node driver.js start   # idempotent — no-ops if already listening on :8080
node driver.js smoke    # drives the UI, screenshots, prints a JSON report
node driver.js status   # UP / DOWN
node driver.js stop     # kills only the instance this driver started (see Gotchas)
```

`smoke` is the main entry point: it ensures the server is up, then in one
headless Chromium session it (1) loads `/`, confirms the title/`<h1>` and
records the header background color in light mode, (2) clicks
`#theme-toggle-btn`, confirms `data-theme="dark"` and the header/panel
background turned purple, then toggles back to light so re-runs start
clean, (3) loads `/build` and confirms the standalone builder page renders,
and (4) collects any browser console errors. It exits non-zero if any
console errors were seen.

Screenshots land in `.claude/skills/run-appverse/screenshots/`:
`01-light.png`, `02-dark.png`, `03-build.png`. **Look at them** — a blank
or unstyled page is a real failure even if the JSON report looks fine.

Sample output from a real run against this server:

```json
{
  "title": "AppVerse",
  "h1": "AppVerse",
  "lightHeaderBg": "rgb(255, 255, 255)",
  "dataThemeDefault": null,
  "darkHeaderBg": "rgb(42, 31, 77)",
  "dataThemeAfterToggle": "dark",
  "buildTitle": "Build Your Own App — AppVerse",
  "consoleErrors": []
}
```

| command | what it does |
|---|---|
| `start` | Spawns `python serve_apps.py` in the background if port 8080 isn't already answering; polls until it responds (15s timeout); writes its pid to `.server.pid` |
| `stop` | Reads `.server.pid` and `taskkill /PID <pid> /T /F`s it; no-ops if there's no pidfile |
| `status` | One HTTP GET to `/`; prints `UP at http://localhost:8080` or `DOWN` |
| `smoke` | `start` + full Playwright pass described above |

## Run (human path)

`.\Start-AppServer.ps1` from `cowork apps/` — opens a real browser window,
prints the LAN/Tailscale URLs, and loops forever restarting the Python
process on crash (Ctrl+C to stop). This is what the "Cowork Apps Server
(copy to Startup).vbs" shortcut runs automatically at Windows login — see
Gotchas.

## Test

There's a separate, unrelated Playwright agent, `test_apps.js` (via
`.\Run-Tests.ps1`), that mobile-tests every generated `.html` app in the
category folders — it is not about the hub server's own UI and this skill
doesn't duplicate it. Use `.\Run-Tests.ps1` (or `-Category <name>` /
`-App <name>`) for that; reports open at `test_reports\index.html`.

## Gotchas

- **The server is basically always already running.** A Startup-folder
  shortcut (`Cowork Apps Server (copy to Startup).vbs`) launches
  `Start-AppServer.ps1` at login, which auto-restarts the Python process
  forever. Killing the PID you find with `Get-CimInstance Win32_Process`
  often just means a new one reappears seconds later — don't be surprised
  if `driver.js stop` (which only tracks pids *it* spawned) leaves the
  server up anyway. `start`/`smoke` are written to be idempotent against
  this rather than fight it.
- **`PUBLIC_URL` only affects the shareable-link text and email
  "From"/notification links** (`get_base_url()` in `serve_apps.py`); it is
  not required to load or drive the UI locally. `Start-AppServer.ps1` sets
  it to a Tailscale hostname; the driver doesn't set it and everything
  still renders/functions fine over `http://localhost:8080`.
- **Theme state is `localStorage`-backed and shared** between `/` and
  `/build` (key `appverse-theme`) — toggling on one page changes the
  other's default on next load. `smoke` toggles dark then back to light
  before finishing so repeated runs always start from the same default
  state.
- **No pip install needed.** `serve_apps.py` only imports Python stdlib
  modules (`http.server`, `json`, `smtplib`, etc.) — there's no
  `requirements.txt` and none is needed.

## Troubleshooting

- **`node driver.js start` hangs/times out after 15s**: run
  `python serve_apps.py` directly in a foreground terminal from
  `cowork apps/` and read the traceback — a bad edit to `serve_apps.py`
  (syntax error, etc.) is the usual cause; `python -m py_compile
  serve_apps.py` catches syntax errors faster than waiting out the timeout.
- **Port 8080 shows a stale connection but no `Listen` state** after
  killing a process: that's a lingering `TimeWait` socket, not a real
  listener — `Get-NetTCPConnection -LocalPort 8080 -State Listen` is the
  check that actually matters, `driver.js`'s `isUp()` (an HTTP GET) is more
  reliable than either.

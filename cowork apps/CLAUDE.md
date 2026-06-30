# Software Developer — Cowork Apps

You are a Software Developer building self-contained HTML apps for a local mobile-first app library. Your job is to build apps when asked, following the conventions below exactly.

---

## Project layout

Root: `D:\Documents\Claude Local\cowork apps\`

Apps live in category subfolders. Drop each new app in the right one — the server and test agent auto-discover them:

| Folder | Contents |
|---|---|
| `kids_apps/` | Games and activities for ages 4–10; bright, colorful, large touch targets |
| `adult_puzzle_apps/` | Logic puzzles (Sudoku-style, deduction, grid puzzles); dark polished UI |
| `art_apps/` | Generative and interactive art; canvas-heavy; visually striking |
| `classroom_tools/` | Teacher-facing utilities (timers, pickers, displays) |
| `data_visualization_apps/` | Simulations, physics demos, stats visualizations |
| `educational_apps/` | Learning apps for students; interactive, instructional |
| `health_productivity_apps/` | Wellness trackers, focus tools, productivity aids |
| `music_apps/` | Audio synthesis, rhythm games, music tools (Web Audio API) |

Infrastructure files in root — never modify them:
- `serve_apps.py` + `Start-AppServer.ps1` — HTTP server on port 8080
- `test_apps.js` + `Run-Tests.ps1` — Playwright test agent
- `.app_data.json` — ratings/favorites store

---

## File naming

```
YYYY-MM-DD-kebab-case-name.html
```

Use today's date. Name should be descriptive and unique. Example: `2026-06-25-polyomino-block-fit.html`

---

## HTML app rules

Every app is a **single self-contained `.html` file**. No build step, no external dependencies, no CDN imports. Everything — HTML, CSS, JS, fonts, audio data — must be inline.

### Required boilerplate

```html
<!-- CONCEPT: One-sentence description of what the app is and does. -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>App Name</title>
```

The `<!-- CONCEPT: -->` comment must be the very first line.

> ⚠️ **Viewport meta is mandatory and non-negotiable.** Copy the `<meta name="viewport">` line above **verbatim** — it MUST include `maximum-scale=1.0, user-scalable=no`. A bare `width=device-width, initial-scale=1.0` is NOT acceptable: it lets phones pinch-zoom the app, which breaks the fixed-canvas, mobile-first feel. This is the single most commonly missed guardrail — double-check it before finishing every app.

### CSS conventions

```css
/* Universal reset — always include */
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }

/* Mobile touch — always include on html/body */
html, body {
  margin: 0; padding: 0;
  touch-action: manipulation;
  user-select: none; -webkit-user-select: none;
}
```

- Use **CSS custom properties** (`:root { --var: value; }`) for all colors, spacing, and theme values
- Use **`clamp()`** for font sizes to make them responsive: `font-size: clamp(14px, 3.5vw, 20px)`
- Use **`overflow: hidden`** on `html, body` for full-screen game/app feel (unless the app needs scrolling)
- Use **gradient text** on main headings: `background: linear-gradient(90deg, var(--a), var(--b)); -webkit-background-clip: text; background-clip: text; color: transparent;`

### Theme styles by category

**Kids apps** — bright saturated backgrounds, large emoji or cartoon elements, playful fonts (`"Comic Sans MS", "Trebuchet MS", system-ui`), big tap targets (min 60px)

**Puzzle / adult apps** — dark background (`#0f1420` range), muted panel colors, accent colors for highlights (teal + blue gradient typical), `'Segoe UI', system-ui` font stack

**Art / music apps** — near-black background (`#06070d` range), vivid accent colors, minimal UI chrome

**All others** — dark or neutral, clean, system font stack

### JavaScript conventions

- Vanilla JS only — no frameworks, no libraries
- All JS in a single `<script>` tag at end of `<body>`
- Use `const` / `let`, arrow functions, modern ES2020+ syntax (these run in Chromium via Playwright)
- Web Audio API is fine for music/sound
- Canvas 2D API is fine for drawing/animation
- `requestAnimationFrame` for animation loops
- Store any persistent state in `localStorage` with a namespaced key: `cowork-{appname}-{key}`

### Mobile-first layout rules

- Design for portrait phone first (375px wide baseline), then ensure it works on tablet (768px+)
- Use `min()`, `max()`, `clamp()`, `vw`/`vh` units to make layouts fluid
- All interactive elements: minimum 44px tap target, `cursor: pointer`
- No hover-only interactions — everything must be tappable
- Avoid `position: fixed` overlapping important content on small screens

### Quality checklist before finishing

- [ ] First line is `<!-- CONCEPT: ... -->`
- [ ] Viewport meta is correct (no user-scalable)
- [ ] No external URLs anywhere (no CDN, no fonts API, no images from web)
- [ ] Works at 375px wide without horizontal scroll
- [ ] All buttons/inputs are tappable (≥44px)
- [ ] App has a clear title visible on screen
- [ ] There is a way to restart or reset (for games/puzzles)
- [ ] File is saved in the correct category folder with the correct date prefix

---

## Building apps

When the user describes an app to build:

1. **Identify the category** from the description and pick the right folder
2. **Generate the filename** using today's date
3. **Write the complete HTML file** — do not produce partial code or ask clarifying questions unless the concept is genuinely ambiguous
4. **State the output path** so the user knows exactly where it landed

Build the full app in one pass. Do not produce skeleton code or placeholders.

---

## Server and testing

- Server is already running at `http://192.168.0.248:8080` when `Start-AppServer.ps1` is active
- To run Playwright tests: `.\Run-Tests.ps1` from the apps folder
- Test a single category: `.\Run-Tests.ps1 -Category kids`
- Test reports open at `test_reports\index.html`

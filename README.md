# 🕹️ Games Arcade

**Play now: https://tokkathedj.github.io/party-command-games/**

<img src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=https://tokkathedj.github.io/party-command-games/" alt="QR code" />

One catalog for everything — **Party games**, **Carnival**, and **Kids apps** — in a single searchable menu, **54 games** in all. Tap any card and it opens full-screen; tap **← All Games** to come back. No install, no server, no framework.

## What's inside

- **🎉 Party Games (19)** — Floor is Lava, Simon Says, Red/Green Light, Hot Potato, Musical Chairs, Freeze Dance, Would You Rather, Dice & Coins, Memory Match, Quick Match, Charades, Truth or Dare, Never Have I Ever, Scavenger Hunt, Voice Box, Spin the Wheel, Team Picker, Shell Game, Follow the Pattern
- **🎠 Carnival (8)** — each carnival game as its own card (Basketball Hoops, Spin Reels, Guess the Number, Ring Toss, Critter Boop, Prize Wheel, Duck Gallery), plus **Carnival Midway** for the full hub
- **🧒 Kids Games (27)** — drawing & colors, guided math worksheets, math vocabulary (flashcards, matching & a printable word wall), hidden objects, bubble pop, song maker, memory games, monster makers, and lots more

## Smart answer checking (Math Worksheets)

The **Math Worksheets** app grades by mathematical *value*, not exact text — it accepts equivalent forms (`1/2 = 0.5 = 50%`, `x = 7` ⇔ `7`, `3^6` ⇔ `729`, `2(x+3)` ⇔ `2x+6`) using a compact, self-contained polynomial-equivalence normalizer for symbolic algebra (no external libraries). Answer grading is verified end-to-end across these modules:

> counting · fractions · decimals & percents (fdp) · PEMDAS · exponents · equations · proportions · radicals · slope · graphing lines · polynomial division · polynomial products · derivative rules · absolute value · quadratic formula · systems · factors & multiples · functions

## How it works

`index.html` is the catalog. Each card opens its game in a full-screen iframe, so every app runs isolated — the Phaser-based Carnival build and the vanilla party/kids apps never collide. Party games deep-link straight into the chosen game via the party app's own navigation, and every game is addressable with a `#play/<id>` hash (Back button works).

The same catalog file self-adjusts its paths by filename, so it runs identically:
- locally on the app server (served as `cowork apps/all-games-hub.html`), and
- on GitHub Pages (served as the repo-root `index.html`).

## Direct links

- **Combined catalog (home):** `/`
- **Party Command Games (standalone):** `/party.html`

## Usage

Open the link or scan the QR code. No install, no build step, no dependencies. On mobile, add to your home screen for full-screen play.

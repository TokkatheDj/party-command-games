# Cowork Apps — Scheduled Prompts

Single source of truth for the manually-pasted prompts used to kick off "build a new app" runs for each category. Lives in the repo (not a Google Doc) so it can't drift out of sync silently again.

**Build rules — viewport meta, CSS/JS conventions, file naming, quality checklist — live in `CLAUDE.md`, not here.** Every prompt below just points to it instead of duplicating it. If a build rule changes, edit `CLAUDE.md` once; nothing in this file needs to change.

Each prompt only specifies what's actually category-specific: which folder, what concepts to rotate through, and any category-only quirks.

---

## Template

New category prompts should follow this shape:

```
[Category Name]: Instructions

You are a [role] building ONE brand new, fully functional, self-contained app
as a single HTML file for the Cowork Apps library.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\[folder_name]'
(if this folder does not exist yet, create it first). Read their filenames and,
if short, their <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
[category-specific idea rotation — see filled-in examples below]

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Do not skip or re-derive any of it; CLAUDE.md is authoritative.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\[folder_name]' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it does and how you interact with it
  - Which category/subtype it falls into
  - One thing that makes it insightful or different from what's already there
```

---

## Data & Viz — `data_visualization_apps/`

```
Data & Viz: Instructions

You are a creative data-visualization developer building ONE brand new, fully
functional, self-contained interactive data viz or simulation as a single
HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\data_visualization_apps'
(if this folder does not exist yet, create it first). Read their filenames and,
if short, their <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh data-viz or interactive-simulation idea not yet in this
folder. Rotate through these categories — don't always pick the same type:

  EXPLAINERS / SIMULATIONS: physics sims (pendulum, orbits, projectile),
    epidemic/spread models, population/predator-prey, traffic flow,
    flocking/boids, supply-and-demand, compound growth
  CHART PLAYGROUNDS: interactive chart builders where you tweak inputs and
    watch the chart respond — bar/line/scatter/pie with live controls
  MATH / CONCEPT VISUALIZERS: function graphers, Fourier/wave adders,
    probability simulators (dice, coin, Monte Carlo), fractal explorers,
    geometry demonstrators, statistics samplers
  "WHAT IF" CALCULATORS: tip/loan/mortgage/savings calculators with live
    visual output, unit converters with charts, comparison tools
  DECISION / ANALYSIS: weighted decision matrices, scenario comparison,
    sortable/filterable data tables with sample data
  GENERATIVE/INPUT DATA: let the user enter or randomize a small dataset,
    then visualize and explore it

Make the interactivity the point — sliders, toggles, draggable inputs — so
the relationship between input and output becomes visible and intuitive.
Any math, formulas, or models must be CORRECT — verify the logic across a
range of inputs, not just one example, and label units honestly.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Do not skip or re-derive any of it; CLAUDE.md is authoritative.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\data_visualization_apps' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
  Example: 2026-06-24-predator-prey-sim.html
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it visualizes or simulates and how you interact with it
  - Which category it falls into
  - One thing that makes it insightful or different from the others
```

*(Corrected from the original pasted version: folder was `Data & Viz`, which doesn't exist on disk — the real folder is `data_visualization_apps`. STEP 3's full boilerplate/CSS/JS/checklist block was replaced with a pointer to `CLAUDE.md`, which now owns those rules.)*

---

## Kids Apps — `kids_apps/`

```
Kids Apps: Instructions

You are a creative children's app developer building ONE brand new, fully
functional, self-contained game or activity for ages 4-10 as a single HTML
file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\kids_apps'
(if this folder does not exist yet, create it first). Read their filenames and,
if short, their <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh kids' game or activity idea not yet in this folder.
Rotate through these categories — don't always pick the same type:

  MATCHING / MEMORY: card-flip pairs, spot-the-difference, sorting-by-trait
    games. This folder already has several match/memory games (memory-zoo,
    ranked-memory-match, card-match, find-it) — only pick this category if
    your twist is genuinely different (new mechanic, not just a new skin).
  CATCH / TIMING / REFLEX: falling-object catchers, whack-a-mole style,
    rhythm-tap games, simple platformer-lite reactions
  CREATIVE / MAKER: coloring pages, sticker/character builders, simple
    music-making toys, drawing pads, monster/pet customizers
  STORY / ADVENTURE: pick-a-path mini adventures, animal rescue quests,
    treasure hunts, simple choice-driven narratives with illustrations
  EARLY LEARNING: counting, letters/spelling, shapes & colors, size/sequence
    ordering — dressed up as play, not a worksheet
  MAZE / PUZZLE-LITE: simple mazes, drag-the-piece puzzles, cause-and-effect
    contraptions (marble runs, chain reactions) sized for small hands
  PRETEND PLAY: cafe/shop simulators, pet care, dress-up, simple
    build-your-own-scene toys

Bias toward whatever category is thinnest in the existing folder rather than
whatever's already overrepresented (check the file list from Step 1 first).

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Pay special attention to the Kids Apps theme guidance in CLAUDE.md: bright
saturated backgrounds, large emoji/cartoon elements, playful fonts, and big
tap targets (minimum 60px — bigger than the site-wide 44px minimum, since
this age group has less precise motor control). Do not skip or re-derive any
of it; CLAUDE.md is authoritative.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\kids_apps' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
  Example: 2026-06-24-star-catcher.html
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it is and how a kid plays/interacts with it
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Adult Puzzle Apps — `adult_puzzle_apps/`

```
Adult Puzzle Apps: Instructions

You are a logic-puzzle developer building ONE brand new, fully functional,
self-contained puzzle as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\adult_puzzle_apps'
(if this folder does not exist yet, create it first). Read their filenames and,
if short, their <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh logic-puzzle idea not yet in this folder. Rotate through
these categories — don't always pick the same type:

  GRID LOGIC: Sudoku variants (classic, killer, diagonal), KenKen, Slitherlink,
    Masyu, Nurikabe, Minesweeper-style deduction. (No classic Sudoku or
    Slitherlink in the folder yet — good gaps to fill.)
  PATH / CONNECTION: bridges/Hashi-style, pipe-rotation/circuit-connection,
    Hamiltonian-path puzzles, logic mazes
  NUMBER PLACEMENT: Hidato-style number paths, Futoshiki inequality grids,
    Kakuro cross-sums, number-fill grids
  SPATIAL / SHAPE FITTING: polyomino/pentomino packing, tangram-style
    silhouette fitting, tetromino packing
  DEDUCTION / DETECTIVE: rule-induction puzzles, logic-grid "who owns the
    zebra" style clue deduction, Mastermind-style code breaking, cryptograms
  WORD / LANGUAGE LOGIC: word ladders, anagram chains, cryptic clue solving

Check the file list from Step 1 and bias toward whichever category is thin or
missing (e.g. no classic Sudoku, Slitherlink, Nurikabe, or Mastermind-style
puzzle exists yet as of this writing) rather than a category already covered.

Every generated puzzle MUST have a unique, logic-solvable solution — verify
this programmatically with an actual solver/checker in your generation code,
not by eyeballing one example. An unverified or guess-requiring puzzle is a
broken app, not a minor issue. This is the single most commonly skipped
requirement for this category.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Pay special attention to the Puzzle/Adult Apps theme guidance in CLAUDE.md:
dark background (#0f1420 range), muted panel colors, teal/blue gradient
accents, 'Segoe UI'/system-ui font stack. Do not skip or re-derive any of it;
CLAUDE.md is authoritative.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\adult_puzzle_apps' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
  Example: 2026-06-24-futoshiki-inequality.html
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What the puzzle is and how you solve/interact with it
  - Which category it falls into
  - How you verified every generated puzzle has a unique solution
```

---

## Art Apps — `art_apps/`

```
Art Apps: Instructions

You are a generative-art developer building ONE brand new, fully functional,
self-contained interactive art piece as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\art_apps'
(if this folder does not exist yet, create it first). Read their filenames and,
if short, their <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh generative-art idea not yet in this folder. Rotate
through these categories — don't always pick the same type:

  PARTICLE / FLOW SYSTEMS: attractors, flow fields, gravity wells. This
    folder already has several of these (strange-attractor, flow-field-silk,
    gravity-wells) — only pick this category if the mechanic is genuinely
    new, not just a re-skin.
  PROCEDURAL PATTERN GENERATORS: Truchet tiling (already covered — pick a
    different tiling system), Islamic/geometric tiling, Wave-Function-Collapse
    texture synthesis, Voronoi mosaics
  MATH-DRIVEN DRAWING: harmonograph (already covered), spirograph/Lissajous
    curves, string art / curve stitching, moiré interference patterns
  EMERGENT / ALIFE SYSTEMS: reaction-diffusion and cellular automata are
    already covered — fresh ground here is slime-mold/physarum simulations,
    Conway's-Game-of-Life-style variants with unusual rules, or boids-as-art
  TYPOGRAPHIC / GLITCH ART: text-based glitch effects, ASCII-art generators,
    datamosh-style pixel/scanline effects — not yet represented in this
    folder at all
  INTERACTIVE PAINT TOOLS: symmetry/kaleidoscope painting is covered
    (mirror-bloom) — fresh ground is particle-brush painting or generative
    coloring-book tools distinct from the existing stained-glass generator

Check the file list from Step 1 and bias toward whatever's thin or missing
(typographic/glitch art and string-art/spirograph are notably absent as of
this writing) rather than another particle/flow-field piece.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Pay special attention to the Art/Music theme guidance in CLAUDE.md: near-black
background (#06070d range), vivid accent colors, minimal UI chrome — let the
canvas be the star, not the controls. Do not skip or re-derive any of it;
CLAUDE.md is authoritative.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\art_apps' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
  Example: 2026-06-28-cyclic-spiral-automaton.html
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it generates and how you interact with/control it
  - Which category it falls into
  - One thing that makes it visually or technically different from the others
```

---

## Classroom Tools — `classroom_tools/`

```
Classroom Tools: Instructions

You are a teacher-tools developer building ONE brand new, fully functional,
self-contained classroom utility as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\classroom_tools'
(if this folder does not exist yet, create it first). Read their filenames and,
if short, their <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh teacher-facing utility not yet in this folder. Rotate
through these categories — don't always pick the same type:

  RANDOM SELECTION & GROUPING: name pickers and group makers are already
    covered — only revisit this if the mechanic is genuinely new (e.g. a
    weighted picker, a seating-chart randomizer)
  TIMERS & PACING: a countdown timer and bell-ringer board already exist —
    fresh ground is a multi-station rotation timer or a brain-break/movement
    timer
  GAME SHOW / REVIEW FORMATS: Jeopardy-style review and buzzers are covered
    — fresh ground is a trivia bracket, lifeline-based review board, or a
    live quiz board without buzzers
  SCORING & TRACKING: team scoreboard is covered — fresh ground is an
    individual point/token tracker or a class-economy tracker
  AMBIENT / ENVIRONMENT MONITORING: a noise-level meter already exists —
    fresh ground is an on-task/focus visual signal or a transition-time
    tracker
  POLLING / FEEDBACK: a live poll counter exists — fresh ground is an
    exit-ticket quick-check, an "understanding thermometer" (live
    thumbs-up/down), or an SEL mood check-in board
  DISPLAY / ORGANIZATION BOARDS: a hub and bell-ringer board exist — fresh
    ground is a visual daily schedule/agenda board, a seating-chart display,
    or a "parking lot" question board

Check the file list from Step 1 and bias toward whatever's thin or missing
(a seating-chart tool, an exit-ticket/quick-check, an SEL mood check-in
board, and a multi-station rotation timer are all notably absent as of this
writing) rather than another name picker or scoreboard.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack. One category-specific
requirement on top of that: these tools are read from across a room on a
projector or TV, so text, numbers, and any color-coded state (correct/
incorrect, timer warning, etc.) must stay legible at a distance — favor large
type and high contrast over dense layouts. Do not skip or re-derive anything
else in CLAUDE.md; it is authoritative.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\classroom_tools' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
  Example: 2026-06-28-live-poll-counter.html
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it does and how a teacher would use it during class
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Educational Apps — `educational_apps/`

```
Educational Apps: Instructions

You are an educational-software developer building ONE brand new, fully
functional, self-contained learning app as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\educational_apps'
(if this folder does not exist yet, create it first). Read their filenames and,
if short, their <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh learning-app idea not yet in this folder. Rotate through
these subjects — don't always pick the same one:

  SCIENCE: states of matter, animal classification, and the solar system are
    already covered — fresh ground is chemistry (periodic table/elements),
    earth science (weather, water cycle, rock cycle), human body systems, or
    ecosystems/food webs
  MATH: coordinate geometry, angle estimation, and guided worksheets are
    covered — fresh ground is fractions/decimals, shape/geometry exploration,
    times-table fluency, or an intro to probability and data
  LANGUAGE / LITERACY: word roots are covered — fresh ground is reading
    comprehension with passages and questions, grammar/parts of speech,
    vocabulary building, or spelling patterns. Not represented at all yet.
  SOCIAL STUDIES: world capitals/geography is covered — fresh ground is a
    history timeline explorer, civics/how government works, or world
    cultures. History and civics are completely absent so far.
  LOGIC / COMPUTER SCIENCE: binary/bit building is covered — fresh ground is
    algorithm/sequencing puzzles, simple if/then or loop logic puzzles, or
    boolean logic gates
  LIFE SKILLS / FINANCE: compound interest is covered — fresh ground is
    budgeting basics, understanding a paycheck/taxes, or real-world
    measurement and unit conversion

Check the file list from Step 1 and bias toward whatever's thin or missing —
this folder currently leans STEM-heavy (5 of 10 apps are Science/Math), and
history, civics, and reading/literacy are the most notably absent subjects
as of this writing.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack. One category-specific
requirement on top of that: any factual content (science facts, historical
dates, math rules, definitions) must be verified correct before shipping —
this folder is used for actual learning, so an authoritative-sounding wrong
answer is worse than a missing feature. Do not skip or re-derive anything
else in CLAUDE.md; it is authoritative.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\educational_apps' with filename:
  YYYY-MM-DD-[subject]-kebab-case-name.html   (use today's date)
  Example: 2026-06-27-science-animal-classification-sorter.html
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it teaches and how a student interacts with it
  - Which subject it falls into
  - How you verified the factual/academic content is correct
```

---

## Health/Productivity Apps — `health_productivity_apps/`

```
Health/Productivity Apps: Instructions

You are a wellness-and-productivity app developer building ONE brand new,
fully functional, self-contained tool as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\health_productivity_apps'
(if this folder does not exist yet, create it first). Read their filenames and,
if short, their <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh wellness or productivity idea not yet in this folder.
Rotate through these categories — don't always pick the same type:

  MOVEMENT & FITNESS: an interval trainer and a guided-mobility/stretch-flow
    tool already exist — fresh ground is a strength/workout log or a
    posture/eye-strain reminder (e.g. 20-20-20 rule)
  MINDFULNESS & CALM: a breath pacer and an ambient soundscape studio already
    exist — fresh ground is a standalone guided-meditation timer (distinct
    mechanic from the breath pacer) or a stress/anxiety check-in tool
  PLANNING & FOCUS: a priority planner, a to-do/schedule tool, and a pomodoro
    timer already exist — fresh ground is a weekly-review/reflection tool, a
    goal-setting/vision-board tool, or a decision journal
  TRACKING & LOGGING: habit, water, and mood tracking already exist — fresh
    ground is a sleep tracker, a nutrition/meal log, a screen-time/digital-
    wellbeing tracker, or a reading tracker. None of these exist yet.
  DAILY UTILITY: prayer times already exists — fresh ground is a
    sunrise/sunset or daylight tracker, a medication/supplement reminder, or
    a lightweight personal budget/expense tracker

Check the file list from Step 1 and bias toward whatever's thin or missing —
sleep tracking, journaling/gratitude, screen-time, and a standalone
meditation timer are all notably absent as of this writing.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack. One category-specific
requirement on top of that: trackers and logs are meant to be reopened daily,
so persisting state correctly in localStorage (per CLAUDE.md's
`cowork-{appname}-{key}` convention) is the core value of the app, not an
optional nice-to-have — verify data survives a page reload before finishing.
Do not skip or re-derive anything else in CLAUDE.md; it is authoritative.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\health_productivity_apps' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
  Example: 2026-06-28-focus-garden-pomodoro.html
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it tracks or helps with and how you interact with it
  - Which category it falls into
  - How it persists state between visits
```

---

## Music Apps — `music_apps/`

```
Music Apps: Instructions

You are a music-software developer building ONE brand new, fully functional,
self-contained audio tool as a single HTML file using the Web Audio API.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\music_apps'
(if this folder does not exist yet, create it first). Read their filenames and,
if short, their <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh music-tool idea not yet in this folder. Rotate through
these categories — don't always pick the same type:

  STEP SEQUENCERS & BEAT MAKERS: an orbital sequencer and a pulse-grid drum
    machine already exist — fresh ground is a genre-preset drum machine or a
    polyrhythm sequencer
  SYNTHESIS & PHYSICAL-MODELING INSTRUMENTS: string physical-modeling,
    bell/chime synthesis, and an ambient drone instrument already exist —
    fresh ground is a subtractive-synth sound-design playground or a full
    virtual piano/keyboard with recording
  HARMONY & COMPOSITION TOOLS: a chord-suggestion tool and a song-structure
    arranger already exist — fresh ground is a scale/mode explorer or an
    ear-training pitch/interval game. Not represented at all yet.
  RHYTHM & MEMORY GAMES: this folder already has two call-and-repeat memory
    games (note-cascade, echo-chamber) — do NOT add a third. If you want a
    rhythm game, make it about actual timing/accuracy training (tapping to a
    beat, syncopation practice), not sequence memorization.
  GENERATIVE / AUDIO-VISUAL: a few generative sound-and-visual pieces already
    exist, all synth-driven — fresh ground is a mic-input audio-reactive
    visualizer that responds to the user's real environment sound
  LOOPING & ARRANGEMENT: a layered looper already exists — fresh ground is a
    multi-track loop mixer or a full song-section arranger (intro/verse/
    chorus/outro)
  PRACTICE / UTILITY: nothing in this category yet — a metronome/practice
    tool or a karaoke/lyric-timing tool are open ground

Check the file list from Step 1 and bias toward whatever's thin or missing —
ear-training, a metronome/practice tool, and a mic-input visualizer are all
notably absent, and rhythm-memory games are already at their limit.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Pay special attention to the Art/Music theme guidance in CLAUDE.md:
near-black background (#06070d range), vivid accent colors, minimal UI
chrome. One category-specific requirement on top of that: browsers suspend
AudioContext until a user gesture — always create/resume the AudioContext
inside a click/tap handler, never on page load, or the app will be silent on
first use. Do not skip or re-derive anything else in CLAUDE.md; it is
authoritative.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\music_apps' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
  Example: 2026-06-24-string-field.html
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it sounds like and how you interact with it
  - Which category it falls into
  - One thing that makes it musically or technically different from the others
```

---

## Action Games — `action_games/`

```
Action Games: Instructions

You are a game developer building ONE brand new, fully functional,
self-contained arcade action game as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\action_games',
including any files in a nested subfolder if one exists (this folder has an
old 'Action Games Generator' subfolder from an earlier run — check both
locations for existing concepts, but see Step 4 for where to save new ones).
Read filenames and, if short, the <!-- CONCEPT: --> line at the top. Build a
mental list of concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh arcade-action idea not yet in this folder. Every genre
below already has at least two entries, so favor a genuinely new mechanic
over a re-skin:

  MELEE COMBAT / BRAWLER — 2 already exist; fresh ground is a single-boss
    "boss rush" encounter
  DODGE / SURVIVAL — 2 already exist; fresh ground is a wave-survival horde
    format
  PLATFORMER — 2 already exist; fresh ground is grapple-hook/swing
    traversal or parkour-style climbing
  REFLEX / TIMING — 2 already exist; fresh ground is a rhythm-action hybrid
    (timing-based, not memory-based — that belongs in music_game_apps)
  PUZZLE-ACTION HYBRID — 2 already exist; fresh ground is a physics-based
    puzzle-action mechanic
  RUNNER — 2 already exist; fresh ground is a vehicle/chase runner

Genres not represented at all yet: stealth/sneak, and tower-defense-lite.
Strongly prefer one of those, or a genuinely new mechanic within an existing
genre, over adding a third entry to any category above.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack — but action games can
lean high-energy/neon within that, matching the existing files' style. Verify
touch controls work as well as keyboard/mouse — these are fast-reflex games
and touch lag or missed taps make them unplayable on the Pixel devices this
library targets. Do not skip or re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\action_games' directly (NOT
into a subfolder — the existing 'Action Games Generator' subfolder is a
legacy artifact; don't add to it) with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What the game is and how you play it
  - Which genre it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Card Games Apps — `card_games_apps/`

```
Card Games Apps: Instructions

You are a game developer building ONE brand new, fully functional,
self-contained card game as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\card_games_apps',
including any files in a nested subfolder if one exists (this folder has an
old 'Card Games' subfolder from an earlier run — check both locations for
existing concepts, but see Step 4 for where to save new ones). Read filenames
and, if short, the <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh card-game idea not yet in this folder. Rotate through
these mechanics — don't always pick the same type:

  SOLITAIRE VARIANTS — TriPeaks-style solitaire already exists in two forms
    (a near-duplicate pairing worth flagging in your chat summary); if you
    build another solitaire, pick a structurally different variant
    (Klondike, Pyramid, Spider) rather than a third TriPeaks
  MATCHING / SET-COLLECTING — gin rummy already exists; fresh ground is a
    different set-collecting game (e.g. a rummy variant with different
    melding rules)
  TRICK-TAKING — one trick-taking game already exists; fresh ground is a
    different trump/bidding structure
  SHEDDING — a card-shedding/ladder game already exists; fresh ground is a
    different shedding ruleset (e.g. Crazy-Eights-style)
  DECK-BUILDING — one deck-builder already exists; fresh ground is a
    different deck-building theme or resource system
  PUSH-YOUR-LUCK / RISK — not yet represented in this folder — a
    push-your-luck card game (draw-and-bust style) is open ground

Check the file list from Step 1 and bias toward whatever's thin or missing
rather than a second TriPeaks-style solitaire.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack. One category-specific
requirement: card games have real rules — verify the shuffle is fair (no
predictable ordering), scoring matches the stated rules exactly, and win/loss
detection can't produce a false result. Do not skip or re-derive anything
else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\card_games_apps' directly (NOT
into a subfolder — the existing 'Card Games' subfolder is a legacy artifact;
don't add to it) with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What the game is and how a round is played
  - Which mechanic it falls into
  - One thing that makes it different from what's already in the folder
```

---

## DJ Music Apps — `dj_music_apps/`

```
DJ Music Apps: Instructions

You are a music-software developer building ONE brand new, fully functional,
self-contained DJ/performance tool as a single HTML file using the Web Audio
API.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\dj_music_apps',
including any files in a nested subfolder if one exists (this folder has an
old 'DJ' subfolder from an earlier run — check both locations for existing
concepts, but see Step 4 for where to save new ones). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh DJ/live-performance tool not yet in this folder. Rotate
through these categories — don't always pick the same type:

  TURNTABLE / SCRATCH — turntable and scratch-lab tools already exist; fresh
    ground is a genuinely different scratch mechanic (e.g. multi-deck
    battle mode)
  SAMPLE / PAD PERFORMANCE — a sampler-pad tool and a loop-slicer already
    exist; fresh ground is a different triggering mechanic (e.g. velocity-
    or gesture-sensitive pads)
  BEATMATCHING / MIXING TRAINING — a beatmatching sync trainer already
    exists; fresh ground is a harmonic-mixing (key-matching) trainer
  EFFECTS PERFORMANCE — an effects-rack tool already exists; fresh ground is
    a different effect focus (e.g. a filter-sweep/transition-focused tool)
  RHYTHM/SURVIVAL DJ GAME — a beat-drop survival game already exists; fresh
    ground is a different challenge format
  VISUALIZER — an audio-reactive VJ visualizer already exists; fresh ground
    is one with a genuinely different visual style or input source

Check the file list from Step 1 and bias toward whatever's thin rather than
another turntable/scratch tool, which is already the most-covered mechanic.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Pay special attention to the Art/Music theme guidance in CLAUDE.md:
near-black background (#06070d range), vivid accent colors, minimal UI
chrome. One category-specific requirement: browsers suspend AudioContext
until a user gesture — always create/resume it inside a click/tap handler,
never on page load. Do not skip or re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\dj_music_apps' directly (NOT
into a subfolder — the existing 'DJ' subfolder is a legacy artifact; don't
add to it) with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it does and how you perform/interact with it
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Fashion Apps — `fashion_apps/`

```
Fashion Apps: Instructions

You are a creative developer building ONE brand new, fully functional,
self-contained fashion/styling app as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\fashion_apps',
including any files in a nested subfolder if one exists (this folder has an
old 'Fashion' subfolder from an earlier run — check both locations for
existing concepts, but see Step 4 for where to save new ones). Read filenames
and, if short, the <!-- CONCEPT: --> line at the top. Build a mental list of
concepts already covered so you don't repeat them. Note: two nearly-identical
fashion trivia quizzes already exist in this folder (both dated 2026-06-28) —
do NOT build a third fashion trivia quiz.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh fashion/styling idea not yet in this folder. Rotate
through these categories — don't always pick the same type:

  DESIGN TOOLS — a print/pattern design studio already exists; fresh ground
    is a color-palette generator focused on fabric/texture rather than
    wardrobe coordination (which is already covered separately)
  STYLING CHALLENGES — a runway styling challenge already exists; fresh
    ground is an occasion-based styling challenge (interview, event, travel
    capsule)
  TREND / HISTORY EXPLORATION — a decade trend explorer already exists;
    fresh ground is a designer-spotlight or fashion-movement explainer
  WARDROBE TOOLS — a wardrobe color-lab and a cost-per-wear capsule planner
    already exist; fresh ground is an outfit-remix tool that suggests new
    combinations from a small set of pieces
  DRESS-UP / AVATAR — one dress-up avatar tool already exists; fresh ground
    is a genuinely different customization mechanic (e.g. layered
    silhouette building rather than pre-made outfit pieces)
  TRIVIA / QUIZ — already covered twice; do not add a third

Check the file list from Step 1 and bias toward whatever's thin or missing.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack — though a fashion-forward
accent palette fits the subject matter better than a strictly muted one. Do
not skip or re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\fashion_apps' directly (NOT
into a subfolder — the existing 'Fashion' subfolder is a legacy artifact;
don't add to it) with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it does and how you interact with it
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

## Music Game Apps — `music_game_apps/`

```
Music Game Apps: Instructions

You are a music-education developer building ONE brand new, fully
functional, self-contained music-*learning* game as a single HTML file
(distinct from music_apps/, which is synthesis and composition tools, and
Music Production/, which is DAW-style production tools).

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\music_game_apps'
(if this folder does not exist yet, create it first). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them. Note: two guitar-strum instrument
simulators already exist and are near-duplicates of each other — do not add
a third guitar simulator.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh music-learning idea not yet in this folder. Rotate
through these categories — don't always pick the same type:

  EAR TRAINING — an interval ear-trainer already exists; fresh ground is
    chord-quality (major/minor/diminished) recognition or rhythm dictation
  RHYTHM ACCURACY — a rhythm-lane tapper already exists; fresh ground is a
    polyrhythm or syncopation trainer
  INSTRUMENT SIMULATORS — two near-identical guitar simulators and one drum
    kit simulator already exist; do NOT add another guitar simulator — fresh
    ground is a different instrument entirely (keys, bass, or strings other
    than guitar)
  MUSIC-MAKING TOOLS — a sequencer/beat-loop studio already exists; fresh
    ground is a melody-writing game with a clear scoring/challenge structure
    (distinct from the freeform sequencer)
  NOTATION / THEORY LITERACY — a staff-reading note-rush game already
    exists; fresh ground is a rhythm-notation reading game or a key-
    signature identification game

Check the file list from Step 1 and bias toward whatever's thin or missing —
notation/theory literacy beyond staff-reading is the most open ground.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Pay special attention to the Art/Music theme guidance in CLAUDE.md:
near-black background (#06070d range), vivid accent colors, minimal UI
chrome. Two category-specific requirements: (1) AudioContext must be
created/resumed inside a user gesture handler, never on page load; (2) any
music-theory content (intervals, chord names, note names, rhythms) must be
verified musically correct, not just plausible-sounding. Do not skip or
re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\music_game_apps' with filename:
  YYYY-MM-DD-[subtype]-kebab-case-name.html   (use today's date)
  Example: 2026-06-26-ear-training-interval-quest.html
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it teaches and how you play/practice with it
  - Which category it falls into
  - How you verified the musical content is correct
```

---

## Party Apps — `party_apps/`

```
Party Apps: Instructions

You are a game developer building ONE brand new, fully functional,
self-contained group/party game as a single HTML file, designed to be played
by multiple people sharing one screen (pass-and-play or call-and-response,
not networked multiplayer).

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\party_apps'
(if this folder does not exist yet, create it first). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them. Note: this folder already has
several "forbidden word / say the word before time runs out" style games
(speed-word-bomb-pass, word-forbidden-five, word-fuse-bomb-pass,
word-zip-it-forbidden-words) — do not add a fifth variant of this mechanic.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh party-game idea not yet in this folder. Rotate through
these categories — don't always pick the same type:

  WORD / TIMER GAMES — the "forbidden word" family is already saturated
    (4 variants) — avoid this mechanic entirely for now
  VOTING / SOCIAL GAMES — a "most likely to" voting game already exists;
    fresh ground is a prediction game (guess how the group will vote) or an
    opinion-spectrum game
  DRAWING / CHARADES — a doodle-dare drawing game already exists; fresh
    ground is a charades-style acting/guessing game
  IMPROV / PROMPT GAMES — a rapid-pitch improv game and a "same wavelength"
    dial game already exist; fresh ground is a storytelling-chain game
    (each player adds a line)
  TRIVIA — a lightning-categories trivia game already exists; fresh ground
    is a team-based trivia format with wagering or steal mechanics

Check the file list from Step 1 and bias toward voting/prediction or
storytelling-chain games, which are the most open ground.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack — but favor bold, high-
energy color accents since these are meant to be exciting on a shared screen.
One category-specific requirement: these are played by groups without a
referee, so rules, timers, and turn order must be unambiguous on screen —
nobody should need to ask "wait, whose turn is it?". Do not skip or re-derive
anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\party_apps' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What the game is and how a group plays it
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Shooting Games Apps — `shooting_games_apps/`

```
Shooting Games Apps: Instructions

You are a game developer building ONE brand new, fully functional,
self-contained arcade shooter as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\shooting_games_apps'
(if this folder does not exist yet, create it first). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them. Note: there is also a stray
'Shooting Games' (Title Case) folder in the parent directory containing one
more shooter — check it too, but see Step 4 for where to save new ones.
This folder already has THREE twin-stick shooters — do not add a fourth.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh arcade-shooter idea not yet in this folder. Rotate
through these categories — don't always pick the same type:

  TWIN-STICK ARENA — already has three variants; this mechanic is at its
    limit, avoid it for now
  GALLERY SHOOTER — one gallery/carnival-style shooter already exists;
    fresh ground is a different setting or a moving-lane gallery format
  CANNON / PROJECTILE ARC — two cannon/projectile games already exist;
    fresh ground is a different physics puzzle (e.g. bounce/ricochet-based
    rather than direct-arc)
  SPACE SHOOTER — one vertical/space shooter already exists; fresh ground is
    a horizontal side-scrolling shmup or a boss-pattern-focused format
  RAIL / ON-RAILS SHOOTER — not represented yet — a fixed-path shooter where
    the camera moves automatically is open ground
  TOWER DEFENSE SHOOTER — not represented yet — a stationary-defense format
    with waves is open ground

Check the file list from Step 1 and bias toward rail-shooter or tower-
defense formats, which are completely unrepresented, over another
twin-stick or cannon game.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack — neon/arcade accents fit
the genre. Verify touch controls (virtual joystick/tap-to-fire) work as well
as keyboard/mouse; this is a fast-reflex genre where touch lag makes the game
unplayable on the Pixel devices this library targets. Do not skip or
re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\shooting_games_apps' (the
snake_case folder — NOT the stray 'Shooting Games' Title Case folder, which
is a legacy artifact) with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What the game is and how you play it
  - Which sub-genre it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Sports Games Apps — `sports_games_apps/`

```
Sports Games Apps: Instructions

You are a game developer building ONE brand new, fully functional,
self-contained sports simulation/mini-game as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\sports_games_apps',
including any files in a nested subfolder if one exists (this folder has an
old 'Sports Games Generator' subfolder from an earlier run — check both
locations for existing concepts, but see Step 4 for where to save new ones).
Read filenames and, if short, the <!-- CONCEPT: --> line at the top. Build a
mental list of concepts already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh sport not yet in this folder. Archery, ski jump,
curling, baseball, bowling, 100m sprint, and table tennis are already
covered — pick a genuinely different sport (e.g. golf, basketball
free-throws, tennis, skateboarding, swimming, darts, football field goals)
rather than a variant of one already covered. Favor sports with a clear,
simple, physically-plausible input-to-outcome mechanic (a swing/timing meter,
a power-and-angle launch, a precision-aim system) — that's what made the
existing entries work.

Check the file list from Step 1 and pick whichever sport gives you a genuinely
different control scheme from what's already there (e.g. avoid another
timing-bar mechanic if two already use one).

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack. Verify the physics/scoring
model is plausible (realistic enough that a correct input feels rewarding and
an incorrect one clearly fails) and that touch controls work as well as
mouse. Do not skip or re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\sports_games_apps' directly
(NOT into a subfolder — the existing 'Sports Games Generator' subfolder is a
legacy artifact; don't add to it) with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What sport it simulates and how you play it
  - The core input mechanic (timing bar, power/angle, precision-aim, etc.)
  - One thing that makes it different from what's already in the folder
```

## Table Games Apps — `table_games_apps/`

```
Table Games Apps: Instructions

You are a game developer building ONE brand new, fully functional,
self-contained tabletop/board game simulation as a single HTML file (vs. an
AI opponent or solo/pass-and-play — not networked multiplayer).

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\table_games_apps'
(if this folder does not exist yet, create it first). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them. Note: two push-your-luck dice games
already exist (deep-dive, ember-forge) plus a third dice game (ember-hoard) —
do not add a fourth dice/push-your-luck game.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh tabletop-game idea not yet in this folder. Rotate
through these categories — don't always pick the same type:

  DICE / PUSH-YOUR-LUCK — already has three entries; this mechanic is at its
    limit, avoid it for now
  TRICK-TAKING — already covered once; fresh ground is a different
    trump/scoring structure
  MANCALA / CLASSIC REMIX — already covered once; fresh ground is a
    different classic board game reimagined (e.g. Nine Men's Morris, Go-Moku)
  AREA CONTROL / STRATEGY — two strategy games already exist (area-control,
    tile-placement); fresh ground is a route-building or worker-placement
    strategy game
  DEDUCTION — one cipher/deduction puzzle-game already exists; fresh ground
    is a Clue-style elimination deduction game
  ECONOMY / AUCTION — one auction/economy game already exists; fresh ground
    is a trading or resource-management game
  BLUFFING — one bluffing/bidding game already exists; fresh ground is a
    hidden-role or hidden-information bluffing game

Check the file list from Step 1 and bias toward worker-placement or
hidden-role/elimination games, which are the most open ground, over another
dice game.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack. One category-specific
requirement: if there's an AI opponent, it must make legal, non-trivial moves
(not random or exploitable) — verify this by reasoning through a few turns,
not just confirming it doesn't crash. Do not skip or re-derive anything else
in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\table_games_apps' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What the game is and how a turn/round works
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Therapy Apps — `therapy_apps/`

```
Therapy Apps: Instructions

You are a mental-health-tools developer building ONE brand new, fully
functional, self-contained therapeutic tool as a single HTML file (distinct
from health_productivity_apps/, which covers general wellness/focus rather
than clinically-grounded therapeutic techniques).

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\therapy_apps'
(if this folder does not exist yet, create it first). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them. Note: two EMDR bilateral-stimulation
tools already exist (calm-grounding, calm-pacer) — if you build a third EMDR
tool, it needs a genuinely different mechanic, not another pacer variant.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh therapeutic-technique idea not yet in this folder.
Rotate through these categories — don't always pick the same type:

  CBT TECHNIQUES — a thought-record/reframing tool already exists; fresh
    ground is a cognitive-distortion identifier or a behavioral-activation
    planner
  EMDR / BILATERAL STIMULATION — two variants already exist; only revisit
    this with a genuinely different mechanic
  RELAXATION / GROUNDING — progressive muscle relaxation is covered; fresh
    ground is a 5-4-3-2-1 sensory grounding exercise or a body-scan guide
  MOOD / SELF-MONITORING — a daily mood check-in tracker already exists;
    fresh ground is a triggers/patterns journal that surfaces trends over
    time, not just a daily log

Check the file list from Step 1 and bias toward CBT cognitive-distortion
tools or sensory grounding exercises, which are the most open ground.

Ground every technique in real, established practice (CBT, DBT, ACT,
mindfulness-based methods) — do not invent pseudo-therapeutic mechanics.
This tool may be used by someone in a genuinely difficult moment; accuracy
and a calm, non-gimmicky tone matter more than novelty here.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack — favor calm, low-
saturation colors and generous whitespace over the high-energy style used in
the games categories. As with health_productivity_apps, persist state in
localStorage correctly (per CLAUDE.md's `cowork-{appname}-{key}` convention)
since these tools are meant to be revisited. Do not skip or re-derive
anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\therapy_apps' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What technique it's based on and how you use it
  - Which category it falls into
  - What established practice/source the technique is grounded in
```

---

## Content Creation Apps — `Content Creation Apps/`

This category is split into three age-tier subfolders. Pick ONE tier per run
(rotate across tiers over time — check which tier was generated least
recently) rather than defaulting to the same tier every time.

```
Content Creation Apps: Instructions

You are a creative-tools developer building ONE brand new, fully functional,
self-contained content-creation app as a single HTML file, for ONE of three
age tiers: kid, teen, or adult.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in each of:
  'C:\Users\tokka\Claude Local\cowork apps\Content Creation Apps\kid_apps'
  'C:\Users\tokka\Claude Local\cowork apps\Content Creation Apps\teen_apps'
  'C:\Users\tokka\Claude Local\cowork apps\Content Creation Apps\adult_apps'
Read filenames and, if short, the <!-- CONCEPT: --> line at the top. Pick
whichever tier has the fewest apps (or was generated longest ago) to keep
the three tiers roughly balanced, then build a mental list of concepts
already covered in that tier so you don't repeat them.
If any tier folder already contains more than 60 files, note that in your
chat summary so I know it may be time to archive older ones. Do not delete
anything.

--- STEP 2: PICK A CONCEPT ---
Once you've picked a tier, come up with a fresh content-creation idea
appropriate to that age group and not yet covered in its folder:

  KID TIER (imaginative/craft-adjacent creation) — monster/character makers,
    music/sound-band toys, show-and-tell prompts, letter/word art, comic
    creation are covered — fresh ground is a simple stop-motion-style
    animation maker or a make-your-own-storybook tool
  TEEN TIER (identity/self-expression + early digital-content skills) —
    aesthetic/visual theme studios, OC (original character) creators,
    short-form video hook/script builders, social caption studios, and
    reflective journaling are covered — fresh ground is a playlist/mood-
    board creator or a fan-fiction/world-building prompt tool
  ADULT TIER (practical content/marketing tools) — brand-strategy planners,
    newsletter subject-line labs, headline/hook studios, writing-sprint
    timers, and video/podcast script builders are covered — fresh ground is
    a content-calendar-adjacent tool with a different focus (e.g. a
    presentation-outline builder or an SEO-adjacent content-brief generator)

Bias toward whichever tier and concept is thinnest per Step 1, rather than
defaulting to whatever's easiest to build.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Match the theme to the tier: KID tier should follow CLAUDE.md's Kids Apps
theme (bright saturated backgrounds, playful fonts, big tap targets); TEEN
and ADULT tiers fall under "All others" (dark or neutral, clean, system font
stack). Do not skip or re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to the tier subfolder you picked in Step 1, e.g.:
  'C:\Users\tokka\Claude Local\cowork apps\Content Creation Apps\teen_apps'
with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - Which tier you built for and why you picked it
  - What the tool helps someone create
  - One thing that makes it different from what's already in that tier
```

## Cooking Games — `Cooking Games/`

```
Cooking Games: Instructions

You are a game developer building ONE brand new, fully functional,
self-contained cooking/restaurant game as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\Cooking Games'
(if this folder does not exist yet, create it first). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them. Note: this folder already has
THREE "order rush" restaurant-service games (burger-bistro, ramen-rush,
sunny-side-diner) — do not add a fourth restaurant-order-rush game.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh cooking-game idea not yet in this folder. Rotate
through these categories — don't always pick the same type:

  ORDER-RUSH SERVICE GAMES — already at three variants (burger, ramen,
    diner); this mechanic is at its limit, avoid it for now
  RHYTHM/TIMING COOKING — a chef's-tempo rhythm cooking game already exists;
    fresh ground is a different timing challenge (e.g. a multi-station
    juggling game distinct from a pure rhythm mechanic)
  BAKING / DECORATING — a cupcake decorating studio already exists; fresh
    ground is a different baked good with a different decorating mechanic
    (e.g. cake layering, cookie icing with piping precision)
  RECIPE / MEAL-BUILDING — not represented yet — a build-your-own-recipe
    or ingredient-matching game is open ground
  FOOD-PREP PUZZLE — not represented yet — a prep-sequencing puzzle (mise en
    place ordering, knife-skill timing) is open ground

Check the file list from Step 1 and bias toward recipe-building or food-prep
puzzle formats, which are completely unrepresented, over another
order-rush or baking game.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack — warm, appetizing accent
colors fit the subject matter well within that. Do not skip or re-derive
anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\Cooking Games' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What the game is and how you play it
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Crafts — `Crafts/`

```
Crafts: Instructions

You are a creative-tools developer building ONE brand new, fully functional,
self-contained virtual craft-making tool as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\Crafts' (if
this folder does not exist yet, create it first). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them. Note: two kaleidoscope/mandala-
style drawing tools already exist (mandala-painter, kaleidoscope-brush) — do
not add a third symmetry-drawing tool.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh virtual-craft idea not yet in this folder. Rotate
through these categories — don't always pick the same type:

  SYMMETRY / KALEIDOSCOPE DRAWING — already has two entries; this mechanic
    is at its limit, avoid it for now
  TEXTILE / FIBER CRAFTS — a bead-loom bracelet designer already exists;
    fresh ground is a weaving pattern designer or a friendship-bracelet
    (macrame knot) pattern tool
  CERAMICS / SCULPTING — a pottery-wheel tool already exists; fresh ground
    is a different sculpting medium (clay hand-building, sand art layering)
  NATURE CRAFTS — a pressed-flower frame tool already exists; fresh ground
    is a leaf-print/nature-collage tool or a terrarium-design tool
  PAPER CRAFTS — not represented yet — an origami-folding guide or a
    paper-quilling design tool is open ground
  JEWELRY / BEADING (non-loom) — not represented yet — a bead-pattern
    necklace/bracelet designer with a different layout mechanic than the
    existing loom tool is open ground

Check the file list from Step 1 and bias toward paper crafts or non-loom
jewelry design, which are completely unrepresented, over another symmetry-
drawing tool.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack — though a craft tool's
canvas/workspace area should stay light/neutral so colors and materials read
accurately, with the dark theme reserved for chrome around it. Include a
save-as-image option where practical, matching the pattern from the existing
art_apps/ pieces. Do not skip or re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\Crafts' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What you make with it and how you interact with it
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Inspirational — `Inspirational/`

```
Inspirational: Instructions

You are a creative developer building ONE brand new, fully functional,
self-contained motivational/inspirational app as a single HTML file.

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\Inspirational'
(if this folder does not exist yet, create it first). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh inspirational-app idea not yet in this folder. Rotate
through these categories — don't always pick the same type:

  GRATITUDE — a gratitude-constellation tool already exists; fresh ground is
    a different gratitude mechanic (e.g. a gratitude jar/collection you
    build over time rather than a single-session visual)
  QUOTES / WISDOM — a world-proverbs explorer already exists; fresh ground
    is a themed quote generator tied to a specific need (motivation,
    resilience, focus) with context on each quote's origin
  AFFIRMATIONS — a morning-affirmation ritual already exists; fresh ground
    is a custom-affirmation builder the user writes and revisits, rather
    than a pre-written set
  GROWTH MINDSET — a "power of yet" growth-mindset tool already exists;
    fresh ground is a reframing tool for a different mindset concept (e.g.
    turning setbacks into a visible "lessons learned" log)
  VISUALIZATION / GOALS — not represented yet — a vision-board builder or a
    future-self visualization tool is open ground
  KINDNESS / CONNECTION — not represented yet — a random-acts-of-kindness
    idea generator or a connection-prompt tool (things to say to someone you
    care about) is open ground

Check the file list from Step 1 and bias toward visualization/goals or
kindness/connection, which are completely unrepresented.

Keep the tone genuine and specific rather than generic inspirational-poster
language — cite real sources for quotes/proverbs where possible, and avoid
vague, interchangeable affirmation text.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
This category isn't one of CLAUDE.md's named themes, so it falls under "All
others": dark or neutral, clean, system font stack — soft gradients and warm
accent colors fit the subject matter well within that. Do not skip or
re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\Inspirational' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it does and how you interact with it
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Music Production — `Music Production/`

```
Music Production: Instructions

You are a music-software developer building ONE brand new, fully
functional, self-contained DAW-style production tool as a single HTML file
using the Web Audio API (distinct from music_apps/, which is generative/
experimental instruments, and music_game_apps/, which is learning games).

--- STEP 1: CHECK WHAT ALREADY EXISTS ---
List all .html files in 'C:\Users\tokka\Claude Local\cowork apps\Music Production'
(if this folder does not exist yet, create it first). Read filenames and, if
short, the <!-- CONCEPT: --> line at the top. Build a mental list of concepts
already covered so you don't repeat them. Note: there are two files both
literally named '...-drum-machine-808-step-sequencer.html' (dated 2026-06-27
and 2026-06-28) — this looks like an accidental duplicate rather than two
distinct apps; flag it in your chat summary but do not delete or modify
either file yourself.
If this folder already contains more than 60 files, note that in your chat
summary so I know it may be time to archive older ones. Do not delete anything.

--- STEP 2: PICK A CONCEPT ---
Come up with a fresh production-tool idea not yet in this folder. Rotate
through these categories — don't always pick the same type:

  DRUM MACHINES — an 808-style step sequencer already exists (see the
    duplicate-flag note above); if you build another, pick a genuinely
    different drum machine style (e.g. a different genre's classic drum
    sound/pattern conventions), not another 808 clone
  SYNTHESIZERS — an acid-bassline (303-style) synth and an FM poly-synth
    already exist; fresh ground is a different synthesis method (e.g.
    wavetable or granular synthesis) or a different sound target
  MUSIC THEORY TOOLS — a chord-progression studio already exists; fresh
    ground is a scale/mode reference tool built for composers, or a
    voice-leading visualizer
  ARRANGEMENT / EDITING — a piano-roll melody editor already exists; fresh
    ground is a multi-track arrangement view or an automation/mixing tool

Check the file list from Step 1 and bias toward a new synthesis method or an
arrangement/mixing tool, which are the most open ground, over another drum
machine or 808 clone.

--- STEP 3: BUILD IT ---
Follow every convention in 'C:\Users\tokka\Claude Local\cowork apps\CLAUDE.md'
exactly — required boilerplate, the mandatory viewport meta tag, CSS/JS
conventions, mobile-first layout rules, and the pre-finish quality checklist.
Pay special attention to the Art/Music theme guidance in CLAUDE.md:
near-black background (#06070d range), vivid accent colors, minimal UI
chrome. One category-specific requirement: browsers suspend AudioContext
until a user gesture — always create/resume it inside a click/tap handler,
never on page load. Do not skip or re-derive anything else in CLAUDE.md.

--- STEP 4: SAVE IT ---
Save to 'C:\Users\tokka\Claude Local\cowork apps\Music Production' with filename:
  YYYY-MM-DD-kebab-case-name.html   (use today's date)
Do NOT overwrite existing files. If the filename conflicts, append -2.

After saving, write a 3-line summary in chat:
  - What it does and how you produce/interact with it
  - Which category it falls into
  - One thing that makes it different from what's already in the folder
```

---

## Not covered by a scheduled prompt (intentionally)

- **`custom_apps/`** — apps here are generated on-demand by the "Build Your Own App" wizard via a headless `claude -p` invocation triggered from `serve_apps.py`, not by a manually-pasted scheduled prompt. See `CLAUDE.md` for details. No prompt needed here.

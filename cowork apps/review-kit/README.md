# Reviewing AppVerse games with an AI playtester

Hand-driven review: you build a batch of games, point an agent at it, and read what it
found. Nothing here is scheduled or automatic.

The kit is deliberately tool-agnostic. `REVIEW-BRIEF.md` is a rubric and an output format,
not a feature of any product, so the same batch can go through different reviewers and the
results compared fairly.

---

## Which reviewer can you actually use?

A constraint that is easy to forget and costs a wasted setup each time:

- **Antigravity's Browser Subagent is built in, not a plugin**, so it needs no approval on
  either machine. This is the default route.
- **Codex's browser plugin needs admin approval on the Desktop** (school-managed), so it
  cannot be enabled there. It *is* already enabled on the Surface
  (`~/.codex/config.toml`, `[plugins."browser@openai-bundled"] enabled = true`).

Either way, **`New-ReviewBatch.ps1` runs on the Surface**, because that is where the games
are.

---

## Default: Antigravity on the Desktop

On the Surface:

```powershell
cd "C:\Users\tokka\Claude Local\cowork apps\review-kit"
.\New-ReviewBatch.ps1 -Remote
```

`-Remote` does the three things that are easy to get wrong by hand: finds this machine's
Tailscale address, inlines the concepts (the Desktop cannot read this machine's registry),
and writes the batch to `G:\My Drive\AppVerse Review\` where the Desktop sees it. Copy
`REVIEW-BRIEF.md` there too if it is not already.

On the Desktop:

1. Open the base URL the script printed in an ordinary browser first. A batch of dead URLs
   just gets reported back as broken games.
2. Open Antigravity (standalone or IDE — either) and pick **Gemini 3.1 Pro**. Judgement,
   not speed.
3. Allow the Surface's address when the Browser Subagent prompts on first navigation. Its
   allowlist ships with `localhost` only; the file is
   `%USERPROFILE%\.gemini\antigravity\browserAllowlist.txt`.
4. Paste the brief, attach the batch, let it play.
5. Save the report to the same Drive folder as `gemini-review-YYYY-MM-DD.md`, then copy it
   into `cowork apps\Reviews\` on the Surface.

**This route cannot damage anything.** The reviewer reaches the games over HTTP with no
file access, so it is structurally incapable of modifying the collection — a property of
the setup, not of good behaviour.

**Never run the generators on the Desktop** — only review there. A second machine writing
into the collection is how `dj_music_apps` got polluted.

---

## Alternative: Codex on the Surface

Everything on one machine, so no network and no file shuttling:

```powershell
.\New-ReviewBatch.ps1
```

The reviewer reaches the games at `localhost:8080` and reads the registry off disk, so
batches are about 1 KB instead of 95 KB. Use the **`browser` plugin, not computer use** —
everything here happens inside a browser, and full desktop control is a much wider blast
radius on the machine that runs 19 factory tasks and serves AppVerse.

### The trade: read-only becomes a matter of trust

Worth being explicit about. A reviewer on the Desktop *cannot* touch the collection. A
reviewer on the Surface has full write access, so "don't edit anything" holds only because
the brief says so.

That matters here more than it sounds: the generated content's only off-machine copy is the
daily backup zip, several categories are gitignored and not on GitHub at all, and a fix
applied by hand can be silently overwritten by tonight's generator. The brief tells the
reviewer to report problems and never repair them, and to write exactly one file: the
report. If you ever see it editing a game, stop it.

---

## No connectivity at all?

Review the public arcade instead: <https://tokkathedj.github.io/party-command-games/> — 57
curated games, always up, no dependency on the Surface.

---

## Script options

| Switch | Default | What it does |
|---|---|---|
| `-Remote` | off | Antigravity-on-Desktop preset: Tailscale address, `-Embed`, Drive output |
| `-BaseUrl` | `http://localhost:8080` | Overrides where the reviewer reaches AppVerse |
| `-Days` | `1` | How far back to look for new games |
| `-Count` | `10` | Batch size |
| `-Category` | all | Restrict to one folder, e.g. `kids_apps` |
| `-OutDir` | `review-kit\batches` | Where the batch file lands |
| `-Embed` | off | Inline the concepts instead of pointing at the registry |

`-Remote` exits non-zero with an explanation if Tailscale is down, rather than emitting a
batch full of unreachable URLs.

Keep batches near 10 games. Rate limits on both products are published only qualitatively,
so there is no number to plan against and smaller batches fail more gracefully.

---

## Where the feedback goes

`Reviews/` is **gitignored** (`cowork apps/.gitignore:83`), so reports never travel by git.

- **From the Desktop:** save into `G:\My Drive\AppVerse Review\`, then copy into `Reviews\`
  on the Surface.
- **On the Surface:** have the reviewer write straight to
  `cowork apps\Reviews\gemini-review-YYYY-MM-DD.md` (or `codex-review-…`).

The AppVerse hub then renders it beside the automated daily reviews. Two naming rules:

- **Do not** name it `review-YYYY-MM-DD.md` — that is the `Daily-app-check` routine's output
  and you would overwrite it.
- The hub's markdown renderer understands only a small subset (headers, `---`, pipe tables,
  `- ` bullets, bold, italic, code spans, links). The brief already constrains the reviewer
  to it. Table cells colour on the words `SHIP IT`, `MINOR` and `BROKEN`.

---

## What this deliberately does not do

- **No fixing.** The reviewer reports; you decide what to change.
- **Not scheduled.** Both products can run headless (Antigravity has `agy -p`, Codex has a
  CLI), so automating this later is real — but start hand-driven and find out whether the
  feedback is worth automating before building a pipeline around it.
- **No audio checks.** Agent browsers have no speakers; the brief tells the reviewer to list
  that under *Not verified* rather than guess.

# App Factory Floor — dashboard build

Generates the "App Factory Floor" page: a shift-board view of the 18 scheduled
routines, what the collection holds, and where the line has repeated itself.

## Refresh it

```powershell
pwsh -File _scheduler\dashboard\Refresh-FactoryFloor.ps1
```

Then ask Claude Code to update the existing artifact, **naming its URL**:

> update the App Factory Floor artifact at
> `https://claude.ai/code/artifact/e16b5725-991d-410e-a1c1-eacc97d51224`
> from `_scheduler\dashboard\app-factory-floor.html`

Two ways this goes wrong quietly, both worth guarding against:

- **Publishing without that URL forks a second artifact.** The original page was
  published from a different path, and an artifact is identified by its file path;
  a new path means a new URL, leaving your shared link pointing at the old page.
- **Re-pin the shared version afterwards.** A publicly shared artifact cannot track
  "Latest" — Share → Shared version → pick the newest. Skip it and the public link
  keeps serving the previous snapshot with no warning.

Flags: `-SkipRegistry` (a scheduled run has already rebuilt it), `-Check` (run the
theme/structure checks over the rendered page).

## Files

| File | Role |
|---|---|
| `Refresh-FactoryFloor.ps1` | Runs the three steps below in order |
| `build_data.py` | Reads the registry, `manifest.json` and `Logs\*.log` → `factory.json` |
| `render.py` | Injects the data and the computed OKLCH colour scale → the HTML |
| `template.html` | The page itself, with `__DATA__` / `__CATVARS__` placeholders |
| `check.py` | Static checks: theme tokens, literal colours, a11y attributes |

`factory.json` and `app-factory-floor.html` are generated and gitignored.

## Things that were easy to get wrong

Four traps are handled deliberately. If you change `build_data.py`, keep them:

- **Run health is dated.** `Logs\<name>.log` holds many runs; only the last block
  counts, and its date is shown. Several routines legitimately last ran yesterday
  and must not be presented as today's state.
- **Hand tests are excluded.** A run whose START line shows a non-standard
  `max-turns` (not 40 or 60) was a manual test, not a scheduled run. Status *and*
  elapsed are read from the same block, or a later test leaks its numbers in.
- **Rescheduled routines aren't failures.** A routine moved to a new time reads
  "awaiting new slot" until it actually runs there. This is derived by diffing
  `manifest.json` against its newest `.bak-*`, not guessed from log times.
- **`dj_music_apps` is quarantined.** It is the largest folder (90) but is stray
  output from an ad-hoc session, not the schedule — and it accounts for *every*
  cross-category duplicate. It is excluded from the totals and category chart, and
  shown separately. Folding it in would misstate the collection badly.

The registry itself (`_scheduler\Registry\*.tsv`) is rebuilt before every routine
run by `_scheduler\Rebuild-Registry.ps1`; this dashboard only reads it.

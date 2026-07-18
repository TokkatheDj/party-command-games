# Surface auto-start & backup setup

Provisioning scripts for running the Cowork Apps / AppVerse server automatically on
the **Surface** machine (`lance_surface\tokka`) and keeping the daily backup healthy.
Verified end-to-end via a real reboot on 2026-07-18.

> These scripts hard-code this machine's paths (`C:\Users\tokka\Claude Local\cowork apps`,
> `C:\Python314\python.exe`). They are specific to the Surface; the older Desktop-machine
> scripts (with `D:\` paths) live at the repo's `cowork apps/` root.

## How to run them (important)

All of these change scheduled tasks, which requires **administrator elevation**, and a
normal `& script.ps1` is silently blocked by the execution policy. Always run from an
**Administrator terminal** (Start → Terminal (Admin)) like this:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "<path-to-script>"
```

Each script prints its steps and writes an outcome file to
`%LOCALAPPDATA%\CoworkApps\*-result.txt`. Do **not** rely on self-elevating
(`Start-Process -Verb RunAs`) from an automated/background context — the UAC prompt
often fails to reach the interactive desktop.

## Scripts

| Script | What it does |
|---|---|
| `Setup-ServerBootTask.ps1` | Registers `CoworkApps-Server-Boot` — an **AtStartup, S4U** task that starts `serve_apps.py` (port 8080) **before login**, in session 0. This is the pre-login auto-start. |
| `Set-BackupTaskS4U.ps1` | Switches the existing `Backup Cowork Content` task from Interactive to **S4U** (run whether logged on or not), preserving its daily 14:00 trigger and action. |
| `Add-BackupTestTrigger.ps1` | **Test helper.** Adds a temporary **AtLogon** trigger (3-min delay) to the backup task so a reboot exercises it. Undo with `-Remove`. Not part of the steady state. |
| `Verify-BootTask.ps1` | **Read-only** post-reboot check. Confirms a real reboot happened, the boot task fired (server on 8080 from **SessionId 0** = pre-login), and a fresh backup snapshot appeared. No admin needed. |

## The steady-state setup these produce

- **Server, login start:** `CoworkApps-Server.vbs` in the Startup folder (session 1 fallback).
- **Server, boot start:** task `CoworkApps-Server-Boot` (AtStartup, S4U, session 0, pre-login).
- **Daily backup:** task `Backup Cowork Content` (S4U, 14:00) → `C:\Users\tokka\bin\Backup-CoworkContent.ps1`
  → Google Drive `G:\My Drive\Backups\cowork-apps-content`. `G:` is per-user, so logged-off
  runs skip gracefully rather than back up.

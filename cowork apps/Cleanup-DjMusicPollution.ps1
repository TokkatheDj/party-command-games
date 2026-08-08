<#
Cleanup-DjMusicPollution.ps1   -- run ON the Surface (or any machine holding the tree)

Fixes the recurring defect where a whole mini-library of DISPLAY-name category
folders (Action Games, Card Games, Therapy, Content Creation\Teens, ...) ends up
nested INSIDE dj_music_apps instead of the real top-level category folders. Those
apps then ride along in every Google-Drive backup and reappear on restore.

Note: the daily _scheduler routines are NOT the cause -- each saves to its correct
slug folder (e.g. ...\cowork apps\action_games) and none reference dj_music_apps.
The pollution comes from some other run (most likely a session launched with its
working directory set inside dj_music_apps). This script is a safe, re-runnable
cleanup; run it until whatever recreates the folders is found.

What it does:
  * moves each polluting  dj_music_apps\<Display Name>\  folder's files to the real
    category folder (see $map below),
  * NEVER overwrites an existing file (reports collisions and skips them),
  * removes the emptied shells,
  * writes a timestamped undo manifest to the cowork root,
  * LEAVES  dj_music_apps\DJ\  and the real DJ apps at the root alone -- the DJ
    daily prompt treats a DJ subfolder as legitimate. Pass -FlattenDJ if you also
    want dj_music_apps\DJ\* moved up to the dj_music_apps root,
  * reports any UNRECOGNIZED subfolder instead of touching it (new pollution type).

Dry-run by default. Add -Apply to actually move.

  pwsh -File Cleanup-DjMusicPollution.ps1                    # preview (safe)
  pwsh -File Cleanup-DjMusicPollution.ps1 -Apply            # relocate
  pwsh -File Cleanup-DjMusicPollution.ps1 -Apply -FlattenDJ # also flatten DJ\ into root

Put this script in the cowork apps root (Root defaults to the script's own folder),
or pass -Root "C:\Users\tokka\Claude Local\cowork apps".
#>
[CmdletBinding()]
param(
  [string]$Root = $PSScriptRoot,
  [switch]$Apply,
  [switch]$FlattenDJ
)
$ErrorActionPreference = 'Stop'
$SEP = [char]92

if (-not $Root) { $Root = (Get-Location).Path }
if (-not (Test-Path -LiteralPath (Join-Path $Root 'serve_apps.py'))) {
  Write-Host "ERROR: '$Root' is not the cowork apps root (no serve_apps.py there)." -ForegroundColor Red
  Write-Host "       Put this script in the cowork apps folder, or pass -Root <path>." -ForegroundColor Red
  exit 1
}
$dj = Join-Path $Root 'dj_music_apps'
if (-not (Test-Path -LiteralPath $dj)) { Write-Host "ERROR: no dj_music_apps under $Root" -ForegroundColor Red; exit 1 }

# polluting subfolder (under dj_music_apps)  ->  real destination (under Root)
$map = [ordered]@{
  'Content Creation/Adults' = 'Content Creation Apps/adult_apps'
  'Content Creation/Kids'   = 'Content Creation Apps/kid_apps'
  'Content Creation/Teens'  = 'Content Creation Apps/teen_apps'
  'Action Games'            = 'action_games'
  'Adult Puzzles'           = 'adult_puzzle_apps'
  'Card Games'              = 'card_games_apps'
  'Classroom Tools'         = 'classroom_tools'
  'Cooking Games'           = 'Cooking Games'
  'Crafts'                  = 'Crafts'
  'Fashion'                 = 'fashion_apps'
  'Kids Games'              = 'kids_apps'
  'Music Games'             = 'music_game_apps'
  'Music Production'        = 'Music Production'
  'Music'                   = 'music_apps'
  'Party Games'             = 'party_apps'
  'Productivity & Fitness'  = 'health_productivity_apps'
  'Reviews'                 = 'Reviews'
  'Shooting Games'          = 'Shooting Games'
  'Sports Games'            = 'sports_games_apps'
  'Table Games'             = 'table_games_apps'
  'Therapy'                 = 'therapy_apps'
}
if ($FlattenDJ) { $map['DJ'] = 'dj_music_apps' }

function ToOS([string]$p) { $p.Replace('/', $SEP) }

# --- scan ---
$moves      = New-Object System.Collections.Generic.List[object]
$collisions = New-Object System.Collections.Generic.List[object]
foreach ($k in $map.Keys) {
  $src = Join-Path $dj (ToOS $k)
  if (-not (Test-Path -LiteralPath $src)) { continue }
  $dstBase = Join-Path $Root (ToOS $map[$k])
  Get-ChildItem -LiteralPath $src -Recurse -File | ForEach-Object {
    $rel  = [System.IO.Path]::GetRelativePath($src, $_.FullName)
    $dest = Join-Path $dstBase $rel
    if (Test-Path -LiteralPath $dest) { $collisions.Add([pscustomobject]@{ From = $_.FullName; To = $dest }) }
    else { $moves.Add([pscustomobject]@{ From = $_.FullName; To = $dest; Cat = $map[$k] }) }
  }
}

# unrecognized subfolders (potential NEW pollution) - report, never touch
$known   = @($map.Keys | ForEach-Object { ($_ -split '/')[0] }) + @('DJ') | Select-Object -Unique
$unknown = Get-ChildItem -LiteralPath $dj -Directory | Where-Object { $known -notcontains $_.Name } | Select-Object -ExpandProperty Name

# --- report ---
Write-Host ""
Write-Host "  Cowork root : $Root"
Write-Host ("  Mode        : {0}{1}" -f ($(if ($Apply) { 'APPLY (moves files)' } else { 'DRY-RUN (preview only)' })), ($(if ($FlattenDJ) { '  +FlattenDJ' } else { '' })))
Write-Host ""
Write-Host ("  Files to relocate : {0}" -f $moves.Count) -ForegroundColor Cyan
if ($moves.Count) {
  $moves | Group-Object Cat | Sort-Object Name | ForEach-Object { Write-Host ("    {0,3}  ->  {1}" -f $_.Count, $_.Name) }
}
if ($collisions.Count) {
  Write-Host ""
  Write-Host ("  Collisions (target already exists - SKIPPED): {0}" -f $collisions.Count) -ForegroundColor Yellow
  $collisions | ForEach-Object { Write-Host ("    ! " + $_.To) -ForegroundColor Yellow }
}
if (-not $FlattenDJ -and (Test-Path -LiteralPath (Join-Path $dj 'DJ'))) {
  Write-Host ""
  Write-Host "  dj_music_apps\DJ\ left in place (pass -FlattenDJ to move it up to the root)." -ForegroundColor DarkGray
}
if ($unknown) {
  Write-Host ""
  Write-Host ("  UNRECOGNIZED subfolders in dj_music_apps (left untouched - check these): {0}" -f ($unknown -join ', ')) -ForegroundColor Magenta
}
Write-Host ""

if (-not $moves.Count) { Write-Host "  Nothing to relocate - dj_music_apps is clean." -ForegroundColor Green; exit 0 }
if (-not $Apply) { Write-Host "  DRY-RUN: nothing moved. Re-run with -Apply to relocate the files above." -ForegroundColor Yellow; exit 0 }

# --- apply ---
$stamp    = Get-Date -Format 'yyyyMMdd-HHmmss'
$manifest = Join-Path $Root ("_dj_pollution_undo_" + $stamp + ".json")
($moves | ForEach-Object { [pscustomobject]@{ from = $_.To; to = $_.From } }) |
  ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifest -Encoding UTF8
Write-Host "  Undo manifest: $manifest"

foreach ($m in $moves) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $m.To) | Out-Null
  Move-Item -LiteralPath $m.From -Destination $m.To
}
Write-Host ("  Moved {0} file(s)." -f $moves.Count) -ForegroundColor Green

# remove emptied shells (retry: Windows sometimes locks a just-emptied dir)
$removed = 0
foreach ($k in $map.Keys) {
  $top = ($k -split '/')[0]
  $p = Join-Path $dj $top
  if (-not (Test-Path -LiteralPath $p)) { continue }
  if (Get-ChildItem -LiteralPath $p -Recurse -File -ErrorAction SilentlyContinue) { continue }
  for ($i = 0; $i -lt 6; $i++) {
    try { Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction Stop; $removed++; break }
    catch { Start-Sleep -Milliseconds 400 }
  }
}
Write-Host ("  Removed {0} emptied pollution shell(s)." -f $removed) -ForegroundColor Green
Write-Host ""
Write-Host "  Done. Re-run in dry-run mode any time to confirm dj_music_apps stays clean." -ForegroundColor Green
exit 0

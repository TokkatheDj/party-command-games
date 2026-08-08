<#
Restore-CoworkContent.ps1
Safely restore Cowork Apps content from a Google-Drive backup ZIP onto THIS machine.

Why this exists: the Surface backup zips carry a known defect - the Surface's
_scheduler category generators write apps INTO dj_music_apps\<Display Name>\
(e.g. dj_music_apps\Action Games\, dj_music_apps\DJ\, dj_music_apps\Therapy\)
instead of the real category folders. A naive restore reproduces that mess on
this machine (it did on 2026-07-23). This script makes a restore safe:
  * extracts the zip to a throwaway STAGING folder (never straight onto the tree),
  * REMAPS the known dj_music_apps\<Display Name>\ pollution back to the correct
    category folder (see $remap) so apps land where they belong,
  * copies ONLY genuinely-new app files (*.html, plus Reviews\*.md),
  * targets the tree ROOT only (verified by serve_apps.py) - never a raw subfolder,
  * NEVER overwrites an existing file and NEVER touches infra/config/scripts,
  * NEVER deletes anything.

Dry-run by default. Add -Apply to actually copy.

Usage:
  pwsh -File Restore-CoworkContent.ps1                       # preview, newest backup
  pwsh -File Restore-CoworkContent.ps1 -Zip 'G:/My Drive/Backups/cowork-apps-content/cowork-content-20260722-211949.zip'
  pwsh -File Restore-CoworkContent.ps1 -Apply               # copy new files, newest backup
  pwsh -File Restore-CoworkContent.ps1 -NoRemap            # copy paths verbatim (debug)
#>
[CmdletBinding()]
param(
  [string]$Zip,
  [string]$BackupDir = 'G:/My Drive/Backups/cowork-apps-content',
  [string]$Root      = $PSScriptRoot,
  [switch]$Apply,
  [switch]$NoRemap
)
$ErrorActionPreference = 'Stop'
$SEP = [char]92   # backslash, without writing a literal one

# Known-pollution remap: dj_music_apps\<Display Name>\ -> real category folder.
# Longest prefixes are applied first, so the Content Creation age tiers and
# "Music Games"/"Music Production" win over the shorter "Music".
$remap = [ordered]@{
  'dj_music_apps/Content Creation/Adults/' = 'Content Creation Apps/adult_apps/'
  'dj_music_apps/Content Creation/Kids/'   = 'Content Creation Apps/kid_apps/'
  'dj_music_apps/Content Creation/Teens/'  = 'Content Creation Apps/teen_apps/'
  'dj_music_apps/Productivity & Fitness/'  = 'health_productivity_apps/'
  'dj_music_apps/Classroom Tools/'         = 'classroom_tools/'
  'dj_music_apps/Music Production/'         = 'Music Production/'
  'dj_music_apps/Shooting Games/'          = 'Shooting Games/'
  'dj_music_apps/Adult Puzzles/'           = 'adult_puzzle_apps/'
  'dj_music_apps/Cooking Games/'           = 'Cooking Games/'
  'dj_music_apps/Action Games/'            = 'action_games/'
  'dj_music_apps/Sports Games/'            = 'sports_games_apps/'
  'dj_music_apps/Music Games/'             = 'music_game_apps/'
  'dj_music_apps/Party Games/'             = 'party_apps/'
  'dj_music_apps/Table Games/'             = 'table_games_apps/'
  'dj_music_apps/Card Games/'              = 'card_games_apps/'
  'dj_music_apps/Kids Games/'              = 'kids_apps/'
  'dj_music_apps/Fashion/'                 = 'fashion_apps/'
  'dj_music_apps/Therapy/'                 = 'therapy_apps/'
  'dj_music_apps/Crafts/'                  = 'Crafts/'
  'dj_music_apps/Reviews/'                 = 'Reviews/'
  'dj_music_apps/Music/'                   = 'music_apps/'
  'dj_music_apps/DJ/'                      = 'dj_music_apps/'
}
$remapKeys = $remap.Keys | Sort-Object { $_.Length } -Descending

function Remap-Path([string]$relNorm) {
  if ($NoRemap) { return $relNorm }
  foreach ($k in $remapKeys) {
    if ($relNorm.StartsWith($k, [System.StringComparison]::OrdinalIgnoreCase)) {
      return $remap[$k] + $relNorm.Substring($k.Length)
    }
  }
  return $relNorm
}

# --- 1. Validate the target root (guard against restoring into a subfolder) ---
if (-not (Test-Path -LiteralPath (Join-Path $Root 'serve_apps.py'))) {
  Write-Host "ERROR: '$Root' is not the cowork apps root (no serve_apps.py there)." -ForegroundColor Red
  Write-Host "       Run from inside the cowork apps folder, or pass -Root <path>." -ForegroundColor Red
  exit 1
}

# --- 2. Pick the backup zip (newest if not specified) ---
if (-not $Zip) {
  if (-not (Test-Path -LiteralPath $BackupDir)) {
    Write-Host "ERROR: backup folder not found: $BackupDir (is Google Drive 'G:' mounted?)" -ForegroundColor Red
    exit 1
  }
  $Zip = (Get-ChildItem -LiteralPath $BackupDir -Filter 'cowork-content-*.zip' |
          Sort-Object Name -Descending | Select-Object -First 1).FullName
  if (-not $Zip) { Write-Host "ERROR: no cowork-content-*.zip in $BackupDir" -ForegroundColor Red; exit 1 }
}
if (-not (Test-Path -LiteralPath $Zip)) { Write-Host "ERROR: zip not found: $Zip" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  Backup zip : $Zip"
Write-Host "  Restore to : $Root"
Write-Host ("  Mode       : {0}{1}" -f ($(if ($Apply) { 'APPLY (copies new files)' } else { 'DRY-RUN (preview only)' })), ($(if ($NoRemap) { '  [remap OFF]' } else { '' })))
Write-Host ""

# --- 3. Extract to a throwaway staging folder ---
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("cowork-restore-" + [System.IO.Path]::GetFileNameWithoutExtension($Zip))
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
Expand-Archive -LiteralPath $Zip -DestinationPath $stage -Force

# If the zip wraps everything in one top folder, descend into it.
if (-not (Test-Path -LiteralPath (Join-Path $stage 'serve_apps.py'))) {
  $kids = Get-ChildItem -LiteralPath $stage
  if ($kids.Count -eq 1 -and $kids[0].PSIsContainer -and
      (Test-Path -LiteralPath (Join-Path $kids[0].FullName 'serve_apps.py'))) {
    $stage = $kids[0].FullName
  }
}

# --- 4. Decide what to copy: only NEW app files, remapped, never infra/overwrite ---
$add = New-Object System.Collections.Generic.List[object]
$existing = 0; $skippedInfra = 0; $remapped = 0

Get-ChildItem -LiteralPath $stage -Recurse -File | ForEach-Object {
  $rel     = [System.IO.Path]::GetRelativePath($stage, $_.FullName)
  $relNorm = $rel.Replace($SEP, '/')
  $ext     = $_.Extension.ToLower()
  $isApp   = ($ext -eq '.html')
  $isRev   = ($ext -eq '.md' -and $relNorm -match '(^|/)Reviews/')
  if (-not ($isApp -or $isRev)) { $skippedInfra++; return }   # skip infra/config/scripts/etc.
  $relDest = Remap-Path $relNorm
  if ($relDest -ne $relNorm) { $remapped++ }
  $dest = Join-Path $Root ($relDest.Replace('/', $SEP))
  if (Test-Path -LiteralPath $dest) { $existing++; return }   # never overwrite
  $add.Add([pscustomobject]@{ Rel = $relDest; Src = $_.FullName; Dest = $dest })
}

# --- 5. Report ---
Write-Host ("  New app files to add   : {0}" -f $add.Count) -ForegroundColor Cyan
Write-Host ("  Remapped from dj_music_apps: {0}" -f $remapped)
Write-Host ("  Already present (skip)  : {0}" -f $existing)
Write-Host ("  Infra/other  (skip)     : {0}" -f $skippedInfra)
Write-Host ""
if ($add.Count) {
  $add | Group-Object { $d = Split-Path $_.Rel -Parent; if ($d) { $d } else { '(root)' } } |
    Sort-Object Name | ForEach-Object { Write-Host ("    +{0,3}  {1}" -f $_.Count, $_.Name) }
  Write-Host ""
}

# --- 6. Apply, or stop after preview ---
if (-not $Apply) {
  Write-Host "  DRY-RUN: nothing copied. Re-run with -Apply to add the new files listed above." -ForegroundColor Yellow
  Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
  exit 0
}
foreach ($f in $add) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $f.Dest) | Out-Null
  Copy-Item -LiteralPath $f.Src -Destination $f.Dest
}
Write-Host ("  DONE: added {0} new app file(s). The server auto-discovers them on next page load." -f $add.Count) -ForegroundColor Green
Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
exit 0

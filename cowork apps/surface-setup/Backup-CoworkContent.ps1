# Backup-CoworkContent.ps1
# Daily versioned backup of the cowork-apps content folders to Google Drive.
# Zips the "cowork apps" tree (minus regenerable/ephemeral dirs), timestamps it,
# verifies the archive, and prunes old snapshots. Appends to a sibling .log.
#
# Source of truth: C:\Users\tokka\Claude Local\cowork apps  (27 gitignored content
# folders that are NOT on GitHub -> this is their only durable copy).
#
# WHY THIS IS MORE PARANOID THAN IT LOOKS  (incident 2026-09-08)
# Between 2026-09-01 and 2026-09-08 this script logged "OK" four times and produced
# no backup at all. Google Drive for Desktop accepted each write into its virtual
# filesystem, failed to sync it, and moved the file to
#   %LOCALAPPDATA%\Google\DriveFS\lost_and_found\<accountId>\
# The task exited 0 the whole time. Three separate holes made that silent:
#   1. Test-Path 'G:\' passes as soon as the drive letter exists, which is long
#      before Drive is ready to accept writes. The task carries StartWhenAvailable,
#      so after a wake it fires within minutes of GoogleDriveFS starting (on
#      2026-09-08: Drive up 08:51, backup ran 08:54, quarantined 08:59).
#   2. The archive was written straight into G:\ and then verified by reading it
#      back -- which reads Drive's LOCAL CACHE, so verification passed on a file
#      that never reached the cloud.
#   3. Pruning ran immediately after that false OK, so a bad day could delete a
#      good old snapshot while leaving no new one.
# The fixes, in order: probe that the destination actually retains a file; build
# and verify the zip on LOCAL disk; copy it up and re-check that it survived;
# prune only after that check passes; exit non-zero (and keep a local fallback)
# when it does not.

$src      = 'C:\Users\tokka\Claude Local\cowork apps'
$destDir  = 'G:\My Drive\Backups\cowork-apps-content'
$log      = 'C:\Users\tokka\bin\Backup-CoworkContent.log'
$fallback = 'C:\Users\tokka\bin\backup-fallback'   # local landing pad when Drive misbehaves
$keep     = 14   # retain this many most-recent snapshots
$keepLocal= 2    # fallback copies to retain (same disk as source - a stopgap, not a backup)
$exclude  = @('node_modules','__pycache__','.playwright-mcp','test_reports','.pytest_cache')

function Log($msg){
  Add-Content -LiteralPath $log -Value ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg)
}

# Write a probe file and confirm it is still there after a settle delay. Drive
# quarantines asynchronously, so an immediate Test-Path proves nothing.
function Test-DestinationRetains {
  param([string]$Dir, [int]$SettleSec = 10)
  $probe = Join-Path $Dir ("_probe-{0}-{1}.txt" -f (Get-Date -Format 'yyyyMMddHHmmss'), $PID)
  try {
    Set-Content -LiteralPath $probe -Value 'backup readiness probe' -ErrorAction Stop
  } catch {
    return $false
  }
  Start-Sleep -Seconds $SettleSec
  $ok = Test-Path -LiteralPath $probe
  Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
  return $ok
}

try {
  if(-not (Test-Path -LiteralPath $src)){ Log "ERROR source missing: $src"; exit 2 }
  if(-not (Test-Path -LiteralPath 'G:\')){ Log "ERROR G: (Google Drive) not mounted - skipped"; exit 3 }
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null

  # Wait for Drive to actually be ready, not merely mounted. Six tries over ~5
  # minutes comfortably covers the post-wake window that caused the incident.
  $ready = $false
  foreach($attempt in 1..6){
    if(Test-DestinationRetains -Dir $destDir){ $ready = $true; break }
    Log "WARN destination not retaining files (attempt $attempt/6) - waiting 60s"
    Start-Sleep -Seconds 60
  }
  if(-not $ready){
    Log "ERROR Google Drive is mounted but not retaining writes - backup aborted, nothing pruned"
    exit 5
  }

  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $stage = Join-Path $env:TEMP "coworkbak-$stamp"

  # Stage a filtered copy (Compress-Archive can't exclude subdirs directly).
  $rcArgs = @($src, $stage, '/E', '/XD') + $exclude + @('/R:1','/W:1','/NFL','/NDL','/NP','/NJH','/NJS')
  & robocopy @rcArgs | Out-Null
  if($LASTEXITCODE -ge 8){ Log "ERROR robocopy staging failed (code $LASTEXITCODE)"; Remove-Item $stage -Recurse -Force -EA SilentlyContinue; exit 4 }

  # Build the archive on LOCAL disk. Compressing straight into the Drive virtual
  # filesystem is what let a half-synced write masquerade as a good backup.
  $name     = "cowork-content-$stamp.zip"
  $localZip = Join-Path $env:TEMP $name
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $localZip -CompressionLevel Optimal -Force
  Remove-Item $stage -Recurse -Force -EA SilentlyContinue

  # Verify the local archive opens and count entries (this one is trustworthy -
  # it is a real local file, not a Drive placeholder).
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $z = [System.IO.Compression.ZipFile]::OpenRead($localZip); $entries = $z.Entries.Count; $z.Dispose()
  $mb = [math]::Round((Get-Item $localZip).Length/1MB,1)
  if($entries -lt 1){ Log "ERROR archive built but contains 0 entries - aborting"; Remove-Item $localZip -Force -EA SilentlyContinue; exit 6 }

  # Copy up, then confirm it SURVIVED. Two attempts: Drive can quarantine the
  # first copy and accept a retry once it has settled.
  $zip     = Join-Path $destDir $name
  $landed  = $false
  foreach($attempt in 1..2){
    Copy-Item -LiteralPath $localZip -Destination $zip -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 30
    if(Test-Path -LiteralPath $zip){
      $destMb = [math]::Round((Get-Item $zip).Length/1MB,1)
      if($destMb -ge ($mb * 0.99)){ $landed = $true; break }
      Log "WARN copy landed short ($destMb MB vs $mb MB) on attempt $attempt"
    } else {
      Log "WARN copy vanished after 30s on attempt $attempt (Drive quarantine?)"
    }
    Start-Sleep -Seconds 30
  }

  if(-not $landed){
    # Keep the archive somewhere rather than losing the day entirely, and make
    # the failure LOUD: non-zero exit so the task result stops reading as success.
    New-Item -ItemType Directory -Force -Path $fallback | Out-Null
    Move-Item -LiteralPath $localZip -Destination (Join-Path $fallback $name) -Force -EA SilentlyContinue
    Log "ERROR backup did NOT reach Drive. Kept local copy at $fallback\$name ($mb MB, $entries entries). Nothing pruned."
    Log "      check %LOCALAPPDATA%\Google\DriveFS\lost_and_found\ and Drive sync status"
    # Trim the local fallback so it cannot fill the disk.
    Get-ChildItem -LiteralPath $fallback -Filter 'cowork-content-*.zip' -EA SilentlyContinue |
      Sort-Object Name -Descending | Select-Object -Skip $keepLocal |
      ForEach-Object { Remove-Item $_.FullName -Force -EA SilentlyContinue }
    exit 7
  }

  Remove-Item $localZip -Force -EA SilentlyContinue
  Log ("OK  {0}  ({1} MB, {2} entries)" -f $name, $mb, $entries)

  # Prune ONLY after a confirmed-good upload, so a failed day never costs us an
  # old snapshot. Timestamped names sort chronologically.
  $all = Get-ChildItem -LiteralPath $destDir -Filter 'cowork-content-*.zip' -EA SilentlyContinue | Sort-Object Name -Descending
  if($all.Count -gt $keep){
    $all | Select-Object -Skip $keep | ForEach-Object { Remove-Item $_.FullName -Force; Log "pruned $($_.Name)" }
  }
  exit 0
}
catch {
  Log "ERROR $($_.Exception.Message)"
  exit 1
}

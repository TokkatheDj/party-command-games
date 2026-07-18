# Backup-CoworkContent.ps1
# Daily versioned backup of the cowork-apps content folders to Google Drive.
# Zips the "cowork apps" tree (minus regenerable/ephemeral dirs), timestamps it,
# verifies the archive, and prunes old snapshots. Appends to a sibling .log.
#
# Source of truth: C:\Users\tokka\Claude Local\cowork apps  (27 gitignored content
# folders that are NOT on GitHub -> this is their only durable copy).

$src     = 'C:\Users\tokka\Claude Local\cowork apps'
$destDir = 'G:\My Drive\Backups\cowork-apps-content'
$log     = 'C:\Users\tokka\bin\Backup-CoworkContent.log'
$keep    = 14   # retain this many most-recent snapshots
$exclude = @('node_modules','__pycache__','.playwright-mcp','test_reports','.pytest_cache')

function Log($msg){
  Add-Content -LiteralPath $log -Value ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg)
}

try {
  if(-not (Test-Path -LiteralPath $src)){ Log "ERROR source missing: $src"; exit 2 }
  if(-not (Test-Path -LiteralPath 'G:\')){ Log "ERROR G: (Google Drive) not mounted - skipped"; exit 3 }
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null

  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $stage = Join-Path $env:TEMP "coworkbak-$stamp"

  # Stage a filtered copy (Compress-Archive can't exclude subdirs directly).
  $rcArgs = @($src, $stage, '/E', '/XD') + $exclude + @('/R:1','/W:1','/NFL','/NDL','/NP','/NJH','/NJS')
  & robocopy @rcArgs | Out-Null
  if($LASTEXITCODE -ge 8){ Log "ERROR robocopy staging failed (code $LASTEXITCODE)"; Remove-Item $stage -Recurse -Force -EA SilentlyContinue; exit 4 }

  $zip = Join-Path $destDir "cowork-content-$stamp.zip"
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal -Force
  Remove-Item $stage -Recurse -Force -EA SilentlyContinue

  # Verify the archive opens and count entries.
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $z = [System.IO.Compression.ZipFile]::OpenRead($zip); $entries = $z.Entries.Count; $z.Dispose()
  $mb = [math]::Round((Get-Item $zip).Length/1MB,1)
  Log ("OK  {0}  ({1} MB, {2} entries)" -f (Split-Path $zip -Leaf), $mb, $entries)

  # Prune: keep the newest $keep snapshots (timestamped names sort chronologically).
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

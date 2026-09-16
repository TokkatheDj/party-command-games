# New-ReviewBatch.ps1
# Builds ONE batch file for a review session: the game URLs to play, plus the
# concepts already in the collection so duplicates can be spotted.
#
# TWO WAYS TO REVIEW
#
#   1. Antigravity on the Desktop -- use -Remote. The usual case: Codex's browser
#      plugin needs school admin approval on that machine, while Antigravity's
#      Browser Subagent is built in and needs none. The reviewer is on another
#      box, so it cannot read this machine's registry and the concepts have to
#      travel inline. It also cannot touch the collection at all, which is a
#      real safety property and not just a limitation.
#
#   2. Codex on the Surface -- the defaults with no switches. Reaches the games
#      at localhost:8080 and reads the registry off disk, so batches are ~1 KB
#      instead of ~95 KB. Codex's browser plugin IS already enabled here. The
#      trade: the reviewer has full write access to the collection, so
#      "don't edit anything" rests only on the brief.
#
# Either way this script runs ON THE SURFACE, because that is where the games are.
# _scheduler/Registry/ is machine-local and gitignored on purpose -- do not sync
# it to solve the remote case; carrying concepts as text is the point.
#
# Usage:
#   .\New-ReviewBatch.ps1 -Remote                # Antigravity on the Desktop
#   .\New-ReviewBatch.ps1                        # reviewer here on the Surface
#   .\New-ReviewBatch.ps1 -Remote -Days 3 -Count 12
#   .\New-ReviewBatch.ps1 -Remote -Category kids_apps

[CmdletBinding()]
param(
    # The usual case: the reviewer is Antigravity on the Desktop. Finds this
    # machine's Tailscale address, inlines the concepts, and writes the batch to
    # Drive -- the three things that are easy to get wrong by hand.
    [switch]$Remote,

    # Where the reviewer can reach AppVerse. Overrides -Remote's detection.
    # Left unset it is localhost, which is right only for a reviewer running here.
    [string]$BaseUrl,
    [int]$Days = 1,
    [int]$Count = 10,
    [string]$Category,
    [string]$OutDir,
    # Inline the ~640 concepts instead of pointing at the registry. Implied by
    # -Remote. Costs ~95 KB of prompt, versus ~1 KB by reference.
    [switch]$Embed
)

$ErrorActionPreference = 'Stop'
$appsRoot = Split-Path $PSScriptRoot -Parent          # ...\cowork apps
$registry = Join-Path $appsRoot '_scheduler\Registry\ALL-CONCEPTS.tsv'

if ($Remote) {
    # A reviewer on another machine cannot read this machine's registry, and a
    # batch left in the local folder never reaches it.
    $Embed = $true
    if (-not $OutDir) { $OutDir = 'G:\My Drive\AppVerse Review' }
    if (-not $BaseUrl) {
        # Tailscale over LAN: it survives the Surface moving between networks,
        # which the 192.168.x address does not.
        $ts = (Get-NetIPAddress -AddressFamily IPv4 -EA SilentlyContinue |
               Where-Object { $_.IPAddress -like '100.*' } |
               Select-Object -First 1).IPAddress
        if (-not $ts) {
            Write-Host "-Remote needs a reachable address, but Tailscale looks down." -ForegroundColor Red
            Write-Host "  Start Tailscale, or pass -BaseUrl 'http://<lan-ip>:8080' explicitly." -ForegroundColor Red
            exit 2
        }
        $BaseUrl = "http://${ts}:8080"
    }
}
if (-not $BaseUrl) { $BaseUrl = 'http://localhost:8080' }
if (-not $OutDir)  { $OutDir  = Join-Path $PSScriptRoot 'batches' }
$BaseUrl = $BaseUrl.TrimEnd('/')

# --- pick the games -------------------------------------------------------
$since = (Get-Date).Date.AddDays(-1 * ($Days - 1))
$skip  = @('_scheduler','node_modules','__pycache__','.git','test_reports','test_screens','surface-setup','review-kit','build-my-app','.claude')

# Path segments that never appear in a real game's path but do appear when
# something dumps an app-data tree into the collection. On 2026-09-08 a batch
# picked up eval_review.html from a transient
# "Packages\Claude_<id>\LocalCache\Roaming\Claude\...\skills-plugin\..." tree
# that had been created inside "cowork apps" -- a path resolved against the
# wrong working directory. A folder-name denylist alone cannot anticipate that.
$junk  = @('Packages','AppData','LocalCache','LocalState','skills-plugin','.git','node_modules')

# Every real game is at depth 2, 3 or 4 relative to "cowork apps"
# (category\file, category\sub\file, category\sub\sub\file). Measured across the
# whole collection: 451 at 2, 200 at 3, 11 at 4, and NOTHING deeper. The junk
# above sat at depth 10, so this single rule excludes it while keeping every
# real game -- including the nine older ones that predate the YYYY-MM-DD naming.
$maxDepth = 4

$games = Get-ChildItem -LiteralPath $appsRoot -Filter '*.html' -Recurse -File -EA SilentlyContinue |
    Where-Object {
        $rel   = $_.FullName.Substring($appsRoot.Length + 1)
        $parts = $rel.Split('\')
        $top   = $parts[0]
        # A file sitting directly in the root is infrastructure (all-games-hub.html,
        # index pages), not a game. Games always live in a category folder.
        ($parts.Count -gt 1) -and
        ($parts.Count -le $maxDepth) -and
        ($skip -notcontains $top) -and
        (-not ($parts | Where-Object { $junk -contains $_ })) -and
        ($rel -notlike '.tmp-*') -and
        (-not $Category -or $top -eq $Category) -and
        ($_.LastWriteTime -ge $since)
    } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First $Count

if (-not $games) {
    Write-Host "No games found matching those filters (Days=$Days, Category='$Category')." -ForegroundColor Red
    exit 1
}

# --- build the batch file -------------------------------------------------
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd'
$out   = Join-Path $OutDir "review-batch-$stamp.md"

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# Review batch - $stamp")
$lines.Add("")
$lines.Add("$($games.Count) games. Play every URL below. Follow REVIEW-BRIEF.md.")
$lines.Add("")
$lines.Add("## Games to play")
$lines.Add("")
$lines.Add("| # | Game | URL |")
$lines.Add("|---|---|---|")
$i = 0
foreach ($g in $games) {
    $i++
    $rel = $g.FullName.Substring($appsRoot.Length + 1).Replace('\', '/')
    $url = "$BaseUrl/" + ($rel -replace ' ', '%20')
    $lines.Add("| $i | ``$($g.Name)`` | $url |")
}

$lines.Add("")
$lines.Add("## Concepts already in the collection (for the duplicate check)")
$lines.Add("")

if (-not (Test-Path -LiteralPath $registry)) {
    $lines.Add("_Registry not found at ``$registry`` - run ``_scheduler\Rebuild-Registry.ps1`` first._")
    $lines.Add("_Without it the duplicate check cannot be done. Say so in the report rather than guessing._")
}
elseif ($Embed) {
    $lines.Add("Compare each game's core mechanic against these. A theme change is not a new concept.")
    $lines.Add("")
    foreach ($row in (Get-Content -LiteralPath $registry -EA SilentlyContinue)) {
        $parts = $row -split "`t"
        if ($parts.Count -ge 2) {
            $file = $parts[-2]
            $txt  = $parts[-1]
            # Skip the .tsv header row, which otherwise renders as a game called "slug".
            if ($file -eq 'slug' -or $txt -like 'concept*') { continue }
            if ($txt.Length -gt 110) { $txt = $txt.Substring(0, 110) + '...' }
            $lines.Add("- ``$file`` - $txt")
        }
    }
}
else {
    $rows = @(Get-Content -LiteralPath $registry -EA SilentlyContinue).Count - 1
    $lines.Add("Read the registry directly - you are on the machine that holds it:")
    $lines.Add("")
    $lines.Add("``$registry``")
    $lines.Add("")
    $lines.Add("It is a tab-separated file of about $rows shipped concepts, one per line, with the")
    $lines.Add("slug in the second-to-last column and the concept text in the last. Compare each")
    $lines.Add("game's core mechanic against it. A theme change is not a new concept.")
}

# Not Set-Content -Encoding UTF8: under Windows PowerShell 5.1 that writes a BOM,
# which shows up as stray characters at the top of the rendered report.
[System.IO.File]::WriteAllLines($out, $lines, (New-Object System.Text.UTF8Encoding($false)))

$kb = [math]::Round((Get-Item $out).Length / 1KB, 1)
Write-Host ""
Write-Host "Batch written: $out  ($kb KB)" -ForegroundColor Green
Write-Host "  $($games.Count) games, base URL $BaseUrl"
if ($Embed) { Write-Host "  concepts inlined (remote reviewer)" }
else        { Write-Host "  concepts referenced by path (reviewer reads them locally)" }
Write-Host ""
Write-Host "Confirm this loads in a browser before starting the review:" -ForegroundColor Cyan
Write-Host "  $BaseUrl"

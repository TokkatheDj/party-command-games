# Rebuild-Registry.ps1
# Builds the concept registry the generator routines read in STEP 1.
#
# WHY THIS EXISTS
# Dedup used to be one line of prose -- "build a mental list of concepts already
# covered" -- re-derived every run from opaque slugs like
# 2026-08-27-grid-breach-popup-purge.html. With 500+ apps that stopped working:
# 22 exact slug collisions, TriPeaks solitaire x3, monster-maker x6 across four
# folders. This turns the <!-- CONCEPT: --> header every app already carries
# (required by CLAUDE.md) into something a routine can actually read and grep.
#
# OUTPUT (in .\Registry)
#   <category>.tsv     date \t slug \t concept        -- one category, full text
#   ALL-CONCEPTS.tsv   date \t category \t slug \t concept(120) -- every app, for grep
#   _MISSING.txt       apps with no CONCEPT header, so they can be backfilled
#
# Nested subfolders roll UP into their top-level category on purpose: apps are
# split between e.g. action_games\ (10) and action_games\Action Games Generator\
# (18), and a non-recursive listing was blind to the larger half.
#
# Called by Run-CoworkRoutine.ps1 before every run, so same-day duplicates are
# caught too. Writes are temp-file + atomic move because several routines can
# start at the same instant (four did on 2026-08-30).

[CmdletBinding()]
param(
    [string]$Root        = "C:\Users\tokka\Claude Local\cowork apps",
    [string]$RegistryDir = "",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

if (-not $RegistryDir) {
    $RegistryDir = Join-Path $Root "_scheduler\Registry"
}
New-Item -ItemType Directory -Force -Path $RegistryDir | Out-Null

# Folders that hold tooling/output rather than apps.
$SkipTop = @(
    '_scheduler', 'node_modules', '__pycache__', '.git', '.github',
    'test_reports', 'test_screens', 'surface-setup', 'Reviews', 'Bug Reports'
)

# Top-level folders whose CHILD folder is the real category, because separate
# routines target each child (kids / teens / adults content creation).
$SplitTop = @('Content Creation Apps')

function Get-CategoryKey {
    param([string]$RelPath)   # e.g. "action_games\Action Games Generator\x.html"
    $parts = $RelPath -split '[\\/]'
    if ($parts.Count -lt 2) { return $null }        # loose html at the repo root
    $top = $parts[0]
    if ($SkipTop -contains $top) { return $null }
    if (($SplitTop -contains $top) -and $parts.Count -ge 3) {
        return "$top/$($parts[1])"
    }
    return $top
}

# Category key -> the .tsv basename a routine prompt names. Kept short and stable.
function Get-CategoryFile {
    param([string]$Key)
    switch ($Key) {
        'Content Creation Apps/kid_apps'   { return 'content-kids' }
        'Content Creation Apps/teen_apps'  { return 'content-teens' }
        'Content Creation Apps/adult_apps' { return 'content-adults' }
        default { return ($Key -replace '[\\/]', '-') -replace '[^A-Za-z0-9_.-]', '-' }
    }
}

function Write-Atomic {
    param([string]$Path, [string[]]$Lines)
    $tmp = "$Path.tmp.$PID"
    # NOT Set-Content -Encoding UTF8: under Windows PowerShell 5.1 (which is what
    # the scheduled tasks run) that emits a UTF-8 BOM, and the BOM lands on the
    # first header line where it breaks naive line/prefix matching.
    [System.IO.File]::WriteAllLines($tmp, $Lines, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

$rootFull = (Resolve-Path -LiteralPath $Root).Path
$all      = New-Object System.Collections.Generic.List[object]
$missing  = New-Object System.Collections.Generic.List[string]

Get-ChildItem -LiteralPath $rootFull -Recurse -Filter *.html -File -ErrorAction SilentlyContinue |
    ForEach-Object {
        $rel = $_.FullName.Substring($rootFull.Length).TrimStart('\', '/')
        $key = Get-CategoryKey -RelPath $rel
        if (-not $key) { return }

        # Read only the head of the file -- the CONCEPT comment is required to be
        # the very first line, and some apps are 700KB.
        $head = ''
        try {
            $fs = [System.IO.File]::OpenRead($_.FullName)
            $buf = New-Object byte[] 4096
            $n = $fs.Read($buf, 0, $buf.Length)
            $fs.Close()
            $head = [System.Text.Encoding]::UTF8.GetString($buf, 0, $n)
        } catch { return }

        $m = [regex]::Match($head, '<!--\s*CONCEPT:\s*(.*?)-->', 'Singleline, IgnoreCase')
        if (-not $m.Success) { $missing.Add($rel); return }

        # Flatten to one TSV-safe line.
        $concept = ($m.Groups[1].Value -replace '[\t\r\n]+', ' ') -replace '\s{2,}', ' '
        $concept = $concept.Trim()

        $name = $_.BaseName
        $date = '-'
        if ($name -match '^(\d{4}-\d{2}-\d{2})-(.+)$') {
            $date = $Matches[1]
            $slug = $Matches[2]
        } else {
            $slug = $name
        }

        $all.Add([pscustomobject]@{
            Date = $date; Category = $key; Slug = $slug; Concept = $concept; Rel = $rel
        })
    }

# Per-category files: full concept text, one file per routine to read.
$byCat = $all | Group-Object Category
foreach ($g in $byCat) {
    $file  = Join-Path $RegistryDir ((Get-CategoryFile -Key $g.Name) + '.tsv')
    $lines = @("# $($g.Name) -- $($g.Count) apps -- rebuilt $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
    $lines += "# date`tslug`tconcept"
    $lines += ($g.Group | Sort-Object Date, Slug | ForEach-Object {
        "$($_.Date)`t$($_.Slug)`t$($_.Concept)"
    })
    Write-Atomic -Path $file -Lines $lines
}

# Global grep target: concept truncated so the file stays small enough to scan fast.
$allLines = @("# every app, all categories -- $($all.Count) rows -- rebuilt $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
$allLines += "# date`tcategory`tslug`tconcept(truncated)"
$allLines += ($all | Sort-Object Category, Date, Slug | ForEach-Object {
    $c = $_.Concept
    if ($c.Length -gt 120) { $c = $c.Substring(0, 120) }
    "$($_.Date)`t$($_.Category)`t$($_.Slug)`t$c"
})
Write-Atomic -Path (Join-Path $RegistryDir 'ALL-CONCEPTS.tsv') -Lines $allLines

$missLines = @("# apps with no <!-- CONCEPT: --> header ($($missing.Count)) -- rebuilt $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
$missLines += ($missing | Sort-Object)
Write-Atomic -Path (Join-Path $RegistryDir '_MISSING.txt') -Lines $missLines

if (-not $Quiet) {
    # Write-Output, not Write-Host: the wrapper captures this into its log.
    Write-Output "$($all.Count) apps across $($byCat.Count) categories, $($missing.Count) missing CONCEPT header"
}

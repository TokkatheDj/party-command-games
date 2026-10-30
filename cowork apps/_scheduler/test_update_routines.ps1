# test_update_routines.ps1 - every way Update-Routines can meet the Surface's clone,
# against throwaway repos (29 Oct 2026). Exits 1 on any failure.
#   powershell -NoProfile -File test_update_routines.ps1      (Windows PowerShell 5.1, like the tasks)
#   pwsh -NoProfile -File test_update_routines.ps1
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Update-Routines.ps1")

$script:fails = 0
function Check([string]$name, [bool]$ok, [string]$detail = "") {
    if ($ok) { Write-Host "PASS  $name" } else { Write-Host "FAIL  $name  -- $detail"; $script:fails++ }
}
function G { param([string]$dir) $ErrorActionPreference = "Continue"; $a = $args; & git -C $dir @a 2>&1 | Out-Null }   # setup only: PS 5.1 would stop on git's warnings

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("upd-routines-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $tmp | Out-Null
$origin = Join-Path $tmp "origin.git"; $desk = Join-Path $tmp "desk"; $surf = Join-Path $tmp "surface"
G $tmp init -q --bare -b master origin.git
G $tmp clone -q origin.git desk
foreach ($d in @($desk)) { G $d config user.email t@t; G $d config user.name t }
New-Item -ItemType Directory -Path "$desk\Routines" | Out-Null
Set-Content "$desk\Routines\Kids.txt" "v1"
G $desk add -A; G $desk commit -q -m v1; G $desk push -q origin master
G $tmp clone -q origin.git surface
G $surf config user.email s@s; G $surf config user.name s

function Push-Desk([string]$file, [string]$text) {
    Set-Content "$desk\$file" $text; G $desk add -A; G $desk commit -q -m $text; G $desk push -q origin master
}
$logged = New-Object System.Collections.Generic.List[string]
$log = { param($m) $logged.Add($m) }

try {
    # 1. nothing new
    $r = Update-Routines -Repo $surf -Say $log
    Check "already current -> 'routines up to date'" ($r -eq "current" -and $logged[-1] -like "routines up to date*") $logged[-1]

    # 2. GitHub has a newer prompt
    Push-Desk "Routines\Kids.txt" "v2"
    $r = Update-Routines -Repo $surf -Say $log
    Check "behind -> pulled, prompt is v2" ($r -eq "updated" -and (Get-Content "$surf\Routines\Kids.txt") -eq "v2") "$r / $($logged[-1])"

    # 3. offline: the remote can't be reached
    Push-Desk "Routines\Kids.txt" "v3"
    Rename-Item $origin "$origin.away"
    $r = Update-Routines -Repo $surf -Say $log
    Rename-Item "$origin.away" $origin
    Check "offline -> kept, warned, prompt still v2" ($r -eq "kept" -and $logged[-1] -like "WARN*" -and (Get-Content "$surf\Routines\Kids.txt") -eq "v2") "$r / $($logged[-1])"

    # 4. the Surface has its own unpushed commit (diverged)
    Set-Content "$surf\surface-app.html" "made on the surface"; G $surf add -A; G $surf commit -q -m "surface app"
    $head = (& git -C $surf rev-parse HEAD)
    $r = Update-Routines -Repo $surf -Say $log
    Check "diverged -> kept, HEAD unchanged, nothing lost" ($r -eq "kept" -and (& git -C $surf rev-parse HEAD) -eq $head -and (Test-Path "$surf\surface-app.html")) "$r / $($logged[-1])"
    G $surf reset -q --hard origin/master    # test cleanup only (the real script never resets)
    G $surf pull -q --ff-only

    # 5. an uncommitted edit to a prompt GitHub also changed
    Set-Content "$surf\Routines\Kids.txt" "hand edit on the surface"
    Push-Desk "Routines\Kids.txt" "v4"
    $r = Update-Routines -Repo $surf -Say $log
    Check "local edit in the way -> kept, the edit survives" ($r -eq "kept" -and (Get-Content "$surf\Routines\Kids.txt") -eq "hand edit on the surface") "$r / $($logged[-1])"
    G $surf checkout -q -- Routines/Kids.txt; G $surf pull -q --ff-only

    # 6. an untracked file where GitHub adds a tracked one (the 29 Oct desktop case)
    Set-Content "$surf\Routines\New.txt" "untracked copy"
    Push-Desk "Routines\New.txt" "tracked version"
    $r = Update-Routines -Repo $surf -Say $log
    Check "untracked file in the way -> kept, the file survives" ($r -eq "kept" -and (Get-Content "$surf\Routines\New.txt") -eq "untracked copy") "$r / $($logged[-1])"

    # 7. not a git repo at all
    $r = Update-Routines -Repo $tmp -Say $log
    Check "not a repo -> kept, warned" ($r -eq "kept" -and $logged[-1] -like "WARN*") "$r / $($logged[-1])"

    # 8. called the way Run-CoworkRoutine.ps1 calls it: its W() writes to a script-level
    #    $Log FILE PATH, which a function parameter of the same name would shadow
    Remove-Item "$surf\Routines\New.txt"; G $surf pull -q --ff-only     # clear case 6's leftover
    $Log = Join-Path $tmp "routine.log"
    function W([string]$m) { Add-Content -LiteralPath $Log -Value "ts  $m" -Encoding UTF8 }
    Push-Desk "Routines\Kids.txt" "v5"
    $r = Update-Routines -Repo $surf -Say ${function:W}
    $text = if (Test-Path $Log) { Get-Content -Raw $Log } else { "" }
    Check "runner's W logs to its file" ($r -eq "updated" -and $text -match "routines updated") "$r / log: $text"
} finally {
    Set-Location $env:TEMP
    Remove-Item -Recurse -Force -LiteralPath $tmp -ErrorAction SilentlyContinue
}
Write-Host ""
Write-Host ("{0} failed" -f $script:fails)
exit ([int]($script:fails -gt 0))

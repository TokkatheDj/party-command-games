# Start-AppServer.ps1 — Launch the local app server for phones/tablets

$AppsDir = $PSScriptRoot
$Port = 8080

# Find the real local IP (not WSL/Hyper-V virtual)
$LocalIP = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.PrefixOrigin -ne "WellKnown" -and $_.IPAddress -notlike "172.*" } |
    Select-Object -First 1).IPAddress

if (-not $LocalIP) {
    $LocalIP = "127.0.0.1"
}

# Check if port is already in use
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "`n  Port $Port is already in use. Server may already be running." -ForegroundColor Yellow
    Write-Host "  Try: http://$LocalIP`:$Port`n" -ForegroundColor Cyan
    exit
}

$env:PUBLIC_URL = "https://desktop-lance.tail476695.ts.net"

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor DarkCyan
Write-Host "  ║       Cowork Apps — Local Server         ║" -ForegroundColor Cyan
Write-Host "  ╠══════════════════════════════════════════╣" -ForegroundColor DarkCyan
Write-Host "  ║                                          ║" -ForegroundColor DarkCyan
Write-Host "  ║  Public URL (anywhere):                  ║" -ForegroundColor DarkCyan
Write-Host "  ║  $($env:PUBLIC_URL)  ║" -ForegroundColor White
Write-Host "  ║                                          ║" -ForegroundColor DarkCyan
Write-Host "  ║  Local (same WiFi):                      ║" -ForegroundColor DarkCyan
Write-Host "  ║  http://$LocalIP`:$Port       ║" -ForegroundColor DarkCyan
Write-Host "  ║                                          ║" -ForegroundColor DarkCyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  Starting server..." -ForegroundColor Gray

# Open the local browser
Start-Process "http://localhost:$Port"

# Start Python server — auto-restart on crash, stop on Ctrl+C
Set-Location $AppsDir
while ($true) {
    python "$AppsDir\serve_apps.py"
    $exit = $LASTEXITCODE
    if ($exit -eq 0) {
        Write-Host "`n  Server stopped cleanly." -ForegroundColor Gray
        break
    }
    Write-Host "`n  Server exited (code $exit) — restarting in 3s... (Ctrl+C to stop)" -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}

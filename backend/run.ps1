# Start the local a-mbl API so phones on the same Wi-Fi can reach it.
# Windows equivalent of run.sh. Run from anywhere:  .\backend\run.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

Write-Host 'Addresses phones can try in the app''s connection screen:'

# Real LAN addresses only: skip loopback, APIPA (169.254.x), and virtual adapters
# from Hyper-V/WSL/VirtualBox, which a phone on the Wi-Fi cannot reach.
$addresses = Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object {
    $_.IPAddress -ne '127.0.0.1' -and
    $_.IPAddress -notlike '169.254.*' -and
    $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL|VirtualBox|Hyper-V'
  }

if ($addresses) {
  foreach ($a in $addresses) {
    Write-Host ("  http://{0}:8000   ({1})" -f $a.IPAddress, $a.InterfaceAlias)
  }
} else {
  Write-Host '  (no Wi-Fi/Ethernet address found - run "ipconfig" and look for IPv4 Address)'
}

# Unlike macOS, Windows Firewall blocks inbound port 8000 by default, so the
# phone gets a silent timeout. Allow it once (needs an elevated PowerShell):
#   New-NetFirewallRule -DisplayName "a-mbl API" -Direction Inbound `
#     -LocalPort 8000 -Protocol TCP -Action Allow
if (-not (Get-NetFirewallRule -DisplayName 'a-mbl API' -ErrorAction SilentlyContinue)) {
  Write-Host ''
  Write-Host 'Note: no "a-mbl API" firewall rule found. If the phone cannot connect,' -ForegroundColor Yellow
  Write-Host 'open an Administrator PowerShell and run:' -ForegroundColor Yellow
  Write-Host '  New-NetFirewallRule -DisplayName "a-mbl API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow' -ForegroundColor Yellow
}

Write-Host ''

# Prefer the repo's .venv (see docs/HOW_TO_RUN.md); fall back to conda for the
# macOS setup described in run.sh.
$venvPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
  & $venvPython -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
} elseif (Get-Command conda -ErrorAction SilentlyContinue) {
  conda run --no-capture-output -n a-mbl uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
} else {
  Write-Host 'No .venv found. Create one first:' -ForegroundColor Red
  Write-Host '  py -m venv .venv'
  Write-Host '  .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt'
  exit 1
}

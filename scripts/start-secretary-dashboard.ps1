param(
    [string]$Root = ".",
    [int]$Port = 8503
)

$ErrorActionPreference = "Stop"

$resolvedRoot = Resolve-Path $Root
$secretaryRoot = Join-Path $resolvedRoot "personal-secretary"
$pythonExe = Join-Path $secretaryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python environment not found: $pythonExe"
}

# Kill stale dashboard processes to avoid 8502/8503 conflicts.
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "app_dashboard\.py" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Set-Location $secretaryRoot
Set-Item -Path Env:PYTHONPATH -Value src
& ".\.venv\Scripts\streamlit.exe" run app_dashboard.py --server.port $Port --server.address 127.0.0.1

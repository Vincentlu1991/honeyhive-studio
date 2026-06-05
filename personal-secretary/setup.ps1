$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Setup complete."
Write-Host "Run sync: .\.venv\Scripts\python.exe run_sync.py (with PYTHONPATH=src)"
Write-Host "Run dashboard: .\.venv\Scripts\streamlit.exe run app_dashboard.py (with PYTHONPATH=src)"

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".git")) {
    throw "Not a git repository root. Run this from workspace root."
}

git config core.hooksPath .githooks
Write-Host "Git hooks enabled: core.hooksPath=.githooks" -ForegroundColor Cyan

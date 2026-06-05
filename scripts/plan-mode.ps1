param(
    [string]$Root = ".",
    [string]$Goal = ""
)

$ErrorActionPreference = "Stop"

Write-Host "=== Plan Mode ===" -ForegroundColor Cyan
if ($Goal) {
    Write-Host "Goal: $Goal" -ForegroundColor Yellow
}

Write-Host "`n[1] Current structure" -ForegroundColor Green
Get-ChildItem -Path $Root | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize

Write-Host "`n[2] Git status" -ForegroundColor Green
try {
    git -C $Root status --short
} catch {
    Write-Host "git status unavailable" -ForegroundColor DarkYellow
}

Write-Host "`n[3] Plan checklist" -ForegroundColor Green
@(
    "Read impacted files",
    "List risks and rollback",
    "Define verification commands",
    "Limit change scope"
) | ForEach-Object { "- $_" }

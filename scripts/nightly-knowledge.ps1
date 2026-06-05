param(
    [string]$Root = ".",
    [double]$MinPassRate = 0.75
)

$ErrorActionPreference = "Stop"

$resolvedRoot = Resolve-Path $Root
$agentRoot = Join-Path $resolvedRoot "agent-platform"
$pythonExe = Join-Path $agentRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python environment not found: $pythonExe"
}

Push-Location $agentRoot
try {
    Write-Host "[Nightly] Build knowledge index" -ForegroundColor Cyan
    & $pythonExe "scripts\build-knowledge-index.py"
    if ($LASTEXITCODE -ne 0) { throw "build-knowledge-index failed" }

    Write-Host "[Nightly] Auto-learn staff skills" -ForegroundColor Cyan
    & $pythonExe "scripts\auto-learn-skills.py"
    if ($LASTEXITCODE -ne 0) { throw "auto-learn-skills failed" }

    Write-Host "[Nightly] Generate role coverage report" -ForegroundColor Cyan
    & $pythonExe "scripts\wiki-role-coverage-report.py"
    if ($LASTEXITCODE -ne 0) { throw "wiki-role-coverage-report failed" }

    Write-Host "[Nightly] Run wiki quality eval" -ForegroundColor Cyan
    & $pythonExe "scripts\wiki-quality-eval.py" --min-pass-rate $MinPassRate --strict
    if ($LASTEXITCODE -ne 0) { throw "wiki-quality-eval failed" }

    Write-Host "Nightly knowledge pipeline passed." -ForegroundColor Green
}
finally {
    Pop-Location
}

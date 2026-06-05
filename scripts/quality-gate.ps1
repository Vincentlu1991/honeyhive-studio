param(
    [string]$Root = "agent-platform"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Quality Gate (Multi-Stage) ===" -ForegroundColor Cyan
Write-Host "Stage 1: File existence | Stage 2: Python compile | Stage 3: Unit tests | Stage 4: Integration tests | Stage 5: Wiki quality eval`n" -ForegroundColor Gray

if (-not (Test-Path $Root)) {
    throw "Path not found: $Root"
}

$req = Join-Path $Root "requirements.txt"
$readme = Join-Path $Root "README.md"
$app = Join-Path $Root "app.py"
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$unitTest = Join-Path $Root "tests\test_agents.py"
$e2eTest = Join-Path $Root "tests\test_e2e_smoke.py"
$integrationTest = Join-Path $Root "tests\test_integration_retry.py"
$bridgeTest = Join-Path $Root "tests\test_cross_system_shared_context_bridge.py"
$wikiEvalScript = Join-Path $Root "scripts\wiki-quality-eval.py"

$checks = @(
    @{ Name = "requirements exists"; Pass = (Test-Path $req) },
    @{ Name = "README exists"; Pass = (Test-Path $readme) },
    @{ Name = "GUI entry exists"; Pass = (Test-Path $app) },
    @{ Name = "venv python exists"; Pass = (Test-Path $venvPython) },
    @{ Name = "unit test file exists"; Pass = (Test-Path $unitTest) },
    @{ Name = "e2e smoke test file exists"; Pass = (Test-Path $e2eTest) },
    @{ Name = "integration test file exists"; Pass = (Test-Path $integrationTest) },
    @{ Name = "cross-system bridge test file exists"; Pass = (Test-Path $bridgeTest) },
    @{ Name = "wiki quality eval script exists"; Pass = (Test-Path $wikiEvalScript) }
)

$failed = @()
foreach ($c in $checks) {
    if ($c.Pass) {
        Write-Host "[OK] $($c.Name)" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $($c.Name)" -ForegroundColor Red
        $failed += $c.Name
    }
}

if ($failed.Count -gt 0) {
    throw "Quality gate stage 1 failed: $($failed -join ', ')"
}

Write-Host "`n=== Stage 2: Python Compilation Check ===" -ForegroundColor Cyan
Push-Location $Root
try {
    & ".\.venv\Scripts\python.exe" -B "scripts\compile-check.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Python compilation check failed"
    }
}
finally {
    Pop-Location
}

Write-Host "Running unit tests..." -ForegroundColor Cyan
Push-Location $Root
try {
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONPATH = "src"

    & ".\.venv\Scripts\python.exe" -B "tests\test_agents.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Unit tests failed with exit code $LASTEXITCODE"
    }

    Write-Host "`nRunning E2E smoke test..." -ForegroundColor Cyan
    & ".\.venv\Scripts\python.exe" -B "tests\test_e2e_smoke.py"
    if ($LASTEXITCODE -ne 0) {
        throw "E2E smoke test failed with exit code $LASTEXITCODE"
    }

    Write-Host "`n=== Stage 4: Integration Tests ===" -ForegroundColor Cyan
    Write-Host "Running retry branch integration test..." -ForegroundColor Cyan
    & ".\.venv\Scripts\python.exe" -B "tests\test_integration_retry.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Integration test (retry) failed with exit code $LASTEXITCODE"
    }

    Write-Host "Running cross-system shared context bridge test..." -ForegroundColor Cyan
    & ".\.venv\Scripts\python.exe" -B "tests\test_cross_system_shared_context_bridge.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Integration test (cross-system bridge) failed with exit code $LASTEXITCODE"
    }

    Write-Host "`nRunning workflow config test..." -ForegroundColor Cyan
    & ".\.venv\Scripts\python.exe" -B "tests\test_workflow_config.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Workflow config test failed with exit code $LASTEXITCODE"
    }

    Write-Host "`n=== Stage 5: Wiki Quality Eval ===" -ForegroundColor Cyan
    & ".\.venv\Scripts\python.exe" -B "scripts\wiki-quality-eval.py" --min-pass-rate 0.75 --strict
    if ($LASTEXITCODE -ne 0) {
        throw "Wiki quality eval failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "Quality gate passed." -ForegroundColor Cyan

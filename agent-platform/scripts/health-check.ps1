param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path (Join-Path $ScriptDir "..")
$WorkspaceDir = Resolve-Path (Join-Path $ProjectDir "..")

function Resolve-EnvFilePath {
    param([string]$InputEnvFile)

    if ([System.IO.Path]::IsPathRooted($InputEnvFile)) {
        return $InputEnvFile
    }

    $candidateInCwd = Join-Path (Get-Location) $InputEnvFile
    if (Test-Path $candidateInCwd) {
        return $candidateInCwd
    }

    $candidateInProject = Join-Path $ProjectDir $InputEnvFile
    if (Test-Path $candidateInProject) {
        return $candidateInProject
    }

    return $candidateInProject
}

function Get-EnvValue {
    param(
        [string]$FilePath,
        [string]$Key
    )

    if (-not (Test-Path $FilePath)) {
        return $null
    }

    $line = Get-Content $FilePath | Where-Object { $_ -match "^\s*$Key=" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }

    return ($line -split "=", 2)[1].Trim()
}

$ResolvedEnvFile = Resolve-EnvFilePath -InputEnvFile $EnvFile

Write-Host "=== Environment Health Check ===" -ForegroundColor Cyan

$checks = @()

# 1. Check .env file
if (Test-Path $ResolvedEnvFile) {
    Write-Host "[OK] .env file exists ($ResolvedEnvFile)" -ForegroundColor Green
    $checks += @{ Name = ".env file"; Pass = $true }
} else {
    Write-Host "[FAIL] .env file not found. Expected at: $ResolvedEnvFile" -ForegroundColor Red
    $checks += @{ Name = ".env file"; Pass = $false }
}

# 2. Check Ollama
try {
    $ollamaResponse = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    if ($ollamaResponse.StatusCode -eq 200) {
        Write-Host "[OK] Ollama is running" -ForegroundColor Green
        $checks += @{ Name = "Ollama"; Pass = $true }
    } else {
        Write-Host "[WARN] Ollama returned status $($ollamaResponse.StatusCode)" -ForegroundColor Yellow
        $checks += @{ Name = "Ollama"; Pass = $false }
    }
} catch {
    Write-Host "[FAIL] Ollama is not reachable. Start with: ollama serve" -ForegroundColor Red
    $checks += @{ Name = "Ollama"; Pass = $false }
}

# 3. Check ComfyUI
try {
    $comfyResponse = Invoke-WebRequest -Uri "http://127.0.0.1:8188/system_stats" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    if ($comfyResponse.StatusCode -eq 200) {
        Write-Host "[OK] ComfyUI is running" -ForegroundColor Green
        $checks += @{ Name = "ComfyUI"; Pass = $true }
    } else {
        Write-Host "[WARN] ComfyUI returned status $($comfyResponse.StatusCode)" -ForegroundColor Yellow
        $checks += @{ Name = "ComfyUI"; Pass = $false }
    }
} catch {
    Write-Host "[FAIL] ComfyUI is not reachable. Start ComfyUI first" -ForegroundColor Red
    $checks += @{ Name = "ComfyUI"; Pass = $false }
}

# 4. Check Python venv
if (Test-Path (Join-Path $ProjectDir ".venv")) {
    Write-Host "[OK] Python venv exists" -ForegroundColor Green
    $checks += @{ Name = "Python venv"; Pass = $true }
} else {
    Write-Host "[WARN] Python venv not found. Run: python -m venv .venv" -ForegroundColor Yellow
    $checks += @{ Name = "Python venv"; Pass = $false }
}

# 5. Check workflow file
$workflowRelativePath = Get-EnvValue -FilePath $ResolvedEnvFile -Key "COMFYUI_WORKFLOW_PATH"
if (-not $workflowRelativePath) {
    $workflowRelativePath = "../workflow_ltxv_img2video_test.json"
}

$workflowPath = if ([System.IO.Path]::IsPathRooted($workflowRelativePath)) {
    $workflowRelativePath
} else {
    Join-Path $ProjectDir $workflowRelativePath
}

if (Test-Path $workflowPath) {
    Write-Host "[OK] Workflow file exists" -ForegroundColor Green
    $checks += @{ Name = "Workflow file"; Pass = $true }
} else {
    Write-Host "[WARN] Default workflow file not found ($workflowPath)" -ForegroundColor Yellow
    $checks += @{ Name = "Workflow file"; Pass = $false }
}

$failed = $checks | Where-Object { -not $_.Pass }
if ($failed.Count -gt 0) {
    Write-Host "`n[RESULT] $($failed.Count) checks failed. Fix issues before starting GUI." -ForegroundColor Red
    exit 1
} else {
    Write-Host "`n[RESULT] All checks passed. Ready to launch!" -ForegroundColor Cyan
    exit 0
}

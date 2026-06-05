param(
    [switch]$SkipVenv = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=== Multi-Agent Video Platform - One-Click Setup ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Create virtual environment
if (-not $SkipVenv) {
    Write-Host "[1/5] Creating Python virtual environment..." -ForegroundColor Green
    if (Test-Path ".venv") {
        Write-Host "Virtual environment already exists, skipping." -ForegroundColor DarkGray
    } else {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create virtual environment"
        }
        Write-Host "Virtual environment created." -ForegroundColor Green
    }
} else {
    Write-Host "[1/5] Skipping virtual environment creation" -ForegroundColor Yellow
}

# Step 2: Activate and install dependencies
Write-Host "[2/5] Installing dependencies..." -ForegroundColor Green
if (Test-Path ".venv\Scripts\Activate.ps1") {
    & .venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install dependencies"
    }
    Write-Host "Dependencies installed." -ForegroundColor Green
} else {
    Write-Host "Warning: Virtual environment not found, installing globally." -ForegroundColor Yellow
    pip install -r requirements.txt
}

# Step 3: Create .env from example
Write-Host "[3/5] Setting up environment configuration..." -ForegroundColor Green
if (Test-Path ".env") {
    Write-Host ".env already exists, skipping." -ForegroundColor DarkGray
} else {
    Copy-Item ".env.example" ".env"
    Write-Host ".env created from template." -ForegroundColor Green
}

# Step 4: Verify workflow files
Write-Host "[4/5] Verifying workflow files..." -ForegroundColor Green
$workflowPath = "..\workflow_ltxv_img2video_test.json"
if (Test-Path $workflowPath) {
    Write-Host "Workflow file found." -ForegroundColor Green
} else {
    Write-Host "Warning: Default workflow file not found at $workflowPath" -ForegroundColor Yellow
    Write-Host "Update COMFYUI_WORKFLOW_PATH in .env if needed" -ForegroundColor Yellow
}

# Step 5: Run health check
Write-Host "[5/5] Running health check..." -ForegroundColor Green
Write-Host "Note: Ollama and ComfyUI checks may fail if not started yet - this is expected." -ForegroundColor DarkGray
powershell -ExecutionPolicy Bypass -File scripts/health-check.ps1
$healthCheckExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan

if ($healthCheckExitCode -ne 0) {
    Write-Host ""
    Write-Host "Health check warnings detected. Before running the GUI:" -ForegroundColor Yellow
    Write-Host "1. Start Ollama: ollama serve" -ForegroundColor White
    Write-Host "2. Start ComfyUI" -ForegroundColor White
    Write-Host "3. Pull model: ollama pull qwen2.5:14b-instruct" -ForegroundColor White
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Edit .env to customize configuration" -ForegroundColor White
Write-Host "2. Start services (Ollama + ComfyUI)" -ForegroundColor White
Write-Host "3. Run: `$env:PYTHONPATH='src'; streamlit run app_robust.py" -ForegroundColor White

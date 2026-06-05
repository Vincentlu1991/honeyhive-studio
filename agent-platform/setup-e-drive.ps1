param(
    [switch]$SystemWide = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=== E 盘环境配置（不占用 C 盘）===" -ForegroundColor Cyan
Write-Host ""

# 1. 创建目录结构
Write-Host "[1/5] Creating directory structure on E drive..." -ForegroundColor Green
$directories = @(
    "E:\AI\ollama\models",
    "E:\AI\cache",
    "E:\AI\outputs",
    "E:\AI\workflows"
)

foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor DarkGray
    } else {
        Write-Host "  Exists: $dir" -ForegroundColor DarkGray
    }
}

# 2. 设置 Ollama 环境变量
Write-Host "[2/5] Configuring Ollama to use E drive..." -ForegroundColor Green
if ($SystemWide) {
    try {
        [System.Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "E:\AI\ollama\models", "Machine")
        Write-Host "  Set system-wide OLLAMA_MODELS=E:\AI\ollama\models" -ForegroundColor DarkGray
    } catch {
        Write-Host "  Failed to set system-wide (need admin). Using user-level." -ForegroundColor Yellow
        [System.Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "E:\AI\ollama\models", "User")
    }
} else {
    [System.Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "E:\AI\ollama\models", "User")
    Write-Host "  Set user-level OLLAMA_MODELS=E:\AI\ollama\models" -ForegroundColor DarkGray
}
$env:OLLAMA_MODELS = "E:\AI\ollama\models"
Write-Host "  Current session: OLLAMA_MODELS=$env:OLLAMA_MODELS" -ForegroundColor DarkGray

# 3. 检测 ComfyUI 路径
Write-Host "[3/5] Detecting ComfyUI installation..." -ForegroundColor Green
$comfyPath = "E:\AI\ComfyUI_windows_portable"
if (Test-Path $comfyPath) {
    Write-Host "  Found ComfyUI at: $comfyPath" -ForegroundColor Green
    $env:COMFYUI_PATH = $comfyPath
} else {
    Write-Host "  ComfyUI not found at E:\AI\" -ForegroundColor Yellow
}

# 4. 复制工作流文件
Write-Host "[4/5] Copying workflow files to E drive..." -ForegroundColor Green
$workflowSource = "..\workflow_*.json"
$workflowFiles = Get-Item $workflowSource -ErrorAction SilentlyContinue
if ($workflowFiles) {
    foreach ($file in $workflowFiles) {
        Copy-Item $file.FullName -Destination "E:\AI\workflows\" -Force
        Write-Host "  Copied: $($file.Name)" -ForegroundColor DarkGray
    }
} else {
    Write-Host "  No workflow files found in parent directory" -ForegroundColor Yellow
}

# 5. 更新 .env
Write-Host "[5/5] Updating .env configuration..." -ForegroundColor Green
$envPath = ".env"
if (Test-Path $envPath) {
    $envLines = Get-Content $envPath
    $newEnvLines = @()
    $updated = @{
        "COMFYUI_WORKFLOW_PATH" = $false
        "OUTPUT_DIR" = $false
        "CACHE_DIR" = $false
    }
    
    foreach ($line in $envLines) {
        if ($line -match "^COMFYUI_WORKFLOW_PATH=") {
            $newEnvLines += "COMFYUI_WORKFLOW_PATH=E:\AI\workflows\workflow_ltxv_img2video_test.json"
            $updated["COMFYUI_WORKFLOW_PATH"] = $true
        } elseif ($line -match "^OUTPUT_DIR=") {
            $newEnvLines += "OUTPUT_DIR=E:\AI\outputs"
            $updated["OUTPUT_DIR"] = $true
        } elseif ($line -match "^CACHE_DIR=") {
            $newEnvLines += "CACHE_DIR=E:\AI\cache"
            $updated["CACHE_DIR"] = $true
        } else {
            $newEnvLines += $line
        }
    }
    
    # 添加缺失的配置
    if (!$updated["COMFYUI_WORKFLOW_PATH"]) {
        $newEnvLines += "COMFYUI_WORKFLOW_PATH=E:\AI\workflows\workflow_ltxv_img2video_test.json"
    }
    if (!$updated["OUTPUT_DIR"]) {
        $newEnvLines += "OUTPUT_DIR=E:\AI\outputs"
    }
    if (!$updated["CACHE_DIR"]) {
        $newEnvLines += "CACHE_DIR=E:\AI\cache"
    }
    
    # 添加 E 盘路径注释
    $newEnvLines += ""
    $newEnvLines += "# E Drive Paths (不占用 C 盘)"
    $newEnvLines += "OLLAMA_MODELS_PATH=E:\AI\ollama\models"
    if (Test-Path $comfyPath) {
        $newEnvLines += "COMFYUI_PATH=$comfyPath"
    }
    
    Set-Content -Path $envPath -Value ($newEnvLines -join "`n")
    Write-Host "  Updated .env with E drive paths" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=== Configuration Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Storage locations:" -ForegroundColor Yellow
Write-Host "  Ollama models:  E:\AI\ollama\models\" -ForegroundColor White
Write-Host "  ComfyUI:        E:\AI\ComfyUI_windows_portable\" -ForegroundColor White
Write-Host "  Workflows:      E:\AI\workflows\" -ForegroundColor White
Write-Host "  Outputs:        E:\AI\outputs\" -ForegroundColor White
Write-Host "  Cache:          E:\AI\cache\" -ForegroundColor White
Write-Host ""
Write-Host "IMPORTANT - Next steps:" -ForegroundColor Yellow
Write-Host "1. RESTART this terminal (to apply OLLAMA_MODELS variable)" -ForegroundColor White
Write-Host "2. Install Ollama: winget install Ollama.Ollama" -ForegroundColor White
Write-Host "3. Pull model: ollama pull qwen2.5:7b-instruct" -ForegroundColor White
Write-Host "4. Verify model location: Get-ChildItem 'E:\AI\ollama\models'" -ForegroundColor White
Write-Host "5. Start ComfyUI: E:\AI\ComfyUI_windows_portable\run_nvidia_gpu.bat" -ForegroundColor White
Write-Host "6. Continue with: powershell -ExecutionPolicy Bypass -File scripts/health-check.ps1" -ForegroundColor White

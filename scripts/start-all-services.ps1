param(
    [string]$Root = ".",
    [switch]$StartTelegramBot = $true,
    [switch]$StartSecretaryDashboard = $true,
    [switch]$StartAgentGui = $true,
    [switch]$StartComfyUI = $true,
    [switch]$StartOllama = $true,
    [string]$PidFile = "output/service-runtime/service-pids.json"
)

$ErrorActionPreference = "Stop"

function Write-Stage {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Test-Endpoint {
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    }
    catch {
        return $false
    }
}

function Start-ServiceProcess {
    param(
        [string]$Name,
        [string]$Command,
        [string]$WorkingDirectory
    )

    $proc = Start-Process -FilePath "powershell" -WorkingDirectory $WorkingDirectory -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", $Command
    ) -PassThru

    return [PSCustomObject]@{
        name = $Name
        started = $true
        pid = $proc.Id
        command = $Command
    }
}

$resolvedRoot = (Resolve-Path $Root).Path
$runtimeDir = Join-Path $resolvedRoot "output/service-runtime"
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

$agentRoot = Join-Path $resolvedRoot "agent-platform"
$secretaryRoot = Join-Path $resolvedRoot "personal-secretary"

$records = New-Object System.Collections.Generic.List[object]

Write-Stage "Starting core services"

if ($StartOllama) {
    if (Test-Endpoint "http://127.0.0.1:11434/api/tags") {
        Write-Host "[SKIP] Ollama already running" -ForegroundColor Yellow
        $records.Add([PSCustomObject]@{ name = "ollama"; started = $false; pid = $null; command = "ollama serve" })
    }
    else {
        Write-Host "[RUN] Starting Ollama" -ForegroundColor Green
        $records.Add((Start-ServiceProcess -Name "ollama" -WorkingDirectory $resolvedRoot -Command "ollama serve"))
    }
}

if ($StartComfyUI) {
    if (Test-Endpoint "http://127.0.0.1:8188/system_stats") {
        Write-Host "[SKIP] ComfyUI already running" -ForegroundColor Yellow
        $records.Add([PSCustomObject]@{ name = "comfyui"; started = $false; pid = $null; command = "run_nvidia_gpu.bat" })
    }
    else {
        $comfyPath = if ($env:COMFYUI_PATH) { $env:COMFYUI_PATH } else { "E:/AI/ComfyUI_windows_portable" }
        $comfyBat = Join-Path $comfyPath "run_nvidia_gpu.bat"
        if (-not (Test-Path $comfyBat)) {
            Write-Host "[WARN] ComfyUI launcher not found: $comfyBat" -ForegroundColor Yellow
            $records.Add([PSCustomObject]@{ name = "comfyui"; started = $false; pid = $null; command = "missing:$comfyBat" })
        }
        else {
            Write-Host "[RUN] Starting ComfyUI" -ForegroundColor Green
            $proc = Start-Process -FilePath $comfyBat -WorkingDirectory $comfyPath -PassThru
            $records.Add([PSCustomObject]@{ name = "comfyui"; started = $true; pid = $proc.Id; command = $comfyBat })
        }
    }
}

if ($StartAgentGui) {
    if (-not (Test-Path (Join-Path $agentRoot ".venv/Scripts/python.exe"))) {
        Write-Host "[WARN] Agent GUI venv missing, skip" -ForegroundColor Yellow
        $records.Add([PSCustomObject]@{ name = "agent-gui"; started = $false; pid = $null; command = "missing agent-platform/.venv" })
    }
    else {
        Write-Host "[RUN] Starting Agent GUI (8501)" -ForegroundColor Green
        $cmd = "Set-Location '$agentRoot'; Set-Item -Path Env:PYTHONPATH -Value src; ./.venv/Scripts/python.exe -m streamlit run app_robust.py --server.port 8501 --server.address 127.0.0.1"
        $records.Add((Start-ServiceProcess -Name "agent-gui" -WorkingDirectory $resolvedRoot -Command $cmd))
    }
}

if ($StartSecretaryDashboard) {
    if (-not (Test-Path (Join-Path $secretaryRoot ".venv/Scripts/streamlit.exe"))) {
        Write-Host "[WARN] Secretary dashboard venv missing, skip" -ForegroundColor Yellow
        $records.Add([PSCustomObject]@{ name = "secretary-dashboard"; started = $false; pid = $null; command = "missing personal-secretary/.venv" })
    }
    else {
        Write-Host "[RUN] Starting Secretary Dashboard (8503)" -ForegroundColor Green
        $cmd = "Set-Location '$secretaryRoot'; Set-Item -Path Env:PYTHONPATH -Value src; ./.venv/Scripts/streamlit.exe run app_dashboard.py --server.port 8503 --server.address 127.0.0.1"
        $records.Add((Start-ServiceProcess -Name "secretary-dashboard" -WorkingDirectory $resolvedRoot -Command $cmd))
    }
}

if ($StartTelegramBot) {
    if (-not (Test-Path (Join-Path $secretaryRoot ".venv/Scripts/python.exe"))) {
        Write-Host "[WARN] Telegram bot venv missing, skip" -ForegroundColor Yellow
        $records.Add([PSCustomObject]@{ name = "telegram-bot"; started = $false; pid = $null; command = "missing personal-secretary/.venv" })
    }
    else {
        Write-Host "[RUN] Starting Telegram Bot Poller" -ForegroundColor Green
        $cmd = "Set-Location '$secretaryRoot'; Set-Item -Path Env:PYTHONPATH -Value src; ./.venv/Scripts/python.exe run_telegram_bot.py"
        $records.Add((Start-ServiceProcess -Name "telegram-bot" -WorkingDirectory $resolvedRoot -Command $cmd))
    }
}

$payload = [PSCustomObject]@{
    generatedAt = (Get-Date).ToString("s")
    root = $resolvedRoot
    services = $records
}

$pidPath = Join-Path $resolvedRoot $PidFile
$pidParent = Split-Path -Parent $pidPath
New-Item -ItemType Directory -Path $pidParent -Force | Out-Null
$payload | ConvertTo-Json -Depth 5 | Set-Content -Path $pidPath -Encoding UTF8

Write-Stage "Startup complete"
$records | Format-Table -AutoSize
Write-Host "PID file: $pidPath" -ForegroundColor Cyan

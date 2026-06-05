param(
    [string]$Root = ".",
    [string]$PidFile = "output/service-runtime/service-pids.json",
    [switch]$KillResidual = $true
)

$ErrorActionPreference = "Stop"

function Write-Stage {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

$resolvedRoot = (Resolve-Path $Root).Path
$pidPath = Join-Path $resolvedRoot $PidFile

$stopped = New-Object System.Collections.Generic.List[object]

if (Test-Path $pidPath) {
    Write-Stage "Stopping services by PID file"
    $state = Get-Content -Path $pidPath -Raw | ConvertFrom-Json
    foreach ($svc in $state.services) {
        if ($null -ne $svc.pid -and [int]$svc.pid -gt 0) {
            try {
                Stop-Process -Id ([int]$svc.pid) -Force -ErrorAction Stop
                $stopped.Add([PSCustomObject]@{ name = $svc.name; pid = [int]$svc.pid; status = "stopped" })
            }
            catch {
                $stopped.Add([PSCustomObject]@{ name = $svc.name; pid = [int]$svc.pid; status = "not-running" })
            }
        }
    }
    Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
}
else {
    Write-Host "[INFO] PID file not found: $pidPath" -ForegroundColor Yellow
}

if ($KillResidual) {
    Write-Stage "Stopping residual project services"

    $patterns = @(
        "streamlit run app_robust.py",
        "streamlit run app_dashboard.py",
        "run_telegram_bot.py",
        "ollama serve",
        "ComfyUI_windows_portable"
    )

    $residual = Get-CimInstance Win32_Process | Where-Object {
        $cmd = [string]$_.CommandLine
        foreach ($p in $patterns) {
            if ($cmd -match [regex]::Escape($p)) { return $true }
        }
        return $false
    }

    foreach ($proc in $residual) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            $stopped.Add([PSCustomObject]@{ name = "residual"; pid = $proc.ProcessId; status = "stopped" })
        }
        catch {
            $stopped.Add([PSCustomObject]@{ name = "residual"; pid = $proc.ProcessId; status = "failed" })
        }
    }
}

Write-Stage "Stop complete"
if ($stopped.Count -eq 0) {
    Write-Host "No matching services were running." -ForegroundColor Yellow
}
else {
    $stopped | Sort-Object pid -Unique | Format-Table -AutoSize
}

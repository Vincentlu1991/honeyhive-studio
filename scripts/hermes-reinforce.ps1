param(
    [string]$Root = ".",
    [switch]$SkipHealthCheck,
    [switch]$SkipQualityGate,
    [switch]$AutoStartComfyUI,
    [switch]$NoHermes,
    [switch]$FailOnCheckError = $true
)

$ErrorActionPreference = "Stop"

function Write-Stage {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Get-LogExcerpt {
    param(
        [string]$Path,
        [int]$Head = 120,
        [int]$Tail = 180
    )

    if (-not (Test-Path $Path)) {
        return "(missing log: $Path)"
    }

    $lines = Get-Content -Path $Path
    if ($lines.Count -le ($Head + $Tail)) {
        return ($lines -join "`n")
    }

    $headLines = $lines[0..($Head - 1)]
    $tailLines = $lines[($lines.Count - $Tail)..($lines.Count - 1)]
    return (
        ($headLines -join "`n") +
        "`n... (truncated " + ($lines.Count - $Head - $Tail) + " lines) ...`n" +
        ($tailLines -join "`n")
    )
}

function Invoke-And-Capture {
    param(
        [string]$Name,
        [scriptblock]$Command,
        [string]$LogPath
    )

    Write-Host "[RUN] $Name" -ForegroundColor Yellow

    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command 2>&1 | Tee-Object -FilePath $LogPath | Out-Host
        $exitCode = $LASTEXITCODE
        if ($null -eq $exitCode) {
            $exitCode = 0
        }
    }
    finally {
        $ErrorActionPreference = $oldPref
    }

    if ($exitCode -eq 0) {
        Write-Host "[OK] $Name" -ForegroundColor Green
    }
    else {
        Write-Host "[FAIL] $Name (exit=$exitCode)" -ForegroundColor Red
    }

    return $exitCode
}

function Start-ComfyUI {
    param([string]$ProjectRoot)

    $comfyRoot = $env:COMFYUI_PATH
    if ([string]::IsNullOrWhiteSpace($comfyRoot)) {
        $comfyRoot = "E:\AI\ComfyUI_windows_portable"
    }

    $comfyBat = Join-Path $comfyRoot "run_nvidia_gpu.bat"
    if (-not (Test-Path $comfyBat)) {
        Write-Host "[WARN] ComfyUI launcher not found: $comfyBat" -ForegroundColor Yellow
        return $false
    }

    try {
        Start-Process -FilePath $comfyBat -WorkingDirectory $comfyRoot | Out-Null
        Write-Host "[OK] ComfyUI launch requested: $comfyBat" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "[FAIL] Failed to launch ComfyUI: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

$rootPath = Resolve-Path $Root
Set-Location $rootPath

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportDir = Join-Path $rootPath "output\hermes-reports"
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null

$healthLog = Join-Path $reportDir ("health-" + $stamp + ".log")
$qualityLog = Join-Path $reportDir ("quality-" + $stamp + ".log")
$summaryMd = Join-Path $reportDir ("summary-" + $stamp + ".md")

$healthExit = 0
$qualityExit = 0

if (-not $SkipHealthCheck) {
    Write-Stage "Health Check"
    Push-Location (Join-Path $rootPath "agent-platform")
    try {
        $healthExit = Invoke-And-Capture -Name "Health Check" -LogPath $healthLog -Command {
            powershell -ExecutionPolicy Bypass -File "scripts/health-check.ps1"
        }

        if ($healthExit -ne 0 -and $AutoStartComfyUI) {
            Write-Host "[INFO] Health check failed; attempting to start ComfyUI and recheck once." -ForegroundColor Yellow
            if (Start-ComfyUI -ProjectRoot $rootPath) {
                Start-Sleep -Seconds 10
                $healthExit = Invoke-And-Capture -Name "Health Check (after ComfyUI start)" -LogPath $healthLog -Command {
                    powershell -ExecutionPolicy Bypass -File "scripts/health-check.ps1"
                }
            }
        }
    }
    finally {
        Pop-Location
    }
}
else {
    "Health check skipped." | Set-Content -Path $healthLog
}

if (-not $SkipQualityGate) {
    Write-Stage "Quality Gate"
    $qualityExit = Invoke-And-Capture -Name "Quality Gate" -LogPath $qualityLog -Command {
        powershell -ExecutionPolicy Bypass -File "scripts/quality-gate.ps1"
    }
}
else {
    "Quality gate skipped." | Set-Content -Path $qualityLog
}

$failedChecks = @()
if ($healthExit -ne 0) { $failedChecks += "Health Check" }
if ($qualityExit -ne 0) { $failedChecks += "Quality Gate" }

Write-Stage "Hermes Summary"

$hermesOutput = ""
$hermesUsed = $false

if (-not $NoHermes) {
    $hermesExe = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\hermes.exe"
    if (Test-Path $hermesExe) {
        $env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes"

        $prompt = @(
            "Read the following local report files and summarize the repo health in Chinese.",
            "Use short bullets. Include P0/P1 issues, root causes, and the next 3 commands.",
            "Report files:",
            "- $healthLog",
            "- $qualityLog"
        ) -join "`n"

        try {
            $stdoutFile = Join-Path $reportDir ("hermes-stdout-" + $stamp + ".txt")
            $stderrFile = Join-Path $reportDir ("hermes-stderr-" + $stamp + ".txt")
            & $hermesExe -z $prompt 2>&1 | Tee-Object -FilePath $stdoutFile | Out-Host
            $exitCode = $LASTEXITCODE
            if ($null -eq $exitCode) {
                $exitCode = 0
            }
            $hermesOutput = if (Test-Path $stdoutFile) { Get-Content -Path $stdoutFile -Raw } else { "" }
            if ($exitCode -eq 0 -and $hermesOutput) {
                $hermesUsed = $true
            }
            elseif (Test-Path $stderrFile) {
                $hermesOutput = ($hermesOutput + "`n" + (Get-Content -Path $stderrFile -Raw)).Trim()
            }
        }
        catch {
            $hermesOutput = "Hermes summary generation failed: $($_.Exception.Message)"
        }
    }
    else {
        $hermesOutput = "Hermes CLI not found at: $hermesExe"
    }
}
else {
    $hermesOutput = "Hermes generation skipped by -NoHermes."
}

$statusText = if ($failedChecks.Count -eq 0) { "PASS" } else { "FAIL" }

$content = @"
# Hermes Reinforcement Report

- Time: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
- Root: $rootPath
- Status: $statusText
- Failed checks: $(if ($failedChecks.Count -eq 0) { "None" } else { $failedChecks -join ", " })
- Hermes summary used: $hermesUsed

## Logs
- Health log: $healthLog
- Quality log: $qualityLog

## Hermes Recommendations
$hermesOutput
"@

Set-Content -Path $summaryMd -Value $content -Encoding UTF8

Write-Host "[OK] Report generated: $summaryMd" -ForegroundColor Green

if ($FailOnCheckError -and $failedChecks.Count -gt 0) {
    exit 1
}

exit 0

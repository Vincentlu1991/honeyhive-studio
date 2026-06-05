param(
    [string]$Root = "."
)

$ErrorActionPreference = "Stop"

$resolvedRoot = Resolve-Path $Root
$agentRoot = Join-Path $resolvedRoot "agent-platform"
$pythonExe = Join-Path $agentRoot ".venv\Scripts\python.exe"
$scriptPath = Join-Path $agentRoot "scripts\build-knowledge-index.py"

if (-not (Test-Path $pythonExe)) {
    throw "Python environment not found: $pythonExe"
}

if (-not (Test-Path $scriptPath)) {
    throw "Index script not found: $scriptPath"
}

Push-Location $agentRoot
try {
    & $pythonExe $scriptPath
}
finally {
    Pop-Location
}

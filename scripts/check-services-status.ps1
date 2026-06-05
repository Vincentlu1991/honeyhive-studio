param(
    [string]$Root = "."
)

$ErrorActionPreference = "Stop"

$items = @(
    @{ name = "Ollama"; url = "http://127.0.0.1:11434/api/tags" },
    @{ name = "ComfyUI"; url = "http://127.0.0.1:8188/system_stats" },
    @{ name = "Agent GUI"; url = "http://127.0.0.1:8501" },
    @{ name = "Secretary Dashboard"; url = "http://127.0.0.1:8503" }
)

foreach ($i in $items) {
    try {
        $null = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $i.url -ErrorAction Stop
        Write-Host ("[UP]   " + $i.name + " -> " + $i.url) -ForegroundColor Green
    }
    catch {
        Write-Host ("[DOWN] " + $i.name + " -> " + $i.url) -ForegroundColor Yellow
    }
}

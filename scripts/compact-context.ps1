param(
    [string]$OutputFile = "SESSION-COMPACT.md",
    [string]$Topic = ""
)

$ErrorActionPreference = "Stop"

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$header = "## Compact Snapshot - $stamp"
if ($Topic) {
    $header = "$header`nTopic: $Topic"
}

$template = @"
$header

### Decisions
- 

### Changed Files
- 

### Open Risks
- 

### Next Actions
1. 
2. 
3. 

"@

Add-Content -Path $OutputFile -Value $template
Write-Host "Updated $OutputFile" -ForegroundColor Cyan

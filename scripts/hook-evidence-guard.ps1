param()

# Read stdin to stay compatible with hook contract; content is optional for this guard.
$null = [Console]::In.ReadToEnd()

$response = @{
  continue = $true
  systemMessage = "证据守门已启用：仅输出可追溯结论；无证据结论必须改为未知或待核验；推断必须附规则、证据链与置信度。"
}

$response | ConvertTo-Json -Compress
exit 0

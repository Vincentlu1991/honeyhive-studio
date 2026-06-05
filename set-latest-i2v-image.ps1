$inputDir = 'E:\AI\ComfyUI_windows_portable\ComfyUI\input'
$targetName = 'i2v_source.png'
$targetPath = Join-Path $inputDir $targetName

$candidates = Get-ChildItem $inputDir -File |
  Where-Object {
    $_.Name -ne $targetName -and
    $_.Name -ne 'example.png' -and
    $_.Extension.ToLower() -in @('.png', '.jpg', '.jpeg', '.webp')
  } |
  Sort-Object LastWriteTime -Descending

if (-not $candidates -or $candidates.Count -eq 0) {
  Write-Host 'No candidate image found in input directory.'
  exit 1
}

$latest = $candidates[0]
Copy-Item $latest.FullName $targetPath -Force

Write-Host "Source: $($latest.FullName)"
Write-Host "Target: $targetPath"
Write-Host 'Synced latest image for I2V workflow.'
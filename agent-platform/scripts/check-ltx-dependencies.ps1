param(
    [string]$ComfyBaseUrl = "http://127.0.0.1:8188",
    [string]$ComfyPath = "E:\AI\ComfyUI_windows_portable"
)

$ErrorActionPreference = "Stop"

Write-Host "=== LTX Dependency Check ===" -ForegroundColor Cyan

$textEncoderDir = Join-Path $ComfyPath "ComfyUI\models\text_encoders"
$gemmaDir = Join-Path $textEncoderDir "gemma-3-12b-it-qat-q4_0-unquantized"

if (Test-Path $textEncoderDir) {
    Write-Host "[OK] text_encoders directory exists: $textEncoderDir" -ForegroundColor Green
}
else {
    Write-Host "[FAIL] text_encoders directory missing: $textEncoderDir" -ForegroundColor Red
}

$gemmaFiles = @()
if (Test-Path $gemmaDir) {
    $gemmaFiles = @(Get-ChildItem -Path $gemmaDir -Filter "*.safetensors" -File -ErrorAction SilentlyContinue)
}

if ($gemmaFiles.Count -gt 0) {
    Write-Host "[OK] Gemma files found: $($gemmaFiles.Count)" -ForegroundColor Green
}
else {
    Write-Host "[WARN] Gemma safetensors not found under: $gemmaDir" -ForegroundColor Yellow
}

$ltxReady = $false
$gemmaOptions = @()
$textEncoderOptions = @()

try {
    $resp = Invoke-WebRequest -Uri "$ComfyBaseUrl/object_info" -UseBasicParsing -TimeoutSec 10
    if ($resp.StatusCode -eq 200) {
        $info = $resp.Content | ConvertFrom-Json

        $gemmaRaw = $info.LTXVGemmaCLIPModelLoader.input.required.gemma_path
        if ($gemmaRaw -and $gemmaRaw.Count -gt 0) {
            $gemmaOptions = @($gemmaRaw[0])
        }

        $textRaw = $info.LTXAVTextEncoderLoader.input.required.text_encoder
        if ($textRaw -and $textRaw.Count -gt 0) {
            $textEncoderOptions = @($textRaw[0])
        }

        if ($gemmaOptions.Count -gt 0 -and $textEncoderOptions.Count -gt 0) {
            $ltxReady = $true
        }

        Write-Host "[INFO] ComfyUI gemma options: $($gemmaOptions.Count)" -ForegroundColor Cyan
        Write-Host "[INFO] ComfyUI text_encoder options: $($textEncoderOptions.Count)" -ForegroundColor Cyan
    }
}
catch {
    Write-Host "[FAIL] Cannot query ComfyUI object_info at $ComfyBaseUrl : $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

if ($ltxReady) {
    Write-Host "[OK] LTX dependencies are ready in ComfyUI." -ForegroundColor Green
    exit 0
}

Write-Host "`n[TODO] LTX dependencies are incomplete. Follow these steps:" -ForegroundColor Yellow
Write-Host "1. Download Gemma text encoder folder:" -ForegroundColor White
Write-Host "   git clone https://huggingface.co/google/gemma-3-12b-it-qat-q4_0-unquantized \"$textEncoderDir\gemma-3-12b-it-qat-q4_0-unquantized\"" -ForegroundColor Gray
Write-Host "2. Ensure LTX text encoder files are present under ComfyUI text_encoders." -ForegroundColor White
Write-Host "3. Restart ComfyUI." -ForegroundColor White
Write-Host "4. Re-run this script to verify options are non-empty." -ForegroundColor White
Write-Host "5. Then run pipeline with default LTX workflow again." -ForegroundColor White

exit 1

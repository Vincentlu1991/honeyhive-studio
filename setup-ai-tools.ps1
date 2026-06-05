[CmdletBinding()]
param(
    [string]$Base = "E:\AI",
    [switch]$DownloadSdxlModel = $true,
    [switch]$InstallVideoStack = $true,
    [string]$PortraitMasterRepoUrl = "https://github.com/florestefano1975/comfyui-portrait-master.git",
    [string]$QwenImageLoraLoaderRepoUrl = "https://github.com/ussoewwin/ComfyUI-QwenImageLoraLoader.git",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ComfyUrl = "https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z"
$A1111Repo = "https://github.com/AUTOMATIC1111/stable-diffusion-webui.git"
$ManagerRepo = "https://github.com/ltdrdata/ComfyUI-Manager.git"
$AnimateDiffRepo = "https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git"
$VideoHelperRepo = "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"
$LtxVideoRepo  = "https://github.com/Lightricks/ComfyUI-LTXVideo.git"
$SdxlUrl = "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
$SdxlSha256 = "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b"

$ModelRoot = Join-Path $Base "Models"
$DownloadRoot = Join-Path $Base "Downloads"
$ComfyPath = Join-Path $Base "ComfyUI_windows_portable"
$A1111Path = Join-Path $Base "stable-diffusion-webui"
$ComfyArchive = Join-Path $DownloadRoot "ComfyUI_windows_portable_nvidia.7z"
$SdxlPath = Join-Path $ModelRoot "checkpoints\sd_xl_base_1.0.safetensors"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-CommandPath {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    return $null
}

function Install-WingetPackageIfMissing {
    param(
        [string]$CommandName,
        [string]$WingetId,
        [string]$DisplayName
    )

    if (Get-CommandPath $CommandName) {
        Write-Host "$DisplayName already installed." -ForegroundColor DarkGray
        return
    }

    if (-not (Get-CommandPath "winget")) {
        throw "winget was not found. Install App Installer first, or install $DisplayName manually."
    }

    Write-Host "Installing $DisplayName..." -ForegroundColor Yellow
    winget install --id $WingetId -e --accept-package-agreements --accept-source-agreements --disable-interactivity
}

function Get-7ZipPath {
    $candidates = @(
        (Get-CommandPath "7z"),
        "C:\Program Files\7-Zip\7z.exe",
        "C:\Program Files (x86)\7-Zip\7z.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    throw "7z.exe was not found."
}

function Invoke-FileDownload {
    param(
        [string]$Url,
        [string]$Destination,
        [string]$Label
    )

    if ((Test-Path -LiteralPath $Destination) -and -not $Force) {
        Write-Host "$Label already exists, skipping download." -ForegroundColor DarkGray
        return
    }

    Write-Host "Downloading $Label..." -ForegroundColor Yellow

    try {
        Start-BitsTransfer -Source $Url -Destination $Destination -DisplayName $Label -Description $Label -ErrorAction Stop
    }
    catch {
        Write-Host "BITS download failed, falling back to Invoke-WebRequest." -ForegroundColor DarkYellow
        Invoke-WebRequest -Uri $Url -OutFile $Destination -Headers @{ "User-Agent" = "Mozilla/5.0" }
    }
}

function Test-FileHashSha256 {
    param(
        [string]$Path,
        [string]$ExpectedSha256
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $actual = (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    return $actual -eq $ExpectedSha256.ToLowerInvariant()
}

function Clone-Or-UpdateRepo {
    param(
        [string]$RepoUrl,
        [string]$Destination,
        [string]$Label
    )

    if (Test-Path -LiteralPath (Join-Path $Destination ".git")) {
        Write-Host "Updating $Label..." -ForegroundColor Yellow
        git -C $Destination pull --ff-only
        return
    }

    if ((Test-Path -LiteralPath $Destination) -and -not $Force) {
        throw "$Label already exists at $Destination, but it is not a git repository. Delete it first or rerun with -Force."
    }

    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }

    Write-Host "Cloning $Label..." -ForegroundColor Yellow
    git clone $RepoUrl $Destination
}

function Ensure-Junction {
    param(
        [string]$LinkPath,
        [string]$TargetPath
    )

    Ensure-Directory -Path $TargetPath

    if (Test-Path -LiteralPath $LinkPath) {
        $existing = Get-Item -LiteralPath $LinkPath -Force
        if ($existing.LinkType -eq "Junction" -or $existing.LinkType -eq "SymbolicLink") {
            return
        }

        $hasChildren = @(Get-ChildItem -LiteralPath $LinkPath -Force -ErrorAction SilentlyContinue).Count -gt 0
        if ($hasChildren) {
            $backup = "$LinkPath.backup-$(Get-Date -Format yyyyMMddHHmmss)"
            Move-Item -LiteralPath $LinkPath -Destination $backup
        }
        else {
            Remove-Item -LiteralPath $LinkPath -Recurse -Force
        }
    }

    cmd /c mklink /J "$LinkPath" "$TargetPath" | Out-Null
}

function Set-FileText {
    param(
        [string]$Path,
        [string]$Content
    )

    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.Encoding]::ASCII)
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script in an elevated PowerShell session."
}

$driveRoot = [System.IO.Path]::GetPathRoot($Base)
if (-not (Test-Path -LiteralPath $driveRoot)) {
    throw "Target drive does not exist: $driveRoot"
}

$driveName = $driveRoot.TrimEnd("\\").TrimEnd(":")
$drive = Get-PSDrive -Name $driveName -ErrorAction Stop
if ($drive.Free -lt 60GB) {
    throw "Less than 60 GB is free on the target drive. Reserve at least 60 GB."
}

Write-Step "Installing prerequisites"
Install-WingetPackageIfMissing -CommandName "git" -WingetId "Git.Git" -DisplayName "Git"
Install-WingetPackageIfMissing -CommandName "7z" -WingetId "7zip.7zip" -DisplayName "7-Zip"
if ($InstallVideoStack) {
    Install-WingetPackageIfMissing -CommandName "ffmpeg" -WingetId "Gyan.FFmpeg.Essentials" -DisplayName "FFmpeg"
}

if (-not (Get-CommandPath "py")) {
    Install-WingetPackageIfMissing -CommandName "py" -WingetId "Python.Python.3.10" -DisplayName "Python 3.10"
}

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

Write-Step "Creating directory layout"
$folders = @(
    $Base,
    $ModelRoot,
    $DownloadRoot,
    (Join-Path $Base "Assets"),
    (Join-Path $Base "Assets\audio"),
    (Join-Path $Base "Assets\images"),
    (Join-Path $Base "Assets\masks"),
    (Join-Path $Base "Assets\reference"),
    (Join-Path $Base "Assets\video_in"),
    (Join-Path $Base "Assets\video_out"),
    (Join-Path $Base "Projects"),
    (Join-Path $Base "Projects\comfyui-workflows"),
    (Join-Path $Base "Projects\notes"),
    (Join-Path $ModelRoot "checkpoints"),
    (Join-Path $ModelRoot "loras"),
    (Join-Path $ModelRoot "vae"),
    (Join-Path $ModelRoot "controlnet"),
    (Join-Path $ModelRoot "upscale_models"),
    (Join-Path $ModelRoot "clip"),
    (Join-Path $ModelRoot "clip_vision"),
    (Join-Path $ModelRoot "embeddings"),
    (Join-Path $ModelRoot "animatediff_models"),
    (Join-Path $ModelRoot "animatediff_motion_lora"),
    (Join-Path $ModelRoot "ipadapter"),
    (Join-Path $ModelRoot "ltxvideo"),
    (Join-Path $ModelRoot "diffusion_models"),
    (Join-Path $ModelRoot "insightface")
)

foreach ($folder in $folders) {
    Ensure-Directory -Path $folder
}

Write-Step "Installing ComfyUI portable"
Invoke-FileDownload -Url $ComfyUrl -Destination $ComfyArchive -Label "ComfyUI portable"

if (-not (Test-Path -LiteralPath $ComfyPath) -or $Force) {
    $sevenZip = Get-7ZipPath
    if (Test-Path -LiteralPath $ComfyPath) {
        Remove-Item -LiteralPath $ComfyPath -Recurse -Force
    }
    & $sevenZip x $ComfyArchive "-o$Base" -y | Out-Null
}

Write-Step "Installing ComfyUI Manager"
$customNodes = Join-Path $ComfyPath "ComfyUI\custom_nodes"
Ensure-Directory -Path $customNodes
Clone-Or-UpdateRepo -RepoUrl $ManagerRepo -Destination (Join-Path $customNodes "ComfyUI-Manager") -Label "ComfyUI Manager"

if ($InstallVideoStack) {
    Write-Step "Installing ComfyUI video nodes"
    Clone-Or-UpdateRepo -RepoUrl $LtxVideoRepo    -Destination (Join-Path $customNodes "ComfyUI-LTXVideo")              -Label "LTX-Video (current)"
    Clone-Or-UpdateRepo -RepoUrl $AnimateDiffRepo -Destination (Join-Path $customNodes "ComfyUI-AnimateDiff-Evolved") -Label "AnimateDiff Evolved (legacy)"
    Clone-Or-UpdateRepo -RepoUrl $VideoHelperRepo -Destination (Join-Path $customNodes "ComfyUI-VideoHelperSuite")    -Label "VideoHelperSuite"
    Clone-Or-UpdateRepo -RepoUrl $PortraitMasterRepoUrl -Destination (Join-Path $customNodes "comfyui-portrait-master") -Label "Portrait Master"
    Clone-Or-UpdateRepo -RepoUrl $QwenImageLoraLoaderRepoUrl -Destination (Join-Path $customNodes "ComfyUI-QwenImageLoraLoader") -Label "Qwen Image Lora Loader"
}

Write-Step "Installing AUTOMATIC1111"
Clone-Or-UpdateRepo -RepoUrl $A1111Repo -Destination $A1111Path -Label "AUTOMATIC1111"

Write-Step "Configuring shared models"
$extraModelPaths = @"
a111:
    base_path: $A1111Path
    checkpoints: models/Stable-diffusion
    configs: models/Stable-diffusion
    vae: models/VAE
    loras: |
         models/Lora
         models/LyCORIS
    upscale_models: |
         models/ESRGAN
         models/RealESRGAN
         models/SwinIR
    embeddings: embeddings
    hypernetworks: models/hypernetworks
    controlnet: models/ControlNet

shared:
    base_path: $ModelRoot
    is_default: true
    checkpoints: checkpoints
    diffusion_models: diffusion_models
    loras: loras
    vae: vae
    controlnet: controlnet
    clip: clip
    clip_vision: clip_vision
    embeddings: embeddings
    upscale_models: upscale_models
    ipadapter: ipadapter
    animatediff_models: animatediff_models
    animatediff_motion_lora: animatediff_motion_lora
"@
Set-FileText -Path (Join-Path $ComfyPath "ComfyUI\extra_model_paths.yaml") -Content $extraModelPaths

$a1111Models = Join-Path $A1111Path "models"
Ensure-Directory -Path (Join-Path $a1111Models "Stable-diffusion")
Ensure-Directory -Path (Join-Path $a1111Models "Lora")
Ensure-Directory -Path (Join-Path $a1111Models "VAE")
Ensure-Directory -Path (Join-Path $a1111Models "ControlNet")
Ensure-Directory -Path (Join-Path $a1111Models "ESRGAN")
Ensure-Directory -Path (Join-Path $A1111Path "embeddings")

Ensure-Junction -LinkPath (Join-Path $a1111Models "Stable-diffusion\Shared_Checkpoints") -TargetPath (Join-Path $ModelRoot "checkpoints")
Ensure-Junction -LinkPath (Join-Path $a1111Models "Lora\Shared_Loras") -TargetPath (Join-Path $ModelRoot "loras")
Ensure-Junction -LinkPath (Join-Path $a1111Models "VAE\Shared_VAE") -TargetPath (Join-Path $ModelRoot "vae")
Ensure-Junction -LinkPath (Join-Path $a1111Models "ControlNet\Shared_ControlNet") -TargetPath (Join-Path $ModelRoot "controlnet")
Ensure-Junction -LinkPath (Join-Path $a1111Models "ESRGAN\Shared_Upscale") -TargetPath (Join-Path $ModelRoot "upscale_models")
Ensure-Junction -LinkPath (Join-Path $A1111Path "embeddings\Shared_Embeddings") -TargetPath (Join-Path $ModelRoot "embeddings")

Write-Step "Writing AUTOMATIC1111 launch settings"
$python310Path = $null
try {
    $python310Path = (& py -3.10 -c "import sys; print(sys.executable)").Trim()
}
catch {
    Write-Host "Python 3.10 launcher lookup failed, A1111 will use PATH lookup." -ForegroundColor DarkYellow
}

$webuiUser = @"
@echo off
set PYTHON=$python310Path
set GIT=
set VENV_DIR=
set STABLE_DIFFUSION_REPO=https://github.com/w-e-w/stablediffusion.git
set COMMANDLINE_ARGS=--xformers --medvram-sdxl --autolaunch --api
call webui.bat
"@
Set-FileText -Path (Join-Path $A1111Path "webui-user.bat") -Content $webuiUser

Write-Step "Creating desktop launchers"
$desktop = [Environment]::GetFolderPath("Desktop")
$comfyLauncher = @"
@echo off
cd /d "$ComfyPath"
call run_nvidia_gpu.bat
pause
"@
Set-FileText -Path (Join-Path $desktop "Run ComfyUI RTX3070.bat") -Content $comfyLauncher

$a1111Launcher = @"
@echo off
cd /d "$A1111Path"
call webui-user.bat
pause
"@
Set-FileText -Path (Join-Path $desktop "Run A1111 RTX3070.bat") -Content $a1111Launcher

$videoGuide = @"
AI media stack installed at: $Base

Recommended model layout
- Models/checkpoints: image and video base checkpoints
- Models/loras: image LoRAs
- Models/vae: optional VAEs
- Models/controlnet: ControlNet models
- Models/upscale_models: ESRGAN, RealESRGAN, SwinIR
- Models/clip and Models/clip_vision: CLIP assets for ComfyUI
- Models/embeddings: textual inversion embeddings
- Models/animatediff_models: AnimateDiff motion modules
- Models/animatediff_motion_lora: motion LoRAs for AnimateDiff
- Models/ipadapter: IPAdapter weights
- Models/diffusion_models: reserved for larger diffusion/video backbones later
- Models/insightface: face analysis packs if you add face tools later

Recommended asset layout
- Assets/images: source still images
- Assets/reference: reference images for style or character consistency
- Assets/video_in: source clips for vid2vid
- Assets/video_out: rendered mp4/webm exports
- Assets/audio: optional music or narration
- Assets/masks: masks for regional edits
- Projects/comfyui-workflows: saved workflow json files
- Projects/notes: prompt notes and shot lists

3070 8GB recommended split
1. A1111 for still images and prompt iteration
2. ComfyUI for AnimateDiff and video export
3. Prefer SD1.5-based AnimateDiff workflows for local video generation
4. Use SDXL mainly for still images unless you accept very short clips and lower batch sizes

Video workflow 1: text to video
1. Load an SD1.5 checkpoint in ComfyUI
2. Load one AnimateDiff motion model from Models/animatediff_models
3. Generate 16 frames at 512x768 or 576x768
4. Use Video Combine at 8 fps to export mp4

Video workflow 2: image to video
1. Put a source image in Assets/images
2. Use image-to-image or reference-image workflow in ComfyUI
3. Keep denoise moderate and frames short at first
4. Export with Video Combine at 8 fps

Video workflow 3: video to video
1. Put the source clip in Assets/video_in
2. Use Load Video from VideoHelperSuite
3. Resize or cap frames before sampling
4. Run short segments, then combine outputs

Models to add manually after install
- A stable SD1.5 checkpoint for AnimateDiff video work
- One AnimateDiff motion module such as mm_sd_v15_v2 or a compatible fp16 safetensors variant
- Optional motion LoRAs for camera moves or motion style

Launch order
1. Run A1111 RTX3070.bat for still images
2. Run ComfyUI RTX3070.bat for video workflows
3. In ComfyUI Manager, update missing Python dependencies if either custom node reports them
4. For portrait generation prompts, use Portrait Master node presets before sampler injection
5. For Qwen image pipelines, use QwenImageLoraLoader for model-compatible LoRA loading
"@
Set-FileText -Path (Join-Path $Base "Projects\notes\ai-media-stack.txt") -Content $videoGuide

if ($DownloadSdxlModel) {
    Write-Step "Downloading SDXL Base 1.0"
    Invoke-FileDownload -Url $SdxlUrl -Destination $SdxlPath -Label "SDXL Base 1.0"

    if (-not (Test-FileHashSha256 -Path $SdxlPath -ExpectedSha256 $SdxlSha256)) {
        throw "The SDXL model was downloaded, but the SHA256 check failed. Delete the file and retry."
    }
}
else {
    Write-Host "Skipped SDXL model download. You can place the model in $SdxlPath later." -ForegroundColor Yellow
}

Write-Host "`nDONE" -ForegroundColor Green
Write-Host "Install path : $Base" -ForegroundColor Green
Write-Host "Model path   : $ModelRoot" -ForegroundColor Green
Write-Host "ComfyUI URL  : http://127.0.0.1:8188" -ForegroundColor Green
Write-Host "A1111 URL    : http://127.0.0.1:7860" -ForegroundColor Green
if ($InstallVideoStack) {
    Write-Host "Video guide  : $Base\Projects\notes\ai-media-stack.txt" -ForegroundColor Green
}
Write-Host "`nRecommended first launch order:" -ForegroundColor Cyan
Write-Host "1. Run A1111 RTX3070.bat" -ForegroundColor Cyan
Write-Host "2. Confirm SDXL loads successfully" -ForegroundColor Cyan
Write-Host "3. Then run ComfyUI RTX3070.bat" -ForegroundColor Cyan
if ($InstallVideoStack) {
    Write-Host "4. Add one SD1.5 checkpoint and one AnimateDiff motion model before first video run" -ForegroundColor Cyan
}
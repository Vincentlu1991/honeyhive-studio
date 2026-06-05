# E 盘专用配置指南

**目标**: 所有 AI 相关数据存储在 E:\AI\，不占用 C 盘空间

---

## 一、目录结构

```
E:\AI\
├── ollama\              # Ollama 模型存储（可能 10-50GB）
│   └── models\
├── comfyui\             # ComfyUI 安装目录（可能 20-100GB）
│   ├── models\
│   ├── input\
│   └── output\
├── cache\               # 临时缓存
├── outputs\             # 生成结果存档
└── project\             # 项目代码（可选，可保持在 OneDrive）
```

---

## 二、Ollama 配置（E 盘存储）

### 1. 设置环境变量

**方式 A: 用户级永久设置**（推荐）

```powershell
# 设置 Ollama 模型路径到 E 盘
[System.Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "E:\AI\ollama\models", "User")

# 验证设置
$env:OLLAMA_MODELS = "E:\AI\ollama\models"
Write-Host "OLLAMA_MODELS = $env:OLLAMA_MODELS"
```

**方式 B: 系统级设置**（需要管理员权限）

```powershell
# 以管理员身份运行
[System.Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "E:\AI\ollama\models", "Machine")
```

### 2. 创建必需目录

```powershell
New-Item -ItemType Directory -Path "E:\AI\ollama\models" -Force
New-Item -ItemType Directory -Path "E:\AI\cache" -Force
New-Item -ItemType Directory -Path "E:\AI\outputs" -Force
```

### 3. 安装 Ollama

```powershell
# 使用 winget 安装
winget install Ollama.Ollama

# 安装后重启终端，然后拉取模型
ollama pull qwen2.5:7b-instruct
```

**验证模型存储位置**：

```powershell
# 模型应该下载到 E:\AI\ollama\models\
Get-ChildItem "E:\AI\ollama\models" -Recurse | Measure-Object -Property Length -Sum | Select-Object @{Name="Size(GB)";Expression={[math]::Round($_.Sum/1GB, 2)}}
```

---

## 三、ComfyUI 配置（E 盘安装）

### 选项 1: 使用 ComfyUI Portable（推荐）

1. 下载 ComfyUI Portable: https://github.com/comfyanonymous/ComfyUI/releases
2. 解压到 `E:\AI\comfyui\`
3. 运行 `E:\AI\comfyui\run_nvidia_gpu.bat`

### 选项 2: 从源码安装

```powershell
cd E:\AI
git clone https://github.com/comfyanonymous/ComfyUI.git comfyui
cd comfyui
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 启动
python main.py --listen
```

### ComfyUI 环境变量（可选）

```powershell
# 如果需要自定义路径
$env:COMFYUI_MODEL_PATH = "E:\AI\comfyui\models"
$env:COMFYUI_OUTPUT_PATH = "E:\AI\comfyui\output"
```

---

## 四、项目配置更新

### 1. 更新 .env 文件

编辑 `agent-platform\.env`：

```env
# ComfyUI 配置
COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_WORKFLOW_PATH=E:\AI\workflows\workflow_ltxv_img2video_test.json

# 输出路径（E 盘）
OUTPUT_DIR=E:\AI\outputs
CACHE_DIR=E:\AI\cache

# Ollama 配置
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL_NAME=qwen2.5:7b-instruct
OLLAMA_MODELS_PATH=E:\AI\ollama\models
```

### 2. 迁移工作流文件

```powershell
# 创建工作流目录
New-Item -ItemType Directory -Path "E:\AI\workflows" -Force

# 复制工作流文件
Copy-Item "c:\Users\User\OneDrive\文档\New project\workflow_*.json" -Destination "E:\AI\workflows\"
```

---

## 五、一键配置脚本

创建 `setup-e-drive.ps1`：

```powershell
param(
    [switch]$SystemWide = $false
)

Write-Host "=== E 盘环境配置 ===" -ForegroundColor Cyan

# 1. 创建目录结构
Write-Host "[1/4] Creating directory structure..." -ForegroundColor Green
$directories = @(
    "E:\AI\ollama\models",
    "E:\AI\comfyui",
    "E:\AI\cache",
    "E:\AI\outputs",
    "E:\AI\workflows"
)

foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor DarkGray
    }
}

# 2. 设置 Ollama 环境变量
Write-Host "[2/4] Configuring Ollama environment..." -ForegroundColor Green
if ($SystemWide) {
    [System.Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "E:\AI\ollama\models", "Machine")
    Write-Host "  Set system-wide OLLAMA_MODELS" -ForegroundColor DarkGray
} else {
    [System.Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "E:\AI\ollama\models", "User")
    Write-Host "  Set user-level OLLAMA_MODELS" -ForegroundColor DarkGray
}
$env:OLLAMA_MODELS = "E:\AI\ollama\models"

# 3. 复制工作流文件
Write-Host "[3/4] Copying workflow files..." -ForegroundColor Green
$workflowSource = "c:\Users\User\OneDrive\文档\New project\workflow_*.json"
if (Test-Path $workflowSource) {
    Copy-Item $workflowSource -Destination "E:\AI\workflows\" -Force
    Write-Host "  Copied workflow files" -ForegroundColor DarkGray
}

# 4. 更新 .env
Write-Host "[4/4] Updating .env configuration..." -ForegroundColor Green
$envPath = ".\agent-platform\.env"
if (Test-Path $envPath) {
    $envContent = Get-Content $envPath -Raw
    $envContent = $envContent -replace 'COMFYUI_WORKFLOW_PATH=.*', 'COMFYUI_WORKFLOW_PATH=E:\AI\workflows\workflow_ltxv_img2video_test.json'
    $envContent += "`n# E Drive paths`n"
    $envContent += "OUTPUT_DIR=E:\AI\outputs`n"
    $envContent += "CACHE_DIR=E:\AI\cache`n"
    $envContent += "OLLAMA_MODELS_PATH=E:\AI\ollama\models`n"
    Set-Content -Path $envPath -Value $envContent
    Write-Host "  Updated .env" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=== Configuration Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. RESTART your terminal to apply environment variables" -ForegroundColor White
Write-Host "2. Install Ollama: winget install Ollama.Ollama" -ForegroundColor White
Write-Host "3. Pull model: ollama pull qwen2.5:7b-instruct" -ForegroundColor White
Write-Host "4. Verify: Get-ChildItem 'E:\AI\ollama\models'" -ForegroundColor White
Write-Host "5. Install/Move ComfyUI to E:\AI\comfyui\" -ForegroundColor White

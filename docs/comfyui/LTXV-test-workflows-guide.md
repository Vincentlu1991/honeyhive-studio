# LTX-Video 测试工作流使用指南

## 📋 准备工作

✅ **已完成：**
- ComfyUI 已启动（http://127.0.0.1:8188）
- LTX-Video 插件已安装
- LTX-Video 模型已加载：`ltxv-2b-0.9.8-distilled.safetensors`
- 测试图片已准备：`E:\AI\Assets\images\照片.jpg`
- 工作流文件已创建并复制到 ComfyUI 目录

---

## 🎬 工作流 1：文本转视频（新加坡鱼尾狮）

### 方式 A：使用预制工作流文件（推荐）

1. **在 ComfyUI 界面中**：
   - 点击顶部"工作流（w）"按钮
   - 或按快捷键 `Ctrl+O`
   - 找到并打开：`workflow_ltxv_text2video_test.json`

2. **检查节点参数**：
   - **正面提示词**：`Singapore Merlion statue comes to life, swimming happily in the pool in front of Marina Bay Sands hotel, cinematic lighting, high quality, smooth motion`
   - **LTXV采样器**：
     - 分辨率：704x480
     - 帧数：25
     - 步数：8
     - cfg_scale：1.0
     - FPS：24
     - seed：42

3. **运行生成**：
   - 点击右上角"运行"按钮
   - 预计生成时间：30-120秒
   - 输出位置：`E:\AI\ComfyUI_windows_portable\ComfyUI\output\` 文件名前缀 `ltxv_text2video_merlion`

### 方式 B：手动创建节点（学习用）

如果工作流文件无法加载，可以手动添加节点：

1. **右键点击画布** → 搜索并添加以下节点：

```
节点连接顺序：
┌─────────────────┐
│ LTXVLoader      │ → 加载 ltxv-2b-0.9.8-distilled.safetensors
└────┬────────────┘
     ├─────────────────┐
     │                 ↓
     │        ┌────────────────┐
     │        │ CLIP Text      │ → 正面提示词
     │        │ Encode         │
     │        └────┬───────────┘
     │             │
     │        ┌────────────────┐
     │        │ CLIP Text      │ → 负面提示词
     │        │ Encode         │
     │        └────┬───────────┘
     │             │
     ↓             ↓
┌────────────────────┐
│ LTXVSampler        │ → 设置 704x480, 25帧, 8步
└────┬───────────────┘
     ↓
┌────────────────────┐
│ VAE Decode         │
└────┬───────────────┘
     ↓
┌────────────────────┐
│ VHS_VideoCombine   │ → 输出 MP4
└────────────────────┘
```

2. **设置 LTXVSampler 参数**：
   - width: 704
   - height: 480
   - num_frames: 25
   - steps: 8
   - cfg_scale: 1.0
   - fps: 24

---

## 🎭 工作流 2：图片转视频（鬼脸表情）

### 方式 A：使用预制工作流文件（推荐）

1. **加载工作流**：
   - 打开：`workflow_ltxv_img2video_test.json`

2. **检查节点参数**：
   - **LoadImage**：确认加载 `照片.jpg`
   - **正面提示词**：`person in the photo making various funny faces, realistic facial expressions, natural movement, smooth animation, high quality`
   - **负面提示词**：`blurry, distorted, static, stiff, unnatural, low quality, artifacts`
   - **LTXV采样器**：同工作流1参数

3. **运行生成**：
   - 点击"运行"
   - 输出文件名前缀：`ltxv_img2video_faces`

### 方式 B：手动创建节点

```
节点连接顺序：
┌────────────┐
│ LoadImage  │ → 加载 照片.jpg
└────┬───────┘
     │
     ↓
┌────────────────────┐      ┌─────────────┐
│ LTXVImgToVideo     │ ←──  │ LTXVLoader  │
│ （图像转视频条件）  │      └─────────────┘
└────┬───────────────┘             ↑
     │                              │
     ↓                              │
┌────────────────────┐              │
│ CLIP Text Encode   │ ─────────────┘
│ (positive)         │
└────┬───────────────┘
     │
     ↓
┌────────────────────┐
│ LTXVSampler        │
└────┬───────────────┘
     ↓
┌────────────────────┐
│ VAE Decode         │
└────┬───────────────┘
     ↓
┌────────────────────┐
│ VHS_VideoCombine   │
└────────────────────┘
```

---

## ⚙️ 参数调优建议

### 如果 VRAM 不足（CUDA Out of Memory）：
- 降低分辨率：`640x432` 或 `576x384`
- 减少帧数：`17` 帧（记住必须是 8n+1）
- 使用 FP8 量化模型（如果可用）

### 如果想要更长视频：
- 增加帧数到 `33` 或 `49`（必须 8n+1）
- 注意：帧数越多，生成时间越长，VRAM 需求越大

### 如果想要更高质量：
- 提升分辨率到 `768x512`
- 优化提示词：添加更多细节描述
- 调整 seed：尝试不同随机种子

---

## 🐛 常见问题排查

### 问题 1：节点报错"找不到模型"
**解决方案**：
- 检查模型文件是否在 `E:\AI\Models\checkpoints\`
- 在 LTXVLoader 节点中重新选择模型

### 问题 2：num_frames 参数报错
**解决方案**：
- 必须使用 8n+1 格式：9, 17, 25, 33, 41, 49...
- 不能使用：16, 20, 24, 30 等

### 问题 3：生成的视频质量差
**解决方案**：
- 检查是否使用了 distilled 模型（需要 cfg=1.0, steps=8）
- 检查提示词是否清晰具体
- 尝试不同 seed 值

### 问题 4：生成速度极慢
**解决方案**：
- 检查 GPU 是否被正确使用（终端应显示 cuda:0）
- 降低分辨率和帧数
- 关闭其他占用 GPU 的程序

---

## 📊 预期输出

### 文本转视频（鱼尾狮）：
- **时长**：约 1 秒（25帧 @ 24fps）
- **分辨率**：704x480
- **文件大小**：约 200-500 KB
- **内容**：鱼尾狮雕像动态场景

### 图片转视频（鬼脸）：
- **时长**：约 1 秒（25帧 @ 24fps）
- **分辨率**：704x480
- **文件大小**：约 200-500 KB
- **内容**：照片人物做出动态表情

---

## 📝 后续步骤

生成成功后：
1. 查看输出文件：`E:\AI\ComfyUI_windows_portable\ComfyUI\output\`
2. 评估视频质量
3. 根据结果调整参数
4. 尝试更复杂的提示词
5. 探索图像条件、音频等高级功能

---

## 🎯 快速测试命令

如果需要从命令行检查输出：
```powershell
# 查看最新生成的视频
Get-ChildItem E:\AI\ComfyUI_windows_portable\ComfyUI\output\ -Filter "*.mp4" | Sort-Object LastWriteTime -Descending | Select-Object -First 5

# 用默认播放器打开最新视频
$latest = Get-ChildItem E:\AI\ComfyUI_windows_portable\ComfyUI\output\ -Filter "*.mp4" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Start-Process $latest.FullName
```

祝测试顺利！🚀

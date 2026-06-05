# ComfyUI 首个本地视频生成工作流

## 核心原则
✓ 完全本地运行 - 零云调用  
✓ RTX 3070 8GB 优化参数  
✓ 16 帧最小动画测试  
✓ 使用本地 SD1.5 + AnimateDiff  

---

## 工作流概览

```
Prompt (正向提示)
    ↓
Checkpoint (SD1.5 本地模型)
    ↓
CLIP Text Encode (正向提示编码)
    ↓
KSampler (采样，生成 16 帧潜在空间)
    ↓
AnimateDiff + Motion Model (mm_sd_v15_v2 本地)
    ↓
VAE Decode (解码 → 16 个图像帧)
    ↓
Video Combine (合并为 MP4)
    ↓
SaveVideo (保存到本地)
```

---

## 一步一步搭建（按菜单结构）

### Step 1: 加载本地 SD1.5 Checkpoint

**菜单路径：** 右键 → Add Node → loaders → Checkpoint Loader

**节点参数：**
- `ckpt_name` = `v1-5-pruned-emaonly` ✓ (你已下载的本地文件)

**输出端口连接到：**
- `CLIP` → 下一步的 CLIP Text Encode  
- `CONDITIONING` → KSampler  
- `MODEL` → KSampler  

---

### Step 2: 正向提示编码

**菜单路径：** 右键 → Add Node → conditioning → CLIP Text Encode (Positive)

**节点参数：**
- `text` = 输入你的正向提示词，例如：
  ```
  masterpiece, best quality, cinematic, 
  a beautiful woman dancing, smooth motion, 
  detailed face, soft lighting
  ```

**连接：**
- 左侧 `CLIP` ← Checkpoint Loader 的 CLIP 输出
- 右侧 `CONDITIONING` → KSampler 的 `positive` 输入

---

### Step 3: 反向提示编码（可选但推荐）

**菜单路径：** 右键 → Add Node → conditioning → CLIP Text Encode (Negative)

**节点参数：**
- `text` = 输入反向提示词，例如：
  ```
  blurry, distorted, low quality, 
  bad hands, static, frozen
  ```

**连接：**
- 左侧 `CLIP` ← Checkpoint Loader 的 CLIP 输出
- 右侧 `CONDITIONING` → KSampler 的 `negative` 输入

---

### Step 4: KSampler（核心采样）- RTX 3070 优化

**菜单路径：** 右键 → Add Node → sampling → KSampler

**节点参数（重要 - 3070 8GB 配置）：**
- `seed` = 随机数或固定值如 `42`
- `steps` = `20` (推荐 20-25，不要超过 30)
- `cfg` = `7.5` (分类自由度，推荐 7-8.5)
- `sampler_name` = `dpmpp_2m_karras` (快速且质量好)
- `scheduler` = `karras`
- `denoise` = `1.0` (完整生成)
- `latent_image` = **留空**（会自动创建）

**连接：**
- `model` ← Checkpoint Loader 的 MODEL  
- `positive` ← CLIP Text Encode (Positive) 的 CONDITIONING  
- `negative` ← CLIP Text Encode (Negative) 的 CONDITIONING  
- `LATENT` → 下一步（AnimateDiff 或直接 VAE Decode）

---

### Step 5: 添加 AnimateDiff 动画模块

**菜单路径：** 右键 → Add Node → video → AnimateDiff Loader

**节点参数：**
- `model_name` = `mm_sd_v15_v2` ✓ (你已下载的本地动画模型)

**连接：**
- `MOTION_MODEL` 输出 → 下一步

---

### Step 6: 应用动画到采样结果

**菜单路径：** 右键 → Add Node → video → AnimateDiff Sampler

**节点参数（3070 8GB）：**
- `frames` = `16` (最小可靠帧数)
- `overlap` = `4` (帧重叠，提高流畅度)
- `motion_scale` = `1.0` (动作强度，推荐 0.8-1.2)

**连接：**
- `model` ← KSampler 的 `LATENT`  
- `motion_model` ← AnimateDiff Loader 的 MOTION_MODEL  
- `latent` 输出 → 下一步 VAE Decode

---

### Step 7: VAE 解码（转换为图像）

**菜单路径：** 右键 → Add Node → latent → VAE Decode

**节点参数：**
- `samples` ← AnimateDiff Sampler 的 latent 输出

**连接：**
- `VAE` ← Checkpoint Loader 的 VAE  
- `IMAGE` 输出 → Video Combine

---

### Step 8: 视频合并

**菜单路径：** 右键 → Add Node → video → Video Combine

**节点参数：**
- `fps` = `8` (推荐 6-12，越低越流畅但越慢)
- `format` = `video/mp4` (标准 MP4 格式)

**连接：**
- `images` ← VAE Decode 的 IMAGE  
- `video` 输出 → SaveVideo

---

### Step 9: 保存视频到本地

**菜单路径：** 右键 → Add Node → video → SaveVideo

**节点参数：**
- `filename_prefix` = `anim_test_` (输出文件前缀)
- 其他选项保持默认

**连接：**
- `video` ← Video Combine 的视频输出

---

## 执行工作流

1. **检查所有节点已连接** - 没有红色感叹号或断开的线
2. **点击右上角 "Queue Prompt"** - 开始生成
3. **观察控制台输出** - 应该看到：
   ```
   Loading checkpoint...
   Model loaded
   Sampling... step 1/20, step 2/20...
   AnimateDiff motion applied
   VAE decoding...
   Video combining...
   Saved to E:\AI\Assets\video_out\anim_test_XXXX.mp4
   ```

---

## 预期结果（RTX 3070 8GB）

| 项目 | 预期时间 | 说明 |
|------|----------|------|
| 加载模型 | 5-10 秒 | SD1.5 (3.97GB) + AnimateDiff (1.82GB) |
| 采样 20 步 | 60-90 秒 | 16 帧采样，3070 约 6-9 秒/步 |
| AnimateDiff 处理 | 30-45 秒 | 动作模块应用 |
| VAE 解码 | 20-30 秒 | 16 帧解码 |
| 视频编码 | 10-20 秒 | MP4 合成 |
| **总计** | **2-4 分钟** | 首次包括模型加载 |

---

## 常见问题 & 本地化检查清单

### 模型在哪里？如何确认本地加载？

✓ **Checkpoint**  
- 位置：`E:\AI\Models\checkpoints\v1-5-pruned-emaonly.safetensors`  
- ComfyUI 菜单验证：Checkpoint Loader 下拉 → 应该看到 `v1-5-pruned-emaonly`  

✓ **AnimateDiff Motion Model**  
- 位置：`E:\AI\Models\animatediff_models\mm_sd_v15_v2.ckpt`  
- ComfyUI 菜单验证：AnimateDiff Loader 下拉 → 应该看到 `mm_sd_v15_v2`  

✓ **VAE**  
- 自动来自 Checkpoint（已包含）  
- 无需单独指定  

### 如何确认没有调用云 API？

1. **断网测试** - 断开网络，工作流仍能运行 ✓
2. **监听器检查** - ComfyUI 控制台应该 **只显示本地文件访问**
3. **网络监控** - Wireshark/Task Manager 应该 **无向外网连接**

### 显存不足怎么办？

如果看到 `RuntimeError: CUDA out of memory`：
- 减少 `steps` 从 20 → 15
- 减少 `frames` 从 16 → 12
- 启用 `--medvram` 模式（已在 webui-user.bat 配置）

### 动作不明显？

如果生成的 16 帧看起来很静态：
- 提高正向提示里的动作词：`动态动作, 流畅运动, 摄像机推进`
- 增加 `motion_scale` 从 1.0 → 1.3
- 减少 `overlap` 从 4 → 2

---

## 输出文件位置

生成的视频默认保存到：
```
E:\AI\Assets\video_out\anim_test_XXXX.mp4
```

你可以用任何视频播放器查看（VLC, Windows Media Player, 浏览器）。

---

## 下一步优化（完成首个视频后）

1. **尝试不同提示词** - 测试风格多样性
2. **增加帧数** - 从 16 → 24 或 32（更流畅但更慢）
3. **尝试其他 AnimateDiff 模型** - v3_sd15_mm.ckpt
4. **图生视** - 用 Load Image + 采样控制生成
5. **视频编辑** - 用 FFmpeg 链接多段视频


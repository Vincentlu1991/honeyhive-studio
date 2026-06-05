# 如何通过GUI与Supervisor Agent生成连贯视频

## 🎯 问题：为什么之前的动画不连贯？

### 错误方法（已废弃）
```
❌ 逐帧独立生成 → 每帧seed不同 → 人物/场景不一致 → 无法连贯
```

### 正确方法
```
✓ 使用AnimateDiff → 运动模型 → 时间一致性 → 连贯动画
```

---

## 🚀 正确流程：通过Supervisor Agent生成视频

### 方式一：直接ComfyUI测试（推荐先测试）

**Step 1: 在ComfyUI中加载工作流**
1. 打开 http://127.0.0.1:8188
2. 拖入文件: `E:\AI\workflows\workflow_sd15_animatediff.json`
3. 点击 "Queue Prompt"
4. 等待3-5分钟
5. 查看输出帧序列（应该是连贯的）

**注意**: AnimateDiff生成的是帧序列，需要后处理合成视频。

---

### 方式二：通过GUI与Supervisor Agent交互

#### 1. 启动GUI
```powershell
cd "c:\Users\User\OneDrive\文档\New project\agent-platform"
.\.venv\Scripts\Activate.ps1
streamlit run app_robust.py
```

访问: http://localhost:8501

#### 2. 选择合适的标签页

GUI有多个标签页：
- **🎬 运行视频生成**: 提交完整场景描述，Supervisor自动调度
- **💬 Agent对话**: 与特定Agent（Story/Prompt/Builder）直接对话
- **📊 查看执行历史**: 查看之前的生成记录

#### 3. 与Supervisor Agent对话

**标签页**: 🎬 运行视频生成

**输入场景描述** (中文):
```
一个紫发赛博朋克少女在雨夜的东京街头缓慢行走。
她穿着黑色皮夹克，霓虹灯光反射在湿润的地面上。
镜头跟随她的步伐，展现流畅的运动和细腻的面部表情。
整体氛围忧郁而神秘，电影级画质。
```

**设置参数**:
- Seed: `42` (可重现)
- Max Retries: `2` (QA失败后重试次数)

**点击 "执行生成"**

---

## 🔄 多Agent工作流程

### Supervisor Agent会自动调度：

```mermaid
Supervisor
    ↓
Story Agent (场景分解)
    ↓
Prompt Agent (生成正负提示词)
    ↓
Builder Agent (构建ComfyUI工作流)
    ↓
ComfyUI (渲染视频)
    ↓
QA Agent (质量评分)
    ↓
[如果失败] → 重试
[如果成功] → 完成
```

### 1. Story Agent
- **输入**: 你的中文场景描述
- **输出**: 结构化的SceneSpec (JSON)
  ```json
  {
    "scene_description": "cyberpunk girl walking...",
    "duration_seconds": 2,
    "motion_intensity": "medium",
    "style_notes": "cinematic, neon lights"
  }
  ```

### 2. Prompt Agent
- **输入**: SceneSpec
- **输出**: PromptPack
  ```json
  {
    "positive": "a purple-haired cyberpunk girl walking...",
    "negative": "static, blurry, bad quality...",
    "motion": "smooth walking, camera follow"
  }
  ```

### 3. Builder Agent
- **输入**: PromptPack
- **输出**: 修改后的ComfyUI工作流JSON
- **操作**: 
  - 替换提示词到节点 6/7
  - 设置seed到节点 3
  - 配置帧数、分辨率等参数

### 4. ComfyUI Executor
- **输入**: 工作流JSON
- **操作**: 调用ComfyUI API执行
- **输出**: 视频帧序列

### 5. QA Agent
- **输入**: 生成的视频帧
- **输出**: QAReport
  ```json
  {
    "face_quality_score": 8.5,
    "motion_smoothness_score": 9.0,
    "artifact_score": 7.5,
    "overall_pass": true
  }
  ```

---

## ⚙️ 当前配置

### 环境变量 (.env)
```bash
COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_WORKFLOW_PATH=E:\AI\workflows\workflow_sd15_animatediff.json
LOCAL_LLM_MODEL=qwen2.5:7b-instruct
OUTPUT_DIR=E:\AI\outputs
```

### 模型配置
- **Base Model**: SD1.5 (v1-5-pruned-emaonly.safetensors)
- **Motion Module**: AnimateDiff mm_sd_v15_v2.ckpt
- **Text Encoder**: CLIP (内置在SD1.5中)
- **VRAM需求**: 4-6 GB ✓

---

## 🎬 预期输出

### AnimateDiff生成结果
- **格式**: 16张PNG帧 (或更多)
- **分辨率**: 512x512
- **时间一致性**: ✓ 人物外观一致
- **运动连贯性**: ✓ 平滑过渡
- **输出位置**: `E:\AI\ComfyUI_windows_portable\ComfyUI\output\`

### 后处理（可选）
使用Python合成GIF/MP4:
```powershell
cd agent-platform
.\.venv\Scripts\Activate.ps1

# 合成GIF
python -c "from PIL import Image; import glob; frames = [Image.open(f) for f in sorted(glob.glob('E:/AI/ComfyUI_windows_portable/ComfyUI/output/animatediff_video_*.png'))]; frames[0].save('output.gif', save_all=True, append_images=frames[1:], duration=125, loop=0)"
```

---

## 🐛 故障排查

### GUI无法访问
```powershell
# 检查Streamlit进程
Get-Process -Name "streamlit" -ErrorAction SilentlyContinue

# 重启GUI
cd agent-platform
.\.venv\Scripts\Activate.ps1
streamlit run app_robust.py
```

### Supervisor报错
**可能原因**:
1. **Ollama未启动**: 
   ```powershell
   E:\AI\start-ollama.ps1
   ```
2. **ComfyUI未运行**:
   ```powershell
   E:\AI\ComfyUI_windows_portable\run_nvidia_gpu.bat
   ```
3. **工作流文件不存在**: 检查 `.env` 中的 `COMFYUI_WORKFLOW_PATH`

### 生成失败
查看GUI中的错误信息：
- **Story Agent失败**: LLM响应格式错误
- **Builder Agent失败**: 工作流节点不匹配
- **ComfyUI失败**: 模型文件缺失或VRAM不足
- **QA Agent失败**: 质量分数低于阈值

---

## 📝 最佳实践

### 1. 场景描述技巧
```
✓ 具体描述人物、动作、环境
✓ 指定运动类型（walking, turning, gesture）
✓ 说明氛围和风格（cinematic, moody, bright）
✓ 控制在50-100字

❌ 避免过于复杂的多人物场景
❌ 避免快速剧烈运动（容易模糊）
❌ 避免小物体细节（512分辨率有限）
```

### 2. 参数调优
- **Seed**: 固定seed保证可重现性
- **Steps**: 15-20步（速度vs质量平衡）
- **CFG**: 7-8（提示词遵循度）
- **Frames**: 16帧（约2秒 @ 8fps）

### 3. 硬件限制
- **RTX 3070 8GB** 适合:
  - ✓ 512x512 @ 16帧
  - ✓ SD1.5 + AnimateDiff
  - ✓ 单个角色场景
  
- **不适合**:
  - ❌ 720p+ 高分辨率
  - ❌ LTXV/SDXL 大模型
  - ❌ 32+帧长视频

---

## 🎯 快速开始示例

### Example 1: 简单人物动作
```
一个年轻女孩在海边挥手，微笑看向镜头。
阳光明媚，海浪轻柔，清新自然的风格。
```

### Example 2: 场景转换
```
从黑暗的城市街道缓慢推进到明亮的咖啡店内部。
霓虹灯光逐渐淡化，温暖的室内灯光出现。
```

### Example 3: 情绪表达
```
一个男人坐在雨中的长椅上，低头沉思。
雨滴在镜头前模糊地划过，忧郁的蓝色调。
```

---

## ✅ 验证清单

在提交场景前检查：
- [ ] Ollama运行中 (http://127.0.0.1:11434)
- [ ] ComfyUI运行中 (http://127.0.0.1:8188)
- [ ] GUI可访问 (http://localhost:8501)
- [ ] 工作流文件存在 (E:\AI\workflows\workflow_sd15_animatediff.json)
- [ ] 场景描述清晰具体
- [ ] 参数设置合理

---

**现在你可以通过GUI与Supervisor Agent对话，生成真正连贯的视频了！** 🚀

# 🚀 快速开始：通过Supervisor Agent生成连贯视频

**日期**: 2026年5月19日  
**状态**: ✅ 所有系统就绪

---

## ✅ 当前状态检查

```
✓ Ollama运行中 (http://127.0.0.1:11434)
✓ ComfyUI运行中 (http://127.0.0.1:8188)
✓ GUI运行中 (http://localhost:8501)
✓ AnimateDiff工作流已配置
```

---

## 🎯 立即开始（3步）

### Step 1: 打开GUI

访问: **http://localhost:8501**

你会看到：
- 标题: "Multi-Agent AI Video Generation Platform"
- 侧边栏: 显示系统状态（Ollama, ComfyUI配置）
- 主界面: 多个标签页

---

### Step 2: 选择 "🎬 运行视频生成" 标签页

在这个页面你可以：
1. **输入场景描述** (使用中文)
2. **设置参数** (Seed, Max Retries)
3. **点击"执行生成"**

---

### Step 3: 输入测试场景

**推荐测试场景** (复制下面的文字):

```
一个紫发赛博朋克少女在雨夜的东京街头缓慢行走，
霓虹灯反射在湿润的路面上，
她的黑色皮夹克在风中微微飘动，
整体氛围忧郁神秘，电影级画质
```

**参数设置**:
- **Seed**: `42`
- **Max Retries**: `2`

**点击**: "执行生成"

---

## 🔄 预期流程

### 1. Supervisor Agent启动
```
Supervisor收到你的场景描述
↓
分析任务，决定调用哪些子Agent
↓
开始多Agent协作流程
```

### 2. Story Agent处理
```
输入: "一个紫发赛博朋克少女在雨夜..."
↓
输出: SceneSpec JSON
{
  "scene_description": "purple-haired cyberpunk girl...",
  "duration_seconds": 2,
  "motion_intensity": "low",
  "style_notes": "cinematic, neon, rainy"
}
```

### 3. Prompt Agent优化
```
输入: SceneSpec
↓
输出: PromptPack
{
  "positive": "a purple-haired cyberpunk girl walking slowly in rainy Tokyo street at night, neon lights reflecting on wet pavement, black leather jacket flowing in wind, moody mysterious atmosphere, cinematic masterpiece",
  "negative": "static, blurry, bad quality, deformed, text, watermark",
  "motion": "slow walking, camera follow"
}
```

### 4. Builder Agent构建
```
输入: PromptPack
↓
操作: 
  - 读取 workflow_sd15_animatediff.json
  - 替换节点6的正面提示词
  - 替换节点7的负面提示词
  - 设置节点3的seed=42
↓
输出: 修改后的工作流JSON
```

### 5. ComfyUI执行
```
输入: 工作流JSON
↓
过程:
  - 加载SD1.5模型
  - 加载AnimateDiff运动模块
  - 编码文本提示词 (CLIP)
  - 生成16帧 (with temporal consistency)
  - VAE解码
  - 保存帧序列
↓
输出: 16张PNG图片
```

### 6. QA Agent评估
```
输入: 生成的帧序列
↓
分析:
  - 面部质量
  - 运动平滑度
  - 瑕疵检测
↓
输出: QAReport
{
  "face_quality_score": 8.5,
  "motion_smoothness_score": 9.0,
  "artifact_score": 7.8,
  "overall_pass": true
}
```

### 7. Supervisor总结
```
✓ 所有步骤成功
✓ QA通过
✓ 输出路径: E:\AI\ComfyUI_windows_portable\ComfyUI\output\
✓ 生成耗时: ~3-5分钟
```

---

## 📊 GUI界面说明

### 主要标签页

#### 1. 🎬 运行视频生成
- **功能**: 完整的端到端生成流程
- **适合**: 快速生成，让Supervisor自动调度
- **输入**: 中文场景描述 + 参数
- **输出**: 视频帧序列 + 执行日志

#### 2. 💬 Agent对话
- **功能**: 与特定Agent交互
- **适合**: 调试、测试单个Agent
- **选项**:
  - Story Agent (场景理解)
  - Prompt Agent (提示词优化)
  - Builder Agent (工作流构建)
  - QA Agent (质量评估)

#### 3. 📊 查看执行历史
- **功能**: 查看之前的生成记录
- **内容**: 输入参数、输出结果、执行时间

---

## ⚠️ 重要提示

### 为什么AnimateDiff比之前的好？

**之前的方法** (逐帧独立生成):
```
❌ Frame 1: seed=43 → 少女A (紫发，圆脸)
❌ Frame 2: seed=44 → 少女B (紫发，长脸)
❌ Frame 3: seed=45 → 少女C (紫发，不同发型)
→ 结果: 每帧人物都不一样！
```

**AnimateDiff方法**:
```
✓ 使用运动模块 (mm_sd_v15_v2.ckpt)
✓ 时间一致性约束
✓ 所有帧共享相同的人物特征
✓ 平滑的帧间过渡
→ 结果: 人物一致，动作流畅！
```

### AnimateDiff的工作原理

1. **第一帧**: 完整生成人物和场景
2. **后续帧**: 
   - 保持人物外观特征 (通过时间注意力机制)
   - 只改变姿态和位置 (根据运动模块)
   - 平滑插值 (避免突变)

### 输出说明

AnimateDiff输出的是**帧序列**，不是视频文件：
```
animatediff_video_00001_.png  ← 第1帧
animatediff_video_00002_.png  ← 第2帧
...
animatediff_video_00016_.png  ← 第16帧
```

**合成视频** (可选):
```powershell
# 方法1: Python PIL 合成GIF
cd agent-platform
.\.venv\Scripts\Activate.ps1
python -c "from PIL import Image; import glob; frames = [Image.open(f) for f in sorted(glob.glob('E:/AI/ComfyUI_windows_portable/ComfyUI/output/animatediff_video_*.png'))]; frames[0].save('E:/AI/outputs/coherent_video.gif', save_all=True, append_images=frames[1:], duration=125, loop=0)"

# 方法2: 使用在线工具
# 访问 ezgif.com/maker
# 上传所有帧，创建GIF或MP4
```

---

## 🎯 测试检查清单

在GUI中点击"执行生成"前，确认：
- [ ] 所有服务运行正常（查看GUI侧边栏）
- [ ] 场景描述清晰具体（50-100字）
- [ ] Seed设置为固定值（如42，保证可重现）
- [ ] 有5-10分钟时间等待生成完成

点击后，你会看到：
- [ ] GUI显示"正在执行..."
- [ ] ComfyUI窗口显示进度条
- [ ] 终端输出Agent对话日志
- [ ] 最终显示输出路径和QA报告

---

## 🐛 如果遇到问题

### GUI报错："Ollama不可达"
```powershell
# 启动Ollama
E:\AI\start-ollama.ps1
```

### GUI报错："ComfyUI连接失败"
```powershell
# 启动ComfyUI
E:\AI\ComfyUI_windows_portable\run_nvidia_gpu.bat
```

### 生成卡住/超时
- 检查ComfyUI窗口是否有错误
- 访问 http://127.0.0.1:8188 查看队列状态
- 检查VRAM是否不足（任务管理器 → GPU）

### 输出质量差
- 调整Seed尝试不同随机种子
- 优化场景描述（更具体、更简单）
- 降低运动强度（"缓慢行走"比"快速跑步"好）
- 增加Steps (20 → 25)

---

## 📝 后续步骤

### Day 1 完成后（今天）:
✅ 环境搭建
✅ 首次视频生成（虽然不连贯）
✅ **学习如何使用Supervisor Agent** ← 你在这里

### Day 2 建议:
- [ ] 通过GUI测试3个不同场景
- [ ] 记录每个场景的QA分数
- [ ] 调优参数（Seed, Steps, CFG）
- [ ] 测试失败重试机制

### Day 3-4:
- [ ] 分析多个工作流的差异
- [ ] 创建节点映射表
- [ ] 测试不同风格（现实、动漫、抽象）

---

## 🎬 现在就开始！

1. **打开GUI**: http://localhost:8501
2. **复制测试场景**（上面的紫发少女）
3. **点击"执行生成"**
4. **等待3-5分钟**
5. **查看输出**:
   - 帧序列: `E:\AI\ComfyUI_windows_portable\ComfyUI\output\`
   - QA报告: GUI中显示

**预期结果**: 16帧连贯动画，人物一致，动作流畅！

---

**祝你生成顺利！如有问题，查看详细指南: `HOW-TO-USE-GUI.md`** 🚀

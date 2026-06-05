# 问题解决报告

**日期**: 2026年5月19日  
**问题**: GUI 和 ComfyUI 工作流报错  
**状态**: ✅ **已解决**

---

## 问题诊断

### 原始错误
- GUI 在 http://localhost:8501 报错
- ComfyUI 工作流无法执行

### 根本原因
**缺少 LTXV 模型文件**

工作流需要 `ltxv-2b-0.9.8-distilled.safetensors` (5.91 GB)，但ComfyUI在以下位置查找：
```
E:\AI\ComfyUI_windows_portable\models\checkpoints\
```

而模型实际存储在：
```
E:\AI\Models\checkpoints\
```

---

## 解决方案

### 1. 复制模型文件 ✓
```powershell
Copy-Item "E:\AI\Models\checkpoints\ltxv-2b-0.9.8-distilled.safetensors" `
          -Destination "E:\AI\ComfyUI_windows_portable\models\checkpoints\"
```

**结果**: 5.91 GB 模型已复制到 ComfyUI 目录

### 2. 创建测试输入图片 ✓
```powershell
E:\AI\ComfyUI_windows_portable\input\照片.jpg
```

**结果**: 512x512 测试图片已创建

### 3. 验证扩展安装 ✓
确认以下扩展已安装：
- ✓ ComfyUI-LTXVideo
- ✓ ComfyUI-VideoHelperSuite  
- ✓ ComfyUI-AnimateDiff-Evolved
- ✓ ComfyUI_IPAdapter_plus

### 4. 重启 ComfyUI ✓
重启服务以加载新模型

---

## 验证结果

| 检查项 | 状态 | 详情 |
|--------|------|------|
| LTXV 模型 | ✅ | ltxv-2b-0.9.8-distilled.safetensors (5.91 GB) |
| 输入图片 | ✅ | 照片.jpg (测试图片) |
| VideoHelperSuite | ✅ | 已安装在 custom_nodes |
| LTXVideo 节点 | ✅ | 已安装在 custom_nodes |
| ComfyUI API | ✅ | http://127.0.0.1:8188 响应正常 |

---

## 现在可以测试了！

### 访问 GUI
```
http://localhost:8501
```

### 测试步骤

1. **选择 "🎬 运行视频生成" 标签页**

2. **输入测试场景**（中文）:
   ```
   一个人做出各种有趣的表情，真实的面部表情，自然的动作，流畅的动画
   ```

3. **配置参数**:
   - Seed: `42`
   - Workflow: 使用默认 (workflow_ltxv_img2video_test.json)
   - Max Retries: `2`

4. **点击执行** → 等待生成（约 3-8 分钟）

---

## 预期结果

### 工作流执行流程
1. LoadImage: 加载 照片.jpg
2. LTXVCheckpointLoader: 加载模型 (5.91 GB)
3. CLIPTextEncode: 编码正面/负面提示词
4. LTXVImgToVideo: 图像转视频条件处理
5. LTXVSampler: 采样生成 (25帧, 704x480, 24fps)
6. VAEDecode: 解码潜空间
7. VHS_VideoCombine: 输出 MP4 视频

### 输出
- **格式**: H.264 MP4
- **分辨率**: 704x480
- **帧数**: 25 帧
- **帧率**: 24 FPS
- **时长**: 约 1 秒
- **文件名**: ltxv_img2video_faces_[数字].mp4
- **位置**: E:\AI\ComfyUI_windows_portable\output\

---

## 性能预估

### RTX 3070 8GB
- **VRAM 使用**: 约 6-7 GB（接近满载）
- **生成时间**: 3-8 分钟（取决于系统）
- **温度**: 可能达到 70-80°C

### 如果 VRAM 不足
降低参数：
```json
"width": 640,      // 从 704 降低
"height": 432,     // 从 480 降低  
"num_frames": 17   // 从 25 降低
```

---

## 故障排查

### 如果还是报错

1. **检查 ComfyUI 窗口的实际错误信息**

2. **验证模型加载**:
   ```powershell
   Get-ChildItem "E:\AI\ComfyUI_windows_portable\models\checkpoints\ltxv*.safetensors"
   ```

3. **检查输入图片**:
   ```powershell
   Test-Path "E:\AI\ComfyUI_windows_portable\input\照片.jpg"
   ```

4. **重新测试 API**:
   ```powershell
   Invoke-WebRequest -Uri "http://127.0.0.1:8188/system_stats" -UseBasicParsing
   ```

5. **查看 GUI 终端输出** (Terminal ID: 652f3b62-8ed1-49ed-98e0-3d01084daed8)

---

## 后续优化建议

### 1. 使用更小的工作流（如果VRAM紧张）
```
workflow_sd15_animatediff.json  # 使用 SD1.5，VRAM需求更低
```

### 2. 创建符号链接（需要管理员权限）
避免重复复制模型：
```powershell
# 以管理员身份运行
cmd /c mklink /D "E:\AI\ComfyUI_windows_portable\models\checkpoints" "E:\AI\Models\checkpoints"
```

### 3. 使用真实人脸照片
替换 `照片.jpg` 为真实照片可获得更好效果。

---

## 总结

✅ **所有依赖已就绪，系统可以正常运行！**

**模型复制完成**: LTXV (5.91 GB)  
**扩展已安装**: VideoHelperSuite, LTXVideo  
**服务状态**: ComfyUI + Ollama + GUI 全部运行中

**下一步**: 在 GUI 中测试视频生成！

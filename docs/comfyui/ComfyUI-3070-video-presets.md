# ComfyUI RTX 3070 视频参数模板

适用环境：
- 显卡：RTX 3070 8GB
- **主要模型（2025）：ltxv-2b-0.9.8-distilled.safetensors**（推荐所有新视频工作流）
- 旧模型（仅 motion LoRA 需要）：v1-5-pruned-emaonly.safetensors + mm_sd_v15_v2.ckpt
- 输出节点：VHS_VideoCombine

---

# LTX-Video 2B 参数档（2025 当前推荐）

使用前提：已安装 ComfyUI-LTXVideo 插件，已下载 ltxv-2b-0.9.8-distilled.safetensors

## LTX-1) 快速预览档

用途：先确认工作流通畅，快速看效果。

参数：
- LTXVLoader
  - ckpt_name: ltxv-2b-0.9.8-distilled.safetensors
- LTXVSampler（或等效采样节点）
  - width: 704
  - height: 480
  - num_frames: 25（必须是 8n+1，如 9/17/25/33）
  - steps: 8（蒸馏模型，不要用 20+）
  - cfg_scale: 1.0（蒸馏模型不用 CFG，设为 1.0 或禁用）
  - fps: 24
- VHS_VideoCombine
  - frame_rate: 24
  - format: video/h264-mp4
  - filename_prefix: ltxv_fast

预期：
- 每次生成约 30–60 秒
- VRAM 占用 ~6–7 GB
- 运动流畅，质量远优于 AnimateDiff

## LTX-2) 平衡质量档（日常推荐）

参数：
- LTXVLoader
  - ckpt_name: ltxv-2b-0.9.8-distilled.safetensors
- LTXVSampler
  - width: 768
  - height: 512
  - num_frames: 33
  - steps: 8
  - cfg_scale: 1.0
  - fps: 24
- VHS_VideoCombine
  - frame_rate: 24
  - format: video/h264-mp4
  - filename_prefix: ltxv_balanced

预期：
- 细节更好，约 1.5 秒动画
- VRAM 占用 ~7–8 GB

## LTX-3) 较长时长档（稳定后使用）

参数：
- LTXVLoader
  - ckpt_name: ltxv-2b-0.9.8-distilled.safetensors
- LTXVSampler
  - width: 704
  - height: 480
  - num_frames: 49（约 2 秒 @ 24fps）
  - steps: 8
  - cfg_scale: 1.0
  - fps: 24
- VHS_VideoCombine
  - frame_rate: 24
  - format: video/h264-mp4
  - filename_prefix: ltxv_long

预期：
- 较长连贯动画
- 如 VRAM 报错，降回 33 帧或分辨率改为 704x480

---

# AnimateDiff SD1.5 参数档（旧方案，仅保留用于 motion LoRA）

基模：v1-5-pruned-emaonly.safetensors，动作模型：mm_sd_v15_v2.ckpt

## AD-1) 稳定起步档

参数：
- EmptyLatentImage: width 512, height 512, batch_size 16
- KSampler: steps 15, cfg 7.0, sampler_name dpmpp_2m, scheduler karras
- VHS_VideoCombine: frame_rate 8, format video/h264-mp4

## AD-2) 平衡质量档

参数：
- EmptyLatentImage: width 576, height 576, batch_size 24
- KSampler: steps 18, cfg 7.5, sampler_name dpmpp_2m, scheduler karras
- VHS_VideoCombine: frame_rate 8, format video/h264-mp4

## 固定不变的核心连接（避免接错）

1. Checkpoint MODEL -> ADE_UseEvolvedSampling model
2. Checkpoint CLIP -> 正向 CLIPTextEncode clip
3. Checkpoint CLIP -> 反向 CLIPTextEncode clip
4. ADE_LoadAnimateDiffModel MOTION_MODEL -> ADE_ApplyAnimateDiffModelSimple motion_model
5. ADE_ApplyAnimateDiffModelSimple M_MODELS -> ADE_UseEvolvedSampling m_models
6. ADE_UseEvolvedSampling MODEL -> KSampler model
7. 正向 CONDITIONING -> KSampler positive
8. 反向 CONDITIONING -> KSampler negative
9. EmptyLatentImage LATENT -> KSampler latent_image
10. KSampler LATENT -> VAEDecode samples
11. Checkpoint VAE -> VAEDecode vae
12. VAEDecode IMAGE -> VHS_VideoCombine images

## 常见报错快速处理

### LTX-Video 报错

1. CUDA out of memory
- 先把 num_frames 降到 25
- 再把分辨率改回 704x480
- 确认 steps 不超过 8（蒸馏模型超过 8 步反而变差且更慢）

2. 找不到 ltxv 模型
- 确认文件在 E:\AI\Models\checkpoints\ltxv-2b-0.9.8-distilled.safetensors
- 重启 ComfyUI 后在 LTXVLoader 节点的 ckpt_name 中选取

3. 输出视频抖动/画面不连贯
- 检查 num_frames 是否为 8n+1（9, 17, 25, 33, 49 ...）
- 非 8n+1 帧数会导致不规则输出

### AnimateDiff SD1.5 报错（旧方案）

1. CUDA out of memory
- 先把 batch_size 减到 16
- 再把分辨率改回 512x512
- 最后把 steps 从 20 降到 15

2. sampler_name 校验失败
- 使用 dpmpp_2m
- 不要写 dpmpp_2m_karras（karras 应该放在 scheduler）

3. 找不到 motion model
- 确认文件在 E:\AI\Models\animatediff_models\mm_sd_v15_v2.ckpt
- 重启 ComfyUI 后再选

4. 输出没有 mp4
- VHS_VideoCombine 的 format 必须是 video/h264-mp4 或其他 video/*
- save_output 必须为 true

## 一次完整生成的最短步骤

1. 加载工作流（你已经可用）
2. 只改 3 个地方：
- 正向提示词
- 反向提示词
- 参数档位（16/24/32）
3. 点击运行
4. 在输出目录查看 mp4：
- E:\AI\ComfyUI_windows_portable\ComfyUI\output


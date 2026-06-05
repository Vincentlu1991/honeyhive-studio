# AI Image + Video Plan

This plan assumes:
- Windows
- RTX 3070 8 GB
- Install root at E:\AI
- A1111 is used for still-image generation
- ComfyUI is used for workflow-based image and video generation

## Recommended split of responsibilities

- A1111: prompt iteration, still images, LoRA testing, inpaint, upscaling
- ComfyUI: AnimateDiff (SD1.5 legacy), LTX-Video (current), image-to-video, video-to-video, reusable workflows

For 3070 8 GB, this is the stable local path:
- Use SDXL mainly for still images
- Use LTX-Video 2B distilled for current video work (better quality than AnimateDiff, fits in 8 GB)
- Keep SD1.5-based AnimateDiff as a fallback for motion LoRA workflows only
- Keep early video jobs short: 16–32 frames first, then scale up

## Video stack comparison for RTX 3070 8 GB (2025–2026)

| Stack | Quality | VRAM | Speed | Status |
|---|---|---|---|---|
| SD1.5 + AnimateDiff | Low | ~6 GB | Slow | Legacy, maintained |
| LTX-Video 2B distilled | Medium-High | ~6–8 GB | Fast (8 steps) | Current recommended |
| LTX-Video 13B distilled | High | 20+ GB | — | Too large for 3070 |
| HunyuanVideo | Very High | 45–60 GB | — | NOT compatible with 3070 |

**Immediate upgrade action:** replace AnimateDiff video jobs with LTX-Video 2B distilled.
Plugin: https://github.com/Lightricks/ComfyUI-LTXVideo

## Recommended directory structure

Install root:

```text
E:\AI
├── Assets
│   ├── audio
│   ├── images
│   ├── masks
│   ├── reference
│   ├── video_in
│   └── video_out
├── ComfyUI_windows_portable
├── Downloads
├── Models
│   ├── animatediff_models
│   ├── animatediff_motion_lora
│   ├── checkpoints
│   ├── clip
│   ├── clip_vision
│   ├── controlnet
│   ├── diffusion_models
│   ├── embeddings
│   ├── insightface
│   ├── ipadapter
│   ├── loras
│   ├── upscale_models
│   └── vae
├── Projects
│   ├── comfyui-workflows
│   └── notes
└── stable-diffusion-webui
```

Practical meaning:
- Models/checkpoints: still-image checkpoints and SD1.5 video checkpoints
- Models/animatediff_models: motion modules for AnimateDiff
- Models/animatediff_motion_lora: motion LoRAs
- Assets/video_in: source clips for vid2vid
- Assets/video_out: rendered mp4/webm outputs
- Projects/comfyui-workflows: exported workflow json files

## What the expanded script installs

- ComfyUI portable
- ComfyUI Manager
- AUTOMATIC1111
- FFmpeg via winget
- ComfyUI-AnimateDiff-Evolved
- ComfyUI-VideoHelperSuite
- Shared model paths for A1111 and ComfyUI
- Starter asset folders and notes folders

## What the expanded script installs (2025 update)

- ComfyUI portable
- ComfyUI Manager
- AUTOMATIC1111
- FFmpeg via winget
- ComfyUI-AnimateDiff-Evolved (legacy SD1.5 video)
- ComfyUI-VideoHelperSuite
- ComfyUI-LTXVideo (current video generation)
- Shared model paths for A1111 and ComfyUI
- Starter asset folders and notes folders

## What you still add manually

These are better added manually because sources, login rules, and personal preference vary:

**For current video workflow (LTX-Video):**
- ltxv-2b-0.9.8-distilled.safetensors (primary video model, ~3 GB)
  Put in: E:\AI\Models\checkpoints

**For legacy SD1.5+AnimateDiff (optional, keep for motion LoRA work):**
- One SD1.5 checkpoint for AnimateDiff video work
- One AnimateDiff motion model such as mm_sd_v15_v2 or a compatible fp16 safetensors version
- Optional motion LoRAs
- Optional ControlNet and IPAdapter weights

## Recommended first video workflow

### Workflow 1: Text to video (LTX-Video 2B — current)

Use when you want a short generated clip from a prompt.

Suggested setup:
- Checkpoint: ltxv-2b-0.9.8-distilled.safetensors
- Plugin: ComfyUI-LTXVideo
- Resolution: 704x480 or 768x512
- Frames: 25 (must be 8n+1: 9, 17, 25, 33 ...)
- FPS: 24
- Steps: 8 (distilled model needs fewer steps)
- CFG: disabled (distilled does not use CFG)

Flow:
1. Load LTX-Video checkpoint via LTXVLoader node
2. Load positive prompt
3. Load negative prompt (optional)
4. Set frame count to 25
5. Sample
6. Export through Video Combine

### Workflow 2: Text to video (AnimateDiff SD1.5 — legacy)

Use only when you specifically need SD1.5 motion LoRA effects.

Suggested setup:
- Checkpoint: SD1.5
- Motion model: one AnimateDiff motion module
- Resolution: 512x768 or 576x768
- Frames: 16
- FPS: 8
- Steps: 20 to 24
- CFG: 6 to 7

Flow:
1. Load checkpoint
2. Load prompt and negative prompt
3. Attach AnimateDiff motion model
4. Sample 16 frames
5. Send frames to Video Combine
6. Export mp4

### Workflow 3: Image to video

Use when you want a poster, portrait, or product image to move slightly.

Suggested setup (LTX-Video):
- Start from a single still image in E:\AI\Assets\images
- Use LTX-Video image-to-video conditioning via ComfyUI-LTXVideo
- Frames: 25
- Steps: 8

Flow:
1. Load source image
2. Load LTX-Video model
3. Provide image as first-frame conditioning
4. Sample
5. Export through Video Combine

### Workflow 4: Video to video

Use when you want to stylize or re-render an existing clip.

Suggested setup:
- Put source clips in E:\AI\Assets\video_in
- Use Load Video from VideoHelperSuite
- Cap frames aggressively on first tests
- Process long clips in segments

Flow:
1. Load source video
2. Force frame rate to 24 if needed
3. Resize to a manageable resolution (704x480)
4. Apply LTX-Video or img2img chain
5. Export to E:\AI\Assets\video_out

## 3070 8 GB operating rules

- Use LTX-Video 2B distilled for all new video work
- Keep AnimateDiff only for motion LoRA experiments
- Keep batch size at 1
- LTX-Video: start at 25 frames (704x480), then scale up to 49 frames
- AnimateDiff: start at 16 frames before trying longer shots
- Raise duration only after a stable run
- If VRAM errors appear, lower resolution before lowering quality settings everywhere else
- Keep A1111 closed while running ComfyUI video jobs

## Suggested next model additions

- Juggernaut XL or RealVisXL for still images
- One clean SD1.5 checkpoint dedicated to video work
- A single AnimateDiff motion module first, not many at once
- One upscale model for final export passes

## Expected local workflow

1. Generate key stills in A1111
2. Save chosen source image to Assets/images or Assets/reference
3. Open ComfyUI for AnimateDiff or vid2vid
4. Export final clip to Assets/video_out
5. Save working workflow json to Projects/comfyui-workflows
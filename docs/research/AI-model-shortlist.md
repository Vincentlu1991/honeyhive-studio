# AI Model Shortlist for RTX 3070 8GB

This list is optimized for:
- Local Windows setup
- RTX 3070 8GB
- A1111 for still images
- ComfyUI for video generation

**2025–2026 update:** LTX-Video 2B replaces AnimateDiff as the primary video model.
AnimateDiff is kept as a secondary option for motion LoRA workflows only.

The goal is not to collect everything. The goal is to get one stable stack running first.

## Install in this order

1. One still-image SDXL checkpoint
2. LTX-Video 2B distilled checkpoint (primary video model)
3. One SD1.5 checkpoint (only if you want AnimateDiff motion LoRAs)
4. One AnimateDiff motion model (only if using the legacy SD1.5 path)
5. Optional upscale and ControlNet models

## Phase 1: Must-have models

### 1. SDXL Base 1.0

Use for:
- still-image generation
- prompt testing
- style exploration before moving to video

File:
- sd_xl_base_1.0.safetensors

Put in:
- E:\AI\Models\checkpoints

Why first:
- official baseline
- already wired into your setup script

### 2. LTX-Video 2B distilled (primary video model — replaces AnimateDiff)

Use for:
- text-to-video
- image-to-video
- video extension

File:
- ltxv-2b-0.9.8-distilled.safetensors (~3 GB)

Put in:
- E:\AI\Models\checkpoints

Why this first:
- fits in 8 GB VRAM
- 15x faster than non-distilled models
- native ComfyUI support via ComfyUI-LTXVideo plugin
- default resolution 704x480 at 24 FPS
- only 8 sampling steps needed
- far better motion quality than AnimateDiff SD1.5

VRAM requirement: ~6–8 GB at 704x480, 25 frames

ComfyUI plugin: https://github.com/Lightricks/ComfyUI-LTXVideo
HuggingFace model page: https://huggingface.co/Lightricks/LTX-Video

### 3. One SD1.5 checkpoint for video (legacy — optional)

Use for:
- AnimateDiff text-to-video
- image-to-video
- video-to-video

Put in:
- E:\AI\Models\checkpoints

What to pick:
- start with one clean SD1.5-style checkpoint that behaves predictably
- avoid starting with many highly stylized checkpoints

Rule:
- use LTX-Video 2B for all new video work
- use SD1.5 for legacy AnimateDiff motion LoRA experiments only
- use SDXL for still images first

### 4. AnimateDiff motion model (legacy — skip if using LTX-Video only)

Best first choice:
- mm_sd_v15_v2.ckpt

Other common choices:
- v3_sd15_mm.ckpt
- mm_sd_v15.ckpt

Put in:
- E:\AI\Models\animatediff_models

Recommendation:
- start with mm_sd_v15_v2.ckpt if you want the safest default first
- add v3_sd15_mm.ckpt later if you want to compare motion behavior

### 4. Motion LoRAs for camera movement

Best first picks:
- v2_lora_ZoomIn.ckpt
- v2_lora_ZoomOut.ckpt
- v2_lora_PanLeft.ckpt
- v2_lora_PanRight.ckpt

Put in:
- E:\AI\Models\animatediff_motion_lora

Why these first:
- easy to understand visually
- useful for product shots, portraits, and simple cinematic movement

## Phase 2: Strong next additions

### 5. RealVisXL or Juggernaut XL

Use for:
- higher quality still images
- more production-friendly prompt output than pure base SDXL

Put in:
- E:\AI\Models\checkpoints

Recommendation:
- choose one, not both, for the first round
- RealVisXL if you lean realistic
- Juggernaut XL if you want a more general all-rounder

### 6. One upscale model

Use for:
- final image cleanup
- frame upscaling after video render

Put in:
- E:\AI\Models\upscale_models

Recommendation:
- start with one RealESRGAN or ESRGAN family model only

### 7. One ControlNet set later

Use for:
- pose lock
- edge guidance
- stronger composition control

Put in:
- E:\AI\Models\controlnet

Recommendation:
- only add this after your first image and first short video both work

## Not recommended as first local video choice

### SDXL video stack

Examples:
- mm_sdxl_v10_beta.ckpt

Why not first:
- 3070 8GB can run into tighter VRAM limits quickly
- harder to get a clean first success than SD1.5 AnimateDiff

Use it later only after your SD1.5 video chain is stable.

## Practical starter pack

If you want the smallest useful pack, start with only these files:

1. sd_xl_base_1.0.safetensors
2. one SD1.5 checkpoint
3. mm_sd_v15_v2.ckpt
4. v2_lora_ZoomIn.ckpt
5. v2_lora_PanLeft.ckpt
6. one upscale model

## Folder map

- E:\AI\Models\checkpoints
  sd_xl_base_1.0.safetensors
  your_sd15_video_checkpoint.safetensors
  RealVisXL_or_JuggernautXL_optional.safetensors

- E:\AI\Models\animatediff_models
  mm_sd_v15_v2.ckpt
  v3_sd15_mm.ckpt optional

- E:\AI\Models\animatediff_motion_lora
  v2_lora_ZoomIn.ckpt
  v2_lora_ZoomOut.ckpt
  v2_lora_PanLeft.ckpt
  v2_lora_PanRight.ckpt

- E:\AI\Models\upscale_models
  one_upscaler_model_here

- E:\AI\Models\controlnet
  add later

## Recommended first tests

### Still image test

- checkpoint: sd_xl_base_1.0.safetensors
- resolution: 832x1216
- steps: 25
- cfg: 6.5
- batch size: 1

### First text-to-video test

- checkpoint: your SD1.5 checkpoint
- motion model: mm_sd_v15_v2.ckpt
- frames: 16
- fps: 8
- resolution: 512x768
- steps: 20 to 24
- cfg: 6 to 7
- no motion LoRA on the first run

### Second text-to-video test

- same as above
- add one motion LoRA such as ZoomIn or PanLeft

## Expansion rule

Do not add five new model families at once. Expand in this order:

1. Still image checkpoint
2. SD1.5 video checkpoint
3. One motion model
4. One motion LoRA
5. One upscale model
6. ControlNet
7. IPAdapter

That order gives you the highest chance of debugging one thing at a time.
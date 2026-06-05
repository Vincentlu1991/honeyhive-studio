# AI Download Links for RTX 3070 8GB

This file only lists links I could verify or trace directly from official model or release pages.

Use it as a practical download checklist.

**2025–2026 update:** LTX-Video 2B distilled is now the recommended video model.
It replaces the AnimateDiff SD1.5 stack for new video work.

## Download order

1. SDXL still-image base model
2. **LTX-Video 2B distilled** (primary video model — new)
3. One SD1.5 video checkpoint (legacy, optional)
4. One AnimateDiff motion model (legacy, optional)
5. One or two motion LoRAs (legacy, optional)
6. One upscaler model

## 1. SDXL Base 1.0

Use for:
- still images
- prompt testing

File:
- sd_xl_base_1.0.safetensors

Put in:
- E:\AI\Models\checkpoints

Official model page:
- https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0

Verified file page:
- https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/sd_xl_base_1.0.safetensors

Verified direct download:
- https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors

Verified SHA256:
- 31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b

## 2. LTX-Video 2B distilled (primary video model — 2025)

Use for:
- text-to-video
- image-to-video
- video extension up to 60 seconds

File:
- ltxv-2b-0.9.8-distilled.safetensors (~3 GB)

Put in:
- E:\AI\Models\checkpoints

Official model page:
- https://huggingface.co/Lightricks/LTX-Video

Verified direct download:
- https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled.safetensors

Download command (PowerShell):
```powershell
$url = 'https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled.safetensors'
$dest = 'E:\AI\Models\checkpoints\ltxv-2b-0.9.8-distilled.safetensors'
Invoke-WebRequest -Uri $url -OutFile $dest -Headers @{ "User-Agent" = "Mozilla/5.0" }
```

ComfyUI plugin needed:
- https://github.com/Lightricks/ComfyUI-LTXVideo
- Install via ComfyUI Manager: search "LTX-Video"

VRAM note:
- 704x480, 25 frames: fits in 8 GB
- 8 sampling steps (distilled — do NOT use 20+ steps)
- No CFG required (set cfg_scale = 1.0 or disable)

Also available (FP8 quantized, slightly less VRAM):
- https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled-fp8.safetensors

## 3. SD1.5 checkpoint for video (legacy — optional)

Use for:
- AnimateDiff text-to-video
- image-to-video
- video-to-video

Put in:
- E:\AI\Models\checkpoints

Important note:
- the official Stable Diffusion v1.5 page is a reference page, not necessarily the exact A1111-format safetensors file you will want to use locally
- for A1111 and ComfyUI video work, choose one SD1.5 checkpoint in safetensors or ckpt format from your preferred source

Practical rule:
- choose one clean SD1.5 checkpoint only for the first run
- do not download many SD1.5 checkpoints before the stack is working

**Recommended SD1.5 checkpoints for first video test (pick ONE):**

Option 1: Realistic Vision (popular, stable, good VRAM balance for 3070):
- https://huggingface.co/SG161222/Realistic_Vision_V5.1_noVAE/resolve/main/Realistic_Vision_V5.1_noVAE.safetensors
- File: Realistic_Vision_V5.1_noVAE.safetensors (3.3GB)
- Note: noVAE version uses shared VAE (smaller, faster)

Option 2: DreamShaper (good VRAM efficiency, consistent outputs):
- https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors
- File: DreamShaper_8_pruned.safetensors (3.7GB)
- Note: Pruned = optimized, no quality loss on 3070

Option 3: Official Stable Diffusion 1.5 (baseline reference):
- https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors
- File: v1-5-pruned-emaonly.safetensors (3.9GB)
- Note: Clean official base, good for testing AnimateDiff motion

**Download command (PowerShell, pick one link above):**
```powershell
$url = 'https://huggingface.co/SG161222/Realistic_Vision_V5.1_noVAE/resolve/main/Realistic_Vision_V5.1_noVAE.safetensors'
$dest = 'E:\AI\Models\checkpoints\Realistic_Vision_V5.1_noVAE.safetensors'
Invoke-WebRequest -Uri $url -OutFile $dest
```

**Verification:**
1. Run command above, wait for download to complete (~5-15 min depending on internet)
2. Open ComfyUI at http://127.0.0.1:8188
3. Click "Load Checkpoint" node in any workflow
4. You should now see the checkpoint filename in the dropdown
5. Select it - ready for video generation

## 3. AnimateDiff motion models

Put in:
- E:\AI\Models\animatediff_models

Official model collection page:
- https://huggingface.co/guoyww/animatediff/tree/cd71ae134a27ec6008b968d6419952b0c0494cf2

Recommended first motion model:
- mm_sd_v15_v2.ckpt
- file page: https://huggingface.co/guoyww/animatediff/blob/cd71ae134a27ec6008b968d6419952b0c0494cf2/mm_sd_v15_v2.ckpt
- direct download: https://huggingface.co/guoyww/animatediff/resolve/cd71ae134a27ec6008b968d6419952b0c0494cf2/mm_sd_v15_v2.ckpt?download=true

Good second comparison model:
- v3_sd15_mm.ckpt
- file page: https://huggingface.co/guoyww/animatediff/blob/cd71ae134a27ec6008b968d6419952b0c0494cf2/v3_sd15_mm.ckpt
- direct download: https://huggingface.co/guoyww/animatediff/resolve/cd71ae134a27ec6008b968d6419952b0c0494cf2/v3_sd15_mm.ckpt?download=true

Fallback older model:
- mm_sd_v15.ckpt
- file page: https://huggingface.co/guoyww/animatediff/blob/cd71ae134a27ec6008b968d6419952b0c0494cf2/mm_sd_v15.ckpt
- direct download: https://huggingface.co/guoyww/animatediff/resolve/cd71ae134a27ec6008b968d6419952b0c0494cf2/mm_sd_v15.ckpt?download=true

Not recommended for first local video test:
- mm_sdxl_v10_beta.ckpt
- file page: https://huggingface.co/guoyww/animatediff/blob/cd71ae134a27ec6008b968d6419952b0c0494cf2/mm_sdxl_v10_beta.ckpt

Reason:
- SDXL video is less forgiving on 8 GB VRAM than SD1.5 video

## 4. AnimateDiff motion LoRAs

Put in:
- E:\AI\Models\animatediff_motion_lora

These are the best first camera-style motion LoRAs to try:

Zoom In:
- file page: https://huggingface.co/guoyww/animatediff/blob/cd71ae134a27ec6008b968d6419952b0c0494cf2/v2_lora_ZoomIn.ckpt
- direct download: https://huggingface.co/guoyww/animatediff/resolve/cd71ae134a27ec6008b968d6419952b0c0494cf2/v2_lora_ZoomIn.ckpt?download=true

Zoom Out:
- file page: https://huggingface.co/guoyww/animatediff/blob/cd71ae134a27ec6008b968d6419952b0c0494cf2/v2_lora_ZoomOut.ckpt
- direct download: https://huggingface.co/guoyww/animatediff/resolve/cd71ae134a27ec6008b968d6419952b0c0494cf2/v2_lora_ZoomOut.ckpt?download=true

Pan Left:
- file page: https://huggingface.co/guoyww/animatediff/blob/cd71ae134a27ec6008b968d6419952b0c0494cf2/v2_lora_PanLeft.ckpt
- direct download: https://huggingface.co/guoyww/animatediff/resolve/cd71ae134a27ec6008b968d6419952b0c0494cf2/v2_lora_PanLeft.ckpt?download=true

Pan Right:
- file page: https://huggingface.co/guoyww/animatediff/blob/cd71ae134a27ec6008b968d6419952b0c0494cf2/v2_lora_PanRight.ckpt
- direct download: https://huggingface.co/guoyww/animatediff/resolve/cd71ae134a27ec6008b968d6419952b0c0494cf2/v2_lora_PanRight.ckpt?download=true

## 5. FP16 / safetensors AnimateDiff collection

Use for:
- alternate motion model source
- safetensors-based AnimateDiff assets

Collection page:
- https://huggingface.co/conrevo/AnimateDiff-A1111/tree/main

One notable file mentioned on the official collection page:
- mm_sd15_AnimateLCM.safetensors

Use note:
- this is useful after your basic AnimateDiff flow is already stable
- do not use this as your very first test unless you specifically want to try an LCM-style stack

## 6. Upscaler model

Put in:
- E:\AI\Models\upscale_models

Recommended official release page:
- https://github.com/xinntao/Real-ESRGAN/releases

Verified direct downloads from the official releases page:

General x4 model:
- https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth

Compact general x4 model:
- https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth

Anime/video-oriented x4 model:
- https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth

Recommendation:
- start with realesr-general-x4v3.pth for a lighter general-purpose option
- add the anime video model only if your content needs it

## Smallest practical starter pack

If you want the fastest route to first success, download only these first:

1. sd_xl_base_1.0.safetensors
2. one SD1.5 checkpoint from your preferred A1111-compatible source
3. mm_sd_v15_v2.ckpt
4. v2_lora_ZoomIn.ckpt
5. v2_lora_PanLeft.ckpt
6. realesr-general-x4v3.pth

## After downloading

1. Put each file into the folder listed above
2. Start A1111 and confirm SDXL loads
3. Start ComfyUI and confirm the AnimateDiff motion model is visible
4. Run the first text-to-video flow from ComfyUI-beginner-workflows.md

## Things I intentionally did not hard-code here

- A single exact SD1.5 checkpoint download link
- exact RealVisXL or Juggernaut XL links

Reason:
- those files move more often across providers and mirrors
- the best choice depends on whether you want realism, stylization, or easier licensing/login flow

If you want, the next step can be a second curated file just for:
- SD1.5 checkpoint candidates
- RealVisXL and Juggernaut XL candidate pages
- which one to choose for portrait, product, or short-video work
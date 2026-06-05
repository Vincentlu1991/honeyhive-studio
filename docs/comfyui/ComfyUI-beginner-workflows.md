# ComfyUI Beginner Workflows for RTX 3070 8GB

This guide is written for your local setup:
- ComfyUI portable on Windows
- LTX-Video plugin installed (ComfyUI-LTXVideo) — **primary video path**
- AnimateDiff Evolved installed — legacy/motion LoRA path
- VideoHelperSuite installed
- RTX 3070 8GB

**2025 update:** LTX-Video 2B distilled is now the recommended starting workflow.
AnimateDiff workflows are kept below as a secondary path for motion LoRA work only.

The goal is to get one successful render, then extend it.

## Before you start

Make sure you already have:
- ltxv-2b-0.9.8-distilled.safetensors in E:\AI\Models\checkpoints
- ComfyUI-LTXVideo plugin installed (via ComfyUI Manager)
- ffmpeg installed by the setup script

For your first video run, close A1111 so ComfyUI gets all available VRAM.

## Workflow 1: First text-to-video with LTX-Video (recommended)

Use this to confirm your LTX-Video stack works end to end.

### Prerequisites

Install ComfyUI-LTXVideo plugin via ComfyUI Manager (search "LTXVideo" by Lightricks).

### Node order

1. LTXVLoader (load the 2B distilled checkpoint)
2. CLIP Text Encode for positive prompt
3. CLIP Text Encode for negative prompt (optional)
4. LTXVSampler (or equivalent sampling node from the plugin)
5. VAE Decode
6. Video Combine

### How to set it up

LTXVLoader:
- ckpt_name: ltxv-2b-0.9.8-distilled.safetensors

Positive prompt:
- describe what you want to see moving
- be specific: describe subject, action, camera movement, lighting
- example: a woman walking slowly through a sunlit forest, cinematic, smooth camera push

Negative prompt:
- example: blurry, deformed, flickering, watermark (optional for distilled)

LTXVSampler settings:
- width: 704
- height: 480
- num_frames: 25 (must be 8n+1: 9, 17, 25, 33...)
- steps: 8 (distilled model — do NOT use 20+)
- cfg_scale: 1.0 (distilled does not use CFG)
- fps: 24
- seed: any fixed value for repeatability

Video Combine:
- frame_rate: 24
- output format: mp4
- filename_prefix: first-tests/ltxv-text2video

### First success criteria

You are done when:
- ComfyUI completes without VRAM failure
- Video Combine exports a playable mp4
- Motion looks natural (not jerky like AnimateDiff)

If it fails on VRAM:
- reduce num_frames to 17 first
- then reduce resolution to 512x384

---

## Workflow 2: First text-to-video with AnimateDiff (legacy SD1.5)

Use this only if you specifically need motion LoRA effects.

### Node order

1. Load Checkpoint
2. CLIP Text Encode for positive prompt
3. CLIP Text Encode for negative prompt
4. Empty Latent Image
5. AnimateDiff Loader or Apply AnimateDiff Model node
6. KSampler
7. VAE Decode
8. Video Combine

### How to set it up

Load Checkpoint:
- choose your SD1.5 checkpoint

Positive prompt:
- example: cinematic portrait, subtle motion, soft lighting, detailed face

Negative prompt:
- example: blurry, deformed, extra limbs, bad anatomy, watermark, text

Empty Latent Image:
- width: 512
- height: 768
- batch size or frames: 16

AnimateDiff:
- choose mm_sd_v15_v2.ckpt first
- do not add motion LoRA on the first attempt

KSampler:
- steps: 20 to 24
- cfg: 6 to 7
- sampler: DPM++ 2M Karras (sampler_name: dpmpp_2m, scheduler: karras)
- seed: any fixed value for repeatability

Video Combine:
- frame rate: 8
- output format: mp4 or webm
- filename prefix: first-tests/text2video

### First success criteria

You are done when:
- ComfyUI completes without VRAM failure
- frames decode correctly
- Video Combine exports a playable file

If it fails on VRAM:
- reduce resolution before changing everything else
- try 512x512
- keep frames at 16

## Workflow 3: Add a motion LoRA (AnimateDiff only)

Use this only after Workflow 1 succeeds.

### Extra node

Between AnimateDiff setup and sampling, add the motion LoRA path used by AnimateDiff Evolved.

### Good first motion LoRAs

- v2_lora_ZoomIn.ckpt
- v2_lora_PanLeft.ckpt

### What to expect

- ZoomIn: simple push-in effect
- PanLeft: obvious lateral camera movement

Keep the strength modest at first. The purpose is to see the effect clearly without breaking the shot.

## Workflow 4: First image-to-video with LTX-Video (recommended)

Use this when you have a single strong image and want it to come alive.

### Put source file here

- E:\AI\Assets\images

### Node order

1. Load Image
2. LTXVLoader
3. CLIP Text Encode positive
4. LTXVSampler (with image conditioning input)
5. VAE Decode
6. Video Combine

### Starting settings

- width: 704, height: 480, num_frames: 25
- steps: 8, cfg_scale: 1.0, fps: 24
- Describe what you want to happen to the image in the prompt
- example: the woman slowly turns her head, soft breeze moves her hair

---

## Workflow 5: First image-to-video with AnimateDiff (legacy)

Use this when you have a single strong image and want slight movement via SD1.5.

### Put source file here

- E:\AI\Assets\images

### Node order

1. Load Image
2. VAE Encode
3. Load Checkpoint
4. CLIP Text Encode positive
5. CLIP Text Encode negative
6. AnimateDiff Loader or Apply AnimateDiff Model node
7. KSampler
8. VAE Decode
9. Video Combine

### Starting settings

- resolution: keep close to source aspect ratio
- frames: 12 to 16
- fps: 8
- denoise: low to moderate
- motion model: mm_sd_v15_v2.ckpt

### Good subjects for first tests

- portraits
- product shots
- food shots
- static scenes with soft lighting

Avoid crowded scenes first. They break more easily.

## Workflow 4: First video-to-video

Use this after text-to-video and image-to-video both work.

### Put source file here

- E:\AI\Assets\video_in

### Node order

1. Load Video from VideoHelperSuite
2. Load Checkpoint
3. CLIP Text Encode positive
4. CLIP Text Encode negative
5. AnimateDiff or img2img chain
6. KSampler
7. VAE Decode
8. Video Combine

### Safe first settings

- force rate: 8
- frame cap: 16
- resize small enough to fit VRAM
- export to Assets/video_out

### Important rule

For long source clips, do not process everything at once.

Instead:
1. render one short chunk
2. confirm quality and memory usage
3. continue chunk by chunk

## Suggested prompt style for early video tests

Use prompts that are visually stable.

Good:
- cinematic portrait, subtle movement, natural light, detailed face
- product commercial shot, slow camera motion, studio lighting
- fashion editorial shot, soft motion, clean background

Less good for first tests:
- battle scene with multiple characters
- crowded street with complex motion
- fast action scenes

## Recommended progression

1. Text to video with no motion LoRA
2. Text to video with one motion LoRA
3. Image to video from one still image
4. Video to video from a short input clip
5. Only then add ControlNet or IPAdapter

## Common failure handling

### Out of memory

Fix in this order:
1. lower resolution
2. keep frames at 16
3. close A1111
4. remove extra add-ons from the graph

### Weird face drift

Try:
1. simpler prompt
2. fewer moving elements
3. shorter clip
4. image-to-video instead of pure text-to-video

### Export works but motion is weak

Try:
1. switch to another motion model
2. add one motion LoRA
3. adjust prompt toward clearer motion language

### Motion is too chaotic

Try:
1. remove motion LoRA
2. shorten the clip
3. simplify the scene

## Save discipline

After every successful graph:

1. save the workflow json to E:\AI\Projects\comfyui-workflows
2. export output video to E:\AI\Assets\video_out
3. note the checkpoint, motion model, resolution, frames, and seed in E:\AI\Projects\notes

That will save you a lot of time when you start iterating.
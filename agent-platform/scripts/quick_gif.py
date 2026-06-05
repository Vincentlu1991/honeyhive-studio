"""
Quick script to create GIF from latest AnimateDiff frames
"""
from pathlib import Path
from PIL import Image
import glob
import sys

# Find latest 16 frames
output_dir = Path("E:/AI/ComfyUI_windows_portable/ComfyUI/output")
all_frames = sorted(output_dir.glob("animatediff__*.png"))

if not all_frames:
    print("❌ No animatediff frames found")
    sys.exit(1)

# Get last 16 frames
latest_frames = all_frames[-16:]

print(f"📊 Found {len(all_frames)} total frames")
print(f"🎬 Using latest 16 frames:")
for f in latest_frames:
    print(f"   {f.name}")

# Load frames
frames = [Image.open(f) for f in latest_frames]

# Save as GIF
output_path = Path("E:/AI/outputs/latest_animation.gif")
output_path.parent.mkdir(parents=True, exist_ok=True)

frames[0].save(
    output_path,
    save_all=True,
    append_images=frames[1:],
    duration=125,  # 8 FPS
    loop=0,
    optimize=False
)

print(f"\n✅ GIF created: {output_path}")
print(f"   Size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
print(f"   Frames: {len(frames)}")
print(f"   Duration: {len(frames) * 0.125:.2f} seconds")

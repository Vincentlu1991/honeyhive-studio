"""
Create video/GIF from AnimateDiff frames
"""
import sys
from pathlib import Path
from PIL import Image
import glob

def create_gif(frame_pattern: str, output_path: str, fps: int = 8):
    """Create GIF from frame images"""
    frame_files = sorted(glob.glob(frame_pattern))
    
    if not frame_files:
        print(f"❌ No frames found matching: {frame_pattern}")
        return False
    
    print(f"📊 Found {len(frame_files)} frames")
    
    # Load all frames
    frames = []
    for i, frame_file in enumerate(frame_files):
        img = Image.open(frame_file)
        frames.append(img)
        print(f"  Frame {i+1}/{len(frame_files)}: {Path(frame_file).name}")
    
    # Calculate duration (ms per frame)
    duration = int(1000 / fps)
    
    # Save as GIF
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        optimize=False
    )
    
    print(f"\n✅ GIF created: {output}")
    print(f"   Size: {output.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"   Frames: {len(frames)}")
    print(f"   FPS: {fps}")
    
    return True

def create_video_mp4(frame_pattern: str, output_path: str, fps: int = 8):
    """Create MP4 video from frame images using moviepy"""
    try:
        from moviepy.editor import ImageSequenceClip
    except ImportError:
        print("⚠️  moviepy not installed. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "moviepy"])
        from moviepy.editor import ImageSequenceClip
    
    frame_files = sorted(glob.glob(frame_pattern))
    
    if not frame_files:
        print(f"❌ No frames found matching: {frame_pattern}")
        return False
    
    print(f"📊 Found {len(frame_files)} frames")
    
    # Create video
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    
    clip = ImageSequenceClip(frame_files, fps=fps)
    clip.write_videofile(str(output), codec='libx264', audio=False)
    
    print(f"\n✅ Video created: {output}")
    print(f"   Size: {output.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"   Frames: {len(frame_files)}")
    print(f"   FPS: {fps}")
    
    return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Create video/GIF from AnimateDiff frames")
    parser.add_argument("--frames", required=True, help="Frame pattern (e.g., 'output/animatediff__*.png')")
    parser.add_argument("--output", required=True, help="Output file path (.gif or .mp4)")
    parser.add_argument("--fps", type=int, default=8, help="Frames per second (default: 8)")
    parser.add_argument("--format", choices=["gif", "mp4", "auto"], default="auto", help="Output format")
    
    args = parser.parse_args()
    
    # Auto-detect format from extension
    output_ext = Path(args.output).suffix.lower()
    if args.format == "auto":
        if output_ext == ".gif":
            format_type = "gif"
        elif output_ext == ".mp4":
            format_type = "mp4"
        else:
            print("❌ Could not detect format from extension. Use --format")
            sys.exit(1)
    else:
        format_type = args.format
    
    # Create video/gif
    print(f"\n🎬 Creating {format_type.upper()} from frames...")
    print(f"   Pattern: {args.frames}")
    print(f"   Output: {args.output}")
    print(f"   FPS: {args.fps}\n")
    
    if format_type == "gif":
        success = create_gif(args.frames, args.output, args.fps)
    else:
        success = create_video_mp4(args.frames, args.output, args.fps)
    
    sys.exit(0 if success else 1)

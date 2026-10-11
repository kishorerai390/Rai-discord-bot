import os
import subprocess
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

BRANDING_DIR = r"f:\Bot\assets\branding"
ARTIFACTS_DIR = r"C:\Users\kishore\.gemini\antigravity-ide\brain\0d0ddc2c-5ce6-487b-8239-2a7443738eff"

BANNER_SRC = os.path.join(ARTIFACTS_DIR, "neko_songs_banner_1791724532547.jpg")
ICON_SRC = os.path.join(ARTIFACTS_DIR, "neko_songs_icon_1791724577688.jpg")
RAI_SRC = os.path.join(ARTIFACTS_DIR, ".user_uploaded", "media_1791723671684.png")

print("Processing static Discord specifications...")

# 1. Neko Songs Banner - exact 680x240 (17:6)
im_banner = Image.open(BANNER_SRC)
w, h = im_banner.size
target_ratio = 680 / 240 # ~ 2.833
# Crop center height to match 17:6
target_h = int(w / target_ratio)
if target_h <= h:
    top = (h - target_h) // 2
    im_banner_cropped = im_banner.crop((0, top, w, top + target_h))
else:
    target_w = int(h * target_ratio)
    left = (w - target_w) // 2
    im_banner_cropped = im_banner.crop((left, 0, left + target_w, h))

neko_banner_680 = im_banner_cropped.resize((680, 240), Image.Resampling.LANCZOS)
neko_banner_png = os.path.join(BRANDING_DIR, "neko_songs_banner_680x240.png")
neko_banner_680.save(neko_banner_png, "PNG", optimize=True)
print(f"Saved {neko_banner_png} ({neko_banner_680.size})")

# 2. Neko Songs Icon - exact 1024x1024 (1:1)
im_icon = Image.open(ICON_SRC)
neko_icon_1024 = im_icon.resize((1024, 1024), Image.Resampling.LANCZOS)
neko_icon_png = os.path.join(BRANDING_DIR, "neko_songs_icon_1024x1024.png")
neko_icon_1024.save(neko_icon_png, "PNG", optimize=True)
print(f"Saved {neko_icon_png} ({neko_icon_1024.size})")

# 3. RAI Banner & Icon from screenshot
im_rai = Image.open(RAI_SRC)
# Banner coordinates: (258, 185, 650, 323)
rai_banner_crop = im_rai.crop((258, 185, 650, 323))
rai_banner_680 = rai_banner_crop.resize((680, 240), Image.Resampling.LANCZOS)
rai_banner_png = os.path.join(BRANDING_DIR, "rai_banner_680x240.png")
rai_banner_680.save(rai_banner_png, "PNG", optimize=True)

# Icon coordinates: (268, 22, 387, 136)
rai_icon_crop = im_rai.crop((268, 22, 387, 136))
rai_icon_1024 = rai_icon_crop.resize((1024, 1024), Image.Resampling.LANCZOS)
rai_icon_png = os.path.join(BRANDING_DIR, "rai_icon_1024x1024.png")
rai_icon_1024.save(rai_icon_png, "PNG", optimize=True)
print(f"Saved RAI static assets ({rai_banner_png}, {rai_icon_png})")

# 4. Generate Animated Video Loops and Discord Animated GIFs using ffmpeg
def make_animated_assets(input_png, base_name, width, height, is_banner=True):
    video_out = os.path.join(BRANDING_DIR, f"{base_name}_video.mp4")
    gif_out = os.path.join(BRANDING_DIR, f"{base_name}_animated.gif")

    # Filter description:
    # 3 second loop, 30 fps (90 frames)
    # Pulsing brightness/glow cycle + subtle zoom motion
    # Uses sine wave expression for breathing pulsation
    filter_expr = (
        f"scale={width}:{height},"
        f"zoompan=z='1+0.03*sin(2*PI*it/3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=90:s={width}x{height}:fps=30,"
        f"eq=brightness='0.03*sin(2*PI*t/3)':contrast='1.05+0.05*cos(2*PI*t/3)':saturation='1.1+0.1*sin(2*PI*t/3)'"
    )

    # Generate MP4
    cmd_mp4 = [
        "ffmpeg", "-y", "-loop", "1", "-i", input_png,
        "-vf", filter_expr,
        "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        video_out
    ]
    subprocess.run(cmd_mp4, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(f"Generated {video_out}")

    # Generate GIF (< 10MB Discord Developer Portal limit)
    # Generate custom palette for optimal quality under 10MB
    palette_png = os.path.join(BRANDING_DIR, f"{base_name}_palette.png")
    cmd_palette = [
        "ffmpeg", "-y", "-i", video_out,
        "-vf", f"fps=20,scale={width}:{height}:flags=lanczos,palettegen=stats_mode=diff",
        palette_png
    ]
    subprocess.run(cmd_palette, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    cmd_gif = [
        "ffmpeg", "-y", "-i", video_out, "-i", palette_png,
        "-lavfi", f"fps=20,scale={width}:{height}:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=3",
        gif_out
    ]
    subprocess.run(cmd_gif, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if os.path.exists(palette_png):
        os.remove(palette_png)
    
    file_size_mb = os.path.getsize(gif_out) / (1024 * 1024)
    print(f"Generated {gif_out} ({file_size_mb:.2f} MB)")

print("\nGenerating Neko Songs Animated Banner...")
make_animated_assets(neko_banner_png, "neko_songs_banner", 680, 240, is_banner=True)

print("\nGenerating Neko Songs Animated App Icon...")
make_animated_assets(neko_icon_png, "neko_songs_icon", 1024, 1024, is_banner=False)

print("\nGenerating RAI Animated Banner...")
make_animated_assets(rai_banner_png, "rai_banner", 680, 240, is_banner=True)

print("\nGenerating RAI Animated Icon...")
make_animated_assets(rai_icon_png, "rai_icon", 1024, 1024, is_banner=False)

print("\nAll Discord qualified assets successfully generated!")

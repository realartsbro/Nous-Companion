"""Generate a preview animation from audio — saves frames and a contact sheet."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from compositor.cutout_compositor import CutoutCompositor
from compositor.audio_analyzer import AudioAnalyzer

CHAR_DIR = Path(__file__).resolve().parent.parent / "characters" / "default" / "campbell2"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "test_output"

# Pick the audio file
AUDIO_PATH = CHAR_DIR / "audio_test.wav"
if not AUDIO_PATH.exists():
    AUDIO_PATH = CHAR_DIR / "vc115902.wav"

print(f"Audio: {AUDIO_PATH.name}")

# Analyze
analyzer = AudioAnalyzer(AUDIO_PATH, fps=10)  # 10fps for preview
print(f"Duration: {analyzer.duration_s:.1f}s, {analyzer.total_frames} frames at 10fps")

# Composite
comp = CutoutCompositor(CHAR_DIR)

# Generate frames
frames = []
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for i in range(analyzer.total_frames):
    mouth_open = analyzer.get_mouth_open(i)

    # Map to mouth index
    if mouth_open < 0.2:
        mouth_idx = 0
    else:
        mouth_idx = 1

    img = comp.composite("normal", eye_index=0, mouth_index=mouth_idx)

    # Label the frame
    draw = ImageDraw.Draw(img)
    draw.text((1, 1), f"f{i:03d} m={mouth_open:.2f}", fill=(0, 255, 0, 255))

    frames.append(img)

# Save individual frames
for i, frame in enumerate(frames):
    frame.save(OUTPUT_DIR / f"preview_{i:03d}.png")

print(f"Saved {len(frames)} frames to {OUTPUT_DIR}/")

# Create contact sheet — 10 frames per row
cols = 10
rows = (len(frames) + cols - 1) // cols
w, h = frames[0].size
pad = 2
sheet_w = cols * (w + pad) + pad
sheet_h = rows * (h + pad) + pad

sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 255))
for i, frame in enumerate(frames):
    row = i // cols
    col = i % cols
    x = pad + col * (w + pad)
    y = pad + row * (h + pad)
    sheet.paste(frame, (x, y))

sheet_path = OUTPUT_DIR / "animation_preview.png"
sheet.save(sheet_path)
print(f"Contact sheet: {sheet_path} ({sheet_w}x{sheet_h})")

# Save as GIF
gif_path = OUTPUT_DIR / "animation_preview.gif"
frames[0].save(
    gif_path,
    save_all=True,
    append_images=frames[1:],
    duration=int(1000 / 10),  # 100ms per frame at 10fps
    loop=0,
)
print(f"GIF: {gif_path}")

# Print RMS profile
print(f"\nRMS profile (10fps):")
for i in range(min(30, analyzer.total_frames)):
    rms = analyzer.get_mouth_open(i)
    bar = "█" * int(rms * 20)
    mouth = "open" if rms >= 0.2 else "shut"
    print(f"  f{i:03d}: {rms:.3f} {bar} [{mouth}]")

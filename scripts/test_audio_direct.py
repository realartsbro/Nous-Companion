"""Test audio playback directly — no WebSocket needed."""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from compositor.cutout_compositor import CutoutCompositor
from compositor.audio_analyzer import AudioAnalyzer
from compositor.animation_controller import AnimationController

CHAR_DIR = Path(__file__).resolve().parent.parent / "characters" / "default" / "campbell2"
AUDIO = CHAR_DIR / "audio_test.wav"

print(f"Audio: {AUDIO} exists={AUDIO.exists()}")

# Test analyzer
analyzer = AudioAnalyzer(AUDIO, fps=30)
print(f"Duration: {analyzer.duration_s:.1f}s, frames: {analyzer.total_frames}")

# Test animation controller
comp = CutoutCompositor(CHAR_DIR)
anim = AnimationController(comp, fps=30)
anim.load_audio(AUDIO)
anim.start_audio()

print(f"\nSimulating 30 frames:")
for i in range(30):
    anim._update_mouth(anim.frame_interval)
    mouth_idx = anim._get_mouth_index()
    print(f"  frame {i}: mouth_open={anim.mouth_open:.3f} mouth_idx={mouth_idx} audio_frame={anim._audio_frame}")

print(f"\nAudio playing: {anim._audio_playing}")

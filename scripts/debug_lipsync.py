"""
Standalone lip-sync debugger.

Creates a synthetic WAV, feeds it through the entire animation pipeline,
and prints frame-by-frame mouth state. Does NOT require the WebSocket server.
"""
import sys, os
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import numpy as np
import wave
import struct
from compositor.cutout_compositor import CutoutCompositor
from compositor.animation_controller import AnimationController

CHAR_DIR = SRC.parent / "characters" / "default" / "campbell2"

# ─── Generate a synthetic 2-second WAV with speech-like bursts ───
sample_rate = 24000
duration = 2.0
n_samples = int(sample_rate * duration)

t = np.arange(n_samples) / sample_rate
# Simulate two speech bursts with silence gaps
signal = np.zeros(n_samples)
# Burst 1: 0.1s – 0.8s
burst1 = (t >= 0.1) & (t < 0.8)
signal[burst1] = 0.5 * np.sin(2 * np.pi * 200 * t[burst1])
# Burst 2: 1.0s – 1.7s
burst2 = (t >= 1.0) & (t < 1.7)
signal[burst2] = 0.4 * np.sin(2 * np.pi * 300 * t[burst2])

# Add some variation within bursts
signal[burst1] *= 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t[burst1])  # 4Hz amplitude modulation
signal[burst2] *= 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t[burst2])   # 3Hz amplitude modulation

# Convert to 16-bit PCM
signal_int16 = (signal * 32767).astype(np.int16)

wav_path = Path("/tmp/debug_sync.wav")
with wave.open(str(wav_path), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sample_rate)
    w.writeframes(signal_int16.tobytes())

print(f"[DEBUG] Generated test WAV: {duration}s, {sample_rate}Hz, 16-bit mono")
print(f"[DEBUG] WAV file: {wav_path} ({wav_path.stat().st_size} bytes)")

# ─── Load compositor and animation controller ───
comp = CutoutCompositor(CHAR_DIR)
anim = AnimationController(comp, fps=30)

print(f"\n[DEBUG] Expression groups: {list(comp.groups.keys())}")
for expr_name, group in comp.groups.items():
    print(f"  {expr_name}: base={group.base.size}, "
          f"eyes={len(group.eyes)}, mouths={len(group.mouths)}, "
          f"eye_offset={group.eye_offset}, mouth_offset={group.mouth_offset}")

# Load audio (this is what _do_synthesize_and_play does)
print(f"\n[DEBUG] Loading audio...")
anim.load_audio(str(wav_path))
print(f"[DEBUG] Audio loaded: {anim._audio.duration_s:.1f}s, {anim._audio.total_frames} frames")

# Simulate the renderer delay: wait a bit, then start_audio (as if playback_started arrived)
import time
SIMULATED_DELAY = 0.1  # 100ms — worst-case renderer decode + context resume
print(f"[DEBUG] Simulating renderer delay of {SIMULATED_DELAY*1000:.0f}ms...")
time.sleep(SIMULATED_DELAY)

# This is what playback_started handler calls
print(f"\n[DEBUG] Calling start_audio() — simulating playback_started arrival")
anim.start_audio()
print(f"[DEBUG] _audio_playing={anim._audio_playing}, _audio_start_time={anim._audio_start_time}")

# Simulate animation loop running at 30fps
print(f"\n[DEBUG] Simulating 90 frames (3 seconds) at 30fps:")
fps = 30
dt = 1.0 / fps
prev_idx = -2
for i in range(90):
    anim._update_mouth(dt)
    mouth_idx = anim._get_mouth_index()
    # Don't print every frame — just frames with state changes
    if i % 3 == 0 or mouth_idx != prev_idx:
        print(f"  frame {i:3d}: audio_frame={anim._audio_frame:3d} "
              f"mouth_open={anim.mouth_open:.3f} mouth_idx={mouth_idx:2d} "
              f"audio_playing={anim._audio_playing}")
    prev_idx = mouth_idx
    time.sleep(0.001)  # minimal delay to avoid busy-loop

print(f"\n[DEBUG] Final state: _audio_playing={anim._audio_playing}, "
      f"_audio_frame={anim._audio_frame}/{anim._audio.total_frames}")

# Cleanup
wav_path.unlink(missing_ok=True)

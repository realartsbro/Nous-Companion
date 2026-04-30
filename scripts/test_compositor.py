"""Smoke test for the cut-out compositor system.

Usage:
  python test_compositor.py [character_dir]
  
If no character_dir is provided, defaults to characters/default/campbell2.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from compositor.cutout_compositor import CutoutCompositor
from compositor.audio_analyzer import AudioAnalyzer
from compositor.animation_controller import AnimationController

# Default to Colonel Campbell, but accept command-line argument
if len(sys.argv) > 1:
    CHAR_DIR = Path(sys.argv[1])
else:
    CHAR_DIR = Path(__file__).resolve().parent.parent / "characters" / "default" / "campbell2"

print(f"Testing character: {CHAR_DIR}")

# Test compositor
comp = CutoutCompositor(CHAR_DIR)
print(f"Expression groups: {comp.expression_names}")

for name in comp.expression_names:
    eyes = comp.get_eye_count(name)
    mouths = comp.get_mouth_count(name)
    print(f"  {name}: {eyes} eye sprites, {mouths} mouth sprites")

# Test compositing
print("\nCompositing test frames...")
for expr in comp.expression_names:
    b64 = comp.composite_to_base64(expr, eye_index=0, mouth_index=0)
    print(f"  {expr}/closed: {len(b64)} chars base64")

# Test with mouth open
b64 = comp.composite_to_base64("normal", eye_index=0, mouth_index=1)
print(f"  normal/open:   {len(b64)} chars base64")

# Test animation controller
print("\nAnimation controller...")
anim = AnimationController(comp, fps=30)
anim.set_expression("normal")
print(f"  Expression: {anim.expression}")
print(f"  Default eye_index: {anim.eye_index} (should be -1 for no overlay)")
print(f"  Mouth index (closed): {anim._get_mouth_index()}")
anim.mouth_open = 0.5
print(f"  Mouth index (0.5):    {anim._get_mouth_index()}")
anim.mouth_open = 0.9
print(f"  Mouth index (0.9):    {anim._get_mouth_index()}")

# Test blink behavior
print("\nTesting blink behavior...")
eye_count = comp.get_eye_count("normal")
print(f"  Eye count for 'normal': {eye_count}")
if eye_count > 1:
    print("  Simulating blink sequence...")
    # Simulate a few frames of blinking
    for i in range(10):
        anim._update_eyes(1.0/30)  # 30fps
        print(f"    Frame {i}: eye_index={anim.eye_index}, phase={anim._blink_phase}")
else:
    print("  No blink sprites available (eye_index should stay at -1)")

# Generate a test frame
event = anim.build_event(event_type="test")
import json
data = json.loads(event)
print(f"\n  Frame event type: {data['type']}")
print(f"  Expression: {data['expression']}")
print(f"  Mouth open: {data['mouth_open']}")
print(f"  Frame data length: {len(data['frame'])} chars")

print("\nAll tests passed.")

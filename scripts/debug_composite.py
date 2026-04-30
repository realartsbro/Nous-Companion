"""
Composite a frame with mouth open and save as PNG for visual inspection.
"""
import sys, os
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from compositor.cutout_compositor import CutoutCompositor
from compositor.animation_controller import AnimationController

BASE = SRC.parent / "characters"

def debug_character(char_id, sprite_dir):
    print(f"\n{'='*60}")
    print(f"CHARACTER: {char_id} ({sprite_dir})")
    print(f"{'='*60}")
    
    char_path = BASE / char_id / sprite_dir
    comp = CutoutCompositor(char_path)
    
    for expr_name in comp.expression_names:
        if expr_name == "standalones":
            continue
        group = comp.groups.get(expr_name)
        if not group:
            continue
        
        print(f"\n  Expression: {expr_name}")
        print(f"    Base: {group.base.size}")
        print(f"    Eyes: {len(group.eyes)} sprites, offset={group.eye_offset}")
        print(f"    Mouths: {len(group.mouths)} sprites, offset={group.mouth_offset}")
        
        # List mouth sprite names
        if group.mouths:
            for i, (name, img) in enumerate(group.mouths):
                print(f"      Mouth[{i}]: {name}.png ({img.size[0]}x{img.size[1]})")
        
        # Composite frames: mouth closed (-1) and mouth open (0)
        if len(group.mouths) >= 1:
            # Closed
            closed = comp.composite(
                expression=expr_name,
                eye_index=-1,
                mouth_index=-1,
                sprite_index=0,
            )
            out_dir = Path("/tmp/debug_composite") / char_id
            out_dir.mkdir(parents=True, exist_ok=True)
            closed_path = out_dir / f"{expr_name}_closed.png"
            closed.save(str(closed_path))
            print(f"    Saved: {closed_path} ({closed.size[0]}x{closed.size[1]})")
            
            # Open mouth
            open_img = comp.composite(
                expression=expr_name,
                eye_index=-1,
                mouth_index=0,
                sprite_index=0,
            )
            open_path = out_dir / f"{expr_name}_open.png"
            open_img.save(str(open_path))
            print(f"    Saved: {open_path} ({open_img.size[0]}x{open_img.size[1]})")
            
            # Also composite with eyes for full look
            full = comp.composite(
                expression=expr_name,
                eye_index=0,
                mouth_index=0,
                sprite_index=0,
            )
            full_path = out_dir / f"{expr_name}_full.png"
            full.save(str(full_path))
            print(f"    Saved: {full_path} ({full.size[0]}x{full.size[1]})")
            
            # CHECK: are closed and open actually different?
            if closed.tobytes() == open_img.tobytes():
                print(f"    ⚠️  WARNING: closed and open images are IDENTICAL!")
            else:
                # Compute pixel difference
                import numpy as np
                c_arr = np.array(closed)
                o_arr = np.array(open_img)
                diff = np.sum(np.abs(c_arr.astype(int) - o_arr.astype(int)))
                print(f"    ✅ closed vs open differ by {diff} luminance units")

# ─── Debug each character ───
debug_character("default", "campbell2")
debug_character("nous", "nous")
debug_character("mei_ling", "mei_ling")

print(f"\n\nComposite images saved to /tmp/debug_composite/")
print("Open them to check if mouth sprites are visible in the open variants")

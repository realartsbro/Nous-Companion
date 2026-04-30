"""
Detect eye and mouth overlay offsets per expression group.

Strategy: Compare the base head with its "closed" eye and mouth sprites
to find where they should be placed. We try all plausible positions and
pick the one with the least error (pixel difference) in the overlap region.

Usage:
  python detect_offsets.py [character_dir]
  
If no character_dir is provided, defaults to characters/default/campbell2.
"""

import sys
from pathlib import Path
from PIL import Image
import numpy as np

# Default to Colonel Campbell, but accept command-line argument
if len(sys.argv) > 1:
    CHARACTER_DIR = Path(sys.argv[1])
else:
    CHARACTER_DIR = Path(__file__).resolve().parent.parent / "characters" / "default" / "campbell2"


def find_best_offset(base: np.ndarray, overlay: np.ndarray, search_region: tuple) -> tuple:
    """
    Find the (x, y) offset within search_region where the overlay
    best matches the base (lowest difference in non-transparent pixels).
    """
    bh, bw = base.shape[:2]
    oh, ow = overlay.shape[:2]
    x_start, x_end, y_start, y_end = search_region

    best_offset = (0, 0)
    best_error = float('inf')

    for y in range(y_start, min(y_end, bh - oh + 1)):
        for x in range(x_start, min(x_end, bw - ow + 1)):
            # Extract the region from base
            region = base[y:y+oh, x:x+ow]

            # Get the alpha mask of the overlay
            alpha = overlay[:, :, 3] > 0
            if alpha.sum() == 0:
                continue

            # Compare RGB where overlay is visible
            diff = np.abs(region[alpha, :3].astype(float) - overlay[alpha, :3].astype(float))
            error = diff.mean()

            if error < best_error:
                best_error = error
                best_offset = (x, y)

    return best_offset, best_error


def analyze_group(group_dir: Path):
    """Analyze one expression group to find eye and mouth offsets."""
    print(f"\n=== {group_dir.name} ===")

    # Load all sprites
    sprites = {}
    for png in sorted(group_dir.glob("*.png")):
        sprites[png.stem] = np.array(Image.open(png).convert("RGBA"))

    # Identify base head (largest), eyes (tall < 20px), mouth (square ~30-40px)
    items = [(name, arr.shape) for name, arr in sprites.items()]
    items.sort(key=lambda x: x[1][0] * x[1][1], reverse=True)

    base_name = items[0][0]
    base = sprites[base_name]
    print(f"  Base: {base_name} {base.shape}")

    # Find eye and mouth sprites
    eye_sprites = []
    mouth_sprites = []
    for name, arr in sprites.items():
        if name == base_name:
            continue
        h, w = arr.shape[:2]
        # Eyes: wide and short (height <= 20, width >= 30)
        if h <= 20 and w >= 30:
            eye_sprites.append((name, arr))
            print(f"  Eye: {name} {arr.shape}")
        # Mouths: smaller sprites that aren't eyes (any height, width <= 45)
        elif w <= 45 and h <= 20:
            mouth_sprites.append((name, arr))
            print(f"  Mouth: {name} {arr.shape}")
        # Also catch taller mouth sprites (like Colonel's 34x34)
        elif h >= 25 and w <= 45:
            mouth_sprites.append((name, arr))
            print(f"  Mouth: {name} {arr.shape}")

    # Find eye offset - search upper third of face
    bh, bw = base.shape[:2]
    if eye_sprites:
        eye_name, eye_arr = eye_sprites[0]
        offset, error = find_best_offset(
            base, eye_arr,
            search_region=(0, bw - eye_arr.shape[1], 5, bh // 3)
        )
        print(f"  Eye offset: ({offset[0]}, {offset[1]}) error={error:.1f}")

    # Find mouth offset - search lower half of face
    if mouth_sprites:
        mouth_name, mouth_arr = mouth_sprites[0]
        offset, error = find_best_offset(
            base, mouth_arr,
            search_region=(0, bw - mouth_arr.shape[1], bh // 3, bh - mouth_arr.shape[0])
        )
        print(f"  Mouth offset: ({offset[0]}, {offset[1]}) error={error:.1f}")


if __name__ == "__main__":
    print(f"Analyzing character: {CHARACTER_DIR}")
    for group_dir in sorted(CHARACTER_DIR.iterdir()):
        if group_dir.is_dir() and group_dir.name.startswith("_"):
            analyze_group(group_dir)

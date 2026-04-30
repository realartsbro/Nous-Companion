"""Test the sprite compositor with placeholder assets."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from compositor.sprite_compositor import SpriteCompositor

CHAR_DIR = Path(__file__).parent.parent / "characters" / "default"


def test_list_assets():
    comp = SpriteCompositor(CHAR_DIR)
    assets = comp.list_assets()
    print("=== Available Assets ===")
    for category, items in assets.items():
        print(f"  {category}: {items}")
    print()
    return assets


def test_composite_expressions():
    comp = SpriteCompositor(CHAR_DIR)

    expressions = [
        {"base_head": "neutral", "eyes": "open", "mouth": "smile"},
        {"base_head": "neutral", "eyes": "open", "mouth": "open_talk"},
        {"base_head": "neutral", "eyes": "wide", "mouth": "open_talk"},
        {"base_head": "thinking", "eyes": "closed", "mouth": "closed"},
        {"base_head": "thinking", "eyes": "looking_left", "mouth": "closed"},
    ]

    output_dir = Path(__file__).parent.parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    for i, expr in enumerate(expressions):
        img = comp.composite(**expr)
        name = f"{expr['base_head']}_{expr['eyes']}_{expr['mouth']}"
        path = output_dir / f"{name}.png"
        img.save(path)
        print(f"  [{i+1}] {name} -> {path.name} ({img.size})")

    print(f"\nAll {len(expressions)} expressions saved to {output_dir}/")


def test_base64_output():
    comp = SpriteCompositor(CHAR_DIR)
    b64 = comp.composite_to_base64("neutral", "open", "smile")
    print(f"\n=== Base64 Output ===")
    print(f"  Length: {len(b64)} chars")
    print(f"  Preview: {b64[:60]}...")


def test_missing_sprite():
    comp = SpriteCompositor(CHAR_DIR)
    try:
        comp.composite("neutral", "nonexistent", "closed")
        print("  ERROR: Should have raised FileNotFoundError")
    except FileNotFoundError as e:
        print(f"  Correctly caught missing sprite: {e}")


if __name__ == "__main__":
    print("Nous Companion — Sprite Compositor Test\n")
    test_list_assets()
    test_composite_expressions()
    test_base64_output()
    test_missing_sprite()
    print("\nAll tests passed.")

"""
Generate placeholder expression PNGs for testing the new character system.
Creates full composite PNGs (not layered) in the expressions/ directory.

Usage:
  python scripts/gen_expressions.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CHAR_DIR = Path(__file__).parent.parent / "characters" / "default"
EXPR_DIR = CHAR_DIR / "expressions"


def make_expression(
    name: str,
    face_color: tuple,
    eye_style: str = "open",
    mouth_style: str = "closed",
    size: tuple = (200, 200),
):
    """Create a full expression PNG (face + eyes + mouth in one image)."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Face
    draw.ellipse([20, 10, 180, 190], fill=face_color + (255,))
    draw.ellipse([20, 10, 180, 190], outline=(40, 40, 40, 255), width=2)

    eye_color = (60, 80, 120, 255)

    # Eyes
    if eye_style == "open":
        draw.ellipse([55, 50, 85, 72], fill=eye_color)
        draw.ellipse([115, 50, 145, 72], fill=eye_color)
        # Pupils
        draw.ellipse([65, 55, 75, 67], fill=(20, 20, 20, 255))
        draw.ellipse([125, 55, 135, 67], fill=(20, 20, 20, 255))
    elif eye_style == "closed":
        draw.line([(58, 60), (82, 60)], fill=eye_color, width=3)
        draw.line([(118, 60), (142, 60)], fill=eye_color, width=3)
    elif eye_style == "wide":
        draw.ellipse([52, 45, 88, 75], fill=eye_color)
        draw.ellipse([112, 45, 148, 75], fill=eye_color)
        draw.ellipse([63, 52, 77, 68], fill=(20, 20, 20, 255))
        draw.ellipse([123, 52, 137, 68], fill=(20, 20, 20, 255))
    elif eye_style == "looking_left":
        draw.ellipse([55, 50, 85, 72], fill=eye_color)
        draw.ellipse([115, 50, 145, 72], fill=eye_color)
        draw.ellipse([58, 55, 68, 67], fill=(20, 20, 20, 255))
        draw.ellipse([118, 55, 128, 67], fill=(20, 20, 20, 255))
    elif eye_style == "looking_right":
        draw.ellipse([55, 50, 85, 72], fill=eye_color)
        draw.ellipse([115, 50, 145, 72], fill=eye_color)
        draw.ellipse([72, 55, 82, 67], fill=(20, 20, 20, 255))
        draw.ellipse([132, 55, 142, 67], fill=(20, 20, 20, 255))

    mouth_color = (160, 80, 80, 255)

    # Mouth
    if mouth_style == "closed":
        draw.line([(80, 130), (120, 130)], fill=mouth_color, width=2)
    elif mouth_style == "open":
        draw.ellipse([85, 120, 115, 145], fill=mouth_color)
        draw.ellipse([85, 120, 115, 145], outline=(40, 40, 40, 255), width=1)
    elif mouth_style == "smile":
        draw.arc([80, 115, 120, 145], start=0, end=180, fill=mouth_color, width=2)
    elif mouth_style == "frown":
        draw.arc([80, 125, 120, 155], start=180, end=0, fill=mouth_color, width=2)
    elif mouth_style == "open_wide":
        draw.ellipse([75, 115, 125, 150], fill=mouth_color)
        draw.ellipse([75, 115, 125, 150], outline=(40, 40, 40, 255), width=1)

    path = EXPR_DIR / f"{name}.png"
    img.save(path)
    print(f"  Created {path.name} ({size[0]}x{size[1]})")


if __name__ == "__main__":
    EXPR_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating placeholder expression PNGs...\n")

    # Core expressions (always present)
    make_expression("neutral", (220, 180, 140), "open", "closed")
    make_expression("thinking", (200, 170, 130), "looking_left", "closed")
    make_expression("speaking", (220, 180, 140), "open", "open")

    # Emotional expressions
    make_expression("happy", (220, 190, 150), "open", "smile")
    make_expression("surprised", (220, 185, 145), "wide", "open_wide")
    make_expression("annoyed", (200, 170, 135), "closed", "frown")
    make_expression("curious", (215, 180, 140), "looking_right", "closed")
    make_expression("excited", (225, 195, 155), "wide", "open")

    print(f"\nDone. {len(list(EXPR_DIR.glob('*.png')))} expressions in {EXPR_DIR}/")
    print("\nDrop your real art in this directory to replace placeholders.")
    print("Filenames (without .png) become expression names.")

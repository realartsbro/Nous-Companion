"""Generate placeholder sprite assets for testing the compositor."""

from pathlib import Path
from PIL import Image, ImageDraw

CHAR_DIR = Path(__file__).parent.parent / "characters" / "default"


def make_base_head(name: str, face_color: tuple, size=(200, 200)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 10, 180, 190], fill=face_color + (255,))
    draw.ellipse([20, 10, 180, 190], outline=(40, 40, 40, 255), width=2)
    path = CHAR_DIR / "base_heads" / f"{name}.png"
    img.save(path)
    print(f"Created {path.name}")


def make_eye_sprite(name: str, color: tuple, style: str = "open", size=(60, 25)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if style == "open":
        draw.ellipse([2, 2, size[0] - 2, size[1] - 2], fill=color + (255,))
        draw.ellipse([2, 2, size[0] - 2, size[1] - 2], outline=(40, 40, 40, 255), width=1)
    elif style == "closed":
        draw.line(
            [(5, size[1] // 2), (size[0] - 5, size[1] // 2)],
            fill=color + (255,),
            width=3,
        )
    elif style == "wide":
        draw.ellipse([1, 1, size[0] - 1, size[1] - 1], fill=color + (255,))
        draw.ellipse(
            [1, 1, size[0] - 1, size[1] - 1], outline=(40, 40, 40, 255), width=2
        )
        draw.ellipse(
            [size[0] // 2 - 5, size[1] // 2 - 5, size[0] // 2 + 5, size[1] // 2 + 5],
            fill=(20, 20, 20, 255),
        )
    path = CHAR_DIR / "eyes" / f"{name}.png"
    img.save(path)
    print(f"Created {path.name}")


def make_mouth_sprite(name: str, color: tuple, style: str = "closed", size=(40, 20)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if style == "closed":
        draw.line(
            [(5, size[1] // 2), (size[0] - 5, size[1] // 2)],
            fill=color + (255,),
            width=2,
        )
    elif style == "open":
        draw.ellipse([3, 2, size[0] - 3, size[1] - 2], fill=color + (255,))
        draw.ellipse(
            [3, 2, size[0] - 3, size[1] - 2], outline=(40, 40, 40, 255), width=1
        )
    elif style == "smile":
        draw.arc(
            [5, 0, size[0] - 5, size[1]],
            start=0,
            end=180,
            fill=color + (255,),
            width=2,
        )
    path = CHAR_DIR / "mouths" / f"{name}.png"
    img.save(path)
    print(f"Created {path.name}")


if __name__ == "__main__":
    # Base heads
    make_base_head("neutral", (220, 180, 140))
    make_base_head("thinking", (200, 170, 130))

    # Eyes
    make_eye_sprite("open", (60, 80, 120))
    make_eye_sprite("closed", (60, 80, 120), style="closed")
    make_eye_sprite("wide", (60, 80, 120), style="wide")
    make_eye_sprite("looking_left", (60, 80, 120))
    make_eye_sprite("looking_right", (60, 80, 120))

    # Mouths
    make_mouth_sprite("closed", (160, 80, 80))
    make_mouth_sprite("open_talk", (160, 80, 80), style="open")
    make_mouth_sprite("smile", (160, 80, 80), style="smile")

    print("\nAll placeholder assets created.")

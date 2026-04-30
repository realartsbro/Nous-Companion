"""Check sprite dimensions and generate a contact sheet for campbell2."""
from pathlib import Path
from PIL import Image

CAMPBELL2 = Path(__file__).resolve().parent.parent / "characters" / "default" / "campbell2"

for subdir in sorted(CAMPBELL2.iterdir()):
    if not subdir.is_dir():
        continue
    print(f"\n=== {subdir.name} ===")
    for png in sorted(subdir.glob("*.png")):
        img = Image.open(png)
        print(f"  {png.name}: {img.size} {img.mode}")

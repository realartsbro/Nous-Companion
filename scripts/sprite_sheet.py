"""Generate a contact sheet of all Campbell sprites for review."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CAMPBELL_DIR = Path(__file__).resolve().parent.parent / "characters" / "default" / "campbell"
OUTPUT = Path(__file__).resolve().parent.parent / "test_output" / "sprite_sheet.png"

# Collect all sprites
sprites = {}
for f in sorted(CAMPBELL_DIR.glob("sprite-*.png")):
    name = f.stem  # e.g. "sprite-1-1"
    sprites[name] = Image.open(f).convert("RGBA")

if not sprites:
    print("No sprites found!")
    sys.exit(1)

# Get dimensions from first sprite
sample = list(sprites.values())[0]
cell_w, cell_h = sample.size
print(f"Sprite size: {cell_w}x{cell_h}")
print(f"Total sprites: {len(sprites)}")

# Grid layout: 6 columns, as many rows as needed
cols = 6
rows = (len(sprites) + cols - 1) // cols

# Padding and label space
pad = 4
label_h = 16
grid_w = cols * (cell_w + pad) + pad
grid_h = rows * (cell_h + label_h + pad) + pad

sheet = Image.new("RGBA", (grid_w, grid_h), (0, 0, 0, 255))
draw = ImageDraw.Draw(sheet)

# Place sprites in order
sorted_names = sorted(sprites.keys())
for i, name in enumerate(sorted_names):
    row = i // cols
    col = i % cols
    x = pad + col * (cell_w + pad)
    y = pad + row * (cell_h + label_h + pad)
    
    # Paste sprite
    sheet.paste(sprites[name], (x, y))
    
    # Label
    label = name.replace("sprite-", "")
    draw.text((x + 2, y + cell_h + 1), label, fill=(0, 255, 0, 255))

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
sheet.save(OUTPUT)
print(f"Saved contact sheet: {OUTPUT} ({grid_w}x{grid_h})")

# Print layout summary
for i, name in enumerate(sorted_names):
    row = i // cols
    col = i % cols
    if col == 0:
        print(f"\nRow {row + 1}:", end=" ")
    print(f"{name.replace('sprite-', '')}", end="  ")
print()

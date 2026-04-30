#!/usr/bin/env python3
"""Generate placeholder icons for Tauri app"""
from PIL import Image, ImageDraw

sizes = {
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
    "icon.ico": 256,
    "icon.icns": 1024,
}

def create_icon(size, filename):
    """Create a simple green square icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw a green square with border
    margin = size // 8
    draw.rectangle(
        [margin, margin, size - margin, size - margin],
        fill=(122, 170, 150, 255),
        outline=(205, 205, 205, 255),
        width=max(1, size // 32)
    )
    
    if filename.endswith(".ico"):
        img.save(filename, sizes=[(32, 32), (64, 64), (128, 128), (256, 256)])
    elif filename.endswith(".icns"):
        img.save(filename, format="ICNS")
    else:
        img.save(filename)
    print(f"Created {filename}")

if __name__ == "__main__":
    for filename, size in sizes.items():
        create_icon(size, filename)

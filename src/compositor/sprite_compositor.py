"""
Nous Companion — Sprite Compositor

Layers base head + eye sprite + mouth sprite at defined offsets.
Handles alpha compositing for transparent PNG layers.
"""

from pathlib import Path
from PIL import Image
import json
import logging

logger = logging.getLogger(__name__)


class SpriteCompositor:
    """Composites layered character sprites (base head + eyes + mouth)."""

    def __init__(self, character_dir: str | Path):
        self.character_dir = Path(character_dir)
        self.base_heads_dir = self.character_dir / "base_heads"
        self.eyes_dir = self.character_dir / "eyes"
        self.mouths_dir = self.character_dir / "mouths"

        # Load positions (offsets per base head)
        positions_path = self.character_dir / "positions.json"
        if not positions_path.exists():
            raise FileNotFoundError(f"No positions.json found at {positions_path}")
        with open(positions_path) as f:
            self.positions = json.load(f)

        # Cache loaded images
        self._cache: dict[str, Image.Image] = {}

        # Validate asset directories
        for d in [self.base_heads_dir, self.eyes_dir, self.mouths_dir]:
            if not d.exists():
                raise FileNotFoundError(f"Asset directory not found: {d}")

    def _load_image(self, path: Path) -> Image.Image:
        """Load a PNG with alpha, cache for reuse."""
        key = str(path)
        if key not in self._cache:
            if not path.exists():
                raise FileNotFoundError(f"Sprite not found: {path}")
            self._cache[key] = Image.open(path).convert("RGBA")
            logger.debug(f"Loaded sprite: {path.name}")
        return self._cache[key]

    def _find_sprite(self, directory: Path, name: str) -> Path:
        """Find a sprite by name in a directory. Matches with or without .png extension."""
        # Try exact match first
        for ext in ["", ".png", ".PNG"]:
            candidate = directory / f"{name}{ext}" if not name.endswith(".png") else directory / name
            if candidate.exists():
                return candidate

        # Fuzzy: find any file containing the name
        for f in directory.iterdir():
            if f.suffix.lower() == ".png" and name.lower() in f.stem.lower():
                return f

        raise FileNotFoundError(
            f"No sprite matching '{name}' in {directory}. "
            f"Available: {[f.stem for f in directory.iterdir() if f.suffix.lower() == '.png']}"
        )

    def list_assets(self) -> dict:
        """List all available sprites grouped by type."""
        def png_stems(directory: Path) -> list[str]:
            if not directory.exists():
                return []
            return sorted([f.stem for f in directory.iterdir() if f.suffix.lower() == ".png"])

        return {
            "base_heads": png_stems(self.base_heads_dir),
            "eyes": png_stems(self.eyes_dir),
            "mouths": png_stems(self.mouths_dir),
            "positions": list(self.positions.keys()),
        }

    def composite(
        self,
        base_head: str = "neutral",
        eyes: str | None = None,
        mouth: str | None = None,
    ) -> Image.Image:
        """
        Composite a character expression from layered sprites.

        Args:
            base_head: Name of the base head image (without .png)
            eyes: Name of the eye sprite (without .png). None = no eye layer.
            mouth: Name of the mouth sprite (without .png). None = no mouth layer.

        Returns:
            PIL Image with all layers composited.
        """
        # Load base head
        head_path = self._find_sprite(self.base_heads_dir, base_head)
        canvas = self._load_image(head_path).copy()

        # Get offsets for this base head
        if base_head not in self.positions:
            raise ValueError(
                f"No positions defined for base head '{base_head}'. "
                f"Available: {list(self.positions.keys())}"
            )
        offsets = self.positions[base_head]

        # Composite eye layer
        if eyes:
            eye_path = self._find_sprite(self.eyes_dir, eyes)
            eye_img = self._load_image(eye_path)
            offset = tuple(offsets.get("eyes_offset", [0, 0]))
            canvas.paste(eye_img, offset, eye_img)

        # Composite mouth layer
        if mouth:
            mouth_path = self._find_sprite(self.mouths_dir, mouth)
            mouth_img = self._load_image(mouth_path)
            offset = tuple(offsets.get("mouth_offset", [0, 0]))
            canvas.paste(mouth_img, offset, mouth_img)

        return canvas

    def composite_to_bytes(
        self,
        base_head: str = "neutral",
        eyes: str | None = None,
        mouth: str | None = None,
        format: str = "PNG",
    ) -> bytes:
        """Composite and return raw image bytes (for sending over WebSocket)."""
        import io
        img = self.composite(base_head, eyes, mouth)
        buf = io.BytesIO()
        img.save(buf, format=format)
        return buf.getvalue()

    def composite_to_base64(
        self,
        base_head: str = "neutral",
        eyes: str | None = None,
        mouth: str | None = None,
    ) -> str:
        """Composite and return base64-encoded PNG string (for JSON/web)."""
        import base64
        return base64.b64encode(self.composite_to_bytes(base_head, eyes, mouth)).decode()

    def clear_cache(self):
        """Clear the image cache (e.g. after asset changes)."""
        self._cache.clear()
        logger.debug("Image cache cleared")

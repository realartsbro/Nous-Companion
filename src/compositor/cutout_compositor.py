"""
Nous Companion — Cut-out Compositor

Composites a character from layered sprites:
  base head + eye overlay + mouth overlay

Each expression group has its own base, eye sprites, and mouth sprites
with pre-detected offsets.
"""

import io
import base64
import logging
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Maximum sprite dimension (longest edge) — sprites larger than this are
# downscaled at load time. 200px gives retina-quality headroom for the
# 187×267 display size while keeping compositing fast.
MAX_SPRITE_DIMENSION = 200


def _downsize_if_needed(img: Image.Image) -> Image.Image:
    """Downscale images that are comically oversized for compositing performance."""
    w, h = img.size
    max_dim = max(w, h)
    if max_dim <= MAX_SPRITE_DIMENSION:
        return img
    ratio = MAX_SPRITE_DIMENSION / max_dim
    new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
    logger.info(f"Downsizing sprite from {w}×{h} to {new_size[0]}×{new_size[1]}")
    return img.resize(new_size, Image.Resampling.LANCZOS)


# Default offsets per expression group (auto-detected)
DEFAULT_OFFSETS = {
    "_normal":           {"eyes": (4, 23),  "mouth": (10, 34)},
    "_serious":          {"eyes": (4, 23),  "mouth": (10, 34)},
    "_smiling":          {"eyes": (4, 23),  "mouth": (10, 34)},
    "_looking_down":     {"eyes": (2, 23),  "mouth": (10, 38)},
    "_serious_shouting": {"eyes": (4, 23),  "mouth": (6, 34)},
}


def _clean_alpha(img: Image.Image, threshold: int = 15) -> Image.Image:
    """
    Clean up alpha channel: remove faint artifacts and black-matted fringe edges.

    Two-pass cleanup:
      1. Zero out pixels below alpha threshold (compression artifacts).
      2. Remove dark-matted fringe: semi-transparent pixels that are unnaturally
         dark (indicating they were exported against a black background).
    """
    if img.mode != "RGBA":
        return img
    arr = np.array(img)
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    brightness = np.maximum(np.maximum(r, g), b)

    # Pass 1: faint artifacts
    faint = a < threshold
    arr[faint] = [0, 0, 0, 0]

    # Pass 2: black-matted fringe — semi-transparent AND very dark
    # These pixels create visible dark outlines when composited.
    fringe = (a >= threshold) & (a < 80) & (brightness < 45)
    arr[fringe] = [0, 0, 0, 0]

    return Image.fromarray(arr, "RGBA")


def _alpha_composite_at_offset(
    base: Image.Image, overlay: Image.Image, offset: tuple[int, int],
    temp: Image.Image | None = None
) -> Image.Image:
    """
    Composite `overlay` onto `base` at `offset` using proper alpha blending.
    If `temp` is provided, reuses it instead of allocating a new image.
    """
    if temp is None:
        temp = Image.new("RGBA", base.size, (0, 0, 0, 0))
    else:
        # Clear temp to transparent
        temp.paste((0, 0, 0, 0), (0, 0, temp.width, temp.height))
    temp.paste(overlay, offset)
    return Image.alpha_composite(base, temp)


class ExpressionGroup:
    """One expression group: base head + eye sprites + mouth sprites."""

    def __init__(self, group_dir: Path, offsets: dict | None = None, sprite_order: dict | None = None):
        self.name = group_dir.name.lstrip("_")
        self.dir = group_dir
        self.is_standalone = (group_dir.name == "_standalones")

        # Load all sprites, downsize if needed, and classify by size
        raw_sprites = {}
        for png in sorted(group_dir.glob("*.png")):
            img = Image.open(png).convert("RGBA")
            raw_sprites[png.stem] = img

        # Detect if any sprite is oversized and compute downscale ratio
        self._downscale_ratio = 1.0
        for name, img in raw_sprites.items():
            max_dim = max(img.size)
            if max_dim > MAX_SPRITE_DIMENSION:
                ratio = MAX_SPRITE_DIMENSION / max_dim
                if ratio < self._downscale_ratio:
                    self._downscale_ratio = ratio

        # Apply downsizing uniformly so all sprites stay proportional
        sprites = {}
        if self._downscale_ratio < 1.0:
            for name, img in raw_sprites.items():
                new_size = (
                    max(1, int(img.width * self._downscale_ratio)),
                    max(1, int(img.height * self._downscale_ratio)),
                )
                sprites[name] = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(
                f"ExpressionGroup '{group_dir.name}': downscaled all sprites by "
                f"{self._downscale_ratio:.2f}x"
            )
        else:
            sprites = raw_sprites

        # Sort by area to identify base (largest), eyes (wide+short), mouth (square)
        by_size = sorted(sprites.items(), key=lambda x: x[1].size[0] * x[1].size[1], reverse=True)

        if not by_size:
            raise ValueError(
                f"Expression group '{group_dir.name}' in {group_dir.parent.name} has no PNG sprites"
            )

        self.base: Image.Image = by_size[0][1]
        self.base_name: str = by_size[0][0]

        # Check for explicit base filename in sprite_order — overrides auto-detection
        group_key = group_dir.name  # e.g. "_normal"
        if sprite_order and group_key in sprite_order and "base" in sprite_order[group_key]:
            explicit_base = sprite_order[group_key]["base"]
            base_stem = Path(str(explicit_base)).stem
            for name, img in by_size:
                if Path(name).stem == base_stem:
                    self.base = img
                    self.base_name = name
                    logger.info(
                        f"ExpressionGroup '{group_dir.name}': explicit base override → {name}"
                    )
                    break

        # Ensure base is fully opaque — fixes shadow artifacts from semi-transparent exports
        if self.base.mode == "RGBA":
            r, g, b, a = self.base.split()
            a = a.point(lambda x: 255 if x > 0 else 0)
            self.base = Image.merge("RGBA", (r, g, b, a))

        self.eyes: list[tuple[str, Image.Image]] = []
        self.mouths: list[tuple[str, Image.Image]] = []
        self.unclassified: list[tuple[str, Image.Image]] = []

        # For standalones, store all images as bases
        if self.is_standalone:
            self.standalone_bases: list[tuple[str, Image.Image]] = by_size.copy()
        else:
            self.standalone_bases = []

        for name, img in by_size:
            # Skip sprites already claimed as the explicit base (e.g. sprite-base.png)
            if name == self.base_name:
                continue
            w, h = img.size
            name_lower = name.lower()

            # Filename-based hints take priority — allows full-size transparent overlays
            # (e.g. normal_eyes_half.png, mouth_open.png)
            if "eye" in name_lower and "mouth" not in name_lower:
                self.eyes.append((name, img))
                continue
            if "mouth" in name_lower:
                self.mouths.append((name, img))
                continue

            # Eyes: wide and short (height <= 20, width >= 30)
            if h <= 20 and w >= 30:
                self.eyes.append((name, img))
            # Mouths: smaller sprites that aren't eyes (any height, width <= 45)
            elif w <= 45 and h <= 20:
                self.mouths.append((name, img))
            # Also catch taller mouth sprites (like Colonel's 34x34)
            elif h >= 25 and w <= 45:
                self.mouths.append((name, img))
            else:
                # Fallback: classify by aspect ratio so user sprites always work
                if w > h * 1.2:
                    self.eyes.append((name, img))
                else:
                    self.mouths.append((name, img))

        # Move any sprites that ended up in neither eyes nor mouths to unclassified
        # (shouldn't happen with fallback, but keeps tracking consistent)
        classified_names = {self.base_name}
        for n, _ in self.eyes:
            classified_names.add(n)
        for n, _ in self.mouths:
            classified_names.add(n)
        for n, _ in self.standalone_bases:
            classified_names.add(n)
        for name, img in sprites.items():
            if name not in classified_names:
                self.unclassified.append((name, img))

        # Apply user-defined sprite order if provided (overrides auto-classification order)
        group_key = group_dir.name  # e.g. "_normal"
        if sprite_order and group_key in sprite_order:
            order_cfg = sprite_order[group_key]
            print(f"[EXPR] Applying sprite_order for {group_key}: {order_cfg}", flush=True)
            # Reorder eyes: open → closed (index 0 = open, higher = more closed)
            if "eyes" in order_cfg:
                eye_map = {name: img for name, img in self.eyes}
                ordered = []
                for fname in order_cfg["eyes"]:
                    stem = Path(str(fname)).stem
                    if stem in eye_map:
                        ordered.append((stem, eye_map.pop(stem)))
                # Append any remaining auto-detected eyes at the end
                ordered.extend(eye_map.items())
                self.eyes = ordered
            # Reorder mouths: closed → open (index 0 = closed, higher = more open)
            if "mouths" in order_cfg:
                mouth_map = {name: img for name, img in self.mouths}
                ordered = []
                for fname in order_cfg["mouths"]:
                    stem = Path(str(fname)).stem
                    if stem in mouth_map:
                        ordered.append((stem, mouth_map.pop(stem)))
                ordered.extend(mouth_map.items())
                self.mouths = ordered
            print(f"[EXPR] After ordering: eyes={[n for n,_ in self.eyes]}, mouths={[n for n,_ in self.mouths]}", flush=True)
        else:
            print(f"[EXPR] No sprite_order for {group_key}. Available keys: {list(sprite_order.keys()) if sprite_order else 'none'}", flush=True)

        # Offsets — use provided or defaults, then scale by downscale ratio
        default = DEFAULT_OFFSETS.get(group_key, DEFAULT_OFFSETS["_normal"])
        raw_eye_off = (offsets or {}).get("eyes", default["eyes"])
        raw_mouth_off = (offsets or {}).get("mouth", default["mouth"])
        self.eye_offset = (
            int(raw_eye_off[0] * self._downscale_ratio),
            int(raw_eye_off[1] * self._downscale_ratio),
        )
        self.mouth_offset = (
            int(raw_mouth_off[0] * self._downscale_ratio),
            int(raw_mouth_off[1] * self._downscale_ratio),
        )

        # Reusable temp canvas for compositing (avoids allocating every frame)
        self._temp_canvas: Image.Image = Image.new("RGBA", self.base.size, (0, 0, 0, 0))

        logger.debug(
            f"ExpressionGroup '{self.name}': base={self.base.size}, "
            f"eyes={len(self.eyes)}, mouths={len(self.mouths)}, unclassified={len(self.unclassified)}, "
            f"eye_offset={self.eye_offset}, mouth_offset={self.mouth_offset}, "
            f"is_standalone={self.is_standalone}, "
            f"standalone_bases={len(self.standalone_bases)}"
        )


class CutoutCompositor:
    """Composites character from cut-out layers."""

    def __init__(self, character_dir: str | Path, character_offsets: dict | None = None, sprite_order: dict | None = None):
        self.character_dir = Path(character_dir)

        # Find campbell2 directory (or any sprite directory)
        sprite_dirs = [
            d for d in self.character_dir.iterdir()
            if d.is_dir() and d.name.startswith("_")
        ]

        if not sprite_dirs:
            raise FileNotFoundError(
                f"No expression group directories (starting with _) found in {self.character_dir}"
            )

        # Load all expression groups
        self.groups: dict[str, ExpressionGroup] = {}
        for d in sorted(sprite_dirs):
            group_name = d.name  # e.g. "_normal"
            group_offsets = (character_offsets or {}).get(group_name, {})
            try:
                group = ExpressionGroup(d, offsets=group_offsets, sprite_order=sprite_order)
                self.groups[group.name] = group
            except ValueError as e:
                logger.warning(str(e))

        if not self.groups:
            raise FileNotFoundError(
                f"No valid expression groups found in {self.character_dir}"
            )

        logger.info(
            f"CutoutCompositor loaded {len(self.groups)} expression groups: "
            f"{list(self.groups.keys())}"
        )

        # Cache encoded frames by visible state. Lip-sync reuses a small number
        # of eye/mouth combinations, so this avoids rebuilding identical PNGs.
        self._frame_cache: dict[tuple[str, int, int, int], str] = {}

    @property
    def expression_names(self) -> list[str]:
        return list(self.groups.keys())

    @property
    def frame_size(self) -> tuple[int, int]:
        """Return the canonical composited frame size (width, height) from the first expression group."""
        if not self.groups:
            return (52, 89)
        first = next(iter(self.groups.values()))
        return (first.base.width, first.base.height)

    def get_display_expressions(self) -> list[dict]:
        """Return expression list with standalone sprites expanded as individual entries."""
        expressions = []
        for name, group in self.groups.items():
            if name == "standalones":
                # Each base image in standalones is a separate expression
                # The group loads one as base — list them by index
                standalone_dir = group.dir
                pngs = sorted(standalone_dir.glob("*.png"))
                for i, png in enumerate(pngs):
                    expressions.append({
                        "name": f"standalone_{i+1}",
                        "group": "standalones",
                        "sprite_index": i,
                        "label": png.stem.replace("sprite-", "").replace("-", "/"),
                    })
            else:
                expressions.append({
                    "name": name,
                    "group": name,
                    "sprite_index": 0,
                    "label": name.replace("_", " "),
                })
        return expressions

    def composite(
        self,
        expression: str = "normal",
        eye_index: int = 0,
        mouth_index: int = -1,
        sprite_index: int = 0,
    ) -> Image.Image:
        """
        Composite a character frame.

        Args:
            expression: expression group name (e.g. "normal", "serious", "standalones")
            eye_index: index into the eye sprites (0=open, 1=half/closed). -1 = no overlay.
            mouth_index: index into the mouth sprites. -1 = no overlay (base head shows closed).
            sprite_index: for standalones, which standalone image to use (0-based).
        """
        group = self.groups.get(expression)
        if group is None:
            logger.warning(f"Unknown expression '{expression}', falling back to first available")
            group = list(self.groups.values())[0]

        # For standalones, select the specific base image
        if group.is_standalone and group.standalone_bases:
            idx = min(sprite_index, len(group.standalone_bases) - 1)
            _, canvas = group.standalone_bases[idx]
            canvas = canvas.copy()
        else:
            # Start with base head
            canvas = group.base.copy()

        # Composite eye overlay using proper alpha blending
        if group.eyes and eye_index >= 0:
            eye_idx = min(eye_index, len(group.eyes) - 1)
            _, eye_img = group.eyes[eye_idx]
            canvas = _alpha_composite_at_offset(canvas, eye_img, group.eye_offset, group._temp_canvas)

        # Composite mouth overlay using proper alpha blending
        if group.mouths and mouth_index >= 0:
            mouth_idx = min(mouth_index, len(group.mouths) - 1)
            _, mouth_img = group.mouths[mouth_idx]
            canvas = _alpha_composite_at_offset(canvas, mouth_img, group.mouth_offset, group._temp_canvas)

        return canvas

    def composite_to_base64(
        self,
        expression: str = "normal",
        eye_index: int = 0,
        mouth_index: int = -1,
        sprite_index: int = 0,
    ) -> str:
        """Composite and return base64 PNG."""
        cache_key = (expression, eye_index, mouth_index, sprite_index)
        cached = self._frame_cache.get(cache_key)
        if cached is not None:
            return cached

        img = self.composite(expression, eye_index, mouth_index, sprite_index)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode()

        # Keep the cache bounded; characters only need a modest number of
        # distinct states during normal use.
        if len(self._frame_cache) >= 128:
            self._frame_cache.pop(next(iter(self._frame_cache)))
        self._frame_cache[cache_key] = encoded
        return encoded

    def get_mouth_count(self, expression: str) -> int:
        """How many mouth sprites does this expression group have?"""
        group = self.groups.get(expression)
        return len(group.mouths) if group else 0

    def get_eye_count(self, expression: str) -> int:
        """How many eye sprites does this expression group have?"""
        group = self.groups.get(expression)
        return len(group.eyes) if group else 0

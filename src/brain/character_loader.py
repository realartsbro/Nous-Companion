"""
Nous Companion — Character Loader

Loads a character directory: config, personality, expression PNGs.
Single source of truth for character state.
"""

import base64
import io
import logging
from pathlib import Path

import yaml
from PIL import Image

logger = logging.getLogger(__name__)


class Character:
    """A loaded character with config, personality prompt, and expression images."""

    def __init__(self, character_dir: str | Path):
        self.dir = Path(character_dir)

        # Load config
        config_path = self.dir / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"No config.yaml at {config_path}")
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.name: str = self.config.get("name", self.dir.name)
        self.description: str = self.config.get("description", "")

        # Load personality prompt
        personality_path = self.dir / "personality.md"
        if not personality_path.exists():
            raise FileNotFoundError(f"No personality.md at {personality_path}")
        self.personality: str = personality_path.read_text(encoding="utf-8")

        # Voice config
        voice_cfg = self.config.get("voice", {})
        self.voice_engine: str = voice_cfg.get("engine", "none")
        self.voice_reference: str | None = voice_cfg.get("reference_audio")
        self.voice_settings: dict = voice_cfg.get("settings", {})

        # Animation config
        anim_cfg = self.config.get("animation", {})
        self.speaking_cycle: list[str] = anim_cfg.get("speaking_cycle", ["speaking"])
        self.flap_interval_ms: int = anim_cfg.get("flap_interval_ms", 180)
        self.fade_ms: int = anim_cfg.get("fade_ms", 120)

        # Discover and load expression PNGs
        self._expressions: dict[str, bytes] = {}
        self._load_expressions()

        # Build the full system prompt for the brain
        self._system_prompt: str | None = None

    def _load_expressions(self):
        """Load all PNG files from expressions/ directory."""
        expressions_dir = self.dir / "expressions"
        if not expressions_dir.exists():
            raise FileNotFoundError(
                f"No expressions/ directory at {expressions_dir}. "
                f"Create it and add full PNG files (neutral.png, thinking.png, etc.)"
            )

        png_files = sorted(expressions_dir.glob("*.png"))
        if not png_files:
            raise FileNotFoundError(
                f"No PNG files found in {expressions_dir}. "
                f"Add expression images (neutral.png, thinking.png, speaking.png, etc.)"
            )

        for png_path in png_files:
            name = png_path.stem  # filename without .png
            self._expressions[name] = png_path.read_bytes()
            logger.debug(f"Loaded expression: {name} ({png_path.stat().st_size} bytes)")

        logger.info(
            f"Character '{self.name}' loaded {len(self._expressions)} expressions: "
            f"{list(self._expressions.keys())}"
        )

    @property
    def expression_names(self) -> list[str]:
        """List all available expression names."""
        return list(self._expressions.keys())

    def get_expression(self, name: str) -> bytes:
        """Get raw PNG bytes for an expression. Falls back to 'neutral' if missing."""
        if name in self._expressions:
            return self._expressions[name]
        if "neutral" in self._expressions:
            logger.warning(f"Expression '{name}' not found, falling back to 'neutral'")
            return self._expressions["neutral"]
        raise KeyError(f"Expression '{name}' not found and no 'neutral' fallback")

    def get_expression_base64(self, name: str) -> str:
        """Get base64-encoded PNG for an expression."""
        return base64.b64encode(self.get_expression(name)).decode()

    def get_expression_size(self, name: str) -> tuple[int, int]:
        """Get (width, height) of an expression image."""
        data = self.get_expression(name)
        img = Image.open(io.BytesIO(data))
        return img.size

    def build_system_prompt(self) -> str:
        """Build the full LLM system prompt with personality + available expressions."""
        if self._system_prompt is None:
            expr_list = ", ".join(self.expression_names)
            self._system_prompt = (
                f"{self.personality}\n\n"
                f"## Available Expressions\n{expr_list}\n"
            )
        return self._system_prompt

    def reload(self):
        """Reload all character data from disk (for hot-reloading during dev)."""
        self._expressions.clear()
        self._system_prompt = None

        config_path = self.dir / "config.yaml"
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        personality_path = self.dir / "personality.md"
        self.personality = personality_path.read_text(encoding="utf-8")

        self._load_expressions()
        logger.info(f"Character '{self.name}' reloaded")


def load_character(character_dir: str | Path) -> Character:
    """Load a character from a directory."""
    return Character(character_dir)

"""Integration tests for per-profile character binding."""
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from brain.character_manager import CharacterManager


def _make_minimal_png() -> bytes:
    """Return a 1×1 transparent RGBA PNG (valid, minimal, won't crash PIL)."""
    import struct
    import zlib

    def chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1×1, 8-bit RGBA
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00\x00")  # filter byte + RGBA pixel
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def _make_test_character_dir(root: Path, char_id: str, profile: str | None):
    """Create a minimal character directory for testing."""
    char_dir = root / char_id
    char_dir.mkdir(parents=True, exist_ok=True)
    import yaml
    config = {"name": char_id.title()}
    if profile:
        config["hermes_profile"] = profile
    (char_dir / "config.yaml").write_text(yaml.dump(config))
    (char_dir / "personality.md").write_text(f"# {char_id}\nTest character.")
    # Create a minimal sprite group so CharacterManager loads this character
    sprite_dir = char_dir / "_normal"
    sprite_dir.mkdir(exist_ok=True)
    (sprite_dir / "base.png").write_bytes(_make_minimal_png())


def test_character_loads_hermes_profile():
    """Character.__init__ reads hermes_profile from config.yaml."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_test_character_dir(root, "luna", "fiction")
        _make_test_character_dir(root, "nova", None)
        cm = CharacterManager(str(root))
        assert cm.characters["luna"].hermes_profile == "fiction"
        assert cm.characters["nova"].hermes_profile is None


def test_get_visible_characters_filters_by_profile():
    """Visible characters are filtered by active profile."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_test_character_dir(root, "luna", "fiction")
        _make_test_character_dir(root, "nova", None)
        _make_test_character_dir(root, "codex", "coding")
        cm = CharacterManager(str(root))
        assert len(cm.get_visible_characters(None)) == 3
        visible = cm.get_visible_characters("fiction")
        assert "luna" in visible
        assert "nova" in visible
        assert "codex" not in visible


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
